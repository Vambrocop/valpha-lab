"""逻辑回归设计矩阵：形状、无NaN、缺列容错"""
import numpy as np
import pandas as pd

from signal_model import LOGIT_BINARY, build_design_matrix


def _df():
    return pd.DataFrame({
        "month": [1, 6, 12], "dow": [0, 2, 4], "wom": [1, 3, 5],
        "NASDAQ_above_ma200": [1, 0, None],
        "vix_backwardation": [None, 1, 0],
    })


def test_shape_and_columns():
    X, cols = build_design_matrix(_df())
    assert X.shape == (3, 12 + 5 + 5 + len(LOGIT_BINARY))
    assert cols[0] == "month_1" and "NASDAQ_above_ma200" in cols


def test_no_nan_and_missing_treated_as_zero():
    X, cols = build_design_matrix(_df())
    assert not np.isnan(X).any()
    # 第3行 NASDAQ_above_ma200 是 None → 0
    assert X[2, cols.index("NASDAQ_above_ma200")] == 0.0
    # 完全不存在的列 → 全 0
    assert (X[:, cols.index("overnight_mom_pos")] == 0).all()


def test_onehot_correct():
    X, cols = build_design_matrix(_df())
    assert X[1, cols.index("month_6")] == 1.0
    assert X[1, cols.index("month_1")] == 0.0
    assert X[2, cols.index("wom_5")] == 1.0
