"""个股诚实体检（块0）纯函数：合成数据，无网络。"""
import numpy as np
import pandas as pd

from stock_checkup import (annualized_vol, max_drawdown, beta, compute_basic_risk,
                           compute_evt, market_dependence)


def test_max_drawdown_known():
    assert abs(max_drawdown([100, 50, 75]) - (-0.5)) < 1e-9     # 峰100→谷50 = -50%
    assert max_drawdown([1, 2, 3]) == 0.0                       # 单调升 = 无回撤
    assert max_drawdown([5]) is None                            # 不足两点


def test_beta_known():
    m = np.array([0.01, -0.02, 0.03, -0.01, 0.02])
    assert abs(beta(2 * m, m) - 2.0) < 1e-9                     # 股=2×市场 → β=2
    assert abs(beta(m, m) - 1.0) < 1e-9
    assert beta(m, np.zeros_like(m)) is None                    # 市场零方差 → None


def test_annualized_vol():
    assert annualized_vol([0.0] * 10) == 0.0                    # 零波动
    assert annualized_vol(np.full(252, 0.01)) == 0.0            # 常数收益 std=0
    assert annualized_vol([0.5]) is None                        # 不足两点


def test_compute_basic_risk_insufficient():
    px = pd.Series(np.arange(100.0), index=pd.bdate_range("2020-01-01", periods=100))
    assert compute_basic_risk(px, px)["status"] == "insufficient"


def test_compute_basic_risk_ok_and_deterministic():
    idx = pd.bdate_range("2010-01-01", periods=1000)
    rng = np.random.default_rng(0)
    nas = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 1000))), index=idx)
    px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 1000))), index=idx)
    r1 = compute_basic_risk(px, nas)
    assert r1 == compute_basic_risk(px, nas)                    # 无 RNG → 确定性
    assert r1["status"] == "ok" and r1["n_days"] == 1000
    assert r1["ann_vol_pct"] > 0 and r1["max_drawdown_pct"] <= 0
    assert r1["beta_nasdaq"] is not None


def test_compute_evt_fat_tail_and_insufficient():
    idx = pd.bdate_range("2008-01-01", periods=3000)
    rng = np.random.default_rng(3)
    ret = rng.standard_t(3, 3000) * 0.01                       # t(3) 厚尾
    px = pd.Series(100 * np.cumprod(1 + ret), index=idx)
    r = compute_evt(px)
    assert r["status"] == "ok" and r["xi"] > 0                 # 厚尾 ξ>0
    ve99 = [x for x in r["var_es"] if x["level"] == 0.99][0]
    assert ve99["es_pct"] >= ve99["var_pct"]                   # ES≥VaR
    short = pd.Series(100 + np.arange(200.0), index=pd.bdate_range("2020-01-01", periods=200))
    assert compute_evt(short)["status"] == "insufficient"      # 不足 ~1000 天


def test_market_dependence():
    rng = np.random.default_rng(7)
    m = rng.normal(0, 0.01, 2000)
    assert market_dependence(m, m)["r2_pct"] == 100.0          # 完全跟随 → R²=100%
    md_indep = market_dependence(rng.normal(0, 0.01, 2000), m)
    assert md_indep["r2_pct"] < 10.0 and abs(md_indep["corr"]) < 0.2   # 独立 → R²≈0
    mix = 0.7 * m + 0.3 * rng.normal(0, 0.01, 2000)
    assert 30 < market_dependence(mix, m)["r2_pct"] < 95       # 混合 → R² 居中
    assert market_dependence(np.ones(5), np.ones(5)) is None   # 零方差 → None
