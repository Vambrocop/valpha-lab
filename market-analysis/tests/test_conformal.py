"""方法 E 保形预测：非重叠窗口 + split-conformal 区间/覆盖（合成数据，无网络）。"""
import numpy as np

from conformal import nonoverlap_fwd_returns, split_conformal, conditional_by_vix


def test_nonoverlap_windows_count_and_value():
    px = np.arange(1, 101, dtype=float)          # 100 天，价格 1..100
    r = nonoverlap_fwd_returns(px, 20)
    assert len(r) == 4                            # starts 0,20,40,60（非重叠）
    assert np.isclose(r[0], px[20] / px[0] - 1)   # 首块 = px[20]/px[0]-1


def test_90_interval_wider_than_80():
    rng = np.random.default_rng(0)
    bands = split_conformal(rng.normal(0, 0.05, 2000), levels=(0.80, 0.90), cal_frac=0.7)
    b80 = next(b for b in bands if b["level"] == 0.80)
    b90 = next(b for b in bands if b["level"] == 0.90)
    assert b90["lower_pct"] <= b80["lower_pct"] and b90["upper_pct"] >= b80["upper_pct"]


def test_coverage_near_nominal_iid():
    rng = np.random.default_rng(1)
    b = split_conformal(rng.normal(0, 0.05, 4000), levels=(0.90,), cal_frac=0.7)[0]
    assert 0.85 <= b["empirical_coverage"] <= 0.95     # iid 下经验覆盖≈名义 0.90


def test_split_fields_and_bracketing():
    rng = np.random.default_rng(2)
    b = split_conformal(rng.normal(0, 0.05, 1000), levels=(0.90,), cal_frac=0.7)[0]
    assert b["n_cal"] == 700 and b["n_test"] == 300
    assert b["lower_pct"] < 0 < b["upper_pct"]


def test_conditional_by_vix_width_scales_with_regime():
    """波动随 VIX 放大的合成数据 → 高VIX体制的区间应比低VIX更宽(不确定性随体制放大)。"""
    import pandas as pd
    rng = np.random.default_rng(5)
    n = 4000
    idx = pd.bdate_range("2005-01-01", periods=n)
    vix = pd.Series(12 + 30 * np.abs(np.sin(np.arange(n) / 40)), index=idx)   # 体制差够大,信号压过分位抽样噪声
    daily = rng.normal(0, (vix.values / 100) / np.sqrt(252))    # 波动随 VIX 放大
    px = pd.Series(100 * np.exp(np.cumsum(daily)), index=idx)
    rows = conditional_by_vix(px, vix, horizon=20, n_bins=3)
    assert len(rows) == 3
    assert rows[-1]["width_pct"] > rows[0]["width_pct"]          # 高VIX组更宽
    assert all(r["lower_pct"] < r["upper_pct"] for r in rows)
