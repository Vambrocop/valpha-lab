"""oos_gate.py — 自生长闭环 P-A「门4：样本外(OOS)确认引擎」。

只认每个候选 **注册锚点(declared_date)之后** 的数据是否仍成立——锚点一旦写下不可回改
(candidate_registry append-only) → 物理上没法事后挪靶。复用 autodiscovery 的**同一效应定义**
(命门:OOS 与裁决永不漂移)，按族 floor 语义不同(§10)：
  · calendar：floor **输入** ret(日历无前看依赖) → 月/年频不会有'锚当期 bar 含锚前数据'的边界泄漏。
  · rebound ：阈值=**全样本**百分位(规则定义于全数据) → 只把 (sel,y) 滤到锚后，**绝不**重算阈值。
  · regime  ：均线(50/200)用**全 px** 算 → 只把 (cond,fwd) 滤到锚后，**绝不**在锚后重启均线。
  · factor  ：OOS 待接(§10)，暂全记"未到可判"(不影响:今日全候选锚=注册日、锚后空)。
  · streak  ：runlen(游程)本身是纯回看统计=天然点时间 → 只把 (idx,sel,y) 滤到锚后，
    **绝不**在锚后重启游程计算(2026-07-10·SPEC_STREAK_FAMILY.md)。
  · trailing_extreme：PIT expanding 分位本身即纯回看统计(命门1·t 处分位只用 t 及之前) = 天然点
    时间，与 streak/positioning 同一模式 → 只把 (idx,sel,y) 滤到锚后，**绝不**在锚后重算分位；
    block 用与 discovery 同一 hold+TRAILING_BLOCK_EXTRA 公式/常量(2026-07-11·stage4 真统计)。

三态 + 滞回(防 chatter)：confirmed(方向同 ∧ oos_p<0.10) / overturned(方向反号 OR oos_p>0.20) /
neutral(同向但 0.10–0.20·持中不动) / pending(锚后样本不足 = **未到可判**·一等公民，绝不凑结论)。

本文件只算 OOS 裁决，**不写任何账本**(晋升/降级写库在 knowledge_base.py，单独审)。
"""
import hashlib
import numpy as np
import pandas as pd

import autodiscovery as ad
import placebo_test as pb
import candidate_space as cs
import candidate_registry
from walk_forward import block_bootstrap_diff

PENDING, CONFIRMED, OVERTURNED, NEUTRAL = "pending", "confirmed", "overturned", "neutral"
CONFIRM_P, OVERTURN_P = 0.10, 0.20          # 滞回:confirm 阈 < overturn 阈 → FDR 边界候选不来回翻烧饼
MIN_OOS_N = pb.MIN_GROUP_N                   # 锚后触发组 < 此 → 未到可判(沿用现有检验力下限 30)


def _sign(x):
    """方向号：+1 / -1 / 0(无方向)。None、**NaN**、近零都归 0。

    NaN 必须显式归 0(2026-09-16 独立审规格发现)：空或退化的观测窗会让 `mean()` 出 NaN，
    而旧写法 `0 if (x is None or abs(float(x)) < 1e-12) else (1 if x > 0 else -1)` 里
    `abs(nan) < 1e-12` 为 False、`nan > 0` 也为 False → **静默落 -1**，
    等于给一个根本没有数据的候选**编出一个"看跌"方向号**，并且会随 `full_sign`
    进公开 JSON、再被 `_classify` 当成既定假说方向去判 confirmed/overturned。
    本机 `vix_backwardation` 的可观测行数=0(VIX3M 历史损坏)时就会命中这条路径。
    """
    if x is None:
        return 0
    x = float(x)
    if x != x or abs(x) < 1e-12:      # x != x 即 NaN
        return 0
    return 1 if x > 0 else -1


def _classify(full_sign, oos_sign, oos_p):
    """三态裁决(滞回)。full_sign=None=无方向(omnibus·如周几/月份)→只看 p；有向则先判方向反号。"""
    if oos_p is None:
        return PENDING
    if full_sign is None:                    # omnibus 无单一方向 → 只问"锚后是否仍可测到结构"
        if oos_p < CONFIRM_P:
            return CONFIRMED
        if oos_p > OVERTURN_P:
            return OVERTURNED
        return NEUTRAL
    if oos_sign != full_sign:                # 方向反号 → 翻盘(§10:overturn = 反号 OR p>0.20)
        return OVERTURNED
    if oos_p < CONFIRM_P:
        return CONFIRMED
    if oos_p > OVERTURN_P:                    # 同向但 p 大 = 已淡 → 也算 overturn(喂滞回/降级)
        return OVERTURNED
    return NEUTRAL


def _oos_seed(cid):
    """块自助稳定整数种子(与 autodiscovery 的 perm 种子不同命名空间，可复现)。"""
    return int(hashlib.sha1((cid + "|oos").encode()).hexdigest()[:8], 16)


# 注:full_sign 故意取**全样本**方向 = 候选注册时的既定假说方向（不 floor 到锚后）。OOS 检验问的是
# "锚后数据是否**独立**地仍朝这个既定方向、且显著"——oos_p/oos_sign 才只用锚后数据。别把 full_sign 也 floor。
def _result(cand, anchor, status, *, oos_n=0, n_ctrl=None, oos_p=None, oos_sign=None,
            full_sign=None, note=""):
    return {"candidate_id": cand["candidate_id"], "key": cand["key"], "family": cand["family"],
            "anchor_date": anchor, "oos_status": status, "oos_n": int(oos_n),
            "oos_p": (None if oos_p is None else round(float(oos_p), 6)),
            "oos_sign": (None if oos_sign is None else int(oos_sign)),
            "full_sign": (None if full_sign is None else int(full_sign)),
            # n_ctrl:锚后**对照组**样本数。"触发组够了但对照组不够"和"两边都不够"是两种完全
            # 不同的处境:前者**光等不一定来**(得等条件真的转向),后者攒时间就行。
            # 只报 oos_n 看不出区别 —— 线上 golden_cross 就是这么被说错的。
            "n_ctrl": (None if n_ctrl is None else int(n_ctrl)),
            "note": note}


# ── 日历族：floor 输入 ret(§10) → 锚后重抽 vals/lab；方向型比 mean(lab1)-mean(lab0) 的符号 ──
def _calendar_oos(cand, anchor):
    eff, index, cid = cand["params"]["effect"], cand["params"]["index"], cand["candidate_id"]
    full = ad._calendar_arrays(eff, index)
    if full is None:
        return _result(cand, anchor, PENDING, note="全样本不足")
    vf, lf, _idx, _stat, directional = full
    full_sign = _sign(vf[lf == 1].mean() - vf[lf == 0].mean()) if directional else None
    # S3:基于硬编码日期表的效应(pre_fomc)——若表里最后一个会议日 <= 锚点，锚后区间**永远**不会有触发，
    #     是"结构性饥饿"(需扩表)，而非"引擎刚起步样本少"。**提前**明说，否则永久 pending 会被误读为引擎卡住。
    if eff == "pre_fomc":
        from fomc_dates import load_fomc_dates
        last = max(load_fomc_dates())
        if last <= pd.Timestamp(anchor):
            return _result(cand, anchor, PENDING, full_sign=full_sign,
                           note=f"锚后无已登记 FOMC 会议(fomc_dates 止于 {last.date()}·需补未来日程,OOS 才会累积)")
    oos = ad._calendar_arrays(eff, index, floor=anchor)         # 命门:floor 输入,月/年频无边界泄漏
    if oos is None:
        return _result(cand, anchor, PENDING, full_sign=full_sign, note="锚后样本不足(<1000日)")
    vo, lo, _io, stat_o, _d = oos
    labs, counts = np.unique(lo, return_counts=True)
    if len(labs) < 2 or counts.min() < MIN_OOS_N:
        # 同上:说清是哪一组、各多少。只剩单一标签时最该讲明白(那是"锚后从未出现过反面")。
        if len(labs) < 2:
            only = int(labs[0]) if len(labs) else None
            note = f"锚后只出现单一标签(label={only})→ 无对照组,无法比较(需两组各 ≥{MIN_OOS_N})"
            nmin = int(counts.min()) if len(counts) else 0
        else:
            pairs = " / ".join(f"label{int(l)}={int(c)}" for l, c in zip(labs, counts))
            note = f"锚后分组样本不足:{pairs}(各需 ≥{MIN_OOS_N})"
            nmin = int(counts.min())
        return _result(cand, anchor, PENDING, oos_n=nmin, full_sign=full_sign, note=note)
    oos_p = pb.perm_test(vo, lo, stat_o, np.random.default_rng(_oos_seed(cid)))["p_value"]
    if np.isnan(oos_p):
        return _result(cand, anchor, PENDING, oos_n=int(counts.min()),
                       full_sign=full_sign, note="锚后 p 不可算(单标签组)")
    oos_sign = _sign(vo[lo == 1].mean() - vo[lo == 0].mean()) if directional else None
    status = _classify(full_sign, oos_sign, oos_p)
    return _result(cand, anchor, status, oos_n=int(counts.min()), oos_p=oos_p,
                   oos_sign=oos_sign, full_sign=full_sign)


# ── 反弹/体制族：阈值/均线用全样本算(§10) → 只把 (sel,y) 滤到锚后；方向=锚后 up率差符号 ──
def _diff_oos(cand, anchor, arr, *, block):
    if arr is None:
        return _result(cand, anchor, PENDING, note="全样本不足")
    idx, sel, y = arr
    full_sign = _sign(y[sel].mean() - y.mean())
    mask = np.asarray(idx > pd.Timestamp(anchor))
    sel_o, y_o = sel[mask], y[mask]
    n_trig = int(sel_o.sum())
    n_ctrl = int((~sel_o).sum())
    # 2026-09-14 修:原来两个条件共用一句"锚后触发组样本不足",**会说错话**。
    # 实证:线上 golden_cross_sp500 的 oos_n=33(≥30)却挂着"触发组样本不足" ——
    # 真正缺的是**对照组**(锚点后金叉一天没断过,n_ctrl=0,没有"不成立"的日子可比)。
    # 这个区别决定"等下去有没有用":触发组不足=攒时间就行;对照组不足=**得等条件真的转向**。
    if n_trig < MIN_OOS_N or n_ctrl < MIN_OOS_N:
        which = ("触发组与对照组都不足" if n_trig < MIN_OOS_N and n_ctrl < MIN_OOS_N
                 else ("触发组不足" if n_trig < MIN_OOS_N
                       else "**对照组**不足(条件在锚后几乎一直成立→无可比的反面样本)"))
        return _result(cand, anchor, PENDING, oos_n=n_trig, n_ctrl=n_ctrl, full_sign=full_sign,
                       note=f"锚后{which}:触发 {n_trig} / 对照 {n_ctrl}(各需 ≥{MIN_OOS_N})")
    bb = block_bootstrap_diff(sel_o, y_o, block=block, seed=_oos_seed(cand["candidate_id"]))
    if bb is None:
        return _result(cand, anchor, PENDING, oos_n=n_trig, full_sign=full_sign, note="锚后自助不可算")
    # S1:oos_sign 取**未舍入**原始差(与 full_sign 同尺度)；bb["diff"] 已 round 到 0.01pp,近零会假翻号
    oos_sign = _sign(y_o[sel_o].mean() - y_o.mean())
    status = _classify(full_sign, oos_sign, bb["p_boot"])
    return _result(cand, anchor, status, oos_n=n_trig, oos_p=bb["p_boot"],
                   oos_sign=oos_sign, full_sign=full_sign)


def _rebound_oos(cand, anchor):
    p = cand["params"]
    return _diff_oos(cand, anchor, ad._rebound_arrays(p["pctl"], p["hold"], p["index"]), block=p["hold"])


def _regime_oos(cand, anchor):
    p = cand["params"]
    return _diff_oos(cand, anchor, ad._regime_arrays(p["signal"], p["index"], 20), block=20)


# ── 仓位族(COT)/期权情绪族(P/C) OOS：阈值(滚动分位/滚动z)本身就是纯回看统计=天然点时间，
#   比 rebound 的"全样本阈值"更干净——只把 (idx,sel,y) 滤到锚后，**绝不**在锚后重算阈值/滚动窗。
#   命门(§10 定稿)：positioning block 与 discovery(autodiscovery._positioning_block)同一放大公式，
#   两处必须一致，否则 discovery 与 OOS 用不同块长=同一效应两套显著性口径，自相矛盾。
def _positioning_oos(cand, anchor):
    p = cand["params"]
    arr = ad._positioning_arrays(p["market"], p["series"], p["extreme"], p["hold"])
    return _diff_oos(cand, anchor, arr, block=ad._positioning_block(p["hold"]))


def _optsent_oos(cand, anchor):
    p = cand["params"]
    arr = ad._optsent_arrays(p["series"], p["extreme"], p["hold"])
    return _diff_oos(cand, anchor, arr, block=p["hold"])         # 尖峰型 sel → block=hold 不放大


# ── 连跌族(streak) OOS：事件型 sel，阈值(runlen)本身就是纯回看统计=天然点时间，只把 (idx,sel,y)
#   滤到锚后，**绝不**在锚后重启游程计算(与 rebound/regime 同一"§10 命门"模式)。block=hold(§1)。
def _streak_oos(cand, anchor):
    p = cand["params"]
    arr = ad._streak_arrays(cand["family"], p["n"], p["hold"], p["index"])
    return _diff_oos(cand, anchor, arr, block=p["hold"])


# ── 长跨度反转/延续族(trailing_extreme) OOS：PIT expanding 分位天然点时间(命门1)，只把
#   (idx,sel,y) 滤到锚后，绝不在锚后重算分位；block 与 discovery(autodiscovery._trailing_extreme_block)
#   同一 hold+TRAILING_BLOCK_EXTRA 公式/常量(B1:两处必须一致，见 SPEC §5.4)。
def _trailing_extreme_oos(cand, anchor):
    p = cand["params"]
    arr = ad._trailing_extreme_arrays(p["n"], p["hold"], p["index"], p["side"])
    return _diff_oos(cand, anchor, arr, block=ad._trailing_extreme_block(p["hold"]))


def oos_verdict(cand, anchor):
    """单候选 OOS 门4 裁决 → dict(oos_status/oos_n/oos_p/oos_sign/full_sign/...)。"""
    if anchor is None:
        return _result(cand, None, PENDING, note="未注册(无锚点·不可定 OOS)")
    fam = cand["family"]
    if fam == "calendar":
        return _calendar_oos(cand, anchor)
    if fam == "rebound":
        return _rebound_oos(cand, anchor)
    if fam == "regime":
        return _regime_oos(cand, anchor)
    if fam == "positioning":                 # H-1 BLOCKER:必须显式路由，绝不落 else→"因子族待接"误导 note
        return _positioning_oos(cand, anchor)
    if fam == "options_sentiment":           # H-1 BLOCKER:同上
        return _optsent_oos(cand, anchor)
    if fam in ("streak_down", "streak_break"):   # H-1 BLOCKER:同上(2026-07-10 stage2)
        return _streak_oos(cand, anchor)
    if fam == "trailing_extreme":            # H-1 BLOCKER:同上(2026-07-11 stage4 真统计接线)
        return _trailing_extreme_oos(cand, anchor)
    if fam == "factor":
        return _result(cand, anchor, PENDING, note="因子族 OOS 待接(§10)")
    raise ValueError(f"oos_verdict: 未路由的 family={fam!r}"
                      "(H-1 反退化:新族必须显式接线，不许静默落 pending)")


def run_gate(candidates=None, anchors=None):
    """对全部候选跑门4 → list[verdict]。anchors 缺省读 candidate_registry(append-only 锚点)。"""
    candidates = candidates if candidates is not None else cs.enumerate_candidates()
    anchors = anchors if anchors is not None else candidate_registry.load_anchors()
    return [oos_verdict(c, anchors.get(c["candidate_id"])) for c in candidates]


def summarize(verdicts):
    def cnt(s):
        return sum(1 for v in verdicts if v["oos_status"] == s)
    return {"n": len(verdicts), "pending": cnt(PENDING), "confirmed": cnt(CONFIRMED),
            "overturned": cnt(OVERTURNED), "neutral": cnt(NEUTRAL)}


if __name__ == "__main__":
    vs = run_gate()
    s = summarize(vs)
    print(f"[OK] oos_gate — 候选 {s['n']} | 确认 {s['confirmed']} · 翻盘 {s['overturned']} · "
          f"持中 {s['neutral']} · 未到可判 {s['pending']}")
    for v in vs:
        if v["oos_status"] != PENDING:
            print(f"  {v['oos_status']:10s} {v['key']:24s} oos_n={v['oos_n']} oos_p={v['oos_p']} "
                  f"sign {v['full_sign']}→{v['oos_sign']}")
