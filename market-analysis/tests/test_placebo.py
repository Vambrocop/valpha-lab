"""P4-1 置换检验单元测试：可复现性 + 统计量正确性 + 诚实三态判定。"""
import numpy as np

from placebo_test import (perm_test, make_ssb_stat, make_dir_diff_stat,
                          _verdict, _group_means, benjamini_hochberg,
                          benjamini_yekutieli, MIN_GROUP_N, ALPHA)


def _rng(key=1):
    return np.random.default_rng([20260613, key])


def test_recent_segment_subset_and_reproducible():
    """分段(现代段)逻辑可测部分:子段最小组样本计算 + 独立 rng 流可复现。"""
    rng = np.random.default_rng(1)
    vals = rng.normal(0, 1, 1000)
    labs = np.array([0, 1, 2, 3, 4] * 200)
    mask = np.arange(1000) >= 600                       # "现代段"=后 400(每组 80)
    rmin = int(np.unique(labs[mask], return_counts=True)[1].min())
    assert rmin == 80
    args = (vals[mask], labs[mask], make_ssb_stat(5))
    r1 = perm_test(*args, np.random.default_rng([20260613, 1, 2000]), n_perm=200)
    r2 = perm_test(*args, np.random.default_rng([20260613, 1, 2000]), n_perm=200)
    assert r1["p_value"] == r2["p_value"] and 0 < r1["p_value"] <= 1   # 现代段独立种子可复现


# ── 置换设计：打乱标签必须保持各组样本量不变 ──────────────────────
def test_permutation_preserves_group_sizes():
    labels = np.array([0, 0, 1, 1, 1, 2])
    before = np.bincount(labels)
    after = np.bincount(_rng().permutation(labels))
    assert np.array_equal(before, after)


# ── SS_between：组均值相同 → 约等于 0；有差异 → 显著为正 ───────────
def test_ssb_zero_when_groups_identical():
    vals = np.array([1.0, -1.0, 1.0, -1.0, 1.0, -1.0])   # 每组均值都=0
    labels = np.array([0, 0, 1, 1, 2, 2])
    assert make_ssb_stat(3)(vals, labels) < 1e-12


def test_ssb_positive_with_real_difference():
    g0 = np.full(50, -1.0); g1 = np.full(50, 1.0)
    vals = np.concatenate([g0, g1])
    labels = np.array([0] * 50 + [1] * 50)
    assert make_ssb_stat(2)(vals, labels) > 0


def test_perm_test_detects_strong_signal():
    # 两组均值差极大 + 噪声小 → 置换 p 应该很小（显著）
    rng = np.random.default_rng(0)
    vals = np.concatenate([rng.normal(-1, 0.1, 100), rng.normal(1, 0.1, 100)])
    labels = np.array([0] * 100 + [1] * 100)
    r = perm_test(vals, labels, make_ssb_stat(2), _rng(), n_perm=200)
    assert r["p_value"] < 0.05


def test_perm_test_null_signal_not_significant():
    # 同分布两组 → 不应系统性显著（宽松上界，避免偶发 flaky）
    rng = np.random.default_rng(7)
    vals = rng.normal(0, 1, 400)
    labels = np.array([0, 1] * 200)
    r = perm_test(vals, labels, make_ssb_stat(2), _rng(3), n_perm=300)
    assert r["p_value"] > 0.01


# ── 可复现：同种子流 → 完全一致的 p ──────────────────────────────
def test_perm_test_reproducible():
    rng = np.random.default_rng(1)
    vals = rng.normal(0, 1, 300)
    labels = np.array([0, 1, 2] * 100)
    r1 = perm_test(vals, labels, make_ssb_stat(3), _rng(5), n_perm=200)
    r2 = perm_test(vals, labels, make_ssb_stat(3), _rng(5), n_perm=200)
    assert r1["p_value"] == r2["p_value"]
    assert r1["real"] == r2["real"]


# ── 单边方向统计量 ───────────────────────────────────────────────
def test_dir_diff_sign():
    vals = np.array([2.0, 2.0, 0.0, 0.0])
    labels = np.array([1, 1, 0, 0])      # 组1均值2 > 组0均值0
    assert make_dir_diff_stat()(vals, labels) == 2.0


# ── 诚实三态：显著优先；不显著时再按样本量分"无定论 / 未显现" ─────
def test_verdict_significant_even_with_small_n_is_real():
    # 关键回归：小样本但 p<α 仍应判"真实"，不能被检验力盖过
    status, _ = _verdict(0.01, MIN_GROUP_N - 1)
    assert status == "real"


def test_verdict_underpowered_null_is_inconclusive():
    status, _ = _verdict(0.5, MIN_GROUP_N - 1)
    assert status == "inconclusive"


def test_verdict_powered_null_is_rejected():
    status, _ = _verdict(0.5, MIN_GROUP_N + 1000)
    assert status == "rejected"


# ── _group_means：空组安全 ───────────────────────────────────────
def test_group_means_handles_empty_group():
    vals = np.array([1.0, 2.0, 3.0])
    labels = np.array([0, 0, 2])         # 组1为空
    gm, cnt = _group_means(vals, labels, 3)
    assert cnt[1] == 0
    assert np.isclose(gm[0], 1.5) and np.isclose(gm[2], 3.0)


# ── 多重检验校正 Benjamini-Hochberg ───────────────────────────────
def test_bh_monotone_and_bounded():
    q = benjamini_hochberg([0.001, 0.001, 0.029, 0.095, 0.175, 0.271])
    assert np.all((q >= 0) & (q <= 1))
    # q 在 p 升序上非降（单调化保证）
    order = np.argsort([0.001, 0.001, 0.029, 0.095, 0.175, 0.271])
    assert np.all(np.diff(q[order]) >= -1e-12)


def test_bh_month_just_fails_at_05():
    # 关键诚实点：月份原始 p=0.029 显著，但 6 个检验校正后 q≈0.058，q<0.05 不再成立
    q = benjamini_hochberg([0.001, 0.029, 0.175, 0.271, 0.095, 0.001])
    assert q[1] > 0.05 and q[1] < 0.10        # 月份(第2个)：未过 0.05，过 0.10


def test_bh_single_pvalue_unchanged():
    assert np.isclose(benjamini_hochberg([0.04])[0], 0.04)


# ── Benjamini-Yekutieli（任意相关下有效，比 BH 保守）─────────────────
def test_by_equals_bh_times_harmonic():
    p = [0.001, 0.02, 0.2, 0.5, 0.9]
    c = sum(1.0 / i for i in range(1, len(p) + 1))
    assert np.allclose(benjamini_yekutieli(p), np.clip(np.asarray(benjamini_hochberg(p)) * c, 0, 1))


def test_by_at_least_as_large_as_bh():
    p = [0.001, 0.02, 0.2, 0.5, 0.9]
    assert np.all(benjamini_yekutieli(p) >= np.asarray(benjamini_hochberg(p)) - 1e-12)


def test_by_bounded_and_monotone():
    p = [0.001, 0.001, 0.03, 0.1, 0.4, 0.9]
    by = benjamini_yekutieli(p)
    order = np.argsort(p)
    assert np.all((by >= 0) & (by <= 1))
    assert np.all(np.diff(by[order]) >= -1e-12)
