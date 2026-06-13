"""方法 D 风险仪表盘：VXN-VIX 价差 + 条件下行风险（合成数据，无网络）。"""
import numpy as np
import pandas as pd

from risk_dashboard import vxn_vix_spread, conditional_downside


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
