"""持有期基率统计：horizon_table 的确定性单测"""
import numpy as np
import pandas as pd
import pytest

from horizon_stats import horizon_table


def test_monotonic_growth_certain_win():
    """恒定日增长序列：任意持有期 P(涨)=1，年化中位数等于解析值"""
    n = 3000
    daily = 1.0003
    s = pd.Series(daily ** np.arange(n),
                  index=pd.bdate_range("2000-01-03", periods=n))
    tbl = horizon_table(s, horizons=[("1y", 252)])
    r = tbl["1y"]
    assert r["p_positive"] == 1.0
    assert r["n_windows"] == n - 252
    expected_ann = (daily ** 252 - 1) * 100
    assert r["ann_median"] == pytest.approx(expected_ann, abs=0.1)
    assert r["p_loss_gt_20"] == 0.0


def test_short_series_skips_horizon():
    """窗口数不足（len <= h+50）的持有期不报告"""
    s = pd.Series(np.linspace(100, 110, 200),
                  index=pd.bdate_range("2020-01-01", periods=200))
    tbl = horizon_table(s, horizons=[("6mo", 126), ("10y", 2520)])
    assert "6mo" in tbl and "10y" not in tbl


def test_crash_series_counts_losses():
    """先涨后腰斩的序列：P(亏>20%) 与最差总回报符号正确"""
    up = np.linspace(100, 200, 500)
    down = np.linspace(200, 90, 500)
    s = pd.Series(np.concatenate([up, down]),
                  index=pd.bdate_range("2000-01-03", periods=1000))
    r = horizon_table(s, horizons=[("1y", 252)])["1y"]
    assert r["worst_total"] < -20
    assert 0 < r["p_loss_gt_20"] < 1
