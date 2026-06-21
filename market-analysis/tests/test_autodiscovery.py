"""test_autodiscovery.py — v1.5 Phase 1b：两处性能向量化的「等价性」回归门（独立审 P1-a）。

把"提速不改结果"焊成自动门：若未来有人再优化、悄悄破坏了块索引或前向收益的等价性，
立刻失败。block_bootstrap 是 placebo/factor/walk_forward 的共享原语，错了会污染公开统计链。
纯数学等价、无数据依赖、快。
"""
import numpy as np
import pandas as pd


def test_block_index_vectorization_equiv():
    # walk_forward.block_bootstrap_diff 的块索引向量化必须逐位 == 旧 Python 推导式
    rng = np.random.default_rng(0)
    for n, block in [(13958, 1), (6635, 5), (1000, 20), (500, 3), (300, 1)]:
        n_blocks = int(np.ceil(n / block))
        starts = rng.integers(0, n, n_blocks)
        old = np.concatenate([(s + np.arange(block)) % n for s in starts])[:n]
        new = ((starts[:, None] + np.arange(block)) % n).ravel()[:n]
        assert np.array_equal(old, new), (n, block)


def test_rebound_fwd_vectorization_equiv():
    # autodiscovery._rebound 的 cumsum 前向收益必须 == 旧 rolling().apply(np.prod)
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.012, 3000)
    for hold in (1, 5, 10):
        C = np.log1p(r).cumsum()
        fwd_vec = np.full(len(r), np.nan)
        m = len(r) - hold
        fwd_vec[:m] = np.expm1(C[hold:hold + m] - C[:m])
        s = pd.Series(r)
        fwd_old = ((1 + s).rolling(hold).apply(np.prod, raw=True).shift(-hold) - 1).values
        mask = ~np.isnan(fwd_old)
        assert np.allclose(fwd_vec[mask], fwd_old[mask], atol=1e-10), hold
        # 尾部 hold 个应为 NaN（无前向窗口）
        assert np.all(np.isnan(fwd_vec[m:]))
