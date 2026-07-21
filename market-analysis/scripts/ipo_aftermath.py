"""ipo_aftermath.py — 重大 IPO 挂牌后事实档（W4b·A5·事实档，非计分·观察不荐股）。

对 ipo_alert_log.csv（A3）里 stage∈(listed,priced) 的 major 公司（有 ticker 的），
用 yfinance 抓该 ticker 日线，记录挂牌后 D1/D5/D20 相对首日收盘的表现 + vs QQQ 同窗超额。
**定位是事实档，不是计分**——不判命中/未命中、不打分、不推送，纯客观记录 + anti-hype 基率。

═══ 观察对象（口径）═══════════════════════════════════════════════════════
ipo_alert_log.csv 按 cik 分组，取每家公司**记录过的最高状态档**（filed<priced<listed）；
该最高档 stage 必须 ∈ (listed, priced) 且带 ticker，才进观察池——只有 filed 记录的公司
还早，不构成观察对象。**实际首交易日不看 alert 账本、也不看任何"上市日期"字段——直接看
yfinance 该 ticker 日线返回的第一行**（数据里的事实，不是我们猜的）。

═══ D1/D5/D20 口径 ═══════════════════════════════════════════════════════
以首交易日收盘为第 0 天基准，D1/D5/D20 = 第 1/5/20 个交易日收盘相对基准的涨跌 %
（不是自然日）。vs_qqq_d20_pct = 该股 D20 减去 QQQ 在同一窗口（QQQ 序列里从该股首交易日
起算的第 20 个交易日）的涨跌 %——同窗对齐，不是任意两个时间点硬减。
窗口未走完（数据不够 N+1 行）→ 该字段留空（None），不是 0，避免"未涨跌"被误读成"走平"。

═══ alert_lead_days / alert_quality（判断口径，供审查核对）═══════════════
alert_lead_days = 首交易日 − 该公司在 alert 账本里**最早一条记录的日期**（不限于 listed/priced
那条，只要账本里出现过这家公司就算——含最早的 filed 记录，因为"我们最早何时知道这家公司"
才是"预警是否提前"该问的问题）。**正数 = 提前预警**（alert 记录早于实际开始交易）；
**负数或零 = 迟到**（账本记录时该股已经在交易，如海力士——我们的 IPO 雷达是 2026-07 才
上线，SK hynix 早已挂牌，首条记录必然晚于实际首交易日）。

三态判定（机械·只用 lead_days 符号 + 观察池代表 stage，无隐藏日期假设）：
  · lead_days > 0                     → "lead"    （账本记录先于实际交易，提前预警成立）
  · lead_days ≤ 0 且代表档 == listed   → "late"    （事后才知道，但好歹确认过"已挂牌"这一事实）
  · lead_days ≤ 0 且代表档 == priced   → "missed"  （事后才知道，且账本至今没能把它推进到
                                                      listed——比"late"多一层：我方从未确认过
                                                      挂牌事实，纯靠 yfinance 数据自己发现已在交易）
这是本脚本对任务描述"lead/late/missed 三态"最贴近字段的机械化定义——若审查认为语义不对，
是可调整的判断点，不是写死的红线。

═══ 账本语义：append-only + "最新行为准"（不是每日快照）═══════════════════
data/ipo_aftermath_log.csv **不是每日打卡表**，是"每家公司当前观测到的完成度快照"账本：
每次跑，若某公司的完成度（哪些 D1/D5/D20 已经有数）相比账本里该 ticker 最后一行**没有变化**
→ 幂等跳过，不 append；若变化了（比如上次只有 D1，这次 D5 也测完了）→ append 一整行新快照
（不是只补 D5 那一格）。**消费者（前端/下游）读某 ticker 时只看账本里它的最后一行**——旧行
不删不改，只是被新行取代权威性（append-only 铁律：历史行一字节不动）。

═══ fail-soft ═════════════════════════════════════════════════════════════
· 单个 ticker yfinance 抓不到/抓空 → 打印后跳过该公司，不影响其它公司、不报错。
· QQQ 抓不到 → 全体 vs_qqq_d20_pct 留空，D1/D5/D20 本身照算（部分退化，不整体放弃）。
· 无观察对象 / 全部幂等 → 零 append，JSON 仍按账本现状重写（除非账本从未写过一行）。
· 任何异常 → 顶层 catch 打印后 exit 0，不阻断流水线（同 ipo_alerts/downturn_brief 惯例）。

═══ anti-hype 基率（写死进输出 JSON 的 caveat，标来源）══════════════════
学术共识：美股 IPO 首日平均上涨（underpricing），但上市后 3-5 年平均跑输大盘
（Ritter 长期 underperformance 文献）——单个 IPO 首日大涨 ≠ 值得追高。

单独跑：$env:PYTHONUTF8='1'; py market-analysis/scripts/ipo_aftermath.py
"""
import csv
import datetime
import json
import sys
from pathlib import Path

import pandas as pd

SCRIPTS = Path(__file__).parent
BASE = SCRIPTS.parent
ALERT_LOG = BASE / "data" / "ipo_alert_log.csv"
LOG = BASE / "data" / "ipo_aftermath_log.csv"
OUT = BASE / "web" / "ipo_aftermath.json"

HEADER = ["cik", "company", "ticker", "first_trade_date", "d1_pct", "d5_pct", "d20_pct",
          "vs_qqq_d20_pct", "alert_lead_days", "alert_quality", "updated"]

BENCH = "QQQ"
FETCH_START = "2015-01-01"          # 早锚：新股 yfinance 自然从真实首日起给数据，不会因锚早而误判
WINDOWS = (1, 5, 20)                 # D1/D5/D20 交易日偏移（相对首日=第0天）
_STAGE_RANK = {"filed": 0, "priced": 1, "listed": 2}

CAVEAT = {
    "zh": "学术共识：美股 IPO 首日平均上涨（underpricing），但上市后 3-5 年平均跑输大盘"
          "（Ritter 长期 underperformance 文献）；单个 IPO 首日大涨 ≠ 值得追高。",
    "en": "Academic consensus: US IPOs pop on debut day on average (underpricing), but "
          "underperform the broad market over the following 3-5 years (Ritter's long-run "
          "IPO underperformance research). A strong debut-day pop does not mean it's worth chasing.",
    "source": "Jay R. Ritter (Univ. of Florida) — IPO long-run underperformance data series; "
              "https://site.warrington.ufl.edu/ritter/ipo-data/",
}
DISCLAIMER = {
    "zh": "事实档，非计分、非荐股、非预测——只记录挂牌后已经发生的价格事实，不判"
          "\"命中/未命中\"、不打分、不建议买卖。",
    "en": "A factual record, not a scorecard, not investment advice, not a forecast — it "
          "only logs price facts that already happened after listing; no hit/miss judging, "
          "no scoring, no buy/sell suggestion.",
}


# ── 观察对象：ipo_alert_log.csv → 每家 stage∈(listed,priced) 带 ticker 的公司 ──────
def _observation_targets(path=None):
    """→ list[dict(cik, company, ticker, stage, alert_earliest_utc)]，按 company 排序。
    stage=该公司账本里记录过的最高档；alert_earliest_utc=该公司账本里最早一条记录的 date_utc
    （不限于 listed/priced 那条——见文件头判断口径）。"""
    p = path or ALERT_LOG
    if not p.exists():
        return []
    with open(p, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    by_cik = {}
    for r in rows:
        cik = r.get("cik")
        if not cik:
            continue
        by_cik.setdefault(cik, []).append(r)

    targets = []
    for cik, rs in by_cik.items():
        dated = [r for r in rs if r.get("date_utc")]
        if not dated:
            continue
        earliest = min(r["date_utc"] for r in dated)
        top = max(rs, key=lambda r: _STAGE_RANK.get(r.get("stage"), -1))
        stage = top.get("stage")
        ticker = top.get("ticker")
        if stage not in ("listed", "priced") or not ticker:
            continue
        targets.append({
            "cik": cik, "company": top.get("company") or "", "ticker": ticker,
            "stage": stage, "alert_earliest_utc": earliest,
        })
    targets.sort(key=lambda t: t["company"])
    return targets


# ── yfinance 取价（单独函数，便于测试 monkeypatch、不碰网络）──────────────────
def _fetch_series(ticker, start=FETCH_START):
    """→ pd.Series(Close，DatetimeIndex 升序) 或 None（无数据/异常，fail-soft）。
    首行 = 该 ticker 在 yfinance 里能查到的最早交易日——即"实际首交易日"（数据事实，非猜测）。"""
    try:
        import yfinance as yf
        px = yf.download(ticker, start=start, auto_adjust=True, progress=False)["Close"]
    except Exception:
        return None
    if isinstance(px, pd.DataFrame):
        if ticker in px.columns:
            px = px[ticker]
        else:
            if px.shape[1] == 0:
                return None
            px = px.iloc[:, 0]
    s = pd.to_numeric(px, errors="coerce").dropna().sort_index()
    return s if len(s) > 0 else None


def _pct_at(series, offset):
    """series 第 offset 个交易日(0=首日)收盘相对首日收盘涨跌%；数据不够→None(窗口未走完)。"""
    if series is None or len(series) <= offset:
        return None
    base = float(series.iloc[0])
    if base <= 0:
        return None
    return round((float(series.iloc[offset]) / base - 1.0) * 100, 3)


def _qqq_pct_at(qqq_series, first_trade_date, offset):
    """QQQ 序列里，从 first_trade_date（或其后第一个交易日）起算的第 offset 个交易日涨跌%。
    与 _pct_at 语义一致，只是起点对齐到该股首交易日、不是 QQQ 自己的首行。"""
    if qqq_series is None or len(qqq_series) == 0:
        return None
    anchor = pd.Timestamp(first_trade_date)
    after = qqq_series.index[qqq_series.index >= anchor]
    if len(after) == 0:
        return None
    pos = qqq_series.index.get_indexer([after[0]])[0]
    if pos < 0 or pos + offset >= len(qqq_series):
        return None
    base = float(qqq_series.iloc[pos])
    if base <= 0:
        return None
    return round((float(qqq_series.iloc[pos + offset]) / base - 1.0) * 100, 3)


def _lead_days(first_trade_date, alert_earliest_utc):
    """首交易日 − 账本最早记录日期（天数）。正=提前预警，负/零=迟到（见文件头判断口径）。"""
    ftd = pd.Timestamp(first_trade_date).date()
    ad = datetime.date.fromisoformat(str(alert_earliest_utc)[:10])
    return (ftd - ad).days


def _alert_quality(lead_days, stage):
    """三态：lead_days>0→lead；≤0 且代表档=listed→late；≤0 且代表档=priced→missed。"""
    if lead_days > 0:
        return "lead"
    return "late" if stage == "listed" else "missed"


# ── 账本 I/O（append-only；"最新行为准"——同 ticker 取文件里最后一行）─────────
def _read_rows(path=None):
    p = path or LOG
    if not p.exists():
        return []
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _append_rows(rows, path=None):
    p = path or LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(HEADER)
        for r in rows:
            w.writerow(["" if r.get(k) is None else r.get(k) for k in HEADER])


def _last_row_by_ticker(rows):
    last = {}
    for r in rows:
        last[r.get("ticker")] = r
    return last


def _completion_sig(row_like):
    """(d1有数, d5有数, d20有数) —— 幂等判定用；row_like 可以是 dict(str) 或 dict(float/None)。"""
    def has(v):
        return v is not None and v != ""
    return tuple(has(row_like.get(k)) for k in ("d1_pct", "d5_pct", "d20_pct"))


def _to_num(v, cast):
    if v in (None, ""):
        return None
    try:
        return cast(v)
    except (TypeError, ValueError):
        return None


# ── JSON 输出：账本现状（每 ticker 最后一行）+ caveat/disclaimer ────────────
def _write_json(path=None):
    out_path = path or OUT
    if not LOG.exists():
        return False
    rows = _read_rows()
    last = _last_row_by_ticker(rows)
    if not last:
        return False
    companies = []
    for r in sorted(last.values(), key=lambda r: r.get("company") or ""):
        companies.append({
            "cik": r.get("cik"), "company": r.get("company"), "ticker": r.get("ticker"),
            "first_trade_date": r.get("first_trade_date"),
            "d1_pct": _to_num(r.get("d1_pct"), float),
            "d5_pct": _to_num(r.get("d5_pct"), float),
            "d20_pct": _to_num(r.get("d20_pct"), float),
            "vs_qqq_d20_pct": _to_num(r.get("vs_qqq_d20_pct"), float),
            "alert_lead_days": _to_num(r.get("alert_lead_days"), int),
            "alert_quality": r.get("alert_quality"),
            "updated": r.get("updated"),
        })
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "disclaimer": DISCLAIMER,
        "caveat": CAVEAT,
        "companies": companies,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def run():
    """→ dict(n_checked, n_new, n_skipped_no_data)。见文件头：fail-soft、幂等、append-only。"""
    targets = _observation_targets()
    if not targets:
        print("[IPO事实档] 无 stage∈(listed,priced) 且带 ticker 的 major 公司，零行为")
        return {"n_checked": 0, "n_new": 0, "n_skipped_no_data": 0}

    existing = _read_rows()
    last_by_ticker = _last_row_by_ticker(existing)

    qqq = _fetch_series(BENCH)
    if qqq is None:
        print(f"[IPO事实档] {BENCH} 基准取价失败——D1/D5/D20 照算，vs_qqq_d20 本轮全体留空")

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_rows = []
    n_checked = 0
    n_skipped_no_data = 0
    for tgt in targets:
        ticker = tgt["ticker"]
        series = _fetch_series(ticker)
        if series is None or len(series) == 0:
            print(f"[IPO事实档] {tgt['company']}({ticker}) 无 yfinance 数据，跳过(fail-soft)")
            n_skipped_no_data += 1
            continue
        n_checked += 1

        first_trade_date = series.index[0].date().isoformat()
        d1 = _pct_at(series, 1)
        d5 = _pct_at(series, 5)
        d20 = _pct_at(series, 20)
        qqq_d20 = _qqq_pct_at(qqq, series.index[0], 20) if qqq is not None else None
        vs_qqq_d20 = round(d20 - qqq_d20, 3) if (d20 is not None and qqq_d20 is not None) else None
        lead_days = _lead_days(first_trade_date, tgt["alert_earliest_utc"])
        quality = _alert_quality(lead_days, tgt["stage"])

        row = {
            "cik": tgt["cik"], "company": tgt["company"], "ticker": ticker,
            "first_trade_date": first_trade_date,
            "d1_pct": d1, "d5_pct": d5, "d20_pct": d20,
            "vs_qqq_d20_pct": vs_qqq_d20,
            "alert_lead_days": lead_days, "alert_quality": quality,
            "updated": now,
        }

        prev = last_by_ticker.get(ticker)
        if prev is not None and _completion_sig(prev) == _completion_sig(row):
            print(f"[IPO事实档] {ticker} 完成度未变（D1={d1 is not None} D5={d5 is not None} "
                  f"D20={d20 is not None}），幂等跳过")
            continue
        new_rows.append(row)

    if new_rows:
        _append_rows(new_rows)
        print(f"[OK] ipo_aftermath_log.csv — 新增/更新 {len(new_rows)} 行: "
              + "、".join(r["ticker"] for r in new_rows))
    else:
        print("[IPO事实档] 无新增/更新行（全部幂等或无数据）")

    wrote_json = _write_json()
    print(f"[{'OK' if wrote_json else 'skip'}] ipo_aftermath.json"
          + ("" if wrote_json else "（账本从未写过一行，暂不产出）"))

    return {"n_checked": n_checked, "n_new": len(new_rows), "n_skipped_no_data": n_skipped_no_data}


if __name__ == "__main__":
    try:
        run()
    except Exception as e:                     # fail-soft：绝不阻断流水线
        print(f"[IPO事实档] 异常（非致命，不阻断）: {type(e).__name__}: {e}")
    sys.exit(0)
