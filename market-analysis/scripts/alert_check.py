"""
alert_check.py — 信号告警检测（在 GitHub Actions 中运行）

只在「状态变化」时触发（避免每天重复骚扰）：
  - 纳指/标普信号升入 tier>=4（买入窗口开启）或跌入 tier<=2（回避）
  - VIX 期限结构从正常切换为倒挂（或反向）
触发时写 alert.md → workflow 用 gh 建 Issue → GitHub 自动发邮件通知
"""
import os
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

# ── 持仓感知告警（只在你实际持有的票出现风险事件才提醒；风险提示，非买卖建议）──
# 持仓从 HOLDINGS 环境变量读（GitHub Secret，逗号/换行分隔），私密、绝不进公开仓库；
# 本地可放 data/holdings.txt 测试（已 gitignore）。未配置则整段静默跳过。
# 只对「距 52 周高回撤」做状态分档，进入更深档/收窄回正常时各提醒一次（沿用上面的去重逻辑）。
def _holdings():
    raw = os.environ.get("HOLDINGS", "")
    if not raw:
        hf = Path(__file__).parent.parent / "data" / "holdings.txt"
        if hf.exists():
            raw = hf.read_text(encoding="utf-8")
    out = []
    for line in raw.replace(",", "\n").splitlines():
        tk = line.split("#")[0].strip().upper()
        if tk:
            out.append(tk)
    return out

_held = _holdings()
if _held:
    try:
        _v150 = json.load(open(WEB_DIR / "valpha150.json", encoding="utf-8"))
        _meta = {s["t"].upper(): s for s in _v150.get("stocks", []) if s.get("t")}
    except Exception:
        _meta = {}
    _ORDER = {"ok": 0, "deep": 1, "severe": 2}
    _ZTXT = {"deep": "深度回撤（距52周高 >25%）", "severe": "重度回撤（距52周高 >40%）"}
    def _dd_zone(fh):
        if fh is None:
            return "ok"
        if fh <= -40:
            return "severe"
        if fh <= -25:
            return "deep"
        return "ok"
    for _tk in _held:
        _s = _meta.get(_tk)
        if not _s:
            continue                               # 不在追踪的 150 里：静默跳过（任意票请用点单深算）
        _z = _dd_zone(_s.get("fh"))
        _key = f"hold_{_tk}"
        cur_state[_key] = _z
        _prev = last_state.get(_key, "ok")
        if _ORDER[_z] > _ORDER.get(_prev, 0):      # 进入更深回撤档
            alerts.append(f"🔻 **持仓 {_s.get('n', _tk)}（{_tk}）{_ZTXT[_z]}**——"
                          f"现价 {_s.get('p')}，距52周高 {_s.get('fh')}%，年化波动 {_s.get('v')}%。"
                          f"风险提示，非卖出建议。")
        elif _z == "ok" and _ORDER.get(_prev, 0) > 0:   # 从回撤档收窄回正常
            alerts.append(f"🔺 **持仓 {_tk} 回撤收窄**（距52周高 {_s.get('fh')}%）——风险缓解，非买入建议。")

# 状态持久化（只有真的发出告警时才更新，保证「变化→告警」一一对应）
if alerts:
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(cur_state, f, ensure_ascii=False)
elif not STATE.exists():
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(cur_state, f, ensure_ascii=False)

if alerts:
    body = (f"# Valpha Lab 信号告警 {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            + "\n\n".join(alerts)
            + "\n\n---\n[打开仪表盘](https://vambrocop.github.io/valpha-lab/) · 自动生成，仅供参考")
    ALERT.write_text(body, encoding="utf-8")
    print(f"[ALERT] {len(alerts)} 条告警 → alert.md")
    try:                                               # 同时推 Telegram（未配置 Secrets 则静默跳过）
        import notify_telegram
        notify_telegram.send(body.replace("**", "").replace("# ", ""))
    except Exception as e:
        print(f"  ⚠ Telegram 推送跳过: {e}")
else:
    if ALERT.exists():
        ALERT.unlink()
    print("[OK] 无状态变化，不告警")
