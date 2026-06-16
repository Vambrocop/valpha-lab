"""R3 短期反转(过度反应)overreaction.compute_overreaction:合成数据,无网络。"""
import numpy as np
import pandas as pd

from overreaction import compute_overreaction, _fwd_distribution


def test_detects_planted_reversal():
    idx = pd.bdate_range("2005-01-01", periods=3000)
    rng = np.random.default_rng(0)
    r = rng.normal(0, 0.01, 3000)
    thr = np.percentile(r, 5)
    for i in np.where(r <= thr)[0]:                       # 大跌日次日种入 +2% 反弹
        if i + 1 < 3000:
            r[i + 1] += 0.02
    res = compute_overreaction(pd.Series(r, index=idx), q=5)
    assert res["status"] == "ok"
    assert res["full"]["diff_pct"] > 0 and res["full"]["p_value"] < 0.05   # 检出反弹


def test_null_rejected():
    idx = pd.bdate_range("2005-01-01", periods=3000)
    ret = pd.Series(np.random.default_rng(1).normal(0, 0.01, 3000), index=idx)
    res = compute_overreaction(ret, q=5)
    assert res["status"] == "ok" and res["verdict"] == "rejected"          # iid 无系统反弹


def test_faded_when_reversal_only_pre2000():
    idx = pd.bdate_range("1985-01-01", periods=8000)      # ~1985–2016,跨 2000
    rng = np.random.default_rng(5)
    r = rng.normal(0, 0.01, 8000)
    pre = np.asarray(idx.year < 2000)
    for i in np.where(r <= np.percentile(r, 5))[0]:        # 仅在 2000 前的大跌日次日种入反弹
        if i + 1 < 8000 and pre[i + 1]:
            r[i + 1] += 0.03
    res = compute_overreaction(pd.Series(r, index=idx), q=5)
    assert res["status"] == "ok" and res["verdict"] == "faded"   # 全样本显著、现代(2000后)已无


def test_fwd_distribution_shape_and_order():
    idx = pd.bdate_range("2005-01-01", periods=3000)
    rng = np.random.default_rng(7)
    ret = pd.Series(rng.normal(0, 0.01, 3000), index=idx)
    d = _fwd_distribution(ret, 5, 5)
    assert d["n"] >= 30
    assert d["worst_pct"] <= d["p10_pct"] <= d["median_pct"] <= d["p90_pct"] <= d["best_pct"]
    assert 0 <= d["pct_negative"] <= 100
    short = pd.Series(rng.normal(0, 0.01, 100), index=pd.bdate_range("2020-01-01", periods=100))
    assert _fwd_distribution(short, 5, 5) is None        # 样本不足 → None


def test_insufficient():
    idx = pd.bdate_range("2020-01-01", periods=300)
    ret = pd.Series(np.random.default_rng(2).normal(0, 0.01, 300), index=idx)
    assert compute_overreaction(ret)["status"] == "insufficient"
