"""test_cpcv.py — 方法G CSCV 过拟合概率 PBO 单元测试

要点:已知输入→已知输出(稳健因子 PBO 低、纯噪声 PBO≈0.5)、PBO∈[0,1]、确定性(CSCV 无随机)、perf 矩阵形状。
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cpcv  # noqa: E402


def test_pbo_robust_factor_is_low():
    """因子0 在每片都最强(稳健) → IS-best 总能 OOS 泛化 → PBO≈0。"""
    rng = np.random.default_rng(0)
    R = rng.normal(0, 0.01, (cpcv.S_SLICES, 8))
    R[:, 0] += 0.5
    res = cpcv.pbo(R)
    assert res["pbo"] <= 0.1
    assert res["n_combos"] == 252           # C(10,5)


def test_pbo_pure_noise_near_half():
    """IS/OOS 独立噪声 → IS-best 在 OOS≈随机 → PBO≈0.5(过拟合信号)。"""
    rng = np.random.default_rng(1)
    res = cpcv.pbo(rng.normal(0, 1, (cpcv.S_SLICES, 12)))
    assert 0.3 <= res["pbo"] <= 0.7


def test_pbo_antipersistent_is_high():
    """两因子前/后半反号 → 任何 IS/OOS 分割里 IS-best 恰是 OOS-worst → PBO≈1(锁方向、防符号翻转回归)。"""
    S = cpcv.S_SLICES
    R = np.zeros((S, 2))
    R[:S // 2, 0], R[S // 2:, 0] = 1.0, -1.0      # 因子A:前半强、后半弱
    R[:S // 2, 1], R[S // 2:, 1] = -1.0, 1.0      # 因子B:相反
    assert cpcv.pbo(R)["pbo"] > 0.9


def test_pbo_bounds_and_determinism():
    rng = np.random.default_rng(2)
    R = rng.normal(0, 1, (cpcv.S_SLICES, 10))
    r1, r2 = cpcv.pbo(R), cpcv.pbo(R)
    assert 0.0 <= r1["pbo"] <= 1.0
    assert r1 == r2                          # CSCV 确定性


def test_perf_matrix_shape():
    import pandas as pd
    rng = np.random.default_rng(3)
    n = 2000
    df = pd.DataFrame({
        "fwd_up_20d": rng.integers(0, 2, n).astype(float),
        "f1": rng.integers(0, 2, n), "f2": rng.integers(0, 2, n), "f3": rng.integers(0, 2, n),
    })
    R = cpcv._perf_matrix(df, ["f1", "f2", "f3"])
    assert R.shape == (cpcv.S_SLICES, 3)


def test_pbo_too_few_valid_returns_none():
    R = np.full((cpcv.S_SLICES, 1), np.nan)   # 全 NaN / 因子不足
    assert cpcv.pbo(R) is None
