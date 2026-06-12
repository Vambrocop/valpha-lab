"""v3 稀疏模型：子集过滤等价性单测（计划 rev2 §1 的 (a)(b)(c)(d)，Opus 审查要求锁死）

"过滤 lrs_dict['factors'] 字典即得子集、score_row 零改动"必须是被测的事实，
不是巧合的正确。
"""
import json

import numpy as np
import pytest

from signal_model import bayesian_update, shrink_lr
from walk_forward import score_row, block_bootstrap_diff
from v3_sparse_model import filter_lrs, _clean, VARIANTS


def make_lrs():
    """手工构造可控的 lrs_dict（结构与 learn_lrs 输出一致）"""
    return {
        "base_win_rate": 0.60,
        "n_total": 1000,
        "factors": {
            "month": {"6": {"win_rate": 0.66, "lr": 1.10, "n": 80}},
            "dow":   {"4": {"win_rate": 0.63, "lr": 1.05, "n": 200}},
            "wom":   {"2": {"win_rate": 0.57, "lr": 0.95, "n": 150}},
            "BTC_mom20_pos":     {"name": "btc+", "win_rate": 0.72, "lr": 1.20, "n": 300},
            "BTC_mom20_neg":     {"name": "btc-", "win_rate": 0.48, "lr": 0.80, "n": 250},
            "NASDAQ_above_ma200": {"name": "ma200", "win_rate": 0.66, "lr": 1.10, "n": 700},
            "nasdaq_high_vol":    {"name": "hivol", "win_rate": 0.54, "lr": 0.90, "n": 400},
        },
    }


def make_row(**overrides):
    """基础行：日历 6月/周五/第2周，全部二值因子默认 None（不可观测）"""
    row = {"month": 6, "dow": 4, "wom": 2,
           "BTC_mom20_pos": None, "BTC_mom20_neg": None,
           "NASDAQ_above_ma200": None, "nasdaq_high_vol": None}
    row.update(overrides)
    return row


def test_a_btc_only_equals_hand_computed():
    """(a) 变体 C(btc-only)：输出 == 只用 BTC 因子手算（日历 fallback 1.0 不改变结果）"""
    lrs = make_lrs()
    row = make_row(BTC_mom20_pos=1, BTC_mom20_neg=0)
    got = score_row(row, filter_lrs(lrs, "btc_only"))

    base = lrs["base_win_rate"]
    f = lrs["factors"]
    # pos=1：收缩后的触发侧 LR
    lr_pos = shrink_lr(f["BTC_mom20_pos"]["lr"], f["BTC_mom20_pos"]["n"])
    # neg=0：score_row 的反面还原（全概率公式，p1 用未过滤的 n_total）
    p1 = f["BTC_mom20_neg"]["n"] / lrs["n_total"]
    wr_on = shrink_lr(f["BTC_mom20_neg"]["lr"], f["BTC_mom20_neg"]["n"]) * base
    inv_lr = max(((base - p1 * wr_on) / (1 - p1)) / base, 0.5)
    expected = bayesian_update(base, [lr_pos, inv_lr])
    assert got == pytest.approx(expected, abs=1e-12)


def test_b_inverse_branch_identical_between_subset_and_full():
    """(b) val==0 反面还原：A 与 D 在 BTC 因子上的贡献一致（n_total/factors[col]['n'] 未变）。
    行上仅 BTC 可观测（其余 None）→ 两变体唯一差异是 factors 里多余的 key，输出必须相等。"""
    lrs = make_lrs()
    row = make_row(BTC_mom20_pos=0, BTC_mom20_neg=1)
    a = score_row(row, filter_lrs(lrs, "v3_sparse"))
    d = score_row(row, filter_lrs(lrs, "v2_full"))
    assert a == pytest.approx(d, abs=1e-12)
    # 且过滤不得动 n_total / base_win_rate
    fl = filter_lrs(lrs, "btc_only")
    assert fl["n_total"] == lrs["n_total"]
    assert fl["base_win_rate"] == lrs["base_win_rate"]


def test_c_nan_btc_row_degrades_to_calendar_only():
    """(c) BTC=NaN 行（pre-2015）：变体 A 输出 === 变体 B（退化为纯日历）"""
    lrs = make_lrs()
    row = make_row()   # 全部二值 None
    a = score_row(row, filter_lrs(lrs, "v3_sparse"))
    b = score_row(row, filter_lrs(lrs, "calendar_only"))
    assert a == pytest.approx(b, abs=1e-12)
    # 纯日历手算对照
    base = lrs["base_win_rate"]
    f = lrs["factors"]
    expected = bayesian_update(base, [
        shrink_lr(f["month"]["6"]["lr"], f["month"]["6"]["n"]),
        shrink_lr(f["dow"]["4"]["lr"], f["dow"]["4"]["n"]),
        shrink_lr(f["wom"]["2"]["lr"], f["wom"]["2"]["n"]),
    ])
    assert a == pytest.approx(expected, abs=1e-12)


def test_d_insufficient_tier4_yields_null_not_nan():
    """(d) Tier≥4 触发不足 → block_bootstrap_diff 返回 None → JSON 输出 null 而非 NaN"""
    y = np.array([1, 0, 1, 1, 0] * 20)
    sel = np.zeros(100, dtype=bool)
    sel[:5] = True   # 仅 5 次触发 < 10
    assert block_bootstrap_diff(sel, y) is None
    payload = _clean({"tier4_boot": block_bootstrap_diff(sel, y), "x": float("nan")})
    s = json.dumps(payload, allow_nan=False)   # 不抛 → 无裸 NaN
    assert '"tier4_boot": null' in s and '"x": null' in s


def test_variant_menu_frozen():
    """变体菜单与计划一致（防中途加变体）"""
    assert set(VARIANTS) == {"v3_sparse", "calendar_only", "btc_only", "v2_full"}
    assert VARIANTS["v3_sparse"]["binary"] == ["BTC_mom20_pos", "BTC_mom20_neg"]
    assert VARIANTS["v2_full"]["binary"] is None
