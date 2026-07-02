"""test_outlook.py — 观点/预测页(outlook.py) _momentum() 排序方向 + main() index_call 阈值锁定测试。

合成数据·monkeypatch RAW/WEB 指向 tmp_path·不联网·util_io.write_json 打桩不落盘真实 web/docs。

读了 market-analysis/scripts/outlook.py：
  - _signals(): 读 WEB/"signals.json"，失败静默返回 {}
  - _momentum(win=126, n=3): 读 RAW/"stocks_prices.csv"，6 个月(126 日)动量排序，
    前 n 高 → 看好(bullish)、后 n 低 → 看淡(bearish)；样本不足/全 NaN 时返回 ([], [])
  - main(): 组装 index_call（latest_prob>=0.5 → 看涨，否则看跌）+ bullish/bearish + disclaimer，
    经 util_io.write_json 写 outlook.json
"""
import json
import math

import numpy as np
import pandas as pd
import pytest

import outlook as ol
import util_io


def _write_prices_csv(path, idx, targets):
    """targets: {symbol: 目标6个月动量(小数, 如 0.5=+50%)}；_momentum 用 iloc[-1] / iloc[-1-win]，
    win=126、140 行 → 动量锚点是 iloc[13](非首行)。因除末行外全填常数 100，锚点值=100，
    故动量比值只由末行决定(Fable 审:原注释误写 idx[0])。"""
    data = {}
    for sym, t in targets.items():
        col = [100.0] * len(idx)
        col[-1] = 100.0 * (1 + t)
        data[sym] = col
    pd.DataFrame(data, index=idx).to_csv(path, index_label="Date")


def _write_signals_json(path, prob=None, tier=None):
    payload = {}
    if prob is not None:
        payload["latest_prob"] = prob
    if tier is not None:
        payload["latest_tier"] = tier
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_real_writes(monkeypatch):
    """main() 内部 `from util_io import write_json` 每次调用都重新查表，
    这里打桩成不落盘、只记录调用，防止测试误写真实 web/docs。"""
    captured = {}
    monkeypatch.setattr(util_io, "write_json",
                         lambda name, payload, **k: captured.update({"name": name, "payload": payload}))
    return captured


# ── ① 动量排序方向：合成 6 支已知动量 → 断言看好/看淡排序与数值正确 ──────────
def test_momentum_bullish_descending_bearish_ascending(tmp_path, monkeypatch):
    idx = pd.bdate_range("2020-01-01", periods=140)          # win=126 默认门槛，留余量
    targets = {"A": 0.50, "B": 0.30, "C": 0.10, "D": -0.05, "E": -0.20, "F": -0.40}
    _write_prices_csv(tmp_path / "stocks_prices.csv", idx, targets)
    monkeypatch.setattr(ol, "RAW", tmp_path)

    top, bot = ol._momentum()

    assert [d["symbol"] for d in top] == ["A", "B", "C"]      # 高→低，看好前3
    assert [d["mom_pct"] for d in top] == [50.0, 30.0, 10.0]
    assert all(d["view"] == "看好" for d in top)
    assert all("领先" in d["reason"] for d in top)

    assert [d["symbol"] for d in bot] == ["F", "E", "D"]      # 最差→最不差，看淡后3(倒序)
    assert [d["mom_pct"] for d in bot] == [-40.0, -20.0, -5.0]
    assert all(d["view"] == "看淡" for d in bot)
    assert all("垫底" in d["reason"] for d in bot)

    # 与看好组不重叠、方向不反：看好组全高于看淡组
    assert min(d["mom_pct"] for d in top) > max(d["mom_pct"] for d in bot)


def test_momentum_mom_pct_matches_ratio_formula(tmp_path, monkeypatch):
    """锁死具体数值口径：mom_pct = round((last/anchor - 1) * 100, 1)，不是别的换算。"""
    idx = pd.bdate_range("2020-01-01", periods=140)
    _write_prices_csv(tmp_path / "stocks_prices.csv", idx, {"X": 0.20, "Y": -0.15})
    monkeypatch.setattr(ol, "RAW", tmp_path)
    top, bot = ol._momentum(n=1)
    assert top[0]["symbol"] == "X" and top[0]["mom_pct"] == 20.0
    assert bot[0]["symbol"] == "Y" and bot[0]["mom_pct"] == -15.0


# ── ② index_call 的 prob>=0.5→看涨 阈值 + call/prob 字段 ───────────────────
def test_index_call_bullish_at_exactly_half(tmp_path, monkeypatch):
    monkeypatch.setattr(ol, "RAW", tmp_path)
    monkeypatch.setattr(ol, "WEB", tmp_path)
    _write_signals_json(tmp_path / "signals.json", prob=0.5, tier=3)
    out = ol.main()
    assert out["index_call"]["call"] == "看涨"                # >=0.5 边界含等号 → 看涨
    assert out["index_call"]["prob"] == 0.5
    assert out["index_call"]["tier"] == 3
    assert out["index_call"]["target"] == "纳指"


def test_index_call_bearish_just_below_half(tmp_path, monkeypatch):
    monkeypatch.setattr(ol, "RAW", tmp_path)
    monkeypatch.setattr(ol, "WEB", tmp_path)
    _write_signals_json(tmp_path / "signals.json", prob=0.4999, tier=2)
    out = ol.main()
    assert out["index_call"]["call"] == "看跌"                # <0.5 → 看跌（用未取整原值比较）


def test_index_call_none_when_signals_missing(tmp_path, monkeypatch):
    """signals.json 不存在（或读不到 latest_prob）：index_call=None，main() 不崩，
    disclaimer 仍非空——print 分支的 `if index_call else '?'` 兜底同样不炸。"""
    monkeypatch.setattr(ol, "RAW", tmp_path)
    monkeypatch.setattr(ol, "WEB", tmp_path)                  # 目录存在但没有 signals.json
    out = ol.main()
    assert out["index_call"] is None
    assert out["disclaimer"]


# ── ③ 边界：并列 / 样本不足 / 全 NaN 不崩、disclaimer 非空 ─────────────────
def test_momentum_insufficient_rows_returns_empty(tmp_path, monkeypatch):
    idx = pd.bdate_range("2020-01-01", periods=50)            # < win(126)+1
    _write_prices_csv(tmp_path / "stocks_prices.csv", idx, {"A": 0.1, "B": -0.1})
    monkeypatch.setattr(ol, "RAW", tmp_path)
    assert ol._momentum() == ([], [])


def test_momentum_all_nan_returns_empty(tmp_path, monkeypatch):
    idx = pd.bdate_range("2020-01-01", periods=140)
    df = pd.DataFrame({"A": [np.nan] * 140, "B": [np.nan] * 140}, index=idx)
    df.to_csv(tmp_path / "stocks_prices.csv", index_label="Date")
    monkeypatch.setattr(ol, "RAW", tmp_path)
    assert ol._momentum() == ([], [])


def test_momentum_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ol, "RAW", tmp_path)                  # 目录存在，stocks_prices.csv 不存在
    assert ol._momentum() == ([], [])


def test_momentum_tied_values_no_crash(tmp_path, monkeypatch):
    """并列动量值：A/B 同为+50%，C/D 同为0% → 排序稳定、不崩，n 按 2*n>总数自动降档。"""
    idx = pd.bdate_range("2020-01-01", periods=140)
    _write_prices_csv(tmp_path / "stocks_prices.csv", idx,
                       {"A": 0.5, "B": 0.5, "C": 0.0, "D": 0.0})
    monkeypatch.setattr(ol, "RAW", tmp_path)
    top, bot = ol._momentum()                                 # 4 支 < 2*n(6) → n 降为 2
    assert len(top) == 2 and len(bot) == 2
    assert {d["symbol"] for d in top} == {"A", "B"}
    assert {d["symbol"] for d in bot} == {"C", "D"}


def test_momentum_small_universe_reduces_n(tmp_path, monkeypatch):
    """观察池只有 2 支：2*n(6) > 2 → n 降为 max(1, 2//2)=1，各出 1 支不崩。"""
    idx = pd.bdate_range("2020-01-01", periods=140)
    _write_prices_csv(tmp_path / "stocks_prices.csv", idx, {"A": 0.3, "B": -0.3})
    monkeypatch.setattr(ol, "RAW", tmp_path)
    top, bot = ol._momentum()
    assert len(top) == 1 and top[0]["symbol"] == "A"
    assert len(bot) == 1 and bot[0]["symbol"] == "B"


def test_main_disclaimer_non_empty_and_mentions_risk(tmp_path, monkeypatch):
    monkeypatch.setattr(ol, "RAW", tmp_path)
    monkeypatch.setattr(ol, "WEB", tmp_path)
    _write_signals_json(tmp_path / "signals.json", prob=0.6, tier=4)
    out = ol.main()
    assert out["disclaimer"] == ol.DISCLAIMER
    assert "非投资建议" in out["disclaimer"]


def test_main_writes_outlook_json_via_util_io(tmp_path, monkeypatch, _no_real_writes):
    """main() 落盘走 util_io.write_json("outlook.json", ...)；这里验证调用形状，不验证真实落盘
    （write_json 已在 autouse fixture 中打桩为不落盘）。"""
    idx = pd.bdate_range("2020-01-01", periods=140)
    _write_prices_csv(tmp_path / "stocks_prices.csv", idx,
                       {"A": 0.5, "B": 0.3, "C": 0.1, "D": -0.05, "E": -0.2, "F": -0.4})
    monkeypatch.setattr(ol, "RAW", tmp_path)
    monkeypatch.setattr(ol, "WEB", tmp_path)
    _write_signals_json(tmp_path / "signals.json", prob=0.55, tier=3)

    out = ol.main()

    assert _no_real_writes["name"] == "outlook.json"
    assert _no_real_writes["payload"] == out
    assert len(out["bullish"]) == 3 and len(out["bearish"]) == 3
    assert "generated" in out and out["generated"].endswith("Z")
