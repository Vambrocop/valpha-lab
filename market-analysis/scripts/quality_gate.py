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
