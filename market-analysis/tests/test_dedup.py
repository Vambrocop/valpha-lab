"""预测日志去重：含 CSV 读回后 model_version "2.0" 变浮点的陷阱"""
import pandas as pd

from track_predictions import COLS, _is_dup


def _log_after_csv_roundtrip(tmp_path):
    df = pd.DataFrame([{
        "logged_at": "2026-06-10 19:28", "signal_date": "2026-06-10",
        "index": "NASDAQ", "model_version": "2.0", "prob": 0.55, "tier": 3,
        "ret_1d": None, "ret_5d": None, "ret_20d": None,
    }])
    p = tmp_path / "log.csv"
    df.to_csv(p, index=False)
    return pd.read_csv(p)


def test_float_trap_exists_and_is_handled(tmp_path):
    log = _log_after_csv_roundtrip(tmp_path)
    # 陷阱确实存在：读回后 model_version 不再是字符串
    assert log["model_version"].dtype != object
    # 但去重仍能命中
    assert _is_dup(log, "2026-06-10", "NASDAQ", "2.0")


def test_different_key_is_not_dup(tmp_path):
    log = _log_after_csv_roundtrip(tmp_path)
    assert not _is_dup(log, "2026-06-10", "NASDAQ", "2.1")
    assert not _is_dup(log, "2026-06-11", "NASDAQ", "2.0")
    assert not _is_dup(log, "2026-06-10", "SP500", "2.0")


def test_empty_log_is_never_dup():
    empty = pd.DataFrame(columns=COLS)
    assert not _is_dup(empty, "2026-06-10", "NASDAQ", "2.0")
