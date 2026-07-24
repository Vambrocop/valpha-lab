"""test_ci_ledger_guard — 防缩水门纯函数(SPEC_LEDGER_GUARD §5)。

只测 append_only_violation(脱 git 可单测);CLI 的 git plumbing 靠本地实弹 dry-run 验。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from ci_ledger_guard import append_only_violation  # noqa: E402

PICK_CORE = ["pick_date", "symbol", "view", "mom_pct"]
PICK_HEADER = ["pick_date", "symbol", "view", "mom_pct", "exit_px", "settled"]


def _row(pd_, sym, view, mom, exit_px="", settled="False"):
    return {"pick_date": pd_, "symbol": sym, "view": view, "mom_pct": mom,
            "exit_px": exit_px, "settled": settled}


def test_clean_append_passes():
    o = [_row("2026-07-20", "AAPL", "看好", "26.8")]
    l = o + [_row("2026-07-24", "KO", "看好", "14.2")]
    assert append_only_violation(PICK_HEADER, o, PICK_HEADER, l, PICK_CORE) is None


def test_settlement_update_passes():
    # 身份列不变,只把非身份列 exit_px/settled 从空填成值 → 放行(pick_ledger 合法结算)
    o = [_row("2026-07-20", "AAPL", "看好", "26.8", exit_px="", settled="False")]
    l = [_row("2026-07-20", "AAPL", "看好", "26.8", exit_px="212.5", settled="True")]
    assert append_only_violation(PICK_HEADER, o, PICK_HEADER, l, PICK_CORE) is None


def test_dropped_row_is_violation():
    a = _row("2026-07-20", "AAPL", "看好", "26.8")
    b = _row("2026-07-21", "KO", "看好", "15.4")
    c = _row("2026-07-22", "TSLA", "看淡", "-13.3")
    o = [a, b, c]
    l = [a, c]  # 丢了 b
    msg = append_only_violation(PICK_HEADER, o, PICK_HEADER, l, PICK_CORE)
    assert msg is not None
    assert "2026-07-21" in msg  # 点名丢失的那行身份


def test_reorder_is_violation():
    a = _row("2026-07-20", "AAPL", "看好", "26.8")
    b = _row("2026-07-21", "KO", "看好", "15.4")
    assert append_only_violation(PICK_HEADER, [a, b], PICK_HEADER, [b, a], PICK_CORE) is not None


def test_empty_origin_passes():
    # 新账本 origin 无行 → 前缀恒成立
    l = [_row("2026-07-24", "AAPL", "看好", "30.1")]
    assert append_only_violation(PICK_HEADER, [], PICK_HEADER, l, PICK_CORE) is None


def test_pure_append_full_row_identity():
    # core_spec=None → 全行皆身份(纯 append 账本 llm_weekly 类)
    hdr = ["week", "stance_trend", "text"]
    o = [{"week": "2026-W26", "stance_trend": "偏积极", "text": "..."}]
    l = o + [{"week": "2026-W28", "stance_trend": "偏积极", "text": "..."}]
    assert append_only_violation(hdr, o, hdr, l, None) is None
    # 丢掉 W26 → 违规
    l2 = [{"week": "2026-W28", "stance_trend": "偏积极", "text": "..."}]
    assert append_only_violation(hdr, o, hdr, l2, None) is not None


def test_schema_change_none_spec_exempt():
    # None spec 且表头变了(合法加列)→ 豁免,不误判为丢行
    o = [{"week": "2026-W26", "stance_trend": "偏积极", "text": "..."}]
    new_hdr = ["week", "stance_trend", "text", "model"]
    l = [{"week": "2026-W26", "stance_trend": "偏积极", "text": "...", "model": "gemini"}]
    assert append_only_violation(["week", "stance_trend", "text"], o, new_hdr, l, None) is None


def test_identity_col_missing_exempt():
    # 指定身份列但某列不在表头(schema 漂移)→ 不误判为丢行
    o = [_row("2026-07-20", "AAPL", "看好", "26.8")]
    bad_header = ["pick_date", "symbol", "view"]  # 缺 mom_pct
    l = [{"pick_date": "2026-07-20", "symbol": "AAPL", "view": "看好"}]
    assert append_only_violation(bad_header, o, bad_header, l, PICK_CORE) is None
