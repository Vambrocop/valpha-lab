"""
stats_util.py — 多重比较校正(BH/BY)的**单一实现**,供 placebo_test / fdr_crossfamily / factor_pruning 共用。

原先 BH/BY 在三处各自重写(审计 S5:等价但有漂移风险)。这里统一两种风格(均为逐字搬迁,行为不变):
- **q 值风格** benjamini_hochberg / benjamini_yekutieli —— 返回各 p 的校正 q 值(placebo / factor_pruning 用);
- **拒绝集风格** bh_reject / by_reject —— step-up 返回被拒(显著存活)索引集(fdr_crossfamily 用)。
两风格在固定阈值下等价;BY = BH 的阈值除以调和数 c(m)=Σ1/i,对任意相关结构稳健(含负相关),比 BH 保守。
"""
import numpy as np


def benjamini_hochberg(pvals):
    """Benjamini-Hochberg FDR：返回各 p 的校正 q 值（已单调化，截断到 [0,1]）。
    多重比较封顶诚实性——逐个看 p 会随测试数膨胀假阳性;测了 m 个效应就该控假发现率。"""
    p = np.asarray(pvals, float)
    m = len(p)
    if m == 0:
        return p
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]   # 单调化(从大p端往回取最小)
    q = np.empty(m)
    q[order] = np.clip(ranked, 0, 1)
    return q


def benjamini_yekutieli(pvals):
    """Benjamini-Yekutieli FDR：任意相关结构下都有效(含负相关)，= BH 的 q 值 × 调和数 c(m)=Σ1/i，比 BH 保守。"""
    p = np.asarray(pvals, float)
    m = len(p)
    if m == 0:
        return p
    c = float(np.sum(1.0 / np.arange(1, m + 1)))
    return np.clip(benjamini_hochberg(p) * c, 0.0, 1.0)


def bh_reject(pvals, q):
    """Benjamini-Hochberg step-up：返回被拒(=显著存活)的索引集合。"""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    thresh_rank = 0
    for rank, idx in enumerate(order, 1):
        if pvals[idx] <= rank / m * q:
            thresh_rank = rank          # step-up：取满足条件的最大 rank
    return set(order[:thresh_rank])


def by_reject(pvals, q):
    """Benjamini-Yekutieli = BH 在 q/c(m) 上（c(m)=调和数，对任意相关结构稳健）。返回 (拒绝集, c_m)。"""
    m = len(pvals)
    c_m = sum(1.0 / i for i in range(1, m + 1))
    return bh_reject(pvals, q / c_m), c_m
