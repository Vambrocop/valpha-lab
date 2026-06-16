"""个股诚实体检（块0）纯函数：合成数据，无网络。"""
import numpy as np
import pandas as pd

from stock_checkup import (annualized_vol, max_drawdown, beta, compute_basic_risk,
                           compute_evt, market_dependence, compute_patterns,
                           _fdr_annotate_patterns, compute_conformal)


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


def test_fdr_annotate_verdicts():
    """块3 六态裁决：real / faded / hist_robust(近期没测) / data_snoop / inconclusive / rejected。"""
    def tk(p, mgn, stable, r_test, r_sig):
        return {"patterns": {"status": "ok", "tests": [
            {"effect": "e", "p_value": p, "min_group_n": mgn, "split_half_stable": stable,
             "recent_testable": r_test, "recent_significant": r_sig}]}}
    out = {"A": tk(0.0009, 1000, True, True, True),     # 三关全过 → real
           "B": tk(0.0009, 1000, True, True, False),    # 近期测了仍消失 → faded
           "F": tk(0.0009, 1000, True, False, False),   # 近期没测(样本不足) → hist_robust(不声称消失)
           "C": tk(0.0009, 1000, False, False, False),  # 分半就不稳 → data_snoop
           "D": tk(0.5, 20, False, True, False),        # 不显著且组样本<30 → inconclusive
           "E": tk(0.5, 1000, False, True, False)}      # 不显著但样本足 → rejected
    any_real = _fdr_annotate_patterns(out)
    g = lambda k: out[k]["patterns"]["tests"][0]["verdict"]
    assert any_real and g("A") == "real" and g("B") == "faded" and g("F") == "hist_robust"
    assert g("C") == "data_snoop" and g("D") == "inconclusive" and g("E") == "rejected"


def test_compute_patterns_planted_persistent_dow():
    idx = pd.bdate_range("2005-01-01", periods=3000)
    rng = np.random.default_rng(21)
    base = rng.normal(0, 0.01, 3000)
    base[idx.dayofweek.values == 0] += 0.004                   # 周一系统性 +0.4%/天，全程(含近期)
    px = pd.Series(100 * np.cumprod(1 + base), index=idx)
    r = compute_patterns(px, "TEST")
    dwt = [t for t in r["tests"] if t["effect"] == "星期几"][0]
    assert r["status"] == "ok" and dwt["p_value"] < 0.05
    assert dwt["split_half_stable"] and dwt["recent_significant"]   # 日频持续效应三关都过
    # 月份近期窗(~5年≈60月<100) 无法测 → recent_testable=False（不得据此误判 faded）
    mot = [t for t in r["tests"] if t["effect"] == "月份"]
    if mot:
        assert mot[0]["recent_testable"] is False


def test_compute_conformal():
    idx = pd.bdate_range("2008-01-01", periods=4000)
    rng = np.random.default_rng(9)
    px = pd.Series(100 * np.cumprod(1 + rng.normal(0.0003, 0.015, 4000)), index=idx)
    r = compute_conformal(px, horizon=20, level=0.90)
    assert r["status"] == "ok" and r["lower_pct"] < r["upper_pct"]   # 双边区间
    assert r["width_pct"] > 0 and 0.0 <= r["empirical_coverage"] <= 1.0
    assert 0 < r["n_test"] < r["n_windows"]                          # 覆盖的真实分母=出样本窗口数
    short = pd.Series(100.0 + np.arange(100.0), index=pd.bdate_range("2020-01-01", periods=100))
    assert compute_conformal(short, horizon=20)["status"] == "insufficient"
