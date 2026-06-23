"""#3 校准漂移诊断（stats_util.calibration_drift）：合成数据，无网络。"""
import numpy as np
import pandas as pd

from stats_util import calibration_drift, forward_returns


def test_forward_returns_equiv_and_no_lookahead():
    """与内联 `s.shift(-h)/s - 1` 逐元素等价；末 h 个为 NaN（含未来价，调用方自负对齐）。"""
    s = pd.Series([10.0, 11.0, 12.0, 9.0, 13.5], index=pd.RangeIndex(5))
    for h in (1, 2):
        got = forward_returns(s, h)
        pd.testing.assert_series_equal(got, s.shift(-h) / s - 1)
        assert got.iloc[-h:].isna().all()          # 末 h 个无未来价 → NaN
    fr1 = forward_returns(s, 1)
    assert abs(fr1.iloc[0] - 0.1) < 1e-12 and abs(fr1.iloc[2] - (9 / 12 - 1)) < 1e-12


def _make(biases, n=3000, seed=0):
    """每折:预测概率 U(0.45,0.70),实际 ~ Bernoulli(clip(p+bias))。bias=该折校准偏移。"""
    rng = np.random.default_rng(seed)
    probs, outs = [], []
    for b in biases:
        p = rng.uniform(0.45, 0.70, n)
        y = (rng.random(n) < np.clip(p + b, 0, 1)).astype(int)
        probs.append(p); outs.append(y)
    return probs, outs, [f"f{i}" for i in range(len(biases))]


def test_insufficient_below_two_folds():
    assert calibration_drift(*_make([0.0]))["status"] == "insufficient"


def test_few_folds_inconclusive():
    r = calibration_drift(*_make([0.0, 0.0, 0.0]))           # 3 折 < 5 → 检验力不足
    assert r["status"] == "ok" and r["verdict"] == "inconclusive" and r["n_folds"] == 3


def test_well_calibrated_is_stable():
    r = calibration_drift(*_make([0.0] * 6, seed=1))
    assert r["verdict"] == "stable" and r["max_abs_gap_pct"] < 5.0


def test_growing_bias_detected_as_drift():
    # 校准偏移逐折单调上升 → |缺口| 单调增 → Spearman 显著 → drifting
    r = calibration_drift(*_make([0.0, 0.03, 0.05, 0.07, 0.09, 0.12], seed=2))
    assert r["verdict"] == "drifting"
    assert r["trend_rho"] > 0 and r["trend_p"] < 0.05
    assert r["recent_abs_gap_pct"] > r["early_abs_gap_pct"]


def test_short_fold_skipped():
    probs, outs, labels = _make([0.0] * 6, seed=4)
    probs[0] = probs[0][:10]; outs[0] = outs[0][:10]          # 首折 n<30 → 跳过
    r = calibration_drift(probs, outs, labels)
    assert r["n_folds"] == 5 and "f0" not in [f["period"] for f in r["folds"]]


def _exact_fold(n, mean_pred, actual):
    """无噪声构造一折:预测全=mean_pred,实际胜率精确=actual → gap 精确可控(锁裁决逻辑)。"""
    k = round(actual * n)
    return np.full(n, mean_pred), np.array([1] * k + [0] * (n - k))


def test_tiny_monotone_gap_not_drifting():
    # |缺口| 单调上升但都 < gap_tol(5pp) → 幅度门拦下,判 stable 而非 drifting(防噪声波纹误报)
    probs, outs, labels = [], [], []
    for i, g in enumerate([0.0, 0.008, 0.016, 0.024, 0.032, 0.040]):
        p, y = _exact_fold(2000, 0.60, 0.60 + g)
        probs.append(p); outs.append(y); labels.append(f"f{i}")
    r = calibration_drift(probs, outs, labels)
    assert r["verdict"] == "stable" and r["max_abs_gap_pct"] < 5.0


def test_large_noise_no_trend_inconclusive():
    # ≥5 折、缺口大但来回无单调趋势 → 生产实际命中的 inconclusive 分支(非折少那条)
    probs, outs, labels = [], [], []
    for i, g in enumerate([0.0, 0.10, -0.08, 0.09, -0.07, 0.02]):
        p, y = _exact_fold(2000, 0.55, 0.55 + g)
        probs.append(p); outs.append(y); labels.append(f"f{i}")
    r = calibration_drift(probs, outs, labels)
    assert r["verdict"] == "inconclusive" and r["max_abs_gap_pct"] >= 5.0 and r["trend_p"] > 0.05


def test_deterministic_and_bounded():
    args = _make([0.0, 0.03, 0.06, 0.0, 0.05, 0.02], seed=3)
    r1 = calibration_drift(*args); r2 = calibration_drift(*args)
    assert r1 == r2                                          # 无 RNG → 确定性
    assert all(-1 <= f["gap"] <= 1 and f["ece"] >= 0 for f in r1["folds"])
    assert -1 <= r1["trend_rho"] <= 1 and 0 <= r1["trend_p"] <= 1
