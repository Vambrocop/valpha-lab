"""档位边界 / 月内周次 / 贝叶斯更新的基本性质"""
import pandas as pd

from signal_model import tier, week_of_month, bayesian_update


def test_tier_boundaries():
    assert tier(0.19) == 1
    assert tier(0.20) == 2
    assert tier(0.39) == 2
    assert tier(0.40) == 3
    assert tier(0.59) == 3
    assert tier(0.60) == 4
    assert tier(0.79) == 4
    assert tier(0.80) == 5


def test_week_of_month_monday_start():
    # 2026-06-01 是周一
    assert week_of_month(pd.Timestamp("2026-06-01")) == 1
    assert week_of_month(pd.Timestamp("2026-06-07")) == 1
    assert week_of_month(pd.Timestamp("2026-06-08")) == 2
    assert week_of_month(pd.Timestamp("2026-06-30")) == 5


def test_week_of_month_sunday_start():
    # 2026-03-01 是周日：第一个"周"只含 1 天
    assert week_of_month(pd.Timestamp("2026-03-01")) == 1
    assert week_of_month(pd.Timestamp("2026-03-02")) == 2


def test_bayesian_update_identity():
    assert abs(bayesian_update(0.6, []) - 0.6) < 1e-9


def test_bayesian_update_clips_to_sane_range():
    assert bayesian_update(0.99, [5, 5, 5]) == 0.98
    assert bayesian_update(0.01, [0.1, 0.1]) == 0.02
