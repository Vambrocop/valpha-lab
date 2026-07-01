"""survivors_live.py — 存活规律观察台（把扛过多重检验的 FDR 存活规律，标出"今天是否应期"）。

autodiscovery 里 verdict=='survive' 的候选 = 在预声明候选池(命门)里扛过 BY-FDR + 现代子样本仍显著的
"存活规律"。它们大多不是每天成立：金叉看当前趋势、九月只在 9 月、回撤看当日大跌。本脚本：
  1. 读 autodiscovery.json 取 verdict=='survive'（历史 edge 数字直接复用、**不重算** → 单一真相源、不漂移）；
  2. 本地按各族**原定义**算"今天是否应期"（金叉 50>200 / BTC 20日动量>+5% / 纳指跌进最低5% / 当前是否 9 月）；
  3. 写 survivors_live.json（web+docs）：常驻清单 + 应期/休眠标记 → 喂 llm_daily_read 做诚实解读、给前端观察台展示。

诚实红线：仅描述性、非预测非荐股；「应期」=今天该条件成立、「休眠」=今天不成立(勿当当前信号)；
前向 OOS(门4)仍在累积、未确认；"扛过检验"≠"下次一定灵"；过去≠未来。数据/autodiscovery 缺失 → 优雅跳过(不阻断)。
"""
import json
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).parent
WEB = SCRIPTS.parent / "web"
RAW = SCRIPTS.parent / "data" / "raw"

BTC_MOM_THRESH = 0.05    # 与 signal_model.BTC_MOM_THRESH 对齐（BTC 20日动量 ±5% 触发）
REBOUND_PCTL = 5         # p5_h1_nasdaq：跌破全样本第 5 百分位
GOLDEN_MA = (50, 200)    # 金叉：50 日均线上穿 200 日均线


def _load_px(fname, floor):
    """读一列价 CSV → 升序正价 Series；行数不足 floor 返回 None。"""
    p = RAW / fname
    if not p.exists():
        return None
    try:
        s = pd.read_csv(p, index_col=0, parse_dates=True)
    except Exception:
        return None
    s = pd.to_numeric(s.iloc[:, 0], errors="coerce").dropna()
    s = s[s > 0].sort_index()
    return s if len(s) >= floor else None


# ── 各族"今天是否应期"（active, 当前态大白话）；无数据 → (None, 说明) ──────────────
def _golden_cross_state():
    px = _load_px("SP500_long.csv", GOLDEN_MA[1])
    if px is None:
        return None, "标普数据不足"
    ma_s = px.rolling(GOLDEN_MA[0]).mean().iloc[-1]
    ma_l = px.rolling(GOLDEN_MA[1]).mean().iloc[-1]
    if pd.isna(ma_s) or pd.isna(ma_l):
        return None, "均线未算出"
    active = bool(ma_s > ma_l)
    return active, ("标普 50 日均线高于 200 日均线（金叉成立·趋势向上）" if active
                    else "标普 50 日均线未高于 200 日均线（金叉未成立）")


def _btc_mom_state():
    px = _load_px("BTC.csv", 21)
    if px is None:
        return None, "BTC 数据不足"
    r20 = float(px.iloc[-1] / px.iloc[-21] - 1)      # pct_change(20)
    active = bool(r20 > BTC_MOM_THRESH)
    return active, f"BTC 近 20 日动量 {r20 * 100:+.1f}%（{'高于' if active else '未高于'} +5% 阈值）"


def _rebound_state():
    px = _load_px("NASDAQ_COMP_long.csv", 1000)
    if px is None:
        return None, "纳指数据不足"
    ret = px.pct_change().dropna()
    thr = float(np.percentile(ret.values, REBOUND_PCTL))
    last = float(ret.iloc[-1])
    active = bool(last <= thr)
    return active, (f"纳指最新日收益 {last * 100:+.1f}%"
                    f"（{'跌进' if active else '未跌进'}历史最低 5% 档 {thr * 100:.1f}%）")


def _september_state():
    m = datetime.date.today().month
    active = (m == 9)
    return active, f"当前 {m} 月（{'正是 9 月·应期' if active else '非 9 月'}）"


# (family, key) → (大白话名, 历史声明前缀, 当前态函数)
_DESCRIPTORS = {
    ("regime", "golden_cross_sp500"): (
        "标普金叉（50 日线上穿 200 日线）", "标普处于金叉时，标普未来 20 日", _golden_cross_state),
    ("factor", "BTC_mom20_pos"): (
        "BTC 20 日动量为正（风险偏好代理）", "BTC 近 20 日动量 >+5% 时，纳指未来 20 日", _btc_mom_state),
    ("rebound", "p5_h1_nasdaq"): (
        "纳指大跌后的次日走向", "纳指单日跌进历史最低 5% 后，次日", _rebound_state),
    ("calendar", "september_sp500"): (
        "标普九月效应", "9 月里，标普当日", _september_state),
    ("calendar", "monthof_9_sp500"): (
        "标普 9 月（机器枚举·另一口径）", "9 月里，标普当日", _september_state),
}


def _pick_window(cand):
    """取历史 edge 窗口：优先'2000后'(现代代表)，回退'完整'。返回 (up, base, label)。"""
    wins = {w.get("label"): w for w in cand.get("windows", [])}
    for lab in ("2000后", "完整"):
        w = wins.get(lab)
        if w and w.get("up_pct") is not None and w.get("base_pct") is not None:
            return w["up_pct"], w["base_pct"], lab
    return None, None, None


def _dnote(up, base):
    """方向标注（诚实：up<base=偏负，别按族名想当然）。"""
    if up is None or base is None:
        return "方向不明"
    d = up - base
    if d >= 5:
        return "明显偏正"
    if d >= 1:
        return "微弱偏正"
    if d <= -5:
        return "明显偏负"
    if d <= -1:
        return "微弱偏负"
    return "≈基率(几乎无差别)"


def build():
    try:
        ad = json.loads((WEB / "autodiscovery.json").read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[survivors_live] 读 autodiscovery.json 失败，跳过: {e}")
        return None
    survivors = [c for c in ad.get("candidates", []) if c.get("verdict") == "survive"]
    rows = []
    for c in survivors:
        fam, key = c.get("family"), c.get("key")
        up, base, wlabel = _pick_window(c)
        dnote = _dnote(up, base)
        desc = _DESCRIPTORS.get((fam, key))
        if desc:
            name, claim, fn = desc
            active, state = fn()
        else:                                        # 未来新存活规律：不落下、也不谎报应期
            name, claim, active, state = f"{fam}/{key}", "", None, "当前态未接入(新存活规律)"
        edge_plain = (f"{claim}上涨率 {up}% vs 基率 {base}%（{wlabel}·{dnote}）"
                      if up is not None and base is not None else "历史 edge 数据缺失")
        rows.append({
            "family": fam, "key": key, "name": name,
            "active": active, "state": state,
            "up_pct": up, "base_pct": base, "window": wlabel, "dnote": dnote,
            "edge_plain": edge_plain,
            "recent_p": c.get("recent_p"), "modern": c.get("modern_status"),
        })

    def _sortkey(x):                                 # 应期在前；同类按历史 |edge| 大的在前
        act = 0 if x["active"] is True else (1 if x["active"] is False else 2)
        mag = -abs((x["up_pct"] or 0) - (x["base_pct"] or 0))
        return (act, mag)

    rows.sort(key=_sortkey)
    n_active = sum(1 for x in rows if x["active"] is True)
    return {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": datetime.date.today().isoformat(),
        "n_survivors": len(rows), "n_active": n_active, "survivors": rows,
        "caveat": "存活规律 = 在预声明候选池里扛过多重检验(BY-FDR)且现代子样本仍显著的历史规律。"
                  "仅描述性、非预测非荐股；「应期」=今天该条件成立、「休眠」=今天不成立(休眠的别当当前信号)；"
                  "前向 OOS(门4)仍在累积、未确认；扛过检验≠下次一定灵；过去≠未来。",
    }


def run(write=True):
    out = build()
    if out is None:
        return None
    if write:
        from util_io import write_json
        write_json("survivors_live.json", out)
        print(f"[OK] survivors_live.json — {out['n_survivors']} 条存活规律 · 今日应期 {out['n_active']} 条")
        for s in out["survivors"]:
            flag = "应期" if s["active"] is True else ("休眠" if s["active"] is False else "未接入")
            print(f"    [{flag}] {s['name']} · {s['state']}")
    return out


if __name__ == "__main__":
    run()
