"""insider_signal.py — 跟内部人「开市买入」之后再跟的诚实**前向公开计分**（出格区·聪明钱族）。

问题：Form 4 公布后，跟着内部人的开市买入(P)买、持有 ~1 个月，相对 SPY 到底有没有超额？
EDGAR 拿不到够长的历史做海量回测（每天上千份 Form 4、三年≈百万次请求，见 fetch_insider 注释），
所以**不做历史回测，走前向计分**：每跑把 insider.json 里新出现的「值得注意的买入」
(≥$MIN_VALUE·有 ticker) append 进 append-only 账本；窗口（默认 30 日历日）走完后用 yfinance
真实股价自动结算 命中/超额，边跑边攒战绩。机械件(账本I/O·取价·前向收益·结算骨架)走 forward_ledger，
本文件只留「内部人」专属判断：取数门槛 + 命中口径(跟买跑赢 SPY 即命中) + 集群去重。

诚实红线（都进 JSON caveat）：
- 前向计分：刚上线 0 结算、约 1 个月后才有第一批战绩；样本早期极小，别当定论。
- 入场口径：从 txn_date+3 日历日（覆盖 ≤2 工作日申报滞后）起、取首个交易日收盘买入，
  持有 HOLD_DAYS 日历日，相对 SPY 同窗超额。→ 测的是「公开披露后再跟」，非抢跑。
- 幸存者偏差：退市/yfinance 无价的代码被丢 → 剩存活者，高估 edge；透明报丢弃比例。
- 选样：每跑只扫近期 daily-index 前若干份(MAX_FILINGS)，是**样本非全量**；再按金额筛 notable。
- 同一标的同一入场日多名内部人(集群买入)战绩只计一次，防单一事件主导。
- 重叠窗口 → 只看描述性均值/胜率，不在重叠数据上算 p 充显著性。
- 相关≠因果；非荐股、非跟单、不可交易(成本/滑点)、会错、过去≠未来。每跑 append 公开计分。
"""
import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

import forward_ledger as fl

SCRIPTS = Path(__file__).parent
BASE = SCRIPTS.parent
PROC = BASE / "data" / "processed"
WEB = BASE / "web"
LOG = BASE / "data" / "insider_signal_log.csv"

HOLD_DAYS = 30           # 跟买后持有的日历天数(~1 个月)
FILING_LAG_DAYS = 3      # txn_date 之后多少日历日才「可跟单」(覆盖 ≤2 工作日申报滞后 + 跟单者次日动作)
MIN_VALUE = 50_000.0     # 值得注意的买入门槛($)：滤掉琐碎小额；越大越像「聪明钱」但样本越少
BENCH = "SPY"

HEADER = ["filed_date", "ticker", "insider", "title", "txn_date", "shares", "value",
          "entry_date", "entry_px", "exit_date", "exit_px",
          "fwd_pct", "spy_pct", "excess_pct", "hit", "settled", "dropped"]


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


# ── 「内部人」专属判断：身份去重键 + 可跟单日 + 命中口径 ───────────────────
def _key(r):
    """同一笔买入的身份：ticker+insider+txn_date+shares（防重复 append）。"""
    return (r.get("ticker"), r.get("insider"), str(r.get("txn_date")), str(r.get("shares")))


def _followable(r):
    return pd.Timestamp(r["txn_date"]) + pd.Timedelta(days=FILING_LAG_DAYS)   # 披露后可跟单日


def _outcome(sret, bret, r):
    """命中口径：跟买跑赢 SPY 即命中。"""
    ex = sret - bret
    return {"fwd_pct": round(sret * 100, 3), "spy_pct": round(bret * 100, 3),
            "excess_pct": round(ex * 100, 3), "hit": bool(ex > 0)}


def _settle(rows, px):
    return fl.settle(rows, px, bench=BENCH, hold=HOLD_DAYS, trading_days=False,
                     symbol_key="ticker", followable_of=_followable, outcome_of=_outcome)


def _scorecard(rows):
    settled_all = [r for r in rows if fl.is_true(r.get("settled"))]
    # 同一标的同一入场日多名内部人(集群买入)→ 战绩只计一次,防单一事件主导均值(同 senate-Perdue 教训)
    dedup = {(r.get("ticker"), r.get("entry_date")): r for r in settled_all}
    settled = list(dedup.values())
    ex = np.array([float(r["excess_pct"]) for r in settled], float)
    n = len(settled)
    n_hit = sum(1 for r in settled if fl.is_true(r.get("hit")))
    n_pending, n_dropped = fl.count_pending_dropped(rows)
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
    rows = fl.read_log(LOG)
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
    unsettled = [r for r in rows if not fl.is_true(r.get("settled")) and not fl.is_true(r.get("dropped"))]
    if unsettled:
        try:                                   # 结算靠 yfinance 网络——出错不许拖垮整条流水线
            if prices is None:
                start = (datetime.date.today() - datetime.timedelta(days=HOLD_DAYS + 220)).isoformat()
                prices = fl.fetch_prices([r["ticker"] for r in unsettled], start, BENCH)
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
              "settled": fl.is_true(r.get("settled")), "dropped": fl.is_true(r.get("dropped")),
              "excess_pct": _num(r.get("excess_pct")), "hit": fl.is_true(r.get("hit"))}
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
        fl.write_log(LOG, HEADER, rows)
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
