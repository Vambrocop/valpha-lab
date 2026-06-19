"""test_repair_ledgers.py — git union 合并后修账本（去重 keep=last + 排序 + 重封链）。

只测 repair_frame 纯逻辑（合成 DataFrame，无文件/网络）。
为可测把原 repair_all 循环体抽成 repair_frame(df, hash_fields, keys)，行为不变。
"""
import pandas as pd

from repair_ledgers import repair_frame
from ledger_hash import verify_hash_chain, HASH_COLS

# 与 repair_ledgers.JOBS 里 paper_ledger 一致的字段/主键
PL_FIELDS = ["date", "strategy", "action", "holdings", "cash", "equity", "note", "logged_at"]
PL_KEYS = ["date", "strategy"]


def _row(date_, strategy, equity, logged_at, action="hold"):
    return {
        "date": date_, "strategy": strategy, "action": action,
        "holdings": "", "cash": "0", "equity": equity, "note": "",
        "logged_at": logged_at,
    }


def test_dedup_keeps_last_and_drops_duplicate_keys():
    # 同一 (date, strategy) 出现两次（union 合并的典型产物）——应只留 keep=last 那行
    df = pd.DataFrame([
        _row("2026-06-10", "buyhold", "10000.0", "2026-06-10T01:00:00Z"),
        _row("2026-06-11", "buyhold", "10010.0", "2026-06-11T01:00:00Z"),
        _row("2026-06-11", "buyhold", "10099.0", "2026-06-11T09:00:00Z"),  # 同键，更晚
    ])
    out = repair_frame(df, PL_FIELDS, PL_KEYS)

    # 无重复主键
    assert not out.duplicated(subset=PL_KEYS).any()
    # 去重后行数 = 唯一键数
    assert len(out) == 2
    # keep=last：保留的是更晚 logged_at 的那行（equity 10099）
    kept = out[out["date"] == "2026-06-11"].iloc[0]
    assert kept["equity"] == "10099.0"
    assert kept["logged_at"] == "2026-06-11T09:00:00Z"


def test_rebuilds_valid_hash_chain_from_broken_input():
    # 构造断链：行里带错误的 prev_hash/row_hash + 顺序乱 + 重复键
    df = pd.DataFrame([
        {**_row("2026-06-12", "buyhold", "10120.0", "2026-06-12T01:00:00Z"),
         "prev_hash": "GENESIS", "row_hash": "deadbeef"},          # 假 hash
        {**_row("2026-06-10", "buyhold", "10000.0", "2026-06-10T01:00:00Z"),
         "prev_hash": "wrong", "row_hash": "notarealhash"},        # 断链 + 乱序
        {**_row("2026-06-10", "buyhold", "10005.0", "2026-06-10T08:00:00Z"),
         "prev_hash": "x", "row_hash": "y"},                       # 与上行同键（重复）
    ])
    # 修前确实断链（verify 报错）
    assert verify_hash_chain(df, PL_FIELDS)

    out = repair_frame(df, PL_FIELDS, PL_KEYS)

    # 修后：链通过、无重复键、按主键升序、行数=去重后(2)
    assert verify_hash_chain(out, PL_FIELDS) == []
    assert not out.duplicated(subset=PL_KEYS).any()
    assert len(out) == 2
    assert list(out["date"]) == ["2026-06-10", "2026-06-12"]      # 已排序
    assert list(out.columns[-2:]) == HASH_COLS                    # hash 列在尾


def test_clean_input_passes_through_with_resealed_chain():
    # 本就干净（无重复、已排序、无 hash 列）——只重封链，不丢行
    df = pd.DataFrame([
        _row("2026-06-10", "buyhold", "10000.0", "2026-06-10T01:00:00Z"),
        _row("2026-06-11", "buyhold", "10010.0", "2026-06-11T01:00:00Z"),
    ])
    out = repair_frame(df, PL_FIELDS, PL_KEYS)

    assert len(out) == 2
    assert verify_hash_chain(out, PL_FIELDS) == []
    # 重封后多出 hash 列，但业务字段值不变
    assert list(out["equity"]) == ["10000.0", "10010.0"]


def test_sorts_unordered_keys_before_sealing():
    # 乱序输入 → 排序后再封链；验证链在“排序后的顺序”上成立
    df = pd.DataFrame([
        _row("2026-06-13", "buyhold", "10130.0", "2026-06-13T01:00:00Z"),
        _row("2026-06-11", "buyhold", "10110.0", "2026-06-11T01:00:00Z"),
        _row("2026-06-12", "buyhold", "10120.0", "2026-06-12T01:00:00Z"),
    ])
    out = repair_frame(df, PL_FIELDS, PL_KEYS)

    assert list(out["date"]) == ["2026-06-11", "2026-06-12", "2026-06-13"]
    assert verify_hash_chain(out, PL_FIELDS) == []
