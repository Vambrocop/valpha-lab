"""官方收盘门禁：模拟盘成交/预测回填的"不可篡改"防线"""
import pandas as pd

import util_time


def test_past_date_is_final():
    assert util_time.is_final_trading_day("2000-01-03")


def test_future_date_not_final():
    assert not util_time.is_final_trading_day("2999-01-01")


def _freeze(monkeypatch, ts):
    monkeypatch.setattr(util_time, "us_now",
                        lambda: pd.Timestamp(ts, tz=util_time.ET))


def test_today_before_1605_not_final(monkeypatch):
    _freeze(monkeypatch, "2026-06-10 16:04")
    assert not util_time.is_final_trading_day("2026-06-10")


def test_today_after_1605_is_final(monkeypatch):
    _freeze(monkeypatch, "2026-06-10 16:05")
    assert util_time.is_final_trading_day("2026-06-10")
    assert not util_time.is_final_trading_day("2026-06-11")
