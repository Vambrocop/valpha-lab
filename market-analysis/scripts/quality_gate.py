"""quality_gate.py — v1.5 自生长 Phase 1：候选裁决引擎（双栏 FDR + 三态，焊进 p-hacking 护栏）。

输入 results[]：每项 dict 至少 {candidate_id, family, p}；可选 {recent_p, recent_powered(默认True)}。
原地加裁决字段并返回。

护栏（命门）：
  ① **分母完整性**——给 expect_n 则断言 len(results)==expect_n（防漏算/偷加分母；FDR 用全部 p，禁预筛）。
  ② **双栏 BY-FDR（🔴-A 用户拍板）**：survive_family（族内池化）+ survive_cross（跨族池化，**诚实头条**）。
     保留"族内成立 vs 全局最严校正后存活"两层，不让候选膨胀把信息一刀切没。
  ③ **三态 verdict**：survive(跨族存活∧现代仍有效) / faded(全段过跨族FDR但现代淡,疑被套利) /
     dead(未过跨族FDR) / inconclusive(现代检验力不足→absence of evidence ≠ evidence of absence)。

复用 stats_util.by_reject（任意相关稳健，与全站 fdr_crossfamily 同一来源），不重写校正。
Phase 1 只做裁决（输入 p 已算好）；候选→p 的数据路由（placebo/bootstrap/segment）在 Phase 1b。
门4 样本外（walk-forward）亦待 Phase 1b 接入。
"""
from stats_util import by_reject, bh_reject

Q_DEFAULT = 0.10
RECENT_ALPHA = 0.10   # 现代段显著阈（与 factor_pruning._segment_lens 一致）


def adjudicate(results, q=Q_DEFAULT, expect_n=None):
    n = len(results)
    if expect_n is not None and n != expect_n:
        raise ValueError(f"分母不完整：results {n} ≠ 预声明 {expect_n}（禁漏算/预筛 = p-hacking）")
    if n == 0:
        return results

    pvals = [float(r["p"]) for r in results]
    cross_rej, _c_m = by_reject(pvals, q)       # 跨族 BY（头条）
    cross_bh = bh_reject(pvals, q)              # 跨族 BH（乐观对照）

    # 族内 BY（每族单独池化）——双栏的"族内"列
    fam_idx = {}
    for i, r in enumerate(results):
        fam_idx.setdefault(r["family"], []).append(i)
    fam_rej = set()
    for idxs in fam_idx.values():
        sub_rej, _ = by_reject([pvals[i] for i in idxs], q)
        fam_rej.update(idxs[k] for k in sub_rej)

    for i, r in enumerate(results):
        sc = i in cross_rej
        r["survive_cross"] = sc
        r["survive_cross_bh"] = i in cross_bh
        r["survive_family"] = i in fam_rej
        # 现代段三态
        powered = r.get("recent_powered", True)
        rp = r.get("recent_p")
        if not powered:
            r["modern_status"] = "现代检验力不足"
        elif rp is not None and rp < RECENT_ALPHA:
            r["modern_status"] = "现代仍有效"
        elif sc or pvals[i] < q:
            r["modern_status"] = "现代已淡"
        else:
            r["modern_status"] = "现代无边际"
        # 总裁决（Phase 1：跨族 FDR + 现代段；门4 OOS 待 Phase 1b）
        if not powered:
            r["verdict"], r["reason"] = "inconclusive", "现代段检验力不足"
        elif sc and r["modern_status"] == "现代仍有效":
            r["verdict"], r["reason"] = "survive", ""
        elif sc:
            r["verdict"], r["reason"] = "faded", "全段过跨族FDR但现代段已淡(疑被套利)"
        else:
            r["verdict"], r["reason"] = "dead", "未过跨族 BY-FDR"
    return results


# ══════════════════════════════════════════════════════════════════════════
# 裁决的蒙特卡洛稳定性（SPEC_MC_RESOLUTION Part B/C · 2026-09-16）
#
# 要回答的问题不是"p 还有效吗"，而是
#   **「有限次重采样得到的这个裁决，和 B=∞ 的理想裁决一致吗？不一致的风险多大？」**
# 这是 sequential Monte Carlo test 的标准口径（Besag & Clifford 1991；
# Gandy 2009 的 uniformly bounded resampling risk；多重检验版本 = MMCTest）。
#
# 为什么**不能**用「p 离自己的 FDR 临界值几个标准误」当判据（规格 B2，三条实证）：
#   ① BY 是 step-up：一条被拒 ⟺ 它的 rank ≤ k，而 k 由**最大**的那个 i 决定
#      → 低 rank 候选的个体比较 `p_i vs c_i` 根本不是它的约束；
#   ② 两个估计器在下限附近都有 SE ≈ p，于是该判据在关键区间**退化成恒真**
#      （实测 Z=2.0 会把全部 14 条拒绝项一条不漏地选中 —— 那不是"边界带"，是"全选"）；
#   ③ `c_i` 在并列组内由**枚举顺序**决定（稳定排序）→ 发布"余量几个 SE"等于
#      发布一个取决于候选枚举顺序的数字。实测打乱输入顺序后某条的 c_i 变了一个数量级。
#   而且它会把**最稳**的一条永久标成"分辨不了"：`p5_h1_nasdaq` 在 B=20000 下仍 X=0，
#   可它 rank=1，是最不可能被噪声改判的一条（实测 84% 的重抽里还在名单上）——
#   给最强的证据挂"无法分辨"的牌子 = 把证据说得比实际**弱**，同样是最重缺陷类型。
#
# 所以直接**模拟 step-up 本身**：重抽 MC 计数 → 重跑 adjudicate → 数改判频率。
# 天然不受并列顺序影响、天然对 step-up 正确、天然覆盖 modern 阈值（同一次 adjudicate 里）。
_MC_SEED = 20260916          # 固定（规格 D4）：产物要可复现；抖动靠**报出来**，不靠随机化掩盖


def _resample_p(rng, mc):
    """按原始计数的后验重抽一个 p。mc=None（根本没跑过统计）→ None = 不施噪。

    θ* ~ Beta(X+½, n−X+½)（Jeffreys 先验，X=0 时后验最宽 —— 正是下限组该有的不确定度）
    X* ~ Binom(n, θ*) → 按该估计器自己的公式重建 p。
    """
    if not mc:
        return None
    x, n, kind = mc["mc_x"], mc["mc_n"], mc["mc_kind"]
    theta = rng.beta(x + 0.5, n - x + 0.5)
    xs = int(rng.binomial(n, theta))
    return min(1.0, 2.0 * xs / n) if kind == "bootstrap" else min(1.0, (xs + 1) / (n + 1))


def change_probabilities(results, q=Q_DEFAULT, K=2000, seed=_MC_SEED):
    """每条候选的「换个 MC 种子会不会改判」概率 + 整体稳定性摘要。

    **不重跑任何自助/置换** —— 只重抽已经存下的计数、重跑 `adjudicate`，纯算术。
    这是它能进 CI 守门的前提（对比：真换种子重跑 compute_results 要 N×2 分钟，只能离线）。

    要求 results 已带 `mc` / `mc_recent`（见 stats_util.mc_meta）。
    `mc` 缺失的候选按"无噪声"处理（它压根没跑统计，p 是硬编码的 1.0）。

    返回 (probs, summary)：
      probs[key] = {"change_prob", "survive_prob", "verdict_dist"}
      summary    = {"K", "mean_changes", "median_changes", "p90_changes", "max_changes",
                    "published_set_prob"(已发布存活集原样复现的比例), "n_resampled"}
    """
    import numpy as np
    base = {r["key"]: r.get("verdict") for r in results}
    pub_surv = frozenset(k for k, v in base.items() if v == "survive")
    rng = np.random.default_rng(seed)
    n_chg, surv, dist = {k: 0 for k in base}, {k: 0 for k in base}, {k: {} for k in base}
    changes, set_hits = [], 0
    for _ in range(K):
        rows = []
        for r in results:
            p_s = _resample_p(rng, r.get("mc"))
            rp_s = _resample_p(rng, r.get("mc_recent"))
            rows.append({**r,
                         "p": r["p"] if p_s is None else p_s,
                         "recent_p": r.get("recent_p") if rp_s is None else rp_s})
        v = {x["key"]: x["verdict"] for x in adjudicate(rows, q=q)}
        c = 0
        for k, vv in v.items():
            dist[k][vv] = dist[k].get(vv, 0) + 1
            if vv == "survive":
                surv[k] += 1
            if base[k] != vv:
                n_chg[k] += 1
                c += 1
        changes.append(c)
        if frozenset(k for k, vv in v.items() if vv == "survive") == pub_surv:
            set_hits += 1
    ch = np.asarray(changes)
    probs = {k: {"change_prob": round(n_chg[k] / K, 4),
                 "survive_prob": round(surv[k] / K, 4),
                 "verdict_dist": {a: round(b / K, 4) for a, b in sorted(dist[k].items())}}
             for k in base}
    summary = {"K": int(K), "seed": int(seed),
               "mean_changes": round(float(ch.mean()), 2),
               "median_changes": int(np.median(ch)),
               "p90_changes": int(np.percentile(ch, 90)),
               "max_changes": int(ch.max()),
               "published_set_prob": round(set_hits / K, 4),
               "n_resampled": sum(1 for r in results if r.get("mc"))}
    return probs, summary


def summarize(results):
    """诚实账单数 + 双栏存活计数。"""
    def cnt(p): return sum(1 for r in results if p(r))
    return {
        "m_total": len(results),
        "n_survive_cross": cnt(lambda r: r.get("survive_cross")),
        "n_survive_cross_bh": cnt(lambda r: r.get("survive_cross_bh")),
        "n_survive_family": cnt(lambda r: r.get("survive_family")),
        "n_survive": cnt(lambda r: r.get("verdict") == "survive"),
        "n_faded": cnt(lambda r: r.get("verdict") == "faded"),
        "n_dead": cnt(lambda r: r.get("verdict") == "dead"),
        "n_inconclusive": cnt(lambda r: r.get("verdict") == "inconclusive"),
    }
