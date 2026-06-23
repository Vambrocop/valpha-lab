"""test_util_io.py — write_json 必须与各脚本原先的内联序列化【逐字节一致】，且只写存在的目录。"""
import json
import util_io


def test_write_json_byte_identical_to_inline(tmp_path, monkeypatch):
    web = tmp_path / "web"; web.mkdir()
    docs = tmp_path / "docs"; docs.mkdir()
    monkeypatch.setattr(util_io, "WEB", web)
    monkeypatch.setattr(util_io, "DOCS", docs)
    payload = {"z": 1, "a": "中文键", "nested": [1, 2, {"x": None, "y": 3.5}], "bool": True}
    written = util_io.write_json("t.json", payload)
    # 旧写法的精确序列化
    expected = json.dumps(payload, ensure_ascii=False, indent=2)
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
