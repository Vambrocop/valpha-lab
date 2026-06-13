"""test_cycles.py — 方法F 周期检验（谱 + AR1 红噪声）单元测试

核心要验证：
- AR(1) 拟合/surrogate 正确；
- 纯白噪声不应检出周期（无假阳性）；强正弦应被检出且周期定位准（有检验力）；
- 具名周期结构正确，且超出数据可检验范围者诚实标 testable=False；
- 同种子可复现。
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cycles  # noqa: E402


def test_fit_ar1_recovers_known_rho():
    rng = np.random.default_rng(0)
    y = cycles._ar1_surrogate(5000, 0.6, 1.0, rng)
    rho, sigma = cycles._fit_ar1(y)
    assert abs(rho - 0.6) < 0.05
    assert sigma > 0


def test_ar1_surrogate_shape_and_finite():
    rng = np.random.default_rng(1)
    y = cycles._ar1_surrogate(500, 0.1, 1.0, rng)
    assert len(y) == 500
    assert np.all(np.isfinite(y))


def test_white_noise_has_no_significant_cycle():
    rng = np.random.default_rng(2)
    x = rng.normal(0, 1, 1200)
    res = cycles.cycle_test(x, n_surr=300, seed=3)
    assert res["status"] == "ok"
    assert 0.0 <= res["p_global"] <= 1.0
    assert res["significant"] is False          # 白噪声不该检出周期


def test_strong_sinusoid_is_detected():
    n, period = 1200, 40                          # 注入周期=40 个样本的强正弦
    t = np.arange(n)
    rng = np.random.default_rng(4)
    x = 3.0 * np.sin(2 * np.pi * t / period) + rng.normal(0, 1, n)
    res = cycles.cycle_test(x, n_surr=300, seed=5)
    assert res["status"] == "ok"
    assert res["significant"] is True
    assert abs(res["top_period_years"] * 12 - period) < 5   # 周期定位准


def test_named_cycles_structure_and_out_of_range():
    rng = np.random.default_rng(6)
    x = rng.normal(0, 1, 1200)                    # ~100 年月度
    res = cycles.cycle_test(x, n_surr=100, seed=7)
    nc = res["named_cycles"]
    assert len(nc) == len(cycles.NAMED_CYCLES)
    kond = next(c for c in nc if "Kondratiev" in c["cycle"])
    assert kond["testable"] is False              # 45-60年 超出 ~100年数据可检验范围
    assert "note" in kond
    kit = next(c for c in nc if "Kitchin" in c["cycle"])
    assert kit["testable"] is True
    assert "exceeds_red_noise_95" in kit


def test_determinism_same_seed():
    rng = np.random.default_rng(8)
    x = rng.normal(0, 1, 800)
    r1 = cycles.cycle_test(x, n_surr=100, seed=9)
    r2 = cycles.cycle_test(x, n_surr=100, seed=9)
    assert r1["p_global"] == r2["p_global"]
    assert r1["top_period_years"] == r2["top_period_years"]


def test_global_verdict_not_hijacked_by_pointwise_crossings():
    """红线守护：纯白噪声(无真周期)下，逐频率'穿线'很常见，但全局检验的'显著'率应≈ALPHA(~5%)。
    证明头条结论由全局 max-statistic 决定，不会被频繁的逐频率假阳性带偏（种子固定→确定性）。"""
    trials, sig, any_cross = 25, 0, False
    for s in range(trials):
        rng = np.random.default_rng(s)
        x = rng.normal(0, 1, 600)
        res = cycles.cycle_test(x, n_surr=120, seed=s + 100)
        sig += int(res["significant"])
        if any(nc.get("exceeds_red_noise_95") for nc in res["named_cycles"]):
            any_cross = True
    assert any_cross                  # 逐频率穿线确实常见（对照：所以才必须用全局检验）
    assert sig / trials <= 0.20       # 但全局误报率被压住（理论≈0.05；宽松上界，确定性不抖动）
