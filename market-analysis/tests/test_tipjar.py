"""tipjar 试胆区诚实保护：命中率算全部已结算（无 cherry-pick）+ 必带"非建议"免责。"""
import pandas as pd

import tipjar as tj


def _synth():
    rows = [
        {"logged_at": "x", "as_of": "2026-06-10", "target_date": "2026-06-11", "call": "UP",
         "rule": "naive_momentum", "actual_ret": 0.5, "actual": "UP", "hit": 1, "prev_hash": "", "row_hash": ""},
        {"logged_at": "x", "as_of": "2026-06-11", "target_date": "2026-06-12", "call": "UP",
         "rule": "naive_momentum", "actual_ret": -0.3, "actual": "DOWN", "hit": 0, "prev_hash": "", "row_hash": ""},
        {"logged_at": "x", "as_of": "2026-06-12", "target_date": None, "call": "DOWN",
         "rule": "naive_momentum", "actual_ret": None, "actual": None, "hit": None, "prev_hash": "", "row_hash": ""},
    ]
    return pd.DataFrame(rows, columns=tj.COLS)


def test_scorecard_honest_hit_rate():
    out = tj.scorecard(_synth())
    assert out["n_scored"] == 2 and out["hits"] == 1
    assert out["hit_rate"] == 50.0                          # = hits/n_scored，无 cherry-pick
    assert out["latest"]["call"] == "DOWN"                  # 未结算的最新判断


def test_must_carry_not_advice_caveat():
    out = tj.scorecard(_synth())
    assert "不是任何买卖建议" in out["caveat"]
    assert "掷硬币" in out["caveat"]
