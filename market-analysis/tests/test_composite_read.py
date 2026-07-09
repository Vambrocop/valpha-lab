"""test_composite_read.py — composite_read 的 history 聚合（D2 微图表）防漂移单测。

只测新增的纯聚合口（_read_history / run_all 输出含 history）——不碰权重/stance 等统计口径。
设计原则同 test_aggregation_guards.py：不联网、不写真实盘、依赖缺失 skip 而非 FAIL。
"""
import json
from pathlib import Path

import pytest

import composite_read

_WEB = Path(__file__).parent.parent / "web"


def _write_log(path, rows):
    """rows = [(date, stance, score_str), ...]；写成与 append_daily_log 同构的 csv。"""
    lines = ["date,stance,score"] + [",".join(r) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# 1. _read_history — 纯聚合口本身
# ══════════════════════════════════════════════════════════════════════════════

def test_read_history_parses_rows_in_order(monkeypatch, tmp_path):
    log = tmp_path / "composite_log.csv"
    _write_log(log, [(f"2026-06-{d:02d}", "中性", str(round(0.01 * d, 3))) for d in range(1, 11)])
    monkeypatch.setattr(composite_read, "LOG", log)
    h = composite_read._read_history()
    assert h[0] == {"d": "2026-06-01", "s": 0.01}
    assert h[-1] == {"d": "2026-06-10", "s": 0.1}
    assert len(h) == 10
    assert all(set(p) == {"d", "s"} and isinstance(p["s"], float) for p in h)


def test_read_history_caps_at_last_n(monkeypatch, tmp_path):
    log = tmp_path / "composite_log.csv"
    rows = [("2026-{:02d}-{:02d}".format(1 + i // 28, 1 + i % 28), "中性", str(i / 100))
            for i in range(40)]
    _write_log(log, rows)
    monkeypatch.setattr(composite_read, "LOG", log)
    h = composite_read._read_history(n=30)
    assert len(h) == 30
    assert h[0]["d"] == rows[10][0]      # 恰好从第 11 行起（末 30 行）
    assert h[-1]["d"] == rows[-1][0]


def test_read_history_skips_bad_score_rows(monkeypatch, tmp_path):
    """score 缺失（"数据不足"日 append 出空串）/非数 → 跳过该点，不抛异常、不污染走势。"""
    log = tmp_path / "composite_log.csv"
    _write_log(log, [("2026-06-01", "中性", "0.1"),
                     ("2026-06-02", "数据不足", ""),
                     ("2026-06-03", "中性", "not-a-number"),
                     ("2026-06-04", "偏积极", "0.2")])
    monkeypatch.setattr(composite_read, "LOG", log)
    h = composite_read._read_history()
    assert [p["d"] for p in h] == ["2026-06-01", "2026-06-04"]


def test_read_history_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(composite_read, "LOG", tmp_path / "nope" / "composite_log.csv")
    assert composite_read._read_history() == []


# ══════════════════════════════════════════════════════════════════════════════
# 2. run_all(write=False) — 输出携带 history，且不写盘不追日志
# ══════════════════════════════════════════════════════════════════════════════

def test_run_all_write_false_carries_history_and_never_writes(monkeypatch, tmp_path):
    log = tmp_path / "composite_log.csv"
    _write_log(log, [("2026-06-01", "中性", "0.1"), ("2026-06-02", "偏积极", "0.2")])
    monkeypatch.setattr(composite_read, "LOG", log)
    before = log.read_text(encoding="utf-8")

    out = composite_read.run_all(write=False)

    assert out["history"] == [{"d": "2026-06-01", "s": 0.1}, {"d": "2026-06-02", "s": 0.2}]
    assert log.read_text(encoding="utf-8") == before, "write=False 不得动 log（append-only 账本）"
    # 与 write_json(allow_nan=False) 同一序列化口径：strict JSON 必须合法
    json.dumps(out, ensure_ascii=False, allow_nan=False)


# ══════════════════════════════════════════════════════════════════════════════
# 3. 已发布的 web/composite_read.json 顶层形状（CI 无生成数据时 skip）
# ══════════════════════════════════════════════════════════════════════════════

def test_published_composite_read_json_has_history():
    p = _WEB / "composite_read.json"
    if not p.exists():
        pytest.skip("composite_read.json 不存在（流水线尚未跑），跳过")
    data = json.loads(p.read_text(encoding="utf-8"))
    for key in ("stance", "score", "action", "factors", "history"):
        assert key in data, f"composite_read.json 缺顶层键 '{key}'"
    assert isinstance(data["history"], list), "history 须是 list"
    for pt in data["history"]:
        assert set(pt) == {"d", "s"}, f"history 元素须只含 d/s：{pt}"
        assert isinstance(pt["s"], (int, float))
