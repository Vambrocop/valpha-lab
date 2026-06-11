"""校准插值：端点夹紧、退化输入"""
from build_signals import calibrate_prob

PTS = [(0.5, 0.52), (0.6, 0.58)]


def test_linear_interpolation():
    assert calibrate_prob(0.55, PTS) == 0.55


def test_clamps_outside_range():
    assert calibrate_prob(0.40, PTS) == 0.52
    assert calibrate_prob(0.70, PTS) == 0.58


def test_degenerate_inputs():
    assert calibrate_prob(0.5, []) is None
    assert calibrate_prob(None, PTS) is None
