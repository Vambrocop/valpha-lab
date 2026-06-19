"""test_export_fx.py — 从 combined_prices 取最新 AUDUSD/USDCNY + 缺列容错。

_latest 是纯函数，直接测；main() 的“缺列回退/沿用上次产物”用 tmp 目录 + monkeypatch
模块路径全局来测（不连网、不碰真实 data/）。
"""
import json

import numpy as np
import pandas as pd

import export_fx
from export_fx import _latest


def _series(values):
    idx = pd.bdate_range("2026-06-01", periods=len(values))
    return pd.Series(values, index=idx, dtype="float64")


# ---------- _latest 纯函数 ----------

def test_latest_returns_last_positive_value_and_date():
    s = _series([0.70, 0.71, 0.72])
    val, d = _latest(s)
    assert val == 0.72
    assert d == "2026-06-03"          # 第三个工作日


def test_latest_skips_trailing_nan():
    # 末尾是 NaN —— 应回退到最后一个有效值，而非取到 NaN
    s = _series([0.70, 0.71, np.nan])
    val, d = _latest(s)
    assert val == 0.71
    assert d == "2026-06-02"


def test_latest_ignores_nonpositive():
    # 0 和负数视为无效（汇率必为正）
    s = _series([0.70, 0.0, -1.0])
    val, d = _latest(s)
    assert val == 0.70
    assert d == "2026-06-01"


def test_latest_all_invalid_returns_none():
    s = _series([np.nan, 0.0, -3.0])
    assert _latest(s) == (None, None)


def test_latest_coerces_string_numbers():
    # CSV 读进来可能是字符串；to_numeric 应能转
    idx = pd.bdate_range("2026-06-01", periods=2)
    s = pd.Series(["7.10", "7.20"], index=idx)
    val, d = _latest(s)
    assert val == 7.20


# ---------- main() 集成（tmp 路径，无网络） ----------

def _point_paths_at_tmp(monkeypatch, tmp_path):
    raw = tmp_path / "raw"
    web = tmp_path / "web"
    raw.mkdir(); web.mkdir()
    monkeypatch.setattr(export_fx, "RAW_DIR", raw)
    monkeypatch.setattr(export_fx, "WEB_DIR", web)
    monkeypatch.setattr(export_fx, "OUT", web / "fx_rates.json")
    return raw, web


def _write_combined(raw, columns):
    idx = pd.bdate_range("2026-06-01", periods=3)
    df = pd.DataFrame(columns, index=idx)
    df.index.name = "Date"
    df.to_csv(raw / "combined_prices.csv")


def test_main_reads_both_rates(monkeypatch, tmp_path):
    raw, web = _point_paths_at_tmp(monkeypatch, tmp_path)
    _write_combined(raw, {"AUD": [0.70, 0.71, 0.72], "CNY": [7.1, 7.15, 7.2]})

    out = export_fx.main()

    assert out["aud_usd"] == 0.72
    assert out["usd_cny"] == 7.2
    assert out["asof"] == "2026-06-03"
    # 文件确实写出且可解析
    written = json.loads((web / "fx_rates.json").read_text(encoding="utf-8"))
    assert written["aud_usd"] == 0.72


def test_main_missing_cny_column_does_not_crash(monkeypatch, tmp_path):
    # 只有 AUD 列，没有 CNY —— 不崩，usd_cny 为 None
    raw, web = _point_paths_at_tmp(monkeypatch, tmp_path)
    _write_combined(raw, {"AUD": [0.70, 0.71, 0.72]})

    out = export_fx.main()

    assert out["aud_usd"] == 0.72
    assert out["usd_cny"] is None


def test_main_missing_combined_file_does_not_crash(monkeypatch, tmp_path):
    # combined_prices.csv 不存在 —— 不崩，两值皆 None
    raw, web = _point_paths_at_tmp(monkeypatch, tmp_path)
    out = export_fx.main()
    assert out["aud_usd"] is None
    assert out["usd_cny"] is None


def test_main_falls_back_to_previous_when_column_missing(monkeypatch, tmp_path):
    # 缺 CNY 列，但上次 fx_rates.json 有 usd_cny —— 应沿用旧值，不让该字段作废
    raw, web = _point_paths_at_tmp(monkeypatch, tmp_path)
    (web / "fx_rates.json").write_text(
        json.dumps({"aud_usd": 0.69, "usd_cny": 7.05}), encoding="utf-8")
    _write_combined(raw, {"AUD": [0.70, 0.71, 0.72]})  # 只有 AUD

    out = export_fx.main()

    assert out["aud_usd"] == 0.72        # 新数据
    assert out["usd_cny"] == 7.05        # 回退到上次产物


def test_main_takes_latest_nonempty_when_trailing_nan(monkeypatch, tmp_path):
    # 末尾 NaN —— main 经 _latest 应取最后有效值，且 asof 是该有效行日期
    raw, web = _point_paths_at_tmp(monkeypatch, tmp_path)
    _write_combined(raw, {"AUD": [0.70, 0.71, np.nan], "CNY": [7.1, 7.15, np.nan]})

    out = export_fx.main()

    assert out["aud_usd"] == 0.71
    assert out["usd_cny"] == 7.15
    assert out["asof"] == "2026-06-02"
