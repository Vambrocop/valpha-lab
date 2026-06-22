"""test_autodiscovery_log.py — Phase2 裁决账本：append-only + 同日幂等 + schema/None 处理。

守住"盘前+盘后同日不重复记"(幂等)与"None→空串不写 nan"，避免污染前向史账本。
"""
import csv
import autodiscovery as ad


def _fake(n=3):
    return [{"candidate_id": f"c{i}", "key": f"k{i}", "family": "calendar",
             "verdict": "dead", "p": 0.5, "recent_p": None} for i in range(n)]


def test_append_then_idempotent(tmp_path):
    log = tmp_path / "adlog.csv"
    assert ad._append_log(_fake(3), path=log) is True       # 首记一批
    assert ad._append_log(_fake(3), path=log) is False      # 同日再调 → 幂等、不改历史行
    rows = list(csv.reader(open(log, encoding="utf-8")))
    assert rows[0] == ["date", "candidate_id", "key", "family", "verdict", "p", "recent_p"]
    assert len(rows) == 1 + 3                                # 表头 + 仅一批 3 行
    assert ad._log_days(path=log) == 1


def test_none_pvalue_blank(tmp_path):
    log = tmp_path / "adlog.csv"
    ad._append_log([{"candidate_id": "c0", "key": "k", "family": "factor",
                     "verdict": "inconclusive", "p": None, "recent_p": None}], path=log)
    rows = list(csv.reader(open(log, encoding="utf-8")))
    assert rows[1][5] == "" and rows[1][6] == ""            # None → 空串(不写 nan)


def test_log_days_empty(tmp_path):
    assert ad._log_days(path=tmp_path / "nope.csv") == 0
