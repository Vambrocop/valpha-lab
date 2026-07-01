"""survivors_live.py — 存活规律观察台（把扛过多重检验的 FDR 存活规律，标出"今天是否应期"）。

autodiscovery 里 verdict=='survive' 的候选 = 在预声明候选池(命门)里扛过 BY-FDR + 现代子样本仍显著的
"存活规律"。它们大多不是每天成立：金叉看当前趋势、九月只在 9 月、回撤看当日大跌。本脚本：
  1. 读 autodiscovery.json 取 verdict=='survive'（历史 edge 数字直接复用、**不重算** → 单一真相源、不漂移）；
  2. 本地按各族**原定义**算"今天是否应期"（金叉 50>200 / BTC 20日动量±5% / 纳指跌进最低5% / 纳指>200日线 / 月份等）；
  3. 写 survivors_live.json（web+docs）：常驻清单 + 应期/休眠标记 → 喂 llm_daily_read 做诚实解读、给前端观察台展示。

**方向诚实命门**：autodiscovery 的窗口口径是 `up_pct = label==1(触发组) 上涨率`、`base_pct = label==0(对照组)`。
对"先验说某期偏弱"的日历效应(九月/世界杯年/sell-in-may)，`label==1` 是**相反的强组**(非九月/非杯年/冬季)——
所以每条描述符显式记 `触发组/对照组`，edge 永远把 up 挂到真实触发组，**绝不**想当然按族名把 up 当成"该条件本身"。

诚实红线：仅描述性、非预测非荐股；「应期」=今天该条件成立、「休眠」=今天不成立(勿当当前信号)、「未接入」=当前态未监测(仅历史)；
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

try:                                     # 单一真相源：BTC 动量阈值与生产对齐(改上游自动传导)
    from signal_model import BTC_MOM_THRESH
except Exception:
    BTC_MOM_THRESH = 0.05
REBOUND_PCTL = 5         # p5_h1_nasdaq：跌破全样本第 5 百分位(与 candidate_space 一致)
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


def _btc_r20():
    """BTC 20 日动量 pct_change(20)；无数据 None。"""
    px = _load_px("BTC.csv", 21)
    if px is None:
        return None
    return float(px.iloc[-1] / px.iloc[-21] - 1)


def _btc_mom_pos_state():
    r = _btc_r20()
    if r is None:
        return None, "BTC 数据不足"
    return bool(r > BTC_MOM_THRESH), f"BTC 近 20 日动量 {r * 100:+.1f}%（{'高于' if r > BTC_MOM_THRESH else '未高于'} +5% 阈值）"


def _btc_mom_neg_state():
    r = _btc_r20()
    if r is None:
        return None, "BTC 数据不足"
    return bool(r < -BTC_MOM_THRESH), f"BTC 近 20 日动量 {r * 100:+.1f}%（{'低于' if r < -BTC_MOM_THRESH else '未低于'} -5% 阈值）"


def _nasdaq_ma200_state():
    px = _load_px("NASDAQ_COMP_long.csv", 200)
    if px is None:
        return None, "纳指数据不足"
    ma200 = px.rolling(200).mean().iloc[-1]
    if pd.isna(ma200):
        return None, "均线未算出"
    active = bool(px.iloc[-1] > ma200)
    return active, f"纳指最新收盘{'高于' if active else '不高于'} 200 日均线"


def _rebound_state():
    px = _load_px("NASDAQ_COMP_long.csv", 1000)
    if px is None:
        return None, "纳指数据不足"
    ret = px.pct_change().dropna()
    thr = float(np.percentile(ret.values, REBOUND_PCTL))   # hold=1 → 与 autodiscovery 阈值仅差末 1 行(§审#3·可忽略)
    last = float(ret.iloc[-1])
    active = bool(last <= thr)
    return active, (f"纳指最新日收益 {last * 100:+.1f}%"
                    f"（{'跌进' if active else '未跌进'}历史最低 5% 档 {thr * 100:.1f}%）")


def _september_state():
    m = datetime.date.today().month
    active = (m == 9)
    return active, f"当前 {m} 月（{'正是 9 月·应期' if active else '非 9 月'}）"


def _world_cup_state():
    today = datetime.date.today()
    summer = today.month in (6, 7, 8)                      # 效应只作用于夏季(6-8月)
    try:
        from seasonality import WORLD_CUP_YEARS            # 单一来源,与 autodiscovery 同表不漂移
        wc = today.year in WORLD_CUP_YEARS
        yr = "世界杯年" if wc else "非世界杯年"
    except Exception:
        yr = "年份未知"
    return summer, f"当前 {today.month} 月（{'夏季·应期' if summer else '非夏季'}）·{today.year} 按年份表为{yr}"


# (family, key) → dict(name 大白话名, trigger label==1 触发组, rest label==0 对照组, horizon 视野, state 当前态函数)
#   edge 恒为 "{trigger} up% vs {rest} base%"——up 永远是 label==1 触发组(见 autodiscovery `_cal_windows` l==1)，方向不反。
_DESCRIPTORS = {
    ("regime", "golden_cross_sp500"): dict(
        name="标普金叉（50 日线上穿 200 日线）", trigger="标普金叉成立时", rest="未成立",
        horizon="标普未来 20 日", state=_golden_cross_state),
    ("factor", "BTC_mom20_pos"): dict(
        name="BTC 20 日动量为正（风险偏好代理）", trigger="BTC 动量 >+5% 时", rest="其余日",
        horizon="纳指未来 20 日", state=_btc_mom_pos_state),
    ("factor", "BTC_mom20_neg"): dict(
        name="BTC 20 日动量为负（风险偏好走弱）", trigger="BTC 动量 <-5% 时", rest="其余日",
        horizon="纳指未来 20 日", state=_btc_mom_neg_state),
    ("factor", "NASDAQ_above_ma200"): dict(
        name="纳指在 200 日线上方（趋势）", trigger="纳指收盘 >200 日线时", rest="200 日线下方",
        horizon="纳指未来 20 日", state=_nasdaq_ma200_state),
    ("rebound", "p5_h1_nasdaq"): dict(
        name="纳指大跌后的次日走向", trigger="纳指跌进历史最低 5% 的大跌日", rest="其余日",
        horizon="次日", state=_rebound_state),
    ("calendar", "september_sp500"): dict(    # 先验:九月最弱 → label==1=非九月(强组);别把 up 当成九月!
        name="标普九月效应（九月历史最弱月）", trigger="非九月", rest="九月",
        horizon="当日", state=_september_state),
    ("calendar", "monthof_9_sp500"): dict(    # 机器枚举:label==1=九月本身
        name="标普 9 月（机器枚举·另一口径）", trigger="九月", rest="其余月份",
        horizon="当日", state=_september_state),
    ("calendar", "world_cup_year_nasdaq"): dict(  # 先验:杯年夏季分心偏弱 → label==1=非杯年夏季(强组)
        name="纳指世界杯年夏季效应（分心先验）", trigger="非世界杯年的夏季", rest="世界杯年夏季",
        horizon="当日", state=_world_cup_state),
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
    """方向标注(诚实：按 up-base 符号，绝不按族名想当然)。up=触发组(label==1) 上涨率。"""
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


def _edge_plain(desc, up, base, window, dnote):
    """历史 edge 大白话。desc 缺失(未接入新存活规律)→ 用 autodiscovery 中性口径'触发组 vs 基率'，绝不猜组名。"""
    if up is None or base is None:
        return "历史 edge 数据缺失"
    if desc is None:
        return f"触发组 {up}% vs 基率 {base}%（{window}·{dnote}·组别待接入）"
    return f"{desc['trigger']} {up}% vs {desc['rest']} {base}%（{desc['horizon']}上涨率·{window}·{dnote}）"


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
            active, state = desc["state"]()
            name = desc["name"]
        else:                                        # 未来新存活规律：不落下、不谎报应期、不猜方向组名
            active, state, name = None, "当前态未接入监测（仅历史·今日不判应期）", f"{fam}/{key}"
        rows.append({
            "family": fam, "key": key, "name": name,
            "active": active, "state": state,
            "up_pct": up, "base_pct": base, "window": wlabel, "dnote": dnote,
            "edge_plain": _edge_plain(desc, up, base, wlabel, dnote),
            "recent_p": c.get("recent_p"), "modern": c.get("modern_status"),
        })

    def _sortkey(x):                                 # 应期在前→休眠→未接入；同类按历史 |edge| 大的在前
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
                  "仅描述性、非预测非荐股；「应期」=今天该条件成立、「休眠」=今天不成立(休眠的别当当前信号)、"
                  "「未接入」=当前态未监测(仅历史)；前向 OOS(门4)仍在累积、未确认；扛过检验≠下次一定灵；过去≠未来。",
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
            print(f"           {s['edge_plain']}")
    return out


if __name__ == "__main__":
    run()
