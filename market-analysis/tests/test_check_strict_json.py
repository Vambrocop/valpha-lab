"""check_strict_json (P1-6) 门 — 拒 NaN/Infinity、缺文件跳过不算失败。合成文件·无网络。"""
from check_strict_json import run


def test_rejects_nan_and_infinity(tmp_path):
    (tmp_path / "good.json").write_text('{"a": 1, "b": [2, 3]}', encoding="utf-8")
    (tmp_path / "nan.json").write_text('{"a": NaN}', encoding="utf-8")
    (tmp_path / "inf.json").write_text('{"a": Infinity}', encoding="utf-8")
    (tmp_path / "ninf.json").write_text('{"a": -Infinity}', encoding="utf-8")
    problems = " ".join(run(["good.json", "nan.json", "inf.json", "ninf.json"], web_dir=tmp_path))
    assert "nan.json" in problems and "inf.json" in problems and "ninf.json" in problems  # 三个非法常量都拦
    assert "good.json" not in problems                                                     # 合法放行


def test_missing_file_skipped_not_failure(tmp_path):
    (tmp_path / "good.json").write_text('{"ok": true}', encoding="utf-8")
    assert run(["good.json", "missing.json"], web_dir=tmp_path) == []   # 缺文件跳过、不计失败


def test_all_missing_returns_empty(tmp_path):
    assert run(["a.json", "b.json"], web_dir=tmp_path) == []            # 全缺=无可校验对象、非失败
