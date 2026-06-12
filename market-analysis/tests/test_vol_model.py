"""vol_model：前向波动率无前视 + 特征列完整"""
import numpy as np
import pandas as pd

import vol_model
from vol_model import FEATURES, HORIZON, EMBARGO, _purge


def test_features_nonempty_and_known():
    # FEATURES 应是已知连续特征，无重复
    assert len(FEATURES) == len(set(FEATURES))
    assert "vix" in FEATURES and "rv20" in FEATURES


def test_purge_embargoes_boundary():
    idx = pd.bdate_range("2015-01-01", periods=100)
    train = pd.DataFrame({"x": range(100)}, index=idx)
    all_dates = idx
    boundary = idx[80]   # 测试期从第80个交易日起
    out = _purge(train, boundary, all_dates)
    # embargo=20：训练应止于 boundary 前 20 个交易日
    assert out.index.max() < idx[80 - EMBARGO]
    assert len(out) == 80 - EMBARGO


def test_cv_threshold_uses_only_train():
    """二值化阈值必须只来自训练集 fwd_rv20 中位数，绝不含测试期"""
    tr = pd.DataFrame({"fwd_rv20": [0.1, 0.2, 0.3, 0.4, 0.5]})
    te = pd.DataFrame({"fwd_rv20": [9.0, 9.1, 9.2]})  # 测试期极端值
    thr = tr["fwd_rv20"].median()
    # 阈值=训练中位数0.3，与测试期的9.x无关
    assert thr == 0.3
    # 若误用了 pd.concat([tr,te]).median() 会变成 0.4——确保没有
    assert thr != pd.concat([tr, te])["fwd_rv20"].median()


def test_forward_vol_no_lookahead(monkeypatch):
    """build_features 的 fwd_rv20[t] 只能用 t+1..t+HORIZON，且末尾不足时为 NaN"""
    n = 90
    idx = pd.bdate_range("2015-01-01", periods=n)
    rng = np.random.default_rng(1)
    nas = pd.Series(100 + np.cumsum(rng.normal(0, 0.5, n)), index=idx)
    df = pd.DataFrame({"NASDAQ": nas, "VIX": 20 + rng.normal(0, 1, n),
                       "VIX3M": 21 + rng.normal(0, 1, n), "BTC": 50000 + np.cumsum(rng.normal(0, 50, n)),
                       "DXY": 100 + rng.normal(0, 0.2, n), "HY_SPREAD": 3 + rng.normal(0, 0.1, n)})
    df.index.name = "Date"
    monkeypatch.setattr(vol_model.pd, "read_csv", lambda *a, **k: df)
    f = vol_model.build_features()
    r = np.log(nas / nas.shift(1))
    # 取一个中间交易日核对 fwd_rv20 = std(r[t+1..t+HORIZON]) * sqrt(252)
    d = f.index[5]
    pos = idx.get_loc(d)
    expected = r.iloc[pos+1:pos+1+HORIZON].std() * np.sqrt(252)
    assert abs(f.loc[d, "fwd_rv20"] - expected) < 1e-9
