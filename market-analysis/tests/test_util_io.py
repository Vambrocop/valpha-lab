"""test_util_io.py — write_json 必须与各脚本原先的内联序列化【逐字节一致】，且只写存在的目录。"""
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
