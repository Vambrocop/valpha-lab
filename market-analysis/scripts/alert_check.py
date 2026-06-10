"""
alert_check.py — 信号告警检测（在 GitHub Actions 中运行）

只在「状态变化」时触发（避免每天重复骚扰）：
  - 纳指/标普信号升入 tier>=4（买入窗口开启）或跌入 tier<=2（回避）
  - VIX 期限结构从正常切换为倒挂（或反向）
触发时写 alert.md → workflow 用 gh 建 Issue → GitHub 自动发邮件通知
"""
import json
import pandas as pd
from pathlib import Path

WEB_DIR = Path(__file__).parent.parent / "web"
RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
ALERT = Path(__file__).parent.parent / "alert.md"

alerts = []

with open(WEB_DIR / "signals.json", encoding="utf-8") as f:
    sig = json.load(f)

# ── 信号档位跨越 ──────────────────────────────────────────────────
streams = {"纳指": sig["daily_signals"], "标普": sig.get("daily_signals_sp500", {})}
for name, daily in streams.items():
    days = sorted(daily)
    if len(days) < 2:
        continue
    prev, cur = daily[days[-2]], daily[days[-1]]
    pt, ct = int(prev["tier"]), int(cur["tier"])
    if ct >= 4 > pt:
        alerts.append(f"🟢 **{name}信号升入第{ct}档**（{days[-1]}，概率 {cur['prob']*100:.1f}%）"
                      f"——买入窗口开启，建议尾盘执行")
    if ct <= 2 < pt:
        alerts.append(f"🔴 **{name}信号跌入第{ct}档**（{days[-1]}，概率 {cur['prob']*100:.1f}%）"
                      f"——回避新仓，考虑减仓")

# ── VIX 期限结构切换 ──────────────────────────────────────────────
try:
    prices = pd.read_csv(RAW_DIR / "combined_prices.csv",
                         index_col="Date", parse_dates=True)
    pair = prices[["VIX", "VIX3M"]].dropna()
    if len(pair) >= 2:
        prev_bwd = pair["VIX"].iloc[-2] >= pair["VIX3M"].iloc[-2]
        cur_bwd  = pair["VIX"].iloc[-1] >= pair["VIX3M"].iloc[-1]
        if cur_bwd and not prev_bwd:
            alerts.append(f"⚠️ **VIX期限结构倒挂**（VIX {pair['VIX'].iloc[-1]:.1f} ≥ "
                          f"VIX3M {pair['VIX3M'].iloc[-1]:.1f}）——市场进入恐慌状态；"
                          f"历史上倒挂后20日胜率64.8%，往往接近底部")
        if prev_bwd and not cur_bwd:
            alerts.append("✅ **VIX期限结构恢复正常**——恐慌解除")
except Exception:
    pass

if alerts:
    body = (f"# Alpha Lab 信号告警 {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            + "\n\n".join(alerts)
            + "\n\n---\n[打开仪表盘](https://vambrocop.github.io/alpha-lab/) · 自动生成，仅供参考")
    ALERT.write_text(body, encoding="utf-8")
    print(f"[ALERT] {len(alerts)} 条告警 → alert.md")
else:
    if ALERT.exists():
        ALERT.unlink()
    print("[OK] 无状态变化，不告警")
