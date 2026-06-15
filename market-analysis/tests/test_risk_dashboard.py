"""方法 D 风险仪表盘：VXN-VIX 价差 + 条件下行风险（合成数据，无网络）。"""
import numpy as np
import pandas as pd

from risk_dashboard import vxn_vix_spread, conditional_downside, evt_tail, path_drawdown


def _idx(n):
    return pd.bdate_range("2005-01-01", periods=n)


def test_spread_basic():
    idx = _idx(300)
    r = vxn_vix_spread(pd.Series(25.0, index=idx), pd.Series(20.0, index=idx))
    assert r["status"] == "ok"
    assert abs(r["current"] - 5.0) < 1e-6 and abs(r["mean"] - 5.0) < 1e-6


def test_spread_percentile_high_when_widest():
    idx = _idx(300)
    vxn = pd.Series(np.linspace(21, 30, 300), index=idx)   # 价差递增 → 当前=最大
    r = vxn_vix_spread(vxn, pd.Series(20.0, index=idx))
    assert r["percentile"] >= 95 and "走阔" in r["regime"]


def test_spread_insufficient():
    idx = _idx(10)
    r = vxn_vix_spread(pd.Series(25.0, index=idx), pd.Series(20.0, index=idx))
    assert r["status"] == "insufficient"


def test_conditional_downside_deeper_at_high_vix():
    n = 2000
    idx = _idx(n)
    rng = np.random.default_rng(0)
    vix = pd.Series(15 + 10 * np.abs(np.sin(np.arange(n) / 50)), index=idx)  # 平滑振荡
    daily = rng.normal(0, (vix.values / 100) / np.sqrt(252))                 # 波动随 VIX 放大
    px = pd.Series(100 * np.exp(np.cumsum(daily)), index=idx)
    rows = conditional_downside(px, vix, horizon=20, q=0.05, n_bins=4)
    assert len(rows) >= 3
    # 高 VIX 档的 20 日 5% 下行分位应比低档更深(更负)
    assert rows[-1]["downside_q05_pct"] < rows[0]["downside_q05_pct"]
    assert all(r["n"] > 0 and r["n_eff"] >= 1 for r in rows)        # 有效独立样本(审查 BLOCKER)
    assert all(r["downside_q05_pct"] <= r["downside_q10_pct"] for r in rows)  # 5%分位不浅于10%


def test_conditional_downside_insufficient():
    idx = _idx(50)
    rows = conditional_downside(pd.Series(np.arange(50.0), index=idx),
                                pd.Series(20.0, index=idx))
    assert rows == []


# ── EVT 极值尾部风险（POT/GPD）─────────────────────────────────────
def test_evt_fat_tail_positive_xi():
    rng = np.random.default_rng(0)
    ret = pd.Series(rng.standard_t(3, 6000) * 0.01, index=_idx(6000))  # t(3) 厚尾
    r = evt_tail(ret)
    assert r["status"] == "ok" and r["xi"] > 0                          # 厚尾 ξ>0


def test_evt_var_es_monotone_and_es_ge_var():
    rng = np.random.default_rng(1)
    r = evt_tail(pd.Series(rng.standard_t(4, 6000) * 0.01, index=_idx(6000)))
    ve = {x["level"]: x for x in r["var_es"]}
    assert ve[0.999]["var_pct"] > ve[0.99]["var_pct"]                   # 更极端分位 VaR 更深
    assert all(x["es_pct"] >= x["var_pct"] for x in r["var_es"])        # ES≥VaR


# ── 路径回撤分布（#4）────────────────────────────────────────────────
def test_path_drawdown_known_value():
    r = np.tile([0.1, -0.2], 60)        # 120 收益,horizon=2 → 60 窗口,每窗净值 1.1→0.88 = 回撤 20%
    res = path_drawdown(r, horizon=2)
    assert res["status"] == "ok" and res["n_windows"] == 60
    assert res["median_pct"] == 20.0 and res["worst_pct"] == 20.0


def test_path_drawdown_insufficient():
    assert path_drawdown(np.array([0.01] * 10), horizon=2)["status"] == "insufficient"


def test_evt_return_period_increases_with_loss():
    rng = np.random.default_rng(2)
    rps = {p["loss_pct"]: p["return_period_yrs"]
           for p in evt_tail(pd.Series(rng.standard_t(4, 6000) * 0.01, index=_idx(6000)))["return_periods"]}
    vals = [rps[l] for l in (3.0, 5.0, 7.0, 10.0) if rps.get(l) is not None]
    assert all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))     # 跌幅越大越稀有


def test_evt_insufficient():
    rng = np.random.default_rng(0)
    r = evt_tail(pd.Series(rng.normal(0, 0.01, 200), index=_idx(200)))
    assert r["status"] == "insufficient"


def test_evt_reports_extremal_index_and_sensitivity():
    rng = np.random.default_rng(0)
    r = evt_tail(pd.Series(rng.standard_t(3, 6000) * 0.01, index=_idx(6000)))
    assert 0 < r["extremal_index"] <= 1.0                       # 极值指数 θ∈(0,1]
    assert 1 <= r["n_clusters"] <= r["n_exceed"]                # 簇数≤超阈数
    assert r["xi_sensitivity"] and set(r["xi_sensitivity"]) <= {"90.0", "95.0", "97.5"}
    assert "start" in r and "end" in r                          # 数据起止可复现
