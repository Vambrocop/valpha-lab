"""test_candidate_space.py — v1.5 Phase 0：候选空间「有界性」单测（纯枚举，无统计）。

守住 p-hacking 命门：候选空间预声明、有限、可枚举；实枚举数 == N_DECLARED（防偷加/漏算分母）；
candidate_id 稳定唯一；反弹参数只在预声明离散集内（防"扫到显著"）；因子族跟随 BINARY_FEATURES。
"""
from candidate_space import (
    enumerate_candidates, calendar_candidates, rebound_candidates, regime_candidates,
    factor_candidates, positioning_candidates, optsent_candidates,
    N_DECLARED, N_CALENDAR, N_REBOUND, N_REGIME, N_FACTOR, N_POSITIONING, N_OPTSENT,
    INDICES, _REB_PCTL, _REB_HOLD, _CAL_FOMC, _CAL_TWOSIDE,
    _POS_MARKET, _POS_SERIES, _POS_EXTREME, _POS_HOLD,
    _OPTSENT_SERIES, _OPTSENT_EXTREME, _OPTSENT_HOLD,
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
                                "positioning", "options_sentiment"}
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
    # 逐族计数相加必须等于总分母（防漏算/偷加）
    cs_all = enumerate_candidates()
    fam_counts = {"calendar": N_CALENDAR, "rebound": N_REBOUND, "regime": N_REGIME,
                  "factor": N_FACTOR, "positioning": N_POSITIONING, "options_sentiment": N_OPTSENT}
    for fam, n in fam_counts.items():
        assert sum(1 for c in cs_all if c["family"] == fam) == n
    assert sum(fam_counts.values()) == N_DECLARED == len(cs_all)
