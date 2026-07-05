"""fetch_cot.py — CFTC COT(Commitments of Traders)期货持仓 → data/cot.csv

拉 CFTC 免费公开历史数据(零 key、零反爬)，只筛两个合约：
  · legacy 报告：非商业者(noncommercial)多空持仓，E-mini S&P 500 / E-mini NASDAQ-100
  · TFF 报告(金融期货细分)：杠杆基金(leveraged funds)多空持仓，同两个合约，2006-06 起

═══ 合约过滤依据(2026-07-03 实测·真实字段样例——命门，务必按 code 不按名称字符串) ═══

CFTC 每行有一个跨年稳定的 "CFTC Contract Market Code"，但"Market and Exchange Names"
文本会跨年多次改名（交易所改名/CFTC 报表标签调整），且**同一名称字符串在早年会混装两个不同
合约**——所以过滤规则钉死在 code，不是名称：

  13874A = E-MINI S&P 500（唯一贯穿全历史的稳定 code）。真实名称变体（同一 code 下）：
    "E-MINI S&P 500 STOCK INDEX - INTERNATIONAL MONETARY MARKET" (1997-09~2000-08)
    "E-MINI S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE"   (2000-08~2016-12)
    "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE"                (2017+)
    **不要**跟同族其它 code 混淆：13874+ = "S&P 500 Consolidated"（mini+micro+全尺寸合并的
    名义口径，OI 不是三者简单相加，混用会做出无意义的净持仓）；13874U = MICRO E-MINI（
    合约名义值只有 E-mini 的 1/10）；138741 = 全尺寸 S&P 500（已停牌，2016 后无新数据）。

  209742 = E-MINI NASDAQ-100（同上，唯一贯穿全历史的稳定 code）。真实名称变体：
    "E-MINI NASDAQ 100 STOCK INDEX - INTERNATIONAL MONETARY MARKET" (1999-06~1999-12，仅25期)
    "NASDAQ-100 STOCK INDEX (MINI) - INTERNATIONAL MONETARY MARKET" (1999-12~2000-08)
    "NASDAQ-100 STOCK INDEX (MINI) - CHICAGO MERCANTILE EXCHANGE"   (2000-08~2016-12)
    "NASDAQ MINI - CHICAGO MERCANTILE EXCHANGE"                      (2017+)
    ⚠ 实测发现真实的"同名多合约"陷阱：1996~2000 年有一批行的名称字符串就是通用的
    "NASDAQ-100 STOCK INDEX - INTERNATIONAL MONETARY MARKET"（不含 "(MINI)"/"E-MINI"字样），
    这批行内部混装了 209741(全尺寸) 与 209742(mini) 两种 code——若按名称字符串过滤会把
    全尺寸合约也当成 E-mini 收进来。**因此本脚本只按 CFTC Contract Market Code 过滤，
    完全不看名称字符串**（名称只留作注释/日志用途）。
    **不要**跟 20974+(Consolidated) / 209747(MICRO E-MINI) / 209741(全尺寸,已停牌) 混淆。

═══ 端点(2026-07-03 实测 HTTP 200) ═══
  legacy 回填(1986~2016 一份大文件)：
    https://www.cftc.gov/files/dea/history/deacot1986_2016.zip   → 内含 FUT86_16.txt
  legacy 逐年(2017+；2006~2016 也有单年份文件，但已被回填覆盖，不重复抓)：
    https://www.cftc.gov/files/dea/history/deacot{YYYY}.zip      → 内含 annual.txt(大小写不定)
  TFF 回填(2006-06~2016 一份大文件；⚠ 文件名是 "fin_fut_txt" 不是 "fut_fin_txt"，前后顺序反了)：
    https://www.cftc.gov/files/dea/history/fin_fut_txt_2006_2016.zip → 内含 F_TFF_2006_2016.txt
  TFF 逐年(2017+；2010~2016 也有单年份文件但已被回填覆盖；2006~2009 无单年份文件，只在回填里)：
    https://www.cftc.gov/files/dea/history/fut_fin_txt_{YYYY}.zip  → 内含 FinFutYY.txt

═══ 点时间纪律(命门) ═══
report_date 固定周二，周五 15:30 ET 发布下周可用 → usable_from = report_date + 4 个美股交易日
(Tue→次周一)。交易日历用项目里现成的 data/raw/SP500_long.csv 索引(真实历史交易日，不自造)；
若某段落在该文件已知范围之外(通常是最近几天，pipeline 还没抓到最新收盘价)，保守退化为纯周一到
周五计数、不排节假日——偶尔多算 1 天(节假日恰好落在该周)，但绝不会少算/前视。
**下游只准用 usable_from，绝不能用 report_date 本身**（否则前视偏差）。

═══ 增量策略 ═══
data/cot.csv 不存在 → 全量回填(两份回填 zip + 2017..今年 逐年 zip)。
已存在 → 只抓"当年" zip(legacy + TFF 各一个请求)，按 (report_date, market, source) 幂等 upsert
(同键重跑不重复；CFTC 修订历史数据时会用新值覆盖，这是可再生缓存不是账本，允许覆盖)。

失败静默退 0 不阻断(同 fetch_earnings/fetch_insider 模式)；不阻塞流水线。
单独跑：$env:PYTHONUTF8='1'; py market-analysis/scripts/fetch_cot.py [--backfill]
"""
import csv
import datetime
import io
import math
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.parent           # market-analysis/
DATA = BASE / "data"
OUT_CSV = DATA / "cot.csv"
CALENDAR_CSV = DATA / "raw" / "SP500_long.csv"

HIST_BASE = "https://www.cftc.gov/files/dea/history"
LEGACY_BACKFILL_URL = f"{HIST_BASE}/deacot1986_2016.zip"
TFF_BACKFILL_URL = f"{HIST_BASE}/fin_fut_txt_2006_2016.zip"          # 注意：fin_fut，不是 fut_fin
LEGACY_YEAR_START = 2017                                             # 逐年抓取起点(早年已在回填里)
TFF_YEAR_START = 2017

HTTP_TIMEOUT = 60
MAX_BYTES = 60_000_000         # 回填包最大 ~23MB；留余量防异常巨响应
UA = "valpha-lab honest-stats dashboard (github.com/Vambrocop)"

# 合约代码 → market 名(见模块 docstring：唯一稳定的过滤键，不按名称字符串)
CODE_SP500_EMINI = "13874A"
CODE_NASDAQ100_EMINI = "209742"
CODE_TO_MARKET = {CODE_SP500_EMINI: "sp500", CODE_NASDAQ100_EMINI: "nasdaq100"}

COLUMNS = ["report_date", "market", "source", "noncomm_net", "noncomm_net_pct_oi",
           "lev_funds_net", "open_interest", "usable_from"]

USABLE_FROM_TRADING_DAYS = 4

LEGACY_COLS = {
    "code": "CFTC Contract Market Code",
    "date": "As of Date in Form YYYY-MM-DD",
    "oi": "Open Interest (All)",
    "ncl": "Noncommercial Positions-Long (All)",
    "ncs": "Noncommercial Positions-Short (All)",
}
TFF_COLS = {
    "code": "CFTC_Contract_Market_Code",
    "date": "Report_Date_as_YYYY-MM-DD",
    "oi": "Open_Interest_All",
    "levl": "Lev_Money_Positions_Long_All",
    "levs": "Lev_Money_Positions_Short_All",
}


# ── 底层 HTTP ─────────────────────────────────────────────────────────
def _get_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        raw = r.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"响应过大(>{MAX_BYTES // 1_000_000}MB)，跳过 {url}")
    return raw


def _read_zip_csv(raw_bytes):
    """zip 里只有一个文件(各年份/回填包命名不一，用 namelist()[0] 稳妥)。"""
    z = zipfile.ZipFile(io.BytesIO(raw_bytes))
    inner = z.namelist()[0]
    with z.open(inner) as f:
        df = pd.read_csv(f, encoding="latin-1", low_memory=False, dtype=str)
    df.columns = df.columns.str.strip()
    return df


def _num(v):
    """把字段转 float；非数值/NaN(含 pandas 把 "N/A"/"NA"/"NULL" 等占位符悄悄转成 NaN 的情况，
    dtype=str 也挡不住——float(nan) 不报错，必须显式判 isnan)一律返回 None。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


# ── 解析：legacy(noncommercial) ─────────────────────────────────────────
def parse_legacy_zip(raw_bytes):
    """解析 legacy annual.txt/FUT86_16.txt zip → [{report_date, market, source,
    noncomm_net, noncomm_net_pct_oi, lev_funds_net(None), open_interest}, ...]。
    坏行(缺字段/非数值)静默跳过。"""
    df = _read_zip_csv(raw_bytes)
    c = LEGACY_COLS
    for need in c.values():
        if need not in df.columns:
            raise ValueError(f"legacy zip 缺列 {need!r}（CFTC 换了字段名？需人工复核）")
    df = df[df[c["code"]].astype(str).str.strip().isin(CODE_TO_MARKET)]
    rows = []
    for _, r in df.iterrows():
        market = CODE_TO_MARKET.get(str(r[c["code"]]).strip())
        if not market:
            continue
        d = pd.to_datetime(str(r[c["date"]]).strip(), errors="coerce")
        if pd.isna(d):
            continue
        oi, ncl, ncs = _num(r[c["oi"]]), _num(r[c["ncl"]]), _num(r[c["ncs"]])
        if oi is None or ncl is None or ncs is None:
            continue                            # 坏行：非数值/NaN占位符，跳过
        noncomm_net = ncl - ncs
        pct = round(100.0 * noncomm_net / oi, 4) if oi else None
        rows.append({
            "report_date": d.date(), "market": market, "source": "legacy",
            "noncomm_net": int(round(noncomm_net)), "noncomm_net_pct_oi": pct,
            "lev_funds_net": None, "open_interest": int(round(oi)),
        })
    return rows


# ── 解析：TFF(leveraged funds) ──────────────────────────────────────────
def parse_tff_zip(raw_bytes):
    """解析 TFF F_TFF_2006_2016.txt/FinFutYY.txt zip → 同上形状，noncomm_net 留空、
    lev_funds_net 填值。坏行静默跳过。"""
    df = _read_zip_csv(raw_bytes)
    c = TFF_COLS
    for need in c.values():
        if need not in df.columns:
            raise ValueError(f"TFF zip 缺列 {need!r}（CFTC 换了字段名？需人工复核）")
    df = df[df[c["code"]].astype(str).str.strip().isin(CODE_TO_MARKET)]
    rows = []
    for _, r in df.iterrows():
        market = CODE_TO_MARKET.get(str(r[c["code"]]).strip())
        if not market:
            continue
        # 回填包(2006_2016)日期形如 "1/10/2012 12:00:00 AM"；逐年包是干净 ISO "YYYY-MM-DD"。
        # pandas.to_datetime 两种都能自动识别(month/day/year 美式惯例，与 CFTC 美国数据一致)。
        d = pd.to_datetime(str(r[c["date"]]).strip(), errors="coerce")
        if pd.isna(d):
            continue
        oi, levl, levs = _num(r[c["oi"]]), _num(r[c["levl"]]), _num(r[c["levs"]])
        if oi is None or levl is None or levs is None:
            continue                            # 坏行：非数值/NaN占位符，跳过
        rows.append({
            "report_date": d.date(), "market": market, "source": "tff",
            "noncomm_net": None, "noncomm_net_pct_oi": None,
            "lev_funds_net": int(round(levl - levs)), "open_interest": int(round(oi)),
        })
    return rows


# ── 交易日历(usable_from 命门)───────────────────────────────────────────
def load_trading_days():
    """从项目现成的 SP500_long.csv 索引读真实交易日(不自造日历)。返回 set[date]。"""
    df = pd.read_csv(CALENDAR_CSV, usecols=["Date"])
    return set(pd.to_datetime(df["Date"]).dt.date)


def add_trading_days(start, n, calendar_days):
    """从 start 起向后数 n 个真实交易日(不含 start 本身)。

    calendar_days 覆盖范围内 = 精确排节假日(真实历史交易日索引)；
    超出已知范围(通常是最近几天，calendar 数据源还没抓到最新收盘价)保守退化为
    纯周一到周五计数、不排节假日——偶尔多算 1 天(节假日周)，但绝不会少算/前视。
    """
    known_max = max(calendar_days) if calendar_days else start
    cur = start
    counted = 0
    while counted < n:
        cur += datetime.timedelta(days=1)
        if cur <= known_max:
            if cur in calendar_days:
                counted += 1
        else:
            if cur.weekday() < 5:
                counted += 1
    return cur


# ── upsert：按 (report_date, market, source) 幂等合并 ───────────────────
def _key(row):
    rd = row["report_date"]
    rd = rd.isoformat() if hasattr(rd, "isoformat") else str(rd)
    return (rd, row["market"], row["source"])


def upsert_rows(existing, new_rows):
    """existing/new_rows 都是 dict 列表；new 覆盖同 key 的 existing(允许 CFTC 修订历史数值)。
    返回合并后的列表(未排序)。"""
    merged = {_key(r): dict(r) for r in existing}
    for r in new_rows:
        merged[_key(r)] = dict(r)
    return list(merged.values())


def _read_existing_csv():
    if not OUT_CSV.exists():
        return []
    rows = []
    with open(OUT_CSV, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "report_date": r["report_date"], "market": r["market"], "source": r["source"],
                "noncomm_net": _to_num(r.get("noncomm_net")),
                "noncomm_net_pct_oi": _to_num(r.get("noncomm_net_pct_oi")),
                "lev_funds_net": _to_num(r.get("lev_funds_net")),
                "open_interest": _to_num(r.get("open_interest")),
            })
    return rows


def _to_num(s):
    if s is None or s == "":
        return None
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def _write_csv(rows, calendar_days):
    def sort_key(r):
        rd = r["report_date"]
        rd = rd if isinstance(rd, str) else rd.isoformat()
        return (rd, r["market"], r["source"])
    rows = sorted(rows, key=sort_key)
    DATA.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in rows:
            rd = r["report_date"]
            rd_date = rd if isinstance(rd, datetime.date) else datetime.date.fromisoformat(rd)
            usable = add_trading_days(rd_date, USABLE_FROM_TRADING_DAYS, calendar_days)
            w.writerow([
                rd_date.isoformat(), r["market"], r["source"],
                _fmt(r.get("noncomm_net")), _fmt(r.get("noncomm_net_pct_oi")),
                _fmt(r.get("lev_funds_net")), _fmt(r.get("open_interest")),
                usable.isoformat(),
            ])
    return len(rows)


def _fmt(v):
    return "" if v is None else v


# ── 主流程 ────────────────────────────────────────────────────────────
def _fetch_legacy():
    """returns list[row]；单个 URL 失败只打印警告、不让整体崩掉。"""
    rows = []
    try:
        rows += parse_legacy_zip(_get_bytes(LEGACY_BACKFILL_URL))
        print(f"  · legacy 回填(1986-2016): +{len(rows)} 行")
    except Exception as e:
        print(f"  ⚠ legacy 回填拉取/解析失败(非致命): {e}")
    today_year = datetime.date.today().year
    for y in range(LEGACY_YEAR_START, today_year + 1):
        try:
            yr_rows = parse_legacy_zip(_get_bytes(f"{HIST_BASE}/deacot{y}.zip"))
            rows += yr_rows
            print(f"  · legacy {y}: +{len(yr_rows)} 行")
        except Exception as e:
            print(f"  ⚠ legacy {y} 拉取/解析失败(非致命): {e}")
    return rows


def _fetch_legacy_current_year_only():
    y = datetime.date.today().year
    try:
        rows = parse_legacy_zip(_get_bytes(f"{HIST_BASE}/deacot{y}.zip"))
        print(f"  · legacy {y}(增量): {len(rows)} 行")
        return rows
    except Exception as e:
        print(f"  ⚠ legacy {y} 拉取/解析失败(非致命，跳过本次 legacy 更新): {e}")
        return []


def _fetch_tff(_unused=None):
    rows = []
    try:
        rows += parse_tff_zip(_get_bytes(TFF_BACKFILL_URL))
        print(f"  · TFF 回填(2006-2016): +{len(rows)} 行")
    except Exception as e:
        print(f"  ⚠ TFF 回填拉取/解析失败(非致命): {e}")
    today_year = datetime.date.today().year
    for y in range(TFF_YEAR_START, today_year + 1):
        try:
            yr_rows = parse_tff_zip(_get_bytes(f"{HIST_BASE}/fut_fin_txt_{y}.zip"))
            rows += yr_rows
            print(f"  · TFF {y}: +{len(yr_rows)} 行")
        except Exception as e:
            print(f"  ⚠ TFF {y} 拉取/解析失败(非致命): {e}")
    return rows


def _fetch_tff_current_year_only():
    y = datetime.date.today().year
    try:
        rows = parse_tff_zip(_get_bytes(f"{HIST_BASE}/fut_fin_txt_{y}.zip"))
        print(f"  · TFF {y}(增量): {len(rows)} 行")
        return rows
    except Exception as e:
        print(f"  ⚠ TFF {y} 拉取/解析失败(非致命，跳过本次 TFF 更新): {e}")
        return []


def run(force_backfill=False):
    print("=== fetch_cot.py：CFTC COT 期货持仓(E-mini S&P 500 / E-mini NASDAQ-100) ===")
    is_backfill = force_backfill or not OUT_CSV.exists()
    print(f"  模式：{'全量回填' if is_backfill else '增量(当年)'}")

    if is_backfill:
        new_rows = _fetch_legacy() + _fetch_tff()
    else:
        new_rows = _fetch_legacy_current_year_only() + _fetch_tff_current_year_only()

    if not new_rows:
        print("✗ 一行都没抓到——保留旧 cot.csv(若有)，不写坏数据")
        return None

    existing = [] if is_backfill else _read_existing_csv()
    merged = upsert_rows(existing, new_rows)

    try:
        calendar_days = load_trading_days()
    except Exception as e:
        print(f"  ⚠ 交易日历加载失败({e})——usable_from 全程退化为纯周一到周五计数")
        calendar_days = set()

    n = _write_csv(merged, calendar_days)
    by_market = {}
    for r in merged:
        by_market.setdefault(r["market"], set()).add(_key(r)[2])
    print(f"[OK] cot.csv — 共 {n} 行 · markets={sorted(by_market)}")
    return n


if __name__ == "__main__":
    run(force_backfill="--backfill" in sys.argv)
