"""test_pick_ledger.py — 荐股前向计分:取数/看好看淡命中口径/挂账/丢弃/append-only/初始态诚实
（合成数据·不联网:价格用 prices= 注入；不落盘 web/docs）。"""
import csv

import numpy as np
import pandas as pd
import pytest

import pick_ledger as pk


def _line(p0, p1, periods=35, start="2026-05-01"):
    idx = pd.bdate_range(start=start, periods=periods)
    return pd.Series(np.linspace(p0, p1, periods), index=idx)


def _rows():
    with open(pk.LOG, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _pick(symbol, view="看好", date="2026-05-01", mom=100.0):
    return {"pick_date": date, "symbol": symbol, "view": view, "mom_pct": mom}


@pytest.fixture
def patched(tmp_path, monkeypatch):
    monkeypatch.setattr(pk, "LOG", tmp_path / "pick_log.csv")
    import util_io
    monkeypatch.setattr(util_io, "write_json", lambda *a, **k: None)
    return tmp_path


# ── 挑票规则:强动量+低波动→看好,弱动量+高波动→看淡 ───────────────────
def test_select_picks_momentum_lowvol():
    idx = pd.bdate_range("2025-01-01", periods=200)
    n = len(idx)
    rng = np.random.default_rng(0)
    good = np.linspace(100, 300, n)                       # 强动量 + 平滑(低波)
    bad = np.linspace(200, 100, n) * (1 + rng.normal(0, 0.05, n))  # 弱动量 + 抖(高波)
    mid = np.full(n, 150.0)
    prices = pd.DataFrame({"GOOD": good, "MID": mid, "BAD": bad}, index=idx)
    picks = pk._select_picks(prices)
    bull = [p["symbol"] for p in picks if p["view"] == "看好"]
    bear = [p["symbol"] for p in picks if p["view"] == "看淡"]
    assert "GOOD" in bull and "BAD" in bear                # 强动量低波→看好;弱动量高波→看淡
    assert all("mom_pct" in p for p in picks)


def test_select_picks_too_short_returns_empty():
    idx = pd.bdate_range("2025-01-01", periods=50)         # < MOM_WIN+1
    prices = pd.DataFrame({"AAA": np.linspace(100, 110, 50)}, index=idx)
    assert pk._select_picks(prices) == []


# ── 看好:跑赢 QQQ → 命中、call_excess 为正 ──────────────────────────
def test_bullish_hit(patched, monkeypatch):
    monkeypatch.setattr(pk, "_load_picks", lambda: [_pick("AAA", "看好")])
    prices = {"AAA": _line(100, 200), "QQQ": _line(100, 101)}
    out = pk.run(write=True, prices=prices)
    tr = out["track_record"]
    assert tr["n_settled"] == 1 and tr["call_hit_pct"] == 100.0
    assert tr["bullish"]["n"] == 1 and tr["bullish"]["hit_pct"] == 100.0
    r = _rows()[0]
    assert str(r["hit"]).lower() == "true" and float(r["call_excess_pct"]) > 0


# ── 看好:跑输 QQQ → 未中 ──────────────────────────────────────────
def test_bullish_miss(patched, monkeypatch):
    monkeypatch.setattr(pk, "_load_picks", lambda: [_pick("AAA", "看好")])
    prices = {"AAA": _line(100, 100), "QQQ": _line(100, 150)}
    out = pk.run(write=True, prices=prices)
    assert out["track_record"]["call_hit_pct"] == 0.0
    assert float(_rows()[0]["call_excess_pct"]) < 0


# ── 看淡:跑输 QQQ → 命中(判断对) ──────────────────────────────────
def test_bearish_hit(patched, monkeypatch):
    monkeypatch.setattr(pk, "_load_picks", lambda: [_pick("BBB", "看淡")])
    prices = {"BBB": _line(100, 100), "QQQ": _line(100, 150)}   # 标的落后大盘=看淡对
    out = pk.run(write=True, prices=prices)
    tr = out["track_record"]
    assert tr["call_hit_pct"] == 100.0 and tr["bearish"]["hit_pct"] == 100.0
    assert float(_rows()[0]["call_excess_pct"]) > 0


# ── 看淡:跑赢 QQQ → 未中 ──────────────────────────────────────────
def test_bearish_miss(patched, monkeypatch):
    monkeypatch.setattr(pk, "_load_picks", lambda: [_pick("BBB", "看淡")])
    prices = {"BBB": _line(100, 200), "QQQ": _line(100, 101)}   # 标的跑赢=看淡错
    out = pk.run(write=True, prices=prices)
    assert out["track_record"]["call_hit_pct"] == 0.0


# ── 窗口未走完 → 挂账 ─────────────────────────────────────────────
def test_pending_when_window_short(patched, monkeypatch):
    monkeypatch.setattr(pk, "_load_picks", lambda: [_pick("AAA", "看好")])
    prices = {"AAA": _line(100, 120, periods=10), "QQQ": _line(100, 105, periods=10)}
    out = pk.run(write=True, prices=prices)
    assert out["track_record"]["n_settled"] == 0 and out["track_record"]["n_pending"] == 1


# ── 退市/无价 → 透明丢弃 ──────────────────────────────────────────
def test_dropped_when_no_price(patched, monkeypatch):
    monkeypatch.setattr(pk, "_load_picks", lambda: [_pick("ZZZ", "看好")])
    prices = {"QQQ": _line(100, 120)}                # 不给 ZZZ
    out = pk.run(write=True, prices=prices)
    assert out["track_record"]["n_dropped"] == 1 and out["track_record"]["n_settled"] == 0


# ── append-only:同一条荐股跑两次不重复 ────────────────────────────
def test_append_only_no_duplicate(patched, monkeypatch):
    monkeypatch.setattr(pk, "_load_picks", lambda: [_pick("AAA", "看好")])
    prices = {"AAA": _line(100, 120, periods=10), "QQQ": _line(100, 105, periods=10)}
    pk.run(write=True, prices=prices)
    pk.run(write=True, prices=prices)
    assert len(_rows()) == 1


# ── 0 结算初始态:caveat 守"非投资建议 + 前向计分"认账框 ──────────────
def test_launch_state_honesty(patched, monkeypatch):
    monkeypatch.setattr(pk, "_load_picks", lambda: [])
    out = pk.run(write=True, prices={})
    assert out["track_record"]["n_settled"] == 0
    assert "非投资建议" in out["caveat"] and "前向计分" in out["caveat"]
