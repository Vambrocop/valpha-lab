"""factor_pruning：embargo 切分 + 方向裁决逻辑的纯函数性质"""
import numpy as np
import pandas as pd

from factor_pruning import _purged_train, _forward_vol_20d, ASSUMED_DIR, EMBARGO, HORIZON


def test_assumed_dir_covers_all_binary_features():
    from walk_forward import BINARY_FEATURES
    for col, _ in BINARY_FEATURES:
        assert col in ASSUMED_DIR, f"{col} 缺少假设方向"
    assert set(ASSUMED_DIR.values()) <= {+1, -1}


def test_purged_train_embargoes_boundary_rows():
    # 构造 100 个连续交易日，year 全 2019（训练候选），测试期从 pos=100 开始
    dates = pd.bdate_range("2019-01-01", periods=120)
    df = pd.DataFrame({"date": dates, "year": [2019]*100 + [2020]*20})
    sorted_dates = df.sort_values("date")["date"].reset_index(drop=True)
    test_start_pos = 100  # 第一个 2020 行
    train = _purged_train(df, 2020, test_start_pos, sorted_dates)
    # embargo=20：训练集应切掉边界前 20 行，最多保留前 80 行
    assert len(train) == test_start_pos - EMBARGO
    assert train["date"].max() < sorted_dates[test_start_pos - EMBARGO]


def test_purged_train_handles_small_index():
    dates = pd.bdate_range("2019-01-01", periods=30)
    df = pd.DataFrame({"date": dates, "year": [2019]*30})
    sorted_dates = df.sort_values("date")["date"].reset_index(drop=True)
    # test_start_pos < EMBARGO → cutoff 夹到 0，训练集为空
    train = _purged_train(df, 2020, 5, sorted_dates)
    assert len(train) == 0


def test_forward_vol_no_lookahead(monkeypatch):
    """fwd_vol[t] 只能用 t+1..t+HORIZON 的收益，不得触及 t 及更早（防前视）"""
    import factor_pruning as fp
    n = 80
    idx = pd.bdate_range("2020-01-01", periods=n)
    # 价格随机游走，注入一个仅在最后窗口才出现的波动尖峰
    rng = np.random.default_rng(0)
    px = pd.Series(100 + np.cumsum(rng.normal(0, 0.1, n)), index=idx)
    monkeypatch.setattr(fp.pd, "read_csv",
                        lambda *a, **k: px.to_frame("v"))
    fv = fp._forward_vol_20d()
    # 第 t 个值应等于 t+1..t+HORIZON 日对数收益的 std
    r = np.log(px / px.shift(1))
    t = 10
    expected = r.iloc[t+1:t+1+HORIZON].std()
    assert abs(fv.iloc[t] - expected) < 1e-9
    # 末尾不足 HORIZON 天的应为 NaN（无未来数据可用，不能凭空造）
    assert pd.isna(fv.iloc[-1])
