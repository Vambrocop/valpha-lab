"""test_candidate_space.py — v1.5 Phase 0：候选空间「有界性」单测（纯枚举，无统计）。

守住 p-hacking 命门：候选空间预声明、有限、可枚举；实枚举数 == N_DECLARED（防偷加/漏算分母）；
candidate_id 稳定唯一；反弹参数只在预声明离散集内（防"扫到显著"）；因子族跟随 BINARY_FEATURES。
"""
from candidate_space import (
    enumerate_candidates, calendar_candidates, rebound_candidates, regime_candidates,
    factor_candidates, positioning_candidates, optsent_candidates,
    streak_candidates, trailing_extreme_candidates,
    N_DECLARED, N_CALENDAR, N_REBOUND, N_REGIME, N_FACTOR, N_POSITIONING, N_OPTSENT,
    N_STREAK, N_TRAILING,
    INDICES, _REB_PCTL, _REB_HOLD, _CAL_FOMC, _CAL_TWOSIDE,
    _POS_MARKET, _POS_SERIES, _POS_EXTREME, _POS_HOLD,
    _OPTSENT_SERIES, _OPTSENT_EXTREME, _OPTSENT_HOLD,
    _STREAK_DOWN_N, _STREAK_BREAK_N, _STREAK_HOLD, _TRAILING_GRID, _TRAILING_SIDES,
)


def test_total_equals_declared():
    # 实枚举数必须等于写死的预声明总数 → 偷加候选 / 漏算分母 立刻失败
    assert len(enumerate_candidates()) == N_DECLARED


def test_family_counts():
    assert len(calendar_candidates()) == N_CALENDAR
    assert len(rebound_candidates()) == N_REBOUND
    assert len(regime_candidates()) == N_REGIME
    assert len(factor_candidates()) == N_FACTOR
    assert len(positioning_candidates()) == N_POSITIONING
    assert len(optsent_candidates()) == N_OPTSENT
    assert len(streak_candidates()) == N_STREAK
    assert len(trailing_extreme_candidates()) == N_TRAILING


def test_pre_fomc_declared_both_indices():
    # 预 FOMC 漂移候选(2026-06-29 扩声明)：× 2 指数(标普+纳指)，进 calendar 族
    assert _CAL_FOMC == ("pre_fomc",)
    keys = {c["key"] for c in calendar_candidates()}
    assert {"pre_fomc_sp500", "pre_fomc_nasdaq"} <= keys


def test_ids_unique():
    ids = [c["candidate_id"] for c in enumerate_candidates()]
    assert len(set(ids)) == len(ids)


def test_ids_stable_across_calls():
    a = [c["candidate_id"] for c in enumerate_candidates()]
    b = [c["candidate_id"] for c in enumerate_candidates()]
    assert a == b


def test_factor_tracks_binary_features():
    # 因子族 = 每因子 1 候选(全段 p + 现代 recent_p 同候选两字段)；漂移即失败 → 强制更新 N_DECLARED
    from walk_forward import BINARY_FEATURES
    assert len(factor_candidates()) == len(BINARY_FEATURES)
    assert N_FACTOR == len(BINARY_FEATURES)


def test_rebound_params_bounded():
    # 反弹阈值/持有期只允许预声明离散集（无界扫描 = p-hacking）
    reb = rebound_candidates()
    assert {c["params"]["pctl"] for c in reb} == set(_REB_PCTL)
    assert {c["params"]["hold"] for c in reb} == set(_REB_HOLD)
    assert {c["params"]["index"] for c in reb} == set(INDICES)


def test_twoside_priors_declared_both_indices():
    # 期权到期周 + 季末效应(2026-06-30 扩声明)：× 2 指数(标普+纳指)，进 calendar 族，两侧无方向先验
    from candidate_space import _CAL_TWOSIDE
    assert _CAL_TWOSIDE == ("opex_week", "quarter_end")
    keys = {c["key"] for c in calendar_candidates()}
    assert {"opex_week_sp500", "opex_week_nasdaq", "quarter_end_sp500", "quarter_end_nasdaq"} <= keys


def test_every_candidate_has_shape():
    for c in enumerate_candidates():
        assert set(c) >= {"family", "key", "params", "candidate_id"}
        assert c["family"] in {"calendar", "rebound", "regime", "factor",
                                "positioning", "options_sentiment",
                                "streak_down", "streak_break", "trailing_extreme"}
        assert isinstance(c["params"], dict) and c["params"]


# ── 2026-07-04 扩声明(#7)：仓位族 positioning(COT·16) + 期权情绪族 options_sentiment(P/C·8) ──
def test_positioning_params_bounded():
    # 阈值/持有期/市场/序列只允许预声明离散集（无界扫描 = p-hacking）
    pos = positioning_candidates()
    assert len(pos) == 16
    assert {c["params"]["market"] for c in pos} == set(_POS_MARKET)
    assert {c["params"]["series"] for c in pos} == set(_POS_SERIES)
    assert {c["params"]["extreme"] for c in pos} == set(_POS_EXTREME)
    assert {c["params"]["hold"] for c in pos} == set(_POS_HOLD)
    assert all(c["family"] == "positioning" for c in pos)


def test_optsent_params_bounded():
    opt = optsent_candidates()
    assert len(opt) == 8
    assert {c["params"]["series"] for c in opt} == set(_OPTSENT_SERIES)
    assert {c["params"]["extreme"] for c in opt} == set(_OPTSENT_EXTREME)
    assert {c["params"]["hold"] for c in opt} == set(_OPTSENT_HOLD)
    assert all(c["family"] == "options_sentiment" for c in opt)


def test_per_family_counts_sum_to_declared():
    # 逐族计数相加必须等于总分母（防漏算/偷加）；streak 拆两个 family(down 18 + break 12 = N_STREAK)
    cs_all = enumerate_candidates()
    fam_counts = {"calendar": N_CALENDAR, "rebound": N_REBOUND, "regime": N_REGIME,
                  "factor": N_FACTOR, "positioning": N_POSITIONING, "options_sentiment": N_OPTSENT,
                  "streak_down": 18, "streak_break": 12, "trailing_extreme": N_TRAILING}
    for fam, n in fam_counts.items():
        assert sum(1 for c in cs_all if c["family"] == fam) == n
    assert fam_counts["streak_down"] + fam_counts["streak_break"] == N_STREAK
    assert sum(fam_counts.values()) == N_DECLARED == len(cs_all)


# ── 2026-07-10 扩声明(SPEC_STREAK_FAMILY.md)：连跌族 streak(30) + 长跨度反转族 trailing_extreme(14) ──
def test_streak_declared_totals():
    # §1 网格：down N∈{3,4,5}×index{2}×hold{3} = 18；break N∈{3,5}×index{2}×hold{3} = 12 → 30
    down = [c for c in streak_candidates() if c["family"] == "streak_down"]
    brk = [c for c in streak_candidates() if c["family"] == "streak_break"]
    assert len(down) == 18 and len(brk) == 12
    assert N_STREAK == 30
    assert {c["params"]["n"] for c in down} == set(_STREAK_DOWN_N)
    assert {c["params"]["n"] for c in brk} == set(_STREAK_BREAK_N)
    assert {c["params"]["hold"] for c in down} | {c["params"]["hold"] for c in brk} == set(_STREAK_HOLD)
    assert {c["params"]["index"] for c in down} == set(INDICES)


def test_trailing_declared_totals_and_grid():
    # §5.3 网格：63/126/252d × low+high × sp500+nasdaq(各4) + 504d × low+high × sp500-only(2) = 14
    tr = trailing_extreme_candidates()
    assert len(tr) == 14 == N_TRAILING
    assert all(c["family"] == "trailing_extreme" for c in tr)
    by_n = {}
    for c in tr:
        by_n.setdefault(c["params"]["n"], []).append(c)
    assert set(by_n) == {63, 126, 252, 504}
    for n in (63, 126, 252):
        assert len(by_n[n]) == 4
        assert {c["params"]["index"] for c in by_n[n]} == set(INDICES)
        assert {c["params"]["side"] for c in by_n[n]} == set(_TRAILING_SIDES)
    assert len(by_n[504]) == 2
    assert {c["params"]["index"] for c in by_n[504]} == {"sp500"}     # S4:504d 不设 nasdaq


def test_trailing_hold_matches_lookback():
    # §5.3 表：hold 与 lookback 一一匹配(63→21, 126→63, 252→126, 504→126)
    expect = {63: 21, 126: 63, 252: 126, 504: 126}
    for c in trailing_extreme_candidates():
        assert c["params"]["hold"] == expect[c["params"]["n"]]


def test_n_declared_is_148_explicit_sum():
    # 分母对账(N3)：104(原基线) + 30(streak) + 14(trailing) = 148，一步到位(不经 134 中转)
    assert N_STREAK == 30 and N_TRAILING == 14
    assert N_DECLARED == 104 + N_STREAK + N_TRAILING == 148
    assert len(list(enumerate_candidates())) == N_DECLARED
