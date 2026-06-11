"""LR 收缩：生产与验证共用的唯一实现"""
from signal_model import shrink_lr


def test_no_sample_means_no_information():
    assert shrink_lr(1.5, 0) == 1.0


def test_halfway_at_k():
    assert abs(shrink_lr(1.5, 200) - 1.25) < 1e-12
    assert abs(shrink_lr(0.8, 200) - 0.9) < 1e-12


def test_large_n_converges_to_raw():
    assert abs(shrink_lr(1.5, 10**9) - 1.5) < 1e-6
