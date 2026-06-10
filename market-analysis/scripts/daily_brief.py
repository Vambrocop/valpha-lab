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
    sig_parts = []
    for k, label in [("NASDAQ", "纳指"), ("SP500", "标普")]:
        s = idx.get(k, {})
        if s:
            cal = f"（校准后{ s['prob_cal']*100:.0f}%）" if s.get("prob_cal") else ""
            sig_parts.append(f"{label} {s['prob']*100:.1f}%{cal} 第{s['tier']}档·{TIER_CN.get(s['tier'],'')}")
    if sig_parts:
        lines.append("【信号】" + "；".join(sig_parts))

    # ── 3. 风险状态（VIX期限结构 + 波动率） ───────────────────────
    risk = []
    v, v3 = prices["VIX"].dropna(), prices.get("VIX3M", pd.Series()).dropna()
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
    }
    with open(WEB_DIR / "brief.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\n".join(lines))
    print(f"[OK] → brief.json")


if __name__ == "__main__":
    main()
