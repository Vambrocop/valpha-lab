"""方法 E 保形预测：非重叠窗口 + split-conformal 区间/覆盖（合成数据，无网络）。"""
import numpy as np

from conformal import nonoverlap_fwd_returns, split_conformal


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
