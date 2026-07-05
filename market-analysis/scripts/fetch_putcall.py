"""fetch_putcall.py — CBOE Put/Call 比(期权情绪) → data/cboe_putcall.csv

两段拼接成一条近 20 年(2006-11 → 今)几乎无缝的序列(2026-07-03 实测✅)：
  ① 冻结历史 CSV(2006-11-01 ~ 2019-10-04)：一次性拉 totalpc.csv + equitypc.csv 两个文件。
  ② 每日 JSON 归档(2019-10-07 ~ 今)：每个交易日一个文件，需要逐日请求。

═══ 端点(实测 HTTP 200) ═══
  https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/totalpc.csv
  https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv
    格式：3 行说明/表头(免责声明 + "PRODUCT: TOTAL/EQUITY" + "DATE,CALLS,PUTS,TOTAL,P/C Ratio"
    列名 total 是复数 CALLS/PUTS、equity 是单数 CALL/PUT——本脚本按列【位置】(0=日期,1=call,2=put)
    解析，不依赖列名。日期格式两种都出现过("11/1/2006" 无补零 / "10/04/2019" 补零)，
    datetime.strptime("%m/%d/%Y") 两种都能解析。
    实测末行都是 2019-10-04(周五)——JSON 段从 2019-10-07(周一)接上，中间无重叠、无缺口。
  https://cdn.cboe.com/data/us/options/market_statistics/daily/{YYYY-MM-DD}_daily_options
    JSON.ratios[] 里 "TOTAL PUT/CALL RATIO"/"EQUITY PUT/CALL RATIO"/"INDEX PUT/CALL RATIO"
    三个 value 字符串(如"0.79")，CBOE 自己算好、四舍五入到 2 位；本脚本直接取用(不用
    volume/call/put 反推，两段口径来源不同没必要强求同精度——下游本来就只准用滚动 z，
    见口径注释)。实测 2019-10-04 (JSON 覆盖前一天) = 403，2019-10-07 = 200，边界干净衔接。

⚠ 实测发现的关键坑(否则会把"该日无数据"误判成"被限流"，白白重试)：
  该 JSON 端点对**任何不存在的 date key**(周末/节假日/未来日期/2019-10-07 之前)一律返回
  HTTP 403，Body 是 S3/CloudFront 标准的 "<Error><Code>AccessDenied</Code>..."——这是【正常】
  情况，不是限流，直接跳过、不重试、不计入退避。真正疑似限流的信号只有：HTTP 429，或者
  HTTP 403 但 body 不含 AccessDenied 字样(比如 WAF 挑战页/限流页)——这两种才指数退避重试。

═══ 增量与限速 ═══
只在【已收集的日期 union 里没有 csv 来源的行】(即从未做过回填)时才拉两个 CSV(2 个请求，
一次性)；之后每次都只按 SP500_long.csv 交易日历(与 fetch_cot.py 同一份真实交易日索引)
逐个交易日检查 JSON 是否已有该日 → 已有跳过、断点续传。1 req/s 限速(每请求 sleep 1s，
无论成功/跳过都算一次真实 HTTP 请求)。首次回填约 ~1700 个交易日请求，需要跑很久——
支持 --max-requests N 分批跑(每次跑够 N 个新请求就落盘退出，下次续跑)；CI 增量态每天
只有 1~2 个新日期，一晃就完。

口径纪律(命门，写死)：2012-06 CBOE 统计口径变更(含 equitypc 从 2012-06-11 起排除
ETP)+ 长期市占漂移(CBOE 在全市场期权成交占比逐年变化)→ 本文件只存【原始值】，
下游只准用【滚动 z-score】、绝不能用绝对阈值跨时期比较。

失败静默退 0 不阻断(同 fetch_earnings/fetch_insider/fetch_cot 模式)；不阻塞流水线。
单独跑：$env:PYTHONUTF8='1'; py market-analysis/scripts/fetch_putcall.py [--max-requests N]
"""
import csv
import datetime
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.parent           # market-analysis/
DATA = BASE / "data"
OUT_CSV = DATA / "cboe_putcall.csv"
CALENDAR_CSV = DATA / "raw" / "SP500_long.csv"

TOTALPC_URL = "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/totalpc.csv"
EQUITYPC_URL = "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv"
JSON_BASE = "https://cdn.cboe.com/data/us/options/market_statistics/daily"
JSON_START_DATE = datetime.date(2019, 10, 7)   # 实测 JSON 归档最早可用日(2019-10-04 之前都 403)

UA = "valpha-lab honest-stats dashboard (github.com/Vambrocop)"
HTTP_TIMEOUT = 20
REQ_INTERVAL = 1.0              # 1 req/s 限速(CI/回填都遵守)
MAX_RETRIES = 3                 # 疑似限流(429 / 非AccessDenied的403)的退避重试上限
BACKOFF_BASE = 2.0              # 退避起始秒数(指数翻倍)
CHECKPOINT_EVERY = 50           # 每 N 个新请求落盘一次(防中途中断丢进度)

_ACCESS_DENIED_MARK = b"AccessDenied"

COLUMNS = ["date", "total_pc", "equity_pc", "index_pc", "source"]


# ── 底层 HTTP ─────────────────────────────────────────────────────────
def _get_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def _get_daily_raw(d):
    """返回 (status_code_or_None, body_bytes)。网络异常时 status=None。"""
    url = f"{JSON_BASE}/{d.isoformat()}_daily_options"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, (e.read() or b"")
    except Exception as e:
        return None, str(e).encode("utf-8", "replace")


def fetch_daily_json(d):
    """返回 (found: bool, payload: bytes|None)。见模块 docstring 的 403 判定规则。"""
    delay = BACKOFF_BASE
    for attempt in range(MAX_RETRIES + 1):
        status, body = _get_daily_raw(d)
        if status == 200:
            return True, body
        if status == 403 and _ACCESS_DENIED_MARK in body:
            return False, None                  # 该日无数据(周末/节假日/未来/边界前)，非错误
        if status == 404:
            return False, None                  # 明确不存在，非错误
        # 剩下的情况(429 / 非AccessDenied的403 / 5xx / 网络异常)疑似限流或瞬时故障 → 退避重试
        if attempt < MAX_RETRIES:
            print(f"    ⚠ {d} HTTP{status}(疑似限流/瞬时故障)第{attempt + 1}次重试，{delay:.0f}s 后...")
            time.sleep(delay)
            delay *= 2
            continue
        print(f"    ⚠ {d} 重试耗尽仍失败(status={status})，跳过该日")
        return False, None
    return False, None


# ── 解析：冻结历史 CSV(总/仅股票) ────────────────────────────────────────
def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f                # f!=f 判 NaN，不用 math 模块也行


def _find_header_row(lines):
    for i, ln in enumerate(lines):
        if ln.strip().upper().startswith("DATE,"):
            return i
    raise ValueError("找不到 'DATE,' 列头行——CBOE CSV 格式可能变了，需要人工复核")


def parse_pc_csv(text):
    """按【列位置】解析(0=日期,1=call,2=put)，不依赖列名(total/equity 列名单复数不同)。
    返回 {date: pc_ratio}；calls<=0 或缺值的行跳过(避免除零/坏行)。"""
    lines = text.splitlines()
    hdr_i = _find_header_row(lines)
    out = {}
    for ln in lines[hdr_i + 1:]:
        if not ln.strip():
            continue
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) < 3:
            continue
        date_s, calls_s, puts_s = parts[0], parts[1], parts[2]
        try:
            d = datetime.datetime.strptime(date_s, "%m/%d/%Y").date()
        except ValueError:
            continue                            # 坏行：日期解析失败，跳过
        calls, puts = _num(calls_s), _num(puts_s)
        if calls is None or puts is None or calls <= 0:
            continue                            # 坏行：非数值/除零风险，跳过
        out[d] = round(puts / calls, 4)
    return out


def build_csv_backfill_rows(total_text, equity_text):
    """合并 totalpc + equitypc 两份(按日期外连接；只有一边的日期照样保留、另一列留空)。"""
    total_by_date = parse_pc_csv(total_text)
    equity_by_date = parse_pc_csv(equity_text)
    rows = []
    for d in sorted(set(total_by_date) | set(equity_by_date)):
        rows.append({
            "date": d, "total_pc": total_by_date.get(d), "equity_pc": equity_by_date.get(d),
            "index_pc": None, "source": "csv",
        })
    return rows


def fetch_csv_backfill():
    total_text = _get_text(TOTALPC_URL)
    equity_text = _get_text(EQUITYPC_URL)
    return build_csv_backfill_rows(total_text, equity_text)


# ── 解析：每日 JSON ──────────────────────────────────────────────────────
def parse_daily_json(payload, d):
    """返回 dict 或 None(解析失败/三个比率都拿不到)。"""
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None
    ratios = {}
    for r in data.get("ratios", []) or []:
        if isinstance(r, dict) and "name" in r:
            ratios[r["name"]] = _num(r.get("value"))
    total = ratios.get("TOTAL PUT/CALL RATIO")
    equity = ratios.get("EQUITY PUT/CALL RATIO")
    index_ = ratios.get("INDEX PUT/CALL RATIO")
    if total is None and equity is None:
        return None
    return {"date": d, "total_pc": total, "equity_pc": equity, "index_pc": index_, "source": "json"}


# ── 交易日历(与 fetch_cot.py 同一份 SP500_long.csv；避免周末/节假日发无谓请求) ──
def load_trading_days():
    df = pd.read_csv(CALENDAR_CSV, usecols=["Date"])
    return set(pd.to_datetime(df["Date"]).dt.date)


def _is_trading_day(d, calendar_days):
    """calendar_days 覆盖范围内 = 精确查表；超出已知范围(最近几天)保守退化为纯周一到周五。"""
    known_max = max(calendar_days) if calendar_days else None
    if known_max is not None and d <= known_max:
        return d in calendar_days
    return d.weekday() < 5


# ── upsert：按 date 合并；csv/json 两段若同日冲突 → STOP(不静默覆盖) ──────
class BoundaryConflict(RuntimeError):
    """CSV 段与 JSON 段在同一天都有数据且数值不一致——命门冲突，必须人工复核，不静默处理。"""


def upsert_one(store, row):
    d = row["date"]
    old = store.get(d)
    if old is not None and old["source"] != row["source"]:
        for f in ("total_pc", "equity_pc", "index_pc"):
            ov, nv = old.get(f), row.get(f)
            if ov is not None and nv is not None and abs(ov - nv) > 0.05:
                raise BoundaryConflict(
                    f"{d} 在 csv 与 json 两段口径都有数据且不一致："
                    f"old[{old['source']}]={old} new[{row['source']}]={row} —— 需人工复核衔接边界"
                )
    store[d] = row


# ── CSV 读写 ─────────────────────────────────────────────────────────
def _read_existing():
    """返回 {date: row}；文件不存在则空字典。"""
    store = {}
    if not OUT_CSV.exists():
        return store
    with open(OUT_CSV, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            d = datetime.date.fromisoformat(r["date"])
            store[d] = {
                "date": d, "total_pc": _num(r.get("total_pc")), "equity_pc": _num(r.get("equity_pc")),
                "index_pc": _num(r.get("index_pc")), "source": r["source"],
            }
    return store


def _write_csv(store):
    DATA.mkdir(parents=True, exist_ok=True)
    rows = sorted(store.values(), key=lambda r: r["date"])
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([r["date"].isoformat(), _fmt(r["total_pc"]), _fmt(r["equity_pc"]),
                        _fmt(r["index_pc"]), r["source"]])
    return len(rows)


def _fmt(v):
    return "" if v is None else v


# ── JSON 段增量抓取(断点续传 + 限速 + 分批 max_requests)──────────────────
def fetch_json_increment(store, calendar_days, max_requests=None, today=None):
    """从 JSON_START_DATE 到 today(默认=真实今天；测试传固定值，避免依赖系统时钟)，
    跳过 store 里已有日期、跳过非交易日，逐日请求。
    每 CHECKPOINT_EVERY 个新请求落盘一次(防中断丢进度)。返回本次实际发出的请求数。"""
    today = today or datetime.date.today()
    d = JSON_START_DATE
    n_req = 0
    while d <= today:
        if d in store or not _is_trading_day(d, calendar_days):
            d += datetime.timedelta(days=1)
            continue
        if max_requests is not None and n_req >= max_requests:
            break
        found, payload = fetch_daily_json(d)
        n_req += 1
        if found:
            parsed = parse_daily_json(payload, d)
            if parsed:
                upsert_one(store, parsed)
        time.sleep(REQ_INTERVAL)
        if n_req % CHECKPOINT_EVERY == 0:
            _write_csv(store)
            print(f"    · 已处理 {n_req} 个请求(累计 {len(store)} 天)，落盘checkpoint")
        d += datetime.timedelta(days=1)
    return n_req


# ── 主流程 ────────────────────────────────────────────────────────────
def run(max_requests=None, today=None):
    print("=== fetch_putcall.py：CBOE Put/Call 比 ===")
    store = _read_existing()
    has_csv_backfill = any(r["source"] == "csv" for r in store.values())

    if not has_csv_backfill:
        try:
            for r in fetch_csv_backfill():
                upsert_one(store, r)
            _write_csv(store)
            n_csv = sum(1 for r in store.values() if r["source"] == "csv")
            print(f"  · CSV 回填(totalpc+equitypc)：{n_csv} 天")
        except Exception as e:
            print(f"  ⚠ CSV 回填拉取/解析失败(非致命，跳过，下次重跑再试): {e}")

    try:
        calendar_days = load_trading_days()
    except Exception as e:
        print(f"  ⚠ 交易日历加载失败({e})——JSON 增量退化为纯周一到周五遍历")
        calendar_days = set()

    n_req = 0
    try:
        n_req = fetch_json_increment(store, calendar_days, max_requests=max_requests, today=today)
    except BoundaryConflict as e:
        _write_csv(store)          # 落盘已确认无冲突的部分，冲突行本身不会被写入(upsert 抛异常前未落地)
        print(f"✗ STOP：{e}")
        raise

    n = _write_csv(store)
    print(f"[OK] cboe_putcall.csv — 共 {n} 天 · 本次新增 JSON 请求 {n_req} 个")
    return {"n_rows": n, "n_requests": n_req}


if __name__ == "__main__":
    mr = None
    if "--max-requests" in sys.argv:
        mr = int(sys.argv[sys.argv.index("--max-requests") + 1])
    run(max_requests=mr)
