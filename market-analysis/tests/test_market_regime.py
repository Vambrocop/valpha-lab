"""R1 当前市场风险体制(market_regime.compute_regime):合成数据,无网络。"""
import numpy as np
import pandas as pd

from market_regime import compute_regime, _pct


def _df(n=2000):
    idx = pd.bdate_range("2010-01-01", periods=n)
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "VIX": np.abs(rng.normal(18, 6, n)),
        "VIX3M": np.abs(rng.normal(20, 6, n)),
        "YIELD_10Y": rng.normal(2.5, 0.5, n),
        "YIELD_2Y": rng.normal(1.5, 0.5, n),
    }, index=idx)


def test_pct():
    assert _pct(pd.Series(np.arange(100.0)), 50) == 50.0


def test_compute_regime_ok():
    r = compute_regime(_df())
    assert r["status"] == "ok"
    names = [c["name"] for c in r["components"]]
    assert any("VIX" in n for n in names) and any("收益率曲线" in n for n in names)
    assert r["composite"].startswith("当前环境")


def test_compute_regime_inverted_curve():
    df = _df()
    df["YIELD_10Y"] = 1.0
    df["YIELD_2Y"] = 3.0                                   # 人为倒挂
    cv = [c for c in compute_regime(df)["components"] if c["name"].startswith("收益率曲线")][0]
    assert cv["inverted"] is True and cv["label"] == "倒挂"


def test_compute_regime_backwardation():
    df = _df()
    df["VIX"] = 30.0
    df["VIX3M"] = 20.0                                     # 近月>远月 → 期限结构倒挂
    r = compute_regime(df)
    tv = [c for c in r["components"] if c["name"].startswith("VIX 期限")][0]
    assert tv["backwardation"] is True and "倒挂" in tv["label"]
    assert "期限结构倒挂" in r["composite"]                # 综合句正确追加(非预测措辞)


def test_compute_regime_insufficient():
    idx = pd.bdate_range("2020-01-01", periods=100)
    assert compute_regime(pd.DataFrame({"VIX": [15.0] * 100}, index=idx))["status"] == "insufficient"
