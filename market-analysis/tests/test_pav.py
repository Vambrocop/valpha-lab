"""PAV 单调化：倒挂/非单调校准曲线 → 非降"""
from signal_model import pav_monotonic


def test_already_monotonic_unchanged():
    pts = [(0.5, 0.55), (0.6, 0.60), (0.7, 0.66)]
    out = pav_monotonic(pts)
    assert [round(y, 4) for _, y in out] == [0.55, 0.60, 0.66]


def test_inverted_curve_collapses_to_flat():
    # 完全倒挂 → 全部坍缩成同一平均值
    pts = [(0.5, 0.74), (0.6, 0.64), (0.7, 0.60)]
    out = pav_monotonic(pts)
    ys = [y for _, y in out]
    assert ys[0] == ys[1] == ys[2]
    assert abs(ys[0] - (0.74 + 0.64 + 0.60) / 3) < 1e-6


def test_output_is_nondecreasing():
    pts = [(0.54, 0.72), (0.58, 0.74), (0.60, 0.71),
           (0.62, 0.65), (0.64, 0.58), (0.67, 0.63), (0.70, 0.64)]
    ys = [y for _, y in pav_monotonic(pts)]
    assert all(ys[i] <= ys[i + 1] + 1e-9 for i in range(len(ys) - 1))


def test_x_values_preserved():
    pts = [(0.5, 0.74), (0.6, 0.60)]
    out = pav_monotonic(pts)
    assert [x for x, _ in out] == [0.5, 0.6]


def test_empty():
    assert pav_monotonic([]) == []
