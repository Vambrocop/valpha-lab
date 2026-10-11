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
    # 两族都用**各自估计器带平滑的**公式重建（D6 之后自助也是 +1 平滑）。
    # 用错公式会让两族的噪声尺度系统性错配，而它们共用一个跨族 BY 池。
    # 舍入位数与生产一致（自助 4 位 / 置换 6 位）—— 基准 p 来自产物(已舍入)，
    # 重抽的若不舍入，两者口径就差一点。今天没有任何 BY 临界值落在舍入间隙里
    # （c₈=9.69e-4、c₉=1.090e-3，间隙 [0.0009995, 0.001]），所以无实际影响，
    # 但对齐更结实（审查 N2）。
    return (round(min(1.0, 2.0 * (xs + 1) / (n + 1)), 4) if kind == "bootstrap"
            else round(min(1.0, (xs + 1) / (n + 1)), 6))


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
    # 本函数的返回按 `key` 索引。key 必须唯一，否则字典会**静默丢掉**一个候选，
    # 而丢掉的那条会拿到别人的改判概率 —— 这种错不会报、只会让数字悄悄失真。
    # （实测今天 148 个 key 全不重复；这道断言是给将来新增候选时的保险。）
    keys = [r["key"] for r in results]
    if len(set(keys)) != len(keys):
        import collections
        dup = [k for k, v in collections.Counter(keys).items() if v > 1]
        raise ValueError(f"change_probabilities: 候选 key 重复 {dup} —— "
                         "返回按 key 索引，重复会让某条拿到别人的改判概率")
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


def unresolved_audit(results, p_unresolved):
    """守门不变式：**每条裁决要么已分辨、要么已标注**（SPEC_MC_RESOLUTION Part D）。

    二者皆非 = 一个悄悄落在蒙特卡洛噪声里的裁决 —— 那正是本规格要消灭的东西。
    返回违规列表 [(key, change_prob, 说明)]；空列表 = 通过。

    ⚠ **这道门的真实强度，别高估**（独立审实现 S1）：
    `run_all` 里 `mc_unresolved = cp > P_UNRESOLVED` 与本函数的
    `cp > p_unresolved and not mc_unresolved` **由同一个 cp、同一个常量导出**
    → "超阈却没标"这条分支在当前生产代码下**不可能命中**；`cp is None` 也不可能。
    所以它抓不到它字面上宣称抓的那件事（"一条悄悄落在噪声里的裁决"）——
    噪声与标注同源。它的实际价值是**回归护栏**：将来有人改标注逻辑、或换个生产者
    来填这些字段时，这里会响。
    真正独立的防线是 `n_unresolved ≤ 15`（S5）那道计数 + 8 条 hermetic 单测
    + 离线的 `tools/mc_stability_audit.py`（真换种子重跑，不共享那个噪声模型）。

    豁免（审查 S-e，已核实线上口径）：
      · `recent_powered=False` 的候选在 `adjudicate` 里短路成 `inconclusive`，
        FDR 判定与 modern 判定对它们的裁决**都不起作用** → 不该被要求"分辨"。
        **注意不许用 `recent_p is None` 当代理** —— 线上实测两者解耦
        （6 条未 powered，其中 2 条 recent_p 非 None；另有 4 条 recent_p 为 None）。
      · `mc` 缺失 = 根本没跑过统计（样本不足，p 硬编码 1.0）→ 无噪声可言。
    """
    bad = []
    for r in results:
        if not r.get("recent_powered", True):
            continue                                  # 裁决不依赖 p，豁免
        if not r.get("mc"):
            continue                                  # 没跑过统计，无噪声
        cp = r.get("mc_change_prob")
        if cp is None:
            bad.append((r.get("key"), None, "缺 mc_change_prob —— 度量没接上，等于没守门"))
        elif cp > p_unresolved and not r.get("mc_unresolved"):
            bad.append((r.get("key"), cp,
                        f"改判概率 {cp:.0%} > 阈值 {p_unresolved:.0%} 却**没标** mc_unresolved"))
        elif r.get("mc_unresolved") and not r.get("mc_unresolved_reason"):
            bad.append((r.get("key"), cp, "标了 mc_unresolved 但没给人话原因"))
    return bad


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
