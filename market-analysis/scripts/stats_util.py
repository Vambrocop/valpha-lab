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


def calibration_drift(fold_probs, fold_outcomes, fold_labels, n_bins=5, gap_tol=0.05):
    """逐折(各前向时间窗)校准漂移诊断:模型【自报把握度是否仍与现实相符、且随时间是否系统性偏移】。

    静态 OOS 校准(reliability 曲线)只看"汇总后准不准";本诊断加**时间维**——
    每折单独算 mean_pred(平均预测概率) / actual_wr(实际胜率) / gap=mean_pred−actual_wr(>0=偏乐观) /
    ece(分位分箱内 |平均预测−实际| 的样本加权平均);再看 |gap| 是否随折序(时间)系统性上升(Spearman)。
    折数少(walk-forward 通常≈7)→ 趋势检验力低,从严判 drifting,多半诚实地落 inconclusive。

    🔴 红线:这是模型**校准质量**诊断,不预测方向。三态裁决:stable / drifting / inconclusive。
    确定性(无 RNG);依赖 numpy + scipy。
    """
    import warnings
    from scipy.stats import spearmanr

    folds = []
    for probs, y, label in zip(fold_probs, fold_outcomes, fold_labels):
        p = np.asarray(probs, float)
        yy = np.asarray(y, float)
        ok = ~np.isnan(p) & ~np.isnan(yy)
        p, yy = p[ok], yy[ok]
        if len(p) < 30:
            continue
        edges = np.linspace(0.0, 1.0, n_bins + 1)   # 等宽分箱(标准 ECE, Guo+2017);分位分箱会因窄概率放大组内噪声、虚高 ECE
        ece = 0.0
        for b in range(n_bins):
            m = (p >= edges[b]) & ((p <= edges[b + 1]) if b == n_bins - 1 else (p < edges[b + 1]))
            if m.sum() == 0:
                continue
            ece += (m.sum() / len(p)) * abs(float(p[m].mean()) - float(yy[m].mean()))
        folds.append({"period": label, "n": int(len(p)),
                      "mean_pred": round(float(p.mean()), 4), "actual_wr": round(float(yy.mean()), 4),
                      "gap": round(float(p.mean() - yy.mean()), 4), "ece": round(float(ece), 4)})

    if len(folds) < 2:
        return {"status": "insufficient", "folds": folds}

    abs_gaps = [abs(f["gap"]) for f in folds]
    n_folds = len(folds)
    if n_folds >= 3:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rho, pval = spearmanr(range(n_folds), abs_gaps)
        rho = float(rho) if rho == rho else 0.0          # nan(常数输入)→0
        pval = float(pval) if pval == pval else 1.0
    else:
        rho, pval = 0.0, 1.0
    half = n_folds // 2
    early = float(np.mean(abs_gaps[:half])) if half else None
    recent = float(np.mean(abs_gaps[half:]))
    max_abs, mean_abs = max(abs_gaps), float(np.mean(abs_gaps))

    if n_folds < 5:                                       # 折太少:检验力不足,不妄断漂移
        verdict = "inconclusive"
        note = f"仅 {n_folds} 折,样本太少无法判断时间漂移(检验力不足)"
    elif rho > 0 and pval < 0.05 and max_abs >= gap_tol:  # 从严:显著单调上升【且】峰值缺口够大才判漂移
        # n=6 时 p<0.05 ≈ 要求近乎完美单调;加幅度门防把"微小但单调"的噪声波纹误判成校准恶化
        verdict = "drifting"
        note = f"|缺口| 随时间系统性上升(Spearman ρ={rho:.2f}, p={pval:.3f}, 峰值 {max_abs*100:.1f}pp)——校准随时间恶化"
    elif max_abs < gap_tol:                               # 各折缺口都小且无显著趋势
        verdict = "stable"
        note = f"各折 |缺口| 均 < {gap_tol*100:.0f}pp 且无显著趋势——自报把握度跨时段与现实一致"
    else:
        verdict = "inconclusive"
        note = (f"|缺口| 无显著时间趋势(ρ={rho:.2f}, p={pval:.3f})但波动达 {max_abs*100:.1f}pp"
                f"——噪声/区制差,未见系统性漂移")

    return {"status": "ok", "model": "naive", "n_folds": n_folds, "folds": folds,
            "mean_abs_gap_pct": round(mean_abs * 100, 2), "max_abs_gap_pct": round(max_abs * 100, 2),
            "early_abs_gap_pct": round(early * 100, 2) if early is not None else None,
            "recent_abs_gap_pct": round(recent * 100, 2),
            "trend_rho": round(rho, 3), "trend_p": round(pval, 3),
            "verdict": verdict, "note": note}


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
