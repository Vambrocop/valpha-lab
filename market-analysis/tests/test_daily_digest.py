"""daily_digest：三层结构 + 🔴 红线门禁（绝不预测方向/荐股）。"""
import json

import pytest

import daily_digest as dd


def test_digest_has_three_tiers_and_caveat():
    out = dd.build_digest()
    for k in ("tier1_facts", "tier2_watch", "tier3_explore", "caveat"):
        assert k in out, f"缺层: {k}"
    assert isinstance(out["tier1_facts"], list)
    assert "不预测方向" in out["caveat"] or "不荐股" in out["caveat"]


def test_live_digest_has_no_asserted_direction_words():
    """真实产出的 digest：不得出现【未否定的】方向/操作/荐股词（与运行时门禁同一逻辑；
    '不荐股''不是抄底'这类免责语境放行）。"""
    out = dd.build_digest()
    hit = dd._violations(out)
    assert hit == [], f"digest 含未否定的红线词: {hit}"


def test_forbidden_gate_actually_raises():
    """门禁本身有效：注入方向词必须被拦下、拒绝发布。"""
    bad = {"tier1_facts": ["纳指明天会涨，建议买入"], "tier2_watch": [], "tier3_explore": []}
    with pytest.raises(ValueError):
        dd._assert_no_forbidden(bad)
