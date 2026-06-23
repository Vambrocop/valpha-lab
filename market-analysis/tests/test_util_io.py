"""test_util_io.py — write_json 与 append_daily_log 必须与各脚本原内联写法【逐字节一致】。"""
import csv
import json
import pytest
import util_io


def test_write_json_byte_identical_to_inline(tmp_path, monkeypatch):
    web = tmp_path / "web"; web.mkdir()
    docs = tmp_path / "docs"; docs.mkdir()
    monkeypatch.setattr(util_io, "WEB", web)
    monkeypatch.setattr(util_io, "DOCS", docs)
    payload = {"z": 1, "a": "中文键", "nested": [1, 2, {"x": None, "y": 3.5}], "bool": True}
    written = util_io.write_json("t.json", payload)
    expected = json.dumps(payload, ensure_ascii=False, indent=2)   # 默认轴：早期 7 脚本口径
    assert (web / "t.json").read_text(encoding="utf-8") == expected
    assert (docs / "t.json").read_text(encoding="utf-8") == expected
    assert written == [web, docs]


def test_write_json_skips_missing_dir(tmp_path, monkeypatch):
    web = tmp_path / "web"; web.mkdir()
    docs = tmp_path / "docs"            # 故意不创建
    monkeypatch.setattr(util_io, "WEB", web)
    monkeypatch.setattr(util_io, "DOCS", docs)
    written = util_io.write_json("t.json", {"a": 1})
    assert written == [web]
    assert (web / "t.json").exists()
    assert not docs.exists()


def test_proc_and_allow_nan_indent_match_inline(tmp_path, monkeypatch):
    """三处写(PROC+WEB+DOCS) + allow_nan=False + indent=1：复刻 fetch_insider 口径。"""
    web = tmp_path / "web"; web.mkdir()
    docs = tmp_path / "docs"; docs.mkdir()
    proc = tmp_path / "proc"; proc.mkdir()
    monkeypatch.setattr(util_io, "WEB", web)
    monkeypatch.setattr(util_io, "DOCS", docs)
    monkeypatch.setattr(util_io, "PROC", proc)
    payload = {"k": [1, 2], "s": "值"}
    written = util_io.write_json("t.json", payload, indent=1, allow_nan=False, proc=True)
    expected = json.dumps(payload, ensure_ascii=False, indent=1, allow_nan=False)
    for d in (web, docs, proc):
        assert (d / "t.json").read_text(encoding="utf-8") == expected
    assert set(written) == {web, docs, proc}


def test_compact_separators_match_inline(tmp_path, monkeypatch):
    """紧凑 separators + indent=None：复刻 quick_quotes 口径。"""
    web = tmp_path / "web"; web.mkdir()
    docs = tmp_path / "docs"; docs.mkdir()
    monkeypatch.setattr(util_io, "WEB", web)
    monkeypatch.setattr(util_io, "DOCS", docs)
    payload = {"quotes": [{"t": "AAPL", "p": 1.5}], "n": 1}
    util_io.write_json("q.json", payload, indent=None, separators=(",", ":"), allow_nan=False)
    expected = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    assert (web / "q.json").read_text(encoding="utf-8") == expected
    assert "\n" not in (web / "q.json").read_text(encoding="utf-8")   # 确实紧凑


def test_allow_nan_false_raises_on_nan(tmp_path, monkeypatch):
    """allow_nan=False 遇 NaN 必须报错(而非吐非法 JSON 的 NaN)——与原脚本一致。"""
    web = tmp_path / "web"; web.mkdir()
    monkeypatch.setattr(util_io, "WEB", web)
    monkeypatch.setattr(util_io, "DOCS", tmp_path / "nope")
    with pytest.raises(ValueError):
        util_io.write_json("bad.json", {"x": float("nan")}, allow_nan=False)


# ── append_daily_log（append-only 账本，最敏感，逐字节核对）──────────────────

def test_append_daily_log_byte_identical_to_inline(tmp_path):
    """与原内联 csv.writer 写法（header + 一行）产出的字节完全一致。"""
    p1 = tmp_path / "a.csv"
    util_io.append_daily_log(p1, ["date", "x"], [["2026-01-01", "1"]], date="2026-01-01")
    p2 = tmp_path / "b.csv"                    # 复刻原内联写法
    with open(p2, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["date", "x"]); w.writerow(["2026-01-01", "1"])
    assert p1.read_bytes() == p2.read_bytes()


def test_append_daily_log_dedup_never_touches_history(tmp_path):
    p = tmp_path / "a.csv"
    assert util_io.append_daily_log(p, ["date", "x"], [["2026-01-01", "1"]], date="2026-01-01") is True
    before = p.read_bytes()
    # 同日再写 → 跳过、返回 False、字节不变（绝不改历史）
    assert util_io.append_daily_log(p, ["date", "x"], [["2026-01-01", "9"]], date="2026-01-01") is False
    assert p.read_bytes() == before
    # 新的一天 → 追加、返回 True
    assert util_io.append_daily_log(p, ["date", "x"], [["2026-01-02", "3"]], date="2026-01-02") is True
    assert list(csv.reader(open(p, encoding="utf-8"))) == [["date", "x"], ["2026-01-01", "1"], ["2026-01-02", "3"]]


def test_append_daily_log_multirow(tmp_path):
    """autodiscovery 那种一天多行。"""
    p = tmp_path / "a.csv"
    n = util_io.append_daily_log(p, ["date", "id"],
                                 [["2026-01-01", "a"], ["2026-01-01", "b"]], date="2026-01-01")
    assert n is True
    assert list(csv.reader(open(p, encoding="utf-8"))) == [["date", "id"], ["2026-01-01", "a"], ["2026-01-01", "b"]]
