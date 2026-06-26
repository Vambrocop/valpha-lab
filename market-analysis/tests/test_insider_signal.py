"""test_insider_signal.py — 内部人买入前向计分：取数清洗/结算命中/集群去重/挂账/丢弃/append-only
（全部合成数据·不联网：价格用 prices= 注入，不调 yfinance；不落盘 web/docs）。"""
import csv

import numpy as np
import pandas as pd
import pytest

import insider_signal as ins


def _line(p0, p1, start="2026-05-01", periods=45):
    """线性收盘价序列（business-day 索引），用于构造已知方向的前向窗口。"""
    idx = pd.bdate_range(start=start, periods=periods)
    return pd.Series(np.linspace(p0, p1, periods), index=idx)


def _rows():
    with open(ins.LOG, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _buy(ticker, txn="2026-05-01", value=100000.0, insider="DOE JOHN", title="CEO"):
    return {"filed_date": "2026-05-04", "ticker": ticker, "insider": insider,
            "title": title, "txn_date": txn, "shares": 1000, "value": value}


@pytest.fixture
def patched(tmp_path, monkeypatch):
    monkeypatch.setattr(ins, "LOG", tmp_path / "insider_log.csv")
    import util_io
    monkeypatch.setattr(util_io, "write_json", lambda *a, **k: None)   # 不落盘 web/docs
    return tmp_path


# ── 取数清洗：垃圾 ticker / 小额 被 _load_recent_buys 过滤 ───────────────
def test_load_filters_junk_and_small(tmp_path, monkeypatch):
    import json
    web = tmp_path / "web"
    web.mkdir()
    (web / "insider.json").write_text(json.dumps({"buys": [
        {"ticker": "AAA", "date": "2026-05-01", "value": 100000.0, "insider": "X", "title": "CEO"},
        {"ticker": "NONE", "date": "2026-05-01", "value": 999999.0},     # 占位符 → 拒
        {"ticker": "N O G", "date": "2026-05-01", "value": 999999.0},    # 带空格 → 拒
        {"ticker": "BBB", "date": "2026-05-01", "value": 1000.0},        # < MIN_VALUE → 拒
    ]}), encoding="utf-8")
    monkeypatch.setattr(ins, "WEB", web)
    out = ins._load_recent_buys()
    assert [b["ticker"] for b in out] == ["AAA"]


# ── 结算：跟买后跑赢 SPY → 命中、超额为正 ──────────────────────────────
def test_settlement_hit(patched, monkeypatch):
    monkeypatch.setattr(ins, "_load_recent_buys", lambda: [_buy("AAA")])
    prices = {"AAA": _line(100, 150), "SPY": _line(100, 101)}            # 股+50% vs 大盘~持平
    out = ins.run(write=True, prices=prices)
    tr = out["track_record"]
    assert tr["n_settled"] == 1 and tr["n_hit"] == 1 and tr["beat_spy_pct"] == 100.0
    assert tr["mean_excess_pct"] > 0
    row = _rows()[0]
    assert str(row["settled"]).lower() == "true" and str(row["hit"]).lower() == "true"
    assert float(row["excess_pct"]) > 0


# ── 结算：跟买后跑输 SPY → 未中、超额为负 ──────────────────────────────
def test_settlement_miss(patched, monkeypatch):
    monkeypatch.setattr(ins, "_load_recent_buys", lambda: [_buy("AAA")])
    prices = {"AAA": _line(100, 101), "SPY": _line(100, 150)}            # 股~持平 vs 大盘+50%
    out = ins.run(write=True, prices=prices)
    tr = out["track_record"]
    assert tr["n_settled"] == 1 and tr["n_hit"] == 0 and tr["beat_spy_pct"] == 0.0
    assert float(_rows()[0]["excess_pct"]) < 0


# ── 集群买入：同标的同入场日多名内部人 → 战绩只计一次（防单一事件主导）──
def test_cluster_dedup_in_scorecard(patched, monkeypatch):
    monkeypatch.setattr(ins, "_load_recent_buys",
                        lambda: [_buy("KARD", insider="DIR A"), _buy("KARD", insider="DIR B")])
    prices = {"KARD": _line(100, 150), "SPY": _line(100, 101)}
    out = ins.run(write=True, prices=prices)
    assert len(_rows()) == 2                       # 账本两行都留痕（展示用）
    assert out["track_record"]["n_settled"] == 1   # 但战绩去重 → 只计一次


# ── 窗口未走完 → 挂账（pending），不结算 ───────────────────────────────
def test_pending_when_window_not_elapsed(patched, monkeypatch):
    monkeypatch.setattr(ins, "_load_recent_buys", lambda: [_buy("AAA")])
    prices = {"AAA": _line(100, 120, periods=8), "SPY": _line(100, 105, periods=8)}  # 序列太短
    out = ins.run(write=True, prices=prices)
    tr = out["track_record"]
    assert tr["n_settled"] == 0 and tr["n_pending"] == 1
    assert str(_rows()[0]["settled"]).lower() != "true"


# ── 退市/无价 → 透明丢弃（survivorship），不算命中也不挂账 ──────────────
def test_dropped_when_no_price(patched, monkeypatch):
    monkeypatch.setattr(ins, "_load_recent_buys", lambda: [_buy("ZZZ")])
    prices = {"SPY": _line(100, 120)}              # 故意不给 ZZZ → 基准已结算但股无价
    out = ins.run(write=True, prices=prices)
    tr = out["track_record"]
    assert tr["n_dropped"] == 1 and tr["n_settled"] == 0
    assert str(_rows()[0]["dropped"]).lower() == "true"


# ── append-only：同一笔买入跑两次不重复记 ─────────────────────────────
def test_append_only_no_duplicate(patched, monkeypatch):
    monkeypatch.setattr(ins, "_load_recent_buys", lambda: [_buy("AAA")])
    prices = {"AAA": _line(100, 120, periods=8), "SPY": _line(100, 105, periods=8)}
    ins.run(write=True, prices=prices)
    ins.run(write=True, prices=prices)
    assert len(_rows()) == 1


# ── 0 结算的诚实初始态：verdict/caveat 守"非荐股+前向计分"框 ────────────
def test_launch_state_honesty(patched, monkeypatch):
    monkeypatch.setattr(ins, "_load_recent_buys", lambda: [])
    out = ins.run(write=True, prices={})
    assert out["track_record"]["n_settled"] == 0
    assert "非荐股" in out["caveat"] and "前向计分" in out["caveat"]
