"""
daily_brief.py — 每日盘后简报（规则化生成，GitHub Actions 云端全自动）

读取 signals.json + 价格数据，把当天的数字翻译成中文结论 → web/brief.json
"""
import json
import pandas as pd
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
WEB_DIR = Path(__file__).parent.parent / "web"

TIER_CN = {1: "回避", 2: "偏弱", 3: "中性", 4: "积极", 5: "强烈"}


def pct(a, b):
    return (a / b - 1) * 100


def main():
    with open(WEB_DIR / "signals.json", encoding="utf-8") as f:
        sig = json.load(f)
    prices = pd.read_csv(RAW_DIR / "combined_prices.csv",
                         index_col="Date", parse_dates=True)

    lines = []

    # ── 1. 市场表现 ───────────────────────────────────────────────
    perf = []
    for name, label in [("NASDAQ", "纳指"), ("SP500", "标普"),
                        ("VIX", "VIX"), ("BTC", "BTC")]:
        if name not in prices.columns:
            continue
        s = prices[name].dropna()
        if len(s) < 2:
            continue
        chg = pct(s.iloc[-1], s.iloc[-2])
        arrow = "▲" if chg > 0 else "▼"
        perf.append(f"{label} {arrow}{abs(chg):.2f}%")
    last_day = prices["NASDAQ"].dropna().index[-1].strftime("%m-%d")
    lines.append(f"【市场 {last_day}】" + "，".join(perf))

    # ── 2. 信号状态 ───────────────────────────────────────────────
    idx = sig.get("indices", {})
    base_rate = sig.get("base_rate_20d", 0.62)
    base_rate_pct = round(base_rate * 100)
    sig_parts = []
    for k, label in [("NASDAQ", "纳指"), ("SP500", "标普")]:
        s = idx.get(k, {})
        if s:
            raw_pct = round(s["prob"] * 100)
            if s.get("prob_cal") is not None:
                cal_pct = round(s["prob_cal"] * 100)
                sig_parts.append(f"{label} 20日上涨概率 {cal_pct}%（校准，原始{raw_pct}%）")
            else:
                sig_parts.append(f"{label} 20日上涨概率 {raw_pct}%（原始）")
    if sig_parts:
        base_note = f"基率 {base_rate_pct}% · 实验性信号"
        lines.append("【信号】" + "；".join(sig_parts) + f"｜{base_note}")

    # ── 3. 风险状态（VIX期限结构 + 波动率） ───────────────────────
    risk = []
    # 成对对齐再取最后一行：两列分别 dropna 会比较不同日期的值（缓存回退时尤甚）
    v = v3 = pd.Series(dtype=float)
    if "VIX" in prices.columns and "VIX3M" in prices.columns:
        pair = prices[["VIX", "VIX3M"]].dropna()
        if len(pair):
            v, v3 = pair["VIX"], pair["VIX3M"]
    if len(v) and len(v3):
        if v.iloc[-1] >= v3.iloc[-1]:
            risk.append(f"⚠ VIX期限结构倒挂（{v.iloc[-1]:.1f} ≥ {v3.iloc[-1]:.1f}）——恐慌状态，"
                        f"但历史上倒挂后20日胜率64.8%，往往接近底部")
        else:
            risk.append(f"VIX期限结构正常（{v.iloc[-1]:.1f} < {v3.iloc[-1]:.1f}），无恐慌")
    ndq_ret = prices["NASDAQ"].dropna().pct_change()
    vol20 = float(ndq_ret.rolling(20).std().iloc[-1] * (252 ** 0.5) * 100)
    risk.append(f"纳指20日年化波动 {vol20:.0f}%" + ("（高波动）" if vol20 > 25 else ""))
    lines.append("【风险】" + "；".join(risk))

    # ── 3.5 关键指标红绿灯（直接看的状态层，不进概率模型）─────────
    lights = []
    ndq_s = prices["NASDAQ"].dropna()
    ma200 = float(ndq_s.rolling(200).mean().iloc[-1])
    above = float(ndq_s.iloc[-1]) > ma200
    lights.append({"name": "趋势(MA200)", "status": "green" if above else "red",
                   "value": f"{'上方' if above else '下方'} {abs(ndq_s.iloc[-1]/ma200-1)*100:.1f}%",
                   "note": "牛熊分界线，下方时一切看空信号加倍认真"})
    if len(v) and len(v3):
        bwd = v.iloc[-1] >= v3.iloc[-1]
        lights.append({"name": "VIX期限结构", "status": "red" if bwd else "green",
                       "value": f"{v.iloc[-1]:.1f}/{v3.iloc[-1]:.1f}",
                       "note": "倒挂=恐慌（历史上倒挂后20日胜率64.8%，常近底部）"})
        lights.append({"name": "VIX水平", "status": "red" if v.iloc[-1] > 30 else
                       ("yellow" if v.iloc[-1] > 20 else "green"),
                       "value": f"{v.iloc[-1]:.1f}",
                       "note": "<20平静 / 20-30警惕 / >30恐慌"})
    if "T10Y2Y" in prices.columns:
        t = prices["T10Y2Y"].dropna()
        if len(t):
            tv = float(t.iloc[-1])
            lights.append({"name": "收益率曲线(10Y-2Y)", "status": "red" if tv < 0 else
                           ("yellow" if tv < 0.3 else "green"),
                           "value": f"{tv:+.2f}%",
                           "note": "倒挂(<0)是历史上最可靠的衰退预警，领先6-18个月"})
    if "HY_SPREAD" in prices.columns:
        h = prices["HY_SPREAD"].dropna()
        if len(h) > 21:
            hv, hchg = float(h.iloc[-1]), float(h.iloc[-1] - h.iloc[-21])
            lights.append({"name": "信用利差(HY)", "status": "red" if hv > 5 or hchg > 0.8 else
                           ("yellow" if hv > 4 or hchg > 0.4 else "green"),
                           "value": f"{hv:.2f}%（20日{hchg:+.2f}）",
                           "note": "信用市场比股市先闻到危险；快速走阔=避险"})

    # ── 4. 未来一周窗口 ───────────────────────────────────────────
    fc = sig.get("next_opportunities", {}).get("all_forecast", [])[:5]
    if fc:
        wk = "，".join(f"{d['date'][5:]}({d['dow_cn']}){d['prob']*100:.0f}%"
                      + ("⚠" + d["macro"] if d.get("macro") else "")
                      for d in fc)
        lines.append(f"【未来一周】{wk}")
        best = max(fc, key=lambda d: d["prob"])
        if best["tier"] >= 4:
            lines.append(f"【提示】{best['date'][5:]}（{best['dow_cn']}）为本周最佳入场窗口"
                         f"（{best['prob']*100:.0f}%），建议尾盘买入")

    # ── 5. 宏观事件 ───────────────────────────────────────────────
    macro = sig.get("macro_calendar", [])[:2]
    if macro:
        lines.append("【事件】" + "；".join(f"{m['date'][5:]} {m['label']}" for m in macro)
                     + " —— 当日波动放大，避免重仓操作")

    out = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "model_version": sig.get("model_version"),
        "lines": lines,
        "lights": lights,
    }
    with open(WEB_DIR / "brief.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\n".join(lines))
    print(f"[OK] → brief.json")


if __name__ == "__main__":
    main()
