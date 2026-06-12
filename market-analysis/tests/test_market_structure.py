"""market_structure：变动构造 + PCA 输出结构"""
import numpy as np
import pandas as pd

import market_structure as msmod
from market_structure import _changes, _change_series, RET, DIFF, PCA_ASSETS


def test_changes_uses_pct_for_returns_diff_for_levels():
    n = 50
    idx = pd.bdate_range("2024-01-01", periods=n)
    px = pd.DataFrame({
        "NASDAQ": np.linspace(100, 110, n),   # 收益类 → pct_change
        "VIX": np.linspace(20, 25, n),        # 水平类 → diff
    }, index=idx)
    nas = _change_series(px, "NASDAQ")
    vix = _change_series(px, "VIX")
    assert abs(nas.iloc[1]) < 0.05                              # pct_change 量级很小
    assert abs(vix.iloc[1] - (px["VIX"].iloc[1] - px["VIX"].iloc[0])) < 1e-9  # diff
    assert "NASDAQ" in RET and "VIX" in DIFF


def test_changes_builds_requested_columns():
    n = 40
    idx = pd.bdate_range("2024-01-01", periods=n)
    rng = np.random.default_rng(0)
    data = {a: 100 + np.cumsum(rng.normal(0, 1, n)) for a in PCA_ASSETS}
    px = pd.DataFrame(data, index=idx)
    ch = _changes(px, PCA_ASSETS)
    assert list(ch.columns) == [a for a in PCA_ASSETS if a in px]
    assert len(ch) == n   # 未 dropna（首行 NaN 由下游 complete-case 处理）


def test_hy_spread_excluded_from_pca_assets():
    # HY_SPREAD 历史短，不能进 PCA（否则把"近10年"偷偷缩成3年）——C1 回归守卫
    assert "HY_SPREAD" not in PCA_ASSETS


def test_pca_sign_anchored_equity_positive(monkeypatch, tmp_path):
    """PCA 符号锚定：股票多头载荷之和应为正（防下次刷新整体翻号）"""
    rng = np.random.default_rng(1)
    n = 600
    idx = pd.bdate_range("2020-01-01", periods=n)
    common = np.cumsum(rng.normal(0, 1, n))   # 共同风险因子
    px = pd.DataFrame(index=idx)
    for a in PCA_ASSETS:
        sign = -1 if a == "VIX" else 1        # VIX 与股票反向
        px[a] = 100 + sign * common + np.cumsum(rng.normal(0, 0.3, n))
    px["HY_SPREAD"] = 3 + np.cumsum(rng.normal(0, 0.02, n))
    monkeypatch.setattr(msmod.pd, "read_csv", lambda *a, **k: px)
    out = msmod.run()
    pc1 = {l["asset"]: l["loading"] for l in out["pca"]["components"][0]["loadings"]}
    eq_sum = pc1.get("NASDAQ", 0) + pc1.get("SP500", 0) + pc1.get("SOX", 0)
    assert eq_sum > 0          # 锚定后股票多头为正
    assert pc1.get("VIX", 0) < 0   # VIX 应为负（与股票反向）
