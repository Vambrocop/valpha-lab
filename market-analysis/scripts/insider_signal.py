"""insider_signal.py — 跟内部人「开市买入」之后再跟的诚实**前向公开计分**（出格区·聪明钱族）。

问题：Form 4 公布后，跟着内部人的开市买入(P)买、持有 ~1 个月，相对 SPY 到底有没有超额？
EDGAR 拿不到够长的历史做海量回测（每天上千份 Form 4、三年≈百万次请求，见 fetch_insider 注释），
所以**不做历史回测，走前向计分**：每跑把 insider.json 里新出现的「值得注意的买入」
(≥$MIN_VALUE·有 ticker) append 进 append-only 账本；窗口（默认 30 日历日）走完后用 yfinance
真实股价自动结算 命中/超额，边跑边攒战绩。范式同 overreaction_alert / senate_signal。

诚实红线（都进 JSON caveat）：
- 前向计分：刚上线 0 结算、约 1 个月后才有第一批战绩；样本早期极小，别当定论。
- 入场口径：从 txn_date+3 日历日（覆盖 2 个工作日申报滞后）起、取首个交易日收盘买入，
  持有 HOLD_DAYS 日历日，相对 SPY 同窗超额。→ 测的是「公开披露后再跟」，非抢跑。
- 幸存者偏差：退市/yfinance 无价的代码被丢 → 剩存活者，高估 edge；透明报丢弃比例。
- 选样：每跑只扫近几日 daily-index 前若干份(MAX_FILINGS)，是**样本非全量**；再按金额筛 notable。
- 重叠窗口 → 只看描述性均值/胜率，不在重叠数据上算 p 充显著性。
- 相关≠因果；非荐股、非跟单、不可交易(成本/滑点)、会错、过去≠未来。每跑 append 公开计分。
"""
import csv
import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).parent
BASE = SCRIPTS.parent
PROC = BASE / "data" / "processed"
WEB = BASE / "web"
LOG = BASE / "data" / "insider_signal_log.csv"

HOLD_DAYS = 30           # 跟买后持有的日历天数（~1 个月）
FILING_LAG_DAYS = 3      # txn_date 之后多少日历日才「可跟单」（覆盖 ≤2 工作日申报滞后 + 跟单者次日动作）
MIN_VALUE = 50_000.0     # 值得注意的买入门槛（$）：滤掉琐碎小额；越大越像「聪明钱」但样本越少
BENCH = "SPY"

HEADER = ["filed_date", "ticker", "insider", "title", "txn_date", "shares", "value",
          "entry_date", "entry_px", "exit_date", "exit_px",
          "fwd_pct", "spy_pct", "excess_pct", "hit", "settled", "dropped"]
_TRUE = ("true", "1", "yes")


def _is_true(v):
    return str(v).strip().lower() in _TRUE


# ── 取近期「值得注意的买入」（读 fetch_insider 写好的 insider.json 快照，解耦网络）──
def _load_recent_buys():
    for p in (WEB / "insider.json", PROC / "insider.json"):
        if p.exists():
            try:
                o = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            gen = o.get("generated", "")[:10]            # insider.json 抓取日 ≈ 申报被发现日
            out = []
            for b in o.get("buys", []):
                tk, val, txn = b.get("ticker"), b.get("value"), b.get("date")
                if not (tk and txn and isinstance(val, (int, float)) and val >= MIN_VALUE):
                    continue
                if " " in tk or tk.upper() in ("NONE", "N/A", "NA", "NULL"):  # 防旧脏数据漏网
                    continue
                out.append({"filed_date": gen, "ticker": tk,
                            "insider": b.get("insider") or "", "title": b.get("title") or "",
                            "txn_date": txn, "shares": b.get("shares"), "value": val})
            return out
    return []


# ── append-only 账本（结算只填空、不改信号身份；同 overreaction_alert）──────
def _read_log():
    if not LOG.exists():
        return []
    with open(LOG, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_log(rows):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HEADER})


def _key(r):
    """同一笔买入的身份：ticker+insider+txn_date+shares（防重复 append）。"""
    return (r.get("ticker"), r.get("insider"), str(r.get("txn_date")), str(r.get("shares")))


# ── yfinance 批量取价（可被测试注入替换）──────────────────────────────
def _fetch_prices(tickers, start):
    import yfinance as yf
    cols = {}
    uniq = sorted({t for t in tickers if t} | {BENCH})
    for i in range(0, len(uniq), 120):
        chunk = uniq[i:i + 120]
        try:
            px = yf.download(chunk, start=start, auto_adjust=True, progress=False)["Close"]
        except Exception:
            continue
        if isinstance(px, pd.Series):
            px = px.to_frame(chunk[0])
        for c in px.columns:
            s = pd.to_numeric(px[c], errors="coerce").dropna()
            if len(s) > 5:
                cols[c] = s
    return cols


# ── 单笔前向收益：从 followable 起首个交易日买、持有 hold 日历日 ──────────
def _fwd(series, followable, hold):
    """返回 (ret, entry_date, exit_date, entry_px, exit_px)；
       窗口未走完 → "pending"；无价(退市/未知) → None。"""
    if series is None or series.empty:
        return None
    f = pd.Timestamp(followable)
    after = series.index[series.index >= f]
    if len(after) == 0:
        return "pending" if f > series.index[-1] else None   # 还没到 / 整段无价
    ed = after[0]
    target = ed + pd.Timedelta(days=hold)
    if target > series.index[-1]:
        return "pending"                                      # 持有窗未走完
    upto = series.index[series.index <= target]
    xd = upto[-1]
    epx, xpx = float(series.loc[ed]), float(series.loc[xd])
    if epx <= 0:
        return None
    return (xpx / epx - 1.0, ed, xd, epx, xpx)


def _settle(rows, px):
    """给未结算行结算：股票&SPY 窗口都走完→记超额/命中；股票无价→标 dropped。返回新结算数。"""
    bench = px.get(BENCH)
    n = 0
    for r in rows:
        if _is_true(r.get("settled")) or _is_true(r.get("dropped")):
            continue
        followable = pd.Timestamp(r["txn_date"]) + pd.Timedelta(days=FILING_LAG_DAYS)
        b = _fwd(bench, followable, HOLD_DAYS)
        if b == "pending" or b is None:
            continue                                          # 基准没结算 → 整体挂账
        s = _fwd(px.get(r["ticker"]), followable, HOLD_DAYS)
        if s == "pending":
            continue
        if s is None:                                         # 退市/无价 → 透明丢弃
            r["dropped"] = True
            n += 1
            continue
        sret, ed, xd, epx, xpx = s
        bret = b[0]
        r["entry_date"], r["exit_date"] = ed.date().isoformat(), xd.date().isoformat()
        r["entry_px"], r["exit_px"] = round(epx, 4), round(xpx, 4)
        r["fwd_pct"], r["spy_pct"] = round(sret * 100, 3), round(bret * 100, 3)
        r["excess_pct"] = round((sret - bret) * 100, 3)
        r["hit"] = bool(sret - bret > 0)                      # 命中 = 跑赢 SPY
        r["settled"] = True
        n += 1
    return n


def _scorecard(rows):
    settled_all = [r for r in rows if _is_true(r.get("settled"))]
    # 同一标的同一入场日多名内部人(集群买入)→ 战绩只计一次,防单一事件主导均值(同 senate-Perdue 教训)
    dedup = {(r.get("ticker"), r.get("entry_date")): r for r in settled_all}
    settled = list(dedup.values())
    ex = np.array([float(r["excess_pct"]) for r in settled], float)
    n = len(settled)
    n_hit = sum(1 for r in settled if _is_true(r.get("hit")))
    n_pending = sum(1 for r in rows
                    if not _is_true(r.get("settled")) and not _is_true(r.get("dropped")))
    n_dropped = sum(1 for r in rows if _is_true(r.get("dropped")))
    return {
        "n_settled": n, "n_hit": n_hit,
        "beat_spy_pct": round(n_hit / n * 100, 1) if n else None,
        "mean_excess_pct": round(float(ex.mean()), 3) if n else None,
        "median_excess_pct": round(float(np.median(ex)), 3) if n else None,
        "n_pending": n_pending, "n_dropped": n_dropped,
        "dropped_pct": round(n_dropped / max(1, n + n_dropped) * 100, 1),
    }


def _verdict(sc):
    n = sc["n_settled"]
    if n == 0:
        return "刚上线·0 结算——约 1 个月后才有第一批跟买战绩，攒数据中。"
    me, beat = sc["mean_excess_pct"], sc["beat_spy_pct"]
    head = f"已结算 {n} 笔：跟买后 ~1 月相对 SPY 平均 {me:+.2f}%、跑赢 {beat}%"
    if n < 30:
        return head + f"（n={n} 太小，纯描述、不是结论）。"
    if abs(me) < 1.5:
        return head + "——披露后再跟整体≈打平大盘，滞后基本磨平。"
    return head + "。多重比较/幸存者偏差未除，别当 edge。"


def run(write=True, prices=None):
    rows = _read_log()
    seen = {_key(r) for r in rows}

    # ① append 新出现的 notable 买入（append-only，按身份去重）
    n_new = 0
    for b in _load_recent_buys():
        if _key(b) in seen:
            continue
        seen.add(_key(b))
        rows.append({**b, "entry_date": "", "entry_px": "", "exit_date": "", "exit_px": "",
                     "fwd_pct": "", "spy_pct": "", "excess_pct": "", "hit": "",
                     "settled": False, "dropped": False})
        n_new += 1

    # ② 结算窗口已走完的挂账行（用 yfinance 真实股价；prices 可注入便于测试）
    settled_now = 0
    unsettled = [r for r in rows if not _is_true(r.get("settled")) and not _is_true(r.get("dropped"))]
    if unsettled:
        try:                                   # 结算靠 yfinance 网络——出错不许拖垮整条流水线
            if prices is None:
                start = (datetime.date.today() - datetime.timedelta(days=HOLD_DAYS + 220)).isoformat()
                prices = _fetch_prices([r["ticker"] for r in unsettled], start)
            settled_now = _settle(rows, prices)
        except Exception as e:
            print(f"[内部人计分] 结算阶段出错(非致命,跳过本次结算): {e}")

    sc = _scorecard(rows)
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "SEC EDGAR Form 4 (开市买入 P) → 前向公开计分",
        "hold_days": HOLD_DAYS, "filing_lag_days": FILING_LAG_DAYS,
        "min_value": MIN_VALUE, "benchmark": BENCH,
        "track_record": sc,
        "recent": sorted(
            [{"ticker": r["ticker"], "insider": r.get("insider"), "title": r.get("title"),
              "txn_date": r.get("txn_date"), "value": _num(r.get("value")),
              "settled": _is_true(r.get("settled")), "dropped": _is_true(r.get("dropped")),
              "excess_pct": _num(r.get("excess_pct")), "hit": _is_true(r.get("hit"))}
             for r in rows],
            key=lambda x: (x["txn_date"] or ""), reverse=True)[:40],
        "verdict": _verdict(sc),
        "caveat": ("出格区·聪明钱前向计分。跟内部人开市买入(P·≥$%s)、披露后 +%d 日可跟单、持有 %d 日 vs SPY。"
                   "**前向计分**：刚上线样本极小（约 1 月后才有首批结算），别当结论。"
                   "幸存者偏差：%s%% 因退市/无价被丢→高估 edge；只扫近期 daily-index 前若干份=样本非全量；"
                   "同一标的同一入场日多名内部人(集群买入)战绩只计一次,防单一事件主导；"
                   "重叠窗口只看描述性均值/胜率不充显著性；相关≠因果；非荐股、非跟单、不可交易、会错、过去≠未来。"
                   "每跑 append 公开计分。"
                   % (f"{MIN_VALUE/1000:.0f}k", FILING_LAG_DAYS, HOLD_DAYS, sc["dropped_pct"])),
    }

    if write:
        from util_io import write_json
        write_json("insider_signal.json", out)
        _write_log(rows)
        print(f"[OK] insider_signal.json — {out['verdict']}")
        print(f"  新增 {n_new} 笔 · 本次新结算 {settled_now} · 已结算 {sc['n_settled']} "
              f"(跑赢 {sc['beat_spy_pct']}%) · 挂账 {sc['n_pending']} · 丢弃 {sc['n_dropped']}")
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    run()
