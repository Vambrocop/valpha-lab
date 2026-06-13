"""方法 B 反事实事件影响：状态机 + 显著性正确性（合成数据，无网络）。"""
import numpy as np
import pandas as pd

from event_causal import counterfactual_impact


def _series(n=200, beta=1.0, noise=0.001, shift=0.0, shift_from=160, seed=0):
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(seed)
    ctrl = pd.Series(rng.normal(0, 0.01, n), index=idx)
    treated = beta * ctrl + pd.Series(rng.normal(0, noise, n), index=idx)
    treated.iloc[shift_from:] += shift            # 事件后每日异常
    return treated, ctrl.to_frame("C1")


def test_detects_real_negative_effect():
    treated, ctrl = _series(shift=-0.01, shift_from=160)
    r = counterfactual_impact(treated, ctrl, treated.index[160], pre_n=120, post_n=20)
    assert r["status"] == "significant"
    assert r["cum_abnormal_pct"] < 0


def test_no_effect_not_significant():
    treated, ctrl = _series(shift=0.0, shift_from=160)
    r = counterfactual_impact(treated, ctrl, treated.index[160], pre_n=120, post_n=20)
    assert r["status"] == "not_significant"


def test_short_post_window_pending():
    treated, ctrl = _series(n=130, shift_from=125)
    r = counterfactual_impact(treated, ctrl, treated.index[125], pre_n=120, post_n=20)
    assert r["status"] == "pending"          # 仅 5 个后窗交易日 < MIN_POST_N


def test_insufficient_pre():
    treated, ctrl = _series()
    r = counterfactual_impact(treated, ctrl, treated.index[50], pre_n=120, post_n=20)
    assert r["status"] == "insufficient_pre"


def test_inadequate_controls_flagged():
    # treated 与 control 无关 → 前窗 R² 极低 → 诚实判"对照不充分"
    idx = pd.bdate_range("2020-01-01", periods=200)
    rng = np.random.default_rng(1)
    ctrl = pd.Series(rng.normal(0, 0.01, 200), index=idx).to_frame("C1")
    treated = pd.Series(rng.normal(0, 0.01, 200), index=idx)
    r = counterfactual_impact(treated, ctrl, treated.index[160], pre_n=120, post_n=20)
    assert r["status"] == "inadequate_controls"


def test_reproducible():
    treated, ctrl = _series(shift=-0.005, shift_from=160)
    r1 = counterfactual_impact(treated, ctrl, treated.index[160], pre_n=120, post_n=20)
    r2 = counterfactual_impact(treated, ctrl, treated.index[160], pre_n=120, post_n=20)
    assert r1["p_value"] == r2["p_value"] and r1["cum_abnormal_pct"] == r2["cum_abnormal_pct"]


def test_alpha_drift_no_event_not_significant():
    # 关键回归(证伪审查 BLOCKER#2)：treated 有强自身漂移(α≠0)但事件后无额外效应。
    # 截距 α 被正确净掉 → cum≈0 → not_significant。若 α 被机械计入 CAR(审查担忧)，
    # 这里会假阳性。它没有 → 说明带截距的市场模型处理是对的。
    idx = pd.bdate_range("2020-01-01", periods=200)
    rng = np.random.default_rng(3)
    ctrl = pd.Series(rng.normal(0, 0.01, 200), index=idx)
    treated = 1.0 * ctrl + 0.001 + pd.Series(rng.normal(0, 0.0004, 200), index=idx)  # +0.1%/天漂移,无事件跳变
    r = counterfactual_impact(treated, ctrl.to_frame("C1"), treated.index[160], pre_n=120, post_n=20)
    assert r["status"] == "not_significant"
    assert abs(r["cum_abnormal_pct"]) < 1.0      # 漂移没有被错误累计成 ~+2%


def test_event_date_non_trading_day_snaps_forward():
    # 事件日落在周末 → searchsorted 顺延到下一交易日，不报错、不 pending
    treated, ctrl = _series(shift=0.0, shift_from=160)
    r = counterfactual_impact(treated, ctrl, "2020-08-15", pre_n=120, post_n=20)  # 2020-08-15 是周六
    assert r["status"] in ("significant", "not_significant", "inadequate_controls")
