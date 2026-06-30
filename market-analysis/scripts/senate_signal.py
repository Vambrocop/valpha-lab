"""senate_signal.py — 参议院买入「披露之后再跟」的诚实 OOS 检验（出格区·政治钱族）。

问题：议员申报有 ~45 天滞后，所以不是抢跑。测「从可跟单日(txn+45d)买入、持有 ~3 个月，
相对 SPY 的超额收益」——议员买入到底有没有 OOS edge，还是滞后磨平了？按议员拆（David Perdue
一人占 42% → 聚合会被他主导，必须分开看）。

诚实红线（都在 JSON caveat 里标）：
- 数据停在 2020-11（免费源停更）→ 历史检验、非实时。
- 幸存者偏差：已退市/并购的代码 yfinance 无价 → 被丢，剩存活者（高估 edge），透明报丢弃比例。
- 重叠窗口 → 只看描述性均值/胜率，不在重叠数据上算 p 充当显著性。
- 相关≠因果；非荐股、非跟单建议。每跑 append 计分。

⚠️ 2026-06-30 复核：上游源已停更(最新 2019-12)→ 本族**完结历史研究**，故意**不进 run_all/workflow**
（fetch_senate 同）——结论已定(≈打平)，改方法论才手动重跑；要实时需换活源(新立项)。详见 fetch_senate.py。
"""
import json
import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

BASE = Path(__file__).parent.parent
TRADES = BASE / "data" / "senate_trades.csv"
LOG = BASE / "data" / "senate_signal_log.csv"
HOLD_DAYS = 90          # ~3 个月日历持有
BENCH = "SPY"


def _fetch_prices(tickers):
    """批量抓收盘价（含基准 SPY）；分块避免一次太多。返回 wide DataFrame(date×ticker)。"""
    cols = {}
    uniq = sorted(set(tickers) | {BENCH})
    for i in range(0, len(uniq), 120):
        chunk = uniq[i:i + 120]
        try:
            px = yf.download(chunk, start="2012-01-01", auto_adjust=True, progress=False)["Close"]
        except Exception:
            continue
        if isinstance(px, pd.Series):
            px = px.to_frame(chunk[0])
        for c in px.columns:
            s = px[c].dropna()
            if len(s) > 50:
                cols[c] = s
    return cols


def _fwd(series, d, hold):
    """从日期 d 起、持有 hold 日历日的收益（asof 最近交易日）。无数据返回 None。"""
    if series is None or series.empty:
        return None
    d = pd.Timestamp(d)
    if d < series.index[0] or (d + pd.Timedelta(days=hold)) > series.index[-1]:
        return None                                    # 整个持有窗须落在数据内，否则退出端会用截短价(审 P2)
    entry = series.asof(d)
    exit_ = series.asof(d + pd.Timedelta(days=hold))
    if pd.isna(entry) or pd.isna(exit_) or entry <= 0:
        return None
    return float(exit_ / entry - 1)


def _stats(arr):
    a = np.asarray([x for x in arr if x is not None], float)
    if len(a) < 20:
        return None
    return {"n": int(len(a)), "mean_excess_pct": round(float(a.mean()) * 100, 2),
            "beat_mkt_pct": round(float((a > 0).mean() * 100), 1),
            "median_pct": round(float(np.median(a)) * 100, 2)}


def run(write=True):
    df = pd.read_csv(TRADES, parse_dates=["txn_date", "followable_date"])
    trades = df[df["side"].isin(["buy", "sell"])].copy()
    px = _fetch_prices(trades["ticker"].unique())
    bench = px.get(BENCH)
    excess, sell_ex, kept = [], [], []
    for _, r in trades.iterrows():
        s = px.get(r["ticker"])
        f = _fwd(s, r["followable_date"], HOLD_DAYS)
        b = _fwd(bench, r["followable_date"], HOLD_DAYS)
        if f is None or b is None:
            continue
        ex = f - b
        if r["side"] == "buy":
            excess.append(ex)
            kept.append({"senator": r["senator"], "ex": ex})
        else:
            sell_ex.append(ex)               # 他们卖的股票之后 vs SPY（负=避开/跟卖有用）
    overall = _stats(excess)                 # 整体 = 跟着买他们买的
    sold = _stats(sell_ex)
    n_buys = int((trades["side"] == "buy").sum())
    drop_pct = round((1 - len(excess) / max(1, n_buys)) * 100, 1)
    # 按议员拆（≥30 笔可统计的才单列）
    kd = pd.DataFrame(kept)
    per = []
    top_note = ""
    if len(kd):
        for sen, g in kd.groupby("senator"):
            st = _stats(g["ex"].tolist())
            if st and st["n"] >= 30:
                per.append({"senator": sen, **st})
        per.sort(key=lambda x: -x["mean_excess_pct"])
        vc = kd["senator"].value_counts()
        top_note = f"整体样本中 {vc.index[0]} 一人占 ~{round(vc.iloc[0] / len(kd) * 100)}%、显著影响整体均值；"
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "horizon_days": HOLD_DAYS, "benchmark": BENCH,
        "data_range": [str(trades["txn_date"].min().date()), str(trades["txn_date"].max().date())],
        "n_buys": n_buys, "n_tested": len(excess), "dropped_pct": drop_pct,
        "overall": overall, "sold_stocks_after": sold, "by_senator": per,
        "comparison": {"follow_buys": (overall or {}).get("mean_excess_pct"),
                       "sold_stocks_after": (sold or {}).get("mean_excess_pct"), "hold_market": 0.0},
        "decision": _decide(overall, sold),
        "verdict": _verdict(overall, per),
        "caveat": "出格区·政治钱诚实检验。45天披露滞后→测的是「披露后再跟」非抢跑。"
                  f"数据停 2020-11(历史·非实时)；{top_note}幸存者偏差：{drop_pct}% 买入因代码退市/无价被丢，剩存活者→高估 edge；"
                  "重叠窗口只看描述性均值/胜率不充当显著性；相关≠因果；非荐股、非跟单。每跑 append 计分。",
    }
    if write:
        from util_io import write_json
        write_json("senate_signal.json", out)
        _log(out)
        print(f"[OK] senate_signal.json — {out['verdict']}")
        print(f"  整体: {overall} · 丢弃 {drop_pct}% · 可统计议员 {len(per)} 位")
        for p in per[:6]:
            print(f"    {p['senator']}: 超额{p['mean_excess_pct']}% 胜率{p['beat_mkt_pct']}% n={p['n']}")
    return out


def _decide(overall, sold):
    """直接回答用户：披露了【买 / 不买 / 避开他们卖的】哪个合适。用中位数(抗极端值)做主判。"""
    if not overall:
        return "样本不足，无定论"
    fbm, fb = overall["median_pct"], overall["mean_excess_pct"]
    ssm = sold["median_pct"] if sold else None
    ss = sold["mean_excess_pct"] if sold else None
    line = (f"跟着买他们买的：中位 {fbm:+.1f}%（均值 {fb:+.1f}%）vs SPY；"
            f"他们卖的股之后：中位 {('—' if ssm is None else f'{ssm:+.1f}%')}"
            f"（均值 {('—' if ss is None else f'{ss:+.1f}%')}·被少数极端赢家拉高）vs SPY；持有大盘=0(基准)。")
    return (line + "→ 披露了【不买、也不必跟卖】最稳：跟买中位输 SPY、他们卖的股中位也≈持平(避开/跟卖没用)；"
            "均值差异多是极端值噪声。别跟，持有大盘即可。")


def _verdict(overall, per):
    if not overall:
        return "样本不足，无定论"
    pos = sum(1 for p in per if p["mean_excess_pct"] > 0)
    base = f"整体 ~3月超额 {overall['mean_excess_pct']}%、跑赢SPY {overall['beat_mkt_pct']}%（n={overall['n']}）"
    # 审 P1：7/14 正≈掷硬币期望，必须明说"不是有 edge 的议员"，否则榜首被误读成信号
    mc = (f"{pos}/{len(per)} 位议员正超额≈掷硬币期望——{len(per)} 人未做多重检验校正，"
          f"个体正值与噪声无法区分，别把任何单个议员(含榜首)当 edge；幸存者偏差未除")
    if abs(overall["mean_excess_pct"]) < 2:
        return f"滞后基本磨平：{base}——披露后再跟整体≈打平。{mc}"
    return f"{base}。{mc}"


def _log(out):
    from util_io import append_daily_log
    today = datetime.date.today().isoformat()
    ov = out.get("overall") or {}
    append_daily_log(LOG, ["date", "n_tested", "overall_excess_pct", "dropped_pct"],
                     [[today, out["n_tested"], ov.get("mean_excess_pct"), out["dropped_pct"]]], date=today)


if __name__ == "__main__":
    run()
