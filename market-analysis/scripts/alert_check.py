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

WEB_DIR  = Path(__file__).parent.parent / "web"
RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
ALERT = Path(__file__).parent.parent / "alert.md"
STATE = PROC_DIR / "alert_state.json"   # 上次已告警的状态（防止小时级重复轰炸）

alerts = []

with open(WEB_DIR / "signals.json", encoding="utf-8") as f:
    sig = json.load(f)

try:
    with open(STATE, encoding="utf-8") as f:
        last_state = json.load(f)
except Exception:
    last_state = {}
cur_state = {}

def _zone(tier):
    return "high" if tier >= 4 else ("low" if tier <= 2 else "mid")

# ── 信号档位状态变化（对比「上次已告警状态」，不是昨天）──────────
streams = {"纳指": sig["daily_signals"], "标普": sig.get("daily_signals_sp500", {})}
for name, daily in streams.items():
    days = sorted(daily)
    if not days:
        continue
    cur = daily[days[-1]]
    z = _zone(int(cur["tier"]))
    cur_state[f"zone_{name}"] = z
    if z != last_state.get(f"zone_{name}", "mid"):
        if z == "high":
            alerts.append(f"🟢 **{name}信号升入第{cur['tier']}档**（{days[-1]}，概率 {cur['prob']*100:.1f}%）"
                          f"——买入窗口开启，建议尾盘执行")
        elif z == "low":
            alerts.append(f"🔴 **{name}信号跌入第{cur['tier']}档**（{days[-1]}，概率 {cur['prob']*100:.1f}%）"
                          f"——回避新仓，考虑减仓")

# ── VIX 期限结构状态变化 ──────────────────────────────────────────
try:
    prices = pd.read_csv(RAW_DIR / "combined_prices.csv",
                         index_col="Date", parse_dates=True)
    pair = prices[["VIX", "VIX3M"]].dropna()   # 成对对齐，避免比较不同日期
    if len(pair):
        cur_bwd = bool(pair["VIX"].iloc[-1] >= pair["VIX3M"].iloc[-1])
        cur_state["vix_bwd"] = cur_bwd
        if cur_bwd != last_state.get("vix_bwd", False):
            if cur_bwd:
                alerts.append(f"⚠️ **VIX期限结构倒挂**（VIX {pair['VIX'].iloc[-1]:.1f} ≥ "
                              f"VIX3M {pair['VIX3M'].iloc[-1]:.1f}）——市场进入恐慌状态；"
                              f"历史上倒挂后20日胜率64.8%，往往接近底部")
            else:
                alerts.append("✅ **VIX期限结构恢复正常**——恐慌解除")
except Exception:
    pass

# 状态持久化（只有真的发出告警时才更新，保证「变化→告警」一一对应）
if alerts:
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(cur_state, f, ensure_ascii=False)
elif not STATE.exists():
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(cur_state, f, ensure_ascii=False)

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
