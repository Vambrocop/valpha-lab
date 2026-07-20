"""downturn_brief.py — 大跌日诚实数据包（W4a·事实通报，非信号非抄底建议）。

市场大跌时，用户最需要的不是情绪、不是"要不要抄底"的建议，而是"我们到底测过什么"的
诚实数据。本脚本**不新算任何统计**——只在触发日把已产出的现成 json/csv 里的真实字段
汇成一条 Telegram 消息：今日跌幅、VXSMH 读数、连跌当前态（+ 其历史检验通过率）、
长跨度当前态（+ 通过率）、极端下跌次日分布、条件下行分位。全部诚实引用，不重算显著性。

═══ 触发条件（机械·写死·任一为真即触发）══════════════════════════════════
  ① NASDAQ 或 SP500 单日跌幅 ≤ -2.5%
  ② VXSMH 现值 ≥ 60 且当日 NASDAQ 跌幅 ≤ -1.5%（半导体恐慌计·纯描述，见 risk_dashboard.py）
  ③ VIX 单日涨幅 ≥ +15%
数据源：data/raw/combined_prices.csv（NASDAQ/SP500/VIX 最新两个有效交易日算日变化）
      + web/risk_dashboard.json 的 vxsmh.close（"现值"，允许比 combined_prices 最新行晚一天，
        两者同一流水线日更、正常运行下口径一致；vxsmh 数据源缺失时②直接判不触发，不报错）。
不满足任一条件 → 打印"未触发"、零行为（不建账本、不推送）。

═══ 数据包各节来源（全部只读现成产物，不新算）════════════════════════════
  · 今日跌幅              ← combined_prices.csv 最新两行
  · VXSMH 读数+分位       ← risk_dashboard.json.vxsmh（"史太短·纯描述"注同 risk_dashboard 口径）
  · 连跌当前态+通过率     ← autodiscovery.json.context_states（down_streak）
                            + candidates 里 streak_down/streak_break 两族的 verdict==survive 计数
                            （2026-07-17 现状：18+12=30 候选、0 存活——即"0/30 过校正"）
  · 长跨度当前态+通过率   ← 同上 context_states.trailing.63d + trailing_extreme 族存活计数
                            （现状：14 候选、0 存活）
  · 极端下跌次日分布      ← overreaction_signal.json（今日是否触发其自身阈值）
                            + overreaction.json 现代段统计（bounce/other/p_value/pct_negative）
  · 条件下行              ← risk_dashboard.json.downside_by_vix（按当前 VIX 落哪个历史档位）
族存活计数用真实字段现算（不硬编码 30/14 这类数字），族口径变化（未来新候选/新裁决）时
消息自动跟着数据走，不会因为忘改硬编码常量而讲错历史。

═══ 去重防轰炸（同 ipo_alerts.py 的取舍）═════════════════════════════════
append-only data/downturn_brief_log.csv：**每自然日最多推一次**——当日已在账（无论
pushed True/False）→ 直接跳过，不重推不重记（同 ipo_alerts："配置了但失败→pushed=False
落账，下轮不重试"——重试要么改历史行、要么脏账本，两者都不如放弃这一条换干净账本）。
**未配置 TELEGRAM token → 完全跳过、不落账不消费**：跟 ipo_alerts 同一取舍——本地常态
无 token，若在此抢先把"今天"消费成 pushed=False，CI（有 secrets）当天就再也推不出去了。
push=False（测试直调）不受此限，用于绕开 token 检查跑通逻辑、不碰网络。

fail-soft：任何异常打印后 exit 0，不阻断流水线（照 ipo_alerts 惯例）。

单独跑：$env:PYTHONUTF8='1'; py market-analysis/scripts/downturn_brief.py
"""
import csv
import datetime
import json
import sys
from pathlib import Path

import pandas as pd

SCRIPTS = Path(__file__).parent
BASE = SCRIPTS.parent
RAW = BASE / "data" / "raw" / "combined_prices.csv"
AUTODISCOVERY = BASE / "web" / "autodiscovery.json"
RISK = BASE / "web" / "risk_dashboard.json"
OVERREACTION_SIGNAL = BASE / "web" / "overreaction_signal.json"
OVERREACTION_FULL = BASE / "web" / "overreaction.json"
LOG = BASE / "data" / "downturn_brief_log.csv"

HEADER = ["date", "trigger_reason", "nasdaq_d1", "vix", "vxsmh", "pushed"]

# 触发阈值——机械·写死，任一为真即触发（见文件头 ①②③）
THRESH_DROP_PCT = -2.5           # ①单日跌幅
THRESH_VXSMH = 60.0              # ②VXSMH 现值门槛
THRESH_VXSMH_NASDAQ_PCT = -1.5   # ②同时要求的纳指跌幅门槛（比①更松，配合 VXSMH 共同判定）
THRESH_VIX_SPIKE_PCT = 15.0      # ③VIX 单日涨幅

# 连跌族 / 长跨度族——历史检验对象（autodiscovery.json candidates 的 family 字段）
STREAK_FAMILIES = {"streak_down", "streak_break"}
TRAILING_FAMILIES = {"trailing_extreme"}


# ── 数据加载（每个来源独立函数，便于测试逐个 monkeypatch）───────────────────
def _read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_market():
    """combined_prices.csv → 最新有效交易日 vs 前一有效交易日的 NASDAQ/SP500/VIX 变化。
    返回 dict(date, nasdaq_d1, sp500_d1, vix, vix_d1) 或 None（数据缺/不足两行）。"""
    if not RAW.exists():
        return None
    df = pd.read_csv(RAW)
    cols = [c for c in ("Date", "NASDAQ", "SP500", "VIX") if c in df.columns]
    if len(cols) < 4:
        return None
    sub = df[cols].dropna()
    if len(sub) < 2:
        return None
    sub = sub.sort_values("Date").reset_index(drop=True)
    last, prev = sub.iloc[-1], sub.iloc[-2]
    return {
        "date": str(last["Date"]),
        "nasdaq_d1": round((float(last["NASDAQ"]) / float(prev["NASDAQ"]) - 1) * 100, 3),
        "sp500_d1": round((float(last["SP500"]) / float(prev["SP500"]) - 1) * 100, 3),
        "vix": round(float(last["VIX"]), 2),
        "vix_d1": round((float(last["VIX"]) / float(prev["VIX"]) - 1) * 100, 3),
    }


def _load_autodiscovery():
    return _read_json(AUTODISCOVERY)


def _load_risk_dashboard():
    return _read_json(RISK)


def _load_overreaction_signal():
    return _read_json(OVERREACTION_SIGNAL)


def _load_overreaction_full():
    return _read_json(OVERREACTION_FULL)


# ── 触发判定（机械·纯函数，方便单测直接打）───────────────────────────────
def check_trigger(market, vxsmh_close):
    """→ (triggered: bool, reasons: list[str])。任一条件为真即触发，原因可多条并存
    （如同日纳指标普都重跌）。vxsmh_close=None（数据源缺失/非 ok 状态）→ ②直接判不触发。"""
    reasons = []
    if market["nasdaq_d1"] <= THRESH_DROP_PCT:
        reasons.append(f"①纳指单日{market['nasdaq_d1']}%(≤{THRESH_DROP_PCT}%)")
    if market["sp500_d1"] <= THRESH_DROP_PCT:
        reasons.append(f"①标普单日{market['sp500_d1']}%(≤{THRESH_DROP_PCT}%)")
    if (vxsmh_close is not None and vxsmh_close >= THRESH_VXSMH
            and market["nasdaq_d1"] <= THRESH_VXSMH_NASDAQ_PCT):
        reasons.append(f"②VXSMH={vxsmh_close}(≥{THRESH_VXSMH})+纳指{market['nasdaq_d1']}%"
                       f"(≤{THRESH_VXSMH_NASDAQ_PCT}%)")
    if market["vix_d1"] >= THRESH_VIX_SPIKE_PCT:
        reasons.append(f"③VIX单日{market['vix_d1']:+.1f}%(≥+{THRESH_VIX_SPIKE_PCT}%)")
    return bool(reasons), reasons


def _family_survival(autodisc, families):
    """autodiscovery.json → (该族候选总数, verdict==survive 数)。诚实引用真实裁决，不重算。"""
    cands = (autodisc or {}).get("candidates") or []
    sub = [c for c in cands if c.get("family") in families]
    return len(sub), sum(1 for c in sub if c.get("verdict") == "survive")


def _downside_bin(vix_now, bins):
    """当前 VIX 落进 downside_by_vix 的哪个历史档位（vix_lo<=vix_now<=vix_hi）；
    越界（低于最低档/高于最高档）钳到最近的首/尾档——总能给条大致读数，不因边界值挂空。"""
    if not bins:
        return None
    for b in bins:
        try:
            if b["vix_lo"] <= vix_now <= b["vix_hi"]:
                return b
        except (TypeError, KeyError):
            continue
    if vix_now < bins[0].get("vix_lo", float("-inf")):
        return bins[0]
    return bins[-1]


# ── 账本（append-only·每自然日最多一行）─────────────────────────────────
def _already_logged_today(date_str, path=None):
    p = path or LOG
    if not p.exists():
        return False
    with open(p, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    return len(rows) > 1 and rows[-1][0] == date_str


def _append_row(date_str, reasons, market, vxsmh_close, pushed, path=None):
    p = path or LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(HEADER)
        w.writerow([date_str, "|".join(reasons), market["nasdaq_d1"], market["vix"],
                    vxsmh_close if vxsmh_close is not None else "", pushed])


def _send(text):
    """推送包装（独立函数便于测试 monkeypatch，同 ipo_alerts 惯例）。"""
    import notify_telegram
    return notify_telegram.send(text, tag="大跌简报")


# ── 消息组装（全部读现成真实字段，缺失就诚实标注"暂无数据"，绝不瞎编）──────
def _build_message(market, reasons, vxsmh, autodisc, risk, ovr_signal, ovr_full, run_date):
    import notify_telegram

    d = market["date"]
    lines = [f"📉 大跌日诚实数据包 · {run_date}（触发：{'、'.join(reasons)}）", ""]

    lines.append(f"【今日跌幅】{d} 纳指 {market['nasdaq_d1']:+.2f}% · 标普 {market['sp500_d1']:+.2f}% · "
                 f"VIX {market['vix']}（{market['vix_d1']:+.1f}%）")

    if vxsmh.get("status") == "ok":
        lines.append(f"【VXSMH半导体恐慌计】{vxsmh.get('date')} 读数 {vxsmh.get('close')}，"
                     f"发布以来（{vxsmh.get('launch_date')} 起 · {vxsmh.get('n_days')} 个交易日）"
                     f"分位 {vxsmh.get('pctile_since_launch')}%——史太短，纯描述、不进信号。")
    else:
        lines.append("【VXSMH半导体恐慌计】暂无数据。")

    ctx = (autodisc or {}).get("context_states") or {}
    idx = ctx.get("indices") or {}
    ctx_asof = ctx.get("asof", "未知")
    nq, sp = idx.get("nasdaq") or {}, idx.get("sp500") or {}
    streak_total, streak_survive = _family_survival(autodisc, STREAK_FAMILIES)
    lines.append(f"【连跌当前态】{ctx_asof} 纳指连跌 {nq.get('down_streak', '?')} 天 · "
                 f"标普连跌 {sp.get('down_streak', '?')} 天。"
                 f"历史检验：连跌N天本身无预测力（{streak_survive}/{streak_total} 过校正）。")

    trailing_total, trailing_survive = _family_survival(autodisc, TRAILING_FAMILIES)
    nq63 = (nq.get("trailing") or {}).get("63d") or {}
    sp63 = (sp.get("trailing") or {}).get("63d") or {}
    lines.append(f"【长跨度当前态】{ctx_asof} 纳指近63日收益处历史 {nq63.get('pctile', '?')} 分位"
                 f"（{nq63.get('zone', '?')}）· 标普 {sp63.get('pctile', '?')} 分位（{sp63.get('zone', '?')}）。"
                 f"同样（{trailing_survive}/{trailing_total} 过校正）。")

    if ovr_signal:
        today_o = ovr_signal.get("today") or {}
        ms = ovr_signal.get("modern_stat") or {}
        trig_txt = "已触发" if today_o.get("triggered") else "未触发"
        lines.append(f"【极端下跌次日分布】标普今日{trig_txt}其自身极端下跌阈值"
                     f"（现代段第{ovr_signal.get('q_pctile', '?')}百分位 {ovr_signal.get('threshold_pct', '?')}%）。"
                     f"历史上这类日子次日：现代段均值 {ms.get('bounce_next_pct', '?')}%"
                     f"（vs 平常 {ms.get('other_next_pct', '?')}%，p={ms.get('p_value', '?')}），"
                     f"约 {ms.get('pct_negative', '?')}% 的情况次日仍跌——非必涨。")
    else:
        lines.append("【极端下跌次日分布】暂无数据。")

    bins = (risk or {}).get("downside_by_vix") or []
    b = _downside_bin(market["vix"], bins)
    if b:
        horizon = (risk or {}).get("horizon", 20)
        lines.append(f"【条件下行】当前 VIX={market['vix']} 落入历史档位 "
                     f"[{b.get('vix_lo')}-{b.get('vix_hi')}]，该档过去{horizon}日收益的"
                     f"5%分位下行为 {b.get('downside_q05_pct')}%。")
    else:
        lines.append("【条件下行】暂无数据。")

    lines += ["", "以上=我们测过的全部相关规律·跌本身不是信号·非投资建议", ""]
    lines += notify_telegram.footer(extra="（大跌日数据包·事实通报·非信号非抄底建议·会错）").splitlines()
    return "\n".join(lines)


def run(push=True):
    """→ dict | None。见文件头：不满足触发条件/无数据 → 零行为；触发才可能落账+推送。"""
    market = _load_market()
    if market is None:
        print("[大跌简报] 无 combined_prices.csv 或有效交易日不足两天，跳过")
        return None

    risk = _load_risk_dashboard() or {}
    vxsmh = risk.get("vxsmh") or {}
    vxsmh_close = vxsmh.get("close") if vxsmh.get("status") == "ok" else None

    triggered, reasons = check_trigger(market, vxsmh_close)
    if not triggered:
        print(f"[大跌简报] {market['date']} 未触发"
              f"（纳指{market['nasdaq_d1']}% 标普{market['sp500_d1']}% VIX{market['vix_d1']:+.1f}%），跳过")
        return {"triggered": False}

    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    if _already_logged_today(today):
        print(f"[大跌简报] 今日（{today}）已处理过（账本已记，自然日限推一次），跳过")
        return {"triggered": True, "skipped_dup": True}

    # 未配置 token → 完全跳过（不落账不消费）：见文件头取舍（同 ipo_alerts）。
    # push=False（测试直调）不受此限。
    import os
    if push and not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
        print(f"[大跌简报] 触发（{'、'.join(reasons)}）但本环境未配置 TELEGRAM token"
              "——跳过（不落账），留给有 token 的环境推送")
        return {"triggered": True, "pushed": False, "skipped_no_token": True}

    autodisc = _load_autodiscovery() or {}
    ovr_signal = _load_overreaction_signal() or {}
    ovr_full = _load_overreaction_full() or {}

    text = _build_message(market, reasons, vxsmh, autodisc, risk, ovr_signal, ovr_full, today)
    ok = bool(push and _send(text))

    _append_row(today, reasons, market, vxsmh_close, ok)
    print(f"[OK] downturn_brief_log.csv — 触发（{'、'.join(reasons)}）"
          f"（{'已推送' if ok else '未推送(失败)·pushed=False 留痕'}）")
    return {"triggered": True, "pushed": ok}


if __name__ == "__main__":
    try:
        run()
    except Exception as e:                     # fail-soft：绝不阻断流水线
        print(f"[大跌简报] 异常（非致命，不阻断）: {type(e).__name__}: {e}")
    sys.exit(0)
