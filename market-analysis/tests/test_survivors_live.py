"""test_survivors_live.py — 存活规律观察台单测。

不碰真数据/真 autodiscovery：合成价 CSV + 合成 autodiscovery.json，把"应期判定 / 方向标注(尤其负向) /
优雅降级 / 未接入新规律 / 诚实框 / 排序"每条路径跑出来断言。命门复用生产模块 survivors_live，不复制逻辑。
"""
import json
import types
import datetime

import numpy as np
import pandas as pd

import survivors_live as sl


# ════════════════════════════════════════════════════════════════════════════
# 1. 纯逻辑：方向标注 — 负向不能按族名想当然（回撤族 up<base 必须报偏负）
# ════════════════════════════════════════════════════════════════════════════
def test_dnote_directions():
    assert sl._dnote(75, 62) == "明显偏正"
    assert sl._dnote(66, 63) == "微弱偏正"
    assert sl._dnote(51, 54) == "微弱偏负"        # 反弹族 up<base → 偏负(反直觉,不能当利好)
    assert sl._dnote(45, 62) == "明显偏负"
    assert sl._dnote(52, 52) == "≈基率(几乎无差别)"
    assert sl._dnote(None, 62) == "方向不明"


def test_pick_window_prefers_2000_then_full():
    cand = {"windows": [{"label": "完整", "up_pct": 60, "base_pct": 58},
                        {"label": "2000后", "up_pct": 66, "base_pct": 63}]}
    assert sl._pick_window(cand) == (66, 63, "2000后")
    cand2 = {"windows": [{"label": "完整", "up_pct": 60, "base_pct": 58}]}
    assert sl._pick_window(cand2) == (60, 58, "完整")
    assert sl._pick_window({"windows": []}) == (None, None, None)


# ════════════════════════════════════════════════════════════════════════════
# 2. 当前态函数：合成价打进 tmp RAW
# ════════════════════════════════════════════════════════════════════════════
def _price(path, values, start="2000-01-01"):
    idx = pd.bdate_range(start, periods=len(values))
    pd.Series(values, index=idx, name="close").to_csv(path, header=True)


def test_golden_cross_active_when_uptrend(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    _price(tmp_path / "SP500_long.csv", list(np.linspace(100, 300, 400)))
    active, state = sl._golden_cross_state()
    assert active is True and "金叉成立" in state


def test_golden_cross_inactive_when_downtrend(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    _price(tmp_path / "SP500_long.csv", list(np.linspace(300, 100, 400)))
    active, state = sl._golden_cross_state()
    assert active is False and "未成立" in state


def test_golden_cross_missing_data_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)          # 无 CSV
    active, state = sl._golden_cross_state()
    assert active is None and "不足" in state


def test_btc_mom_active_and_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    vals = [100.0] * 40
    vals[-1] = 110.0                                  # last/[-21] = 110/100 = +10% > 5%
    _price(tmp_path / "BTC.csv", vals)
    active, state = sl._btc_mom_state()
    assert active is True and "高于" in state


def test_btc_mom_inactive_below_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    _price(tmp_path / "BTC.csv", [100.0] * 40)        # 0% 动量 < 5%
    active, state = sl._btc_mom_state()
    assert active is False and "未高于" in state


def test_rebound_active_on_crash_day(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    rets = np.tile([0.01, -0.01, 0.005, -0.005, 0.0], 220)   # 1100 天,5%分位≈-0.01
    px = 100 * np.cumprod(1 + rets)
    px = np.append(px, px[-1] * 0.90)                 # 末日 -10% → 必 ≤ 5%分位
    _price(tmp_path / "NASDAQ_COMP_long.csv", list(px))
    active, state = sl._rebound_state()
    assert active is True and "跌进" in state


def test_rebound_inactive_on_calm_day(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    rets = np.tile([0.01, -0.01, 0.005, -0.005, 0.0], 220)
    px = 100 * np.cumprod(1 + rets)
    px = np.append(px, px[-1] * 1.02)                 # 末日 +2% → 高于 5%分位
    _price(tmp_path / "NASDAQ_COMP_long.csv", list(px))
    active, state = sl._rebound_state()
    assert active is False and "未跌进" in state


def _freeze_month(monkeypatch, y, m, d):
    class _D(datetime.date):
        @classmethod
        def today(cls):
            return datetime.date(y, m, d)
    monkeypatch.setattr(sl, "datetime",
                        types.SimpleNamespace(date=_D, datetime=datetime.datetime, timezone=datetime.timezone))


def test_september_active_only_in_september(monkeypatch):
    _freeze_month(monkeypatch, 2024, 9, 15)
    active, state = sl._september_state()
    assert active is True and "应期" in state


def test_september_dormant_other_months(monkeypatch):
    _freeze_month(monkeypatch, 2024, 7, 1)
    active, state = sl._september_state()
    assert active is False and "非 9 月" in state


# ════════════════════════════════════════════════════════════════════════════
# 3. build()：只取 verdict==survive、算应期、排序、未接入新规律、诚实框、优雅降级
# ════════════════════════════════════════════════════════════════════════════
def _autodisc(tmp_path, candidates):
    (tmp_path / "autodiscovery.json").write_text(
        json.dumps({"candidates": candidates}, ensure_ascii=False), encoding="utf-8")


def test_build_extracts_survivors_flags_sorts(tmp_path, monkeypatch):
    web = tmp_path / "web"; raw = tmp_path / "raw"
    web.mkdir(); raw.mkdir()
    monkeypatch.setattr(sl, "WEB", web)
    monkeypatch.setattr(sl, "RAW", raw)
    _price(raw / "SP500_long.csv", list(np.linspace(100, 300, 400)))   # 金叉应期
    _freeze_month(monkeypatch, 2024, 7, 1)                             # 九月休眠
    _autodisc(web, [
        {"family": "regime", "key": "golden_cross_sp500", "verdict": "survive",
         "recent_p": 0.026, "modern_status": "现代仍有效",
         "windows": [{"label": "2000后", "up_pct": 66, "base_pct": 63}]},
        {"family": "calendar", "key": "september_sp500", "verdict": "survive",
         "recent_p": 0.03, "modern_status": "现代仍有效",
         "windows": [{"label": "2000后", "up_pct": 54, "base_pct": 51}]},
        {"family": "factor", "key": "some_dead_thing", "verdict": "dead",
         "windows": [{"label": "2000后", "up_pct": 50, "base_pct": 50}]},   # 非 survive → 排除
        {"family": "newfam", "key": "brand_new", "verdict": "survive",       # 未接入描述符
         "windows": [{"label": "完整", "up_pct": 70, "base_pct": 60}]},
    ])
    out = sl.build()
    assert out["n_survivors"] == 3                     # dead 被排除
    keys = [s["key"] for s in out["survivors"]]
    assert "some_dead_thing" not in keys
    # 金叉应期 True 排最前；未接入(None)排最后
    assert out["survivors"][0]["key"] == "golden_cross_sp500"
    assert out["survivors"][0]["active"] is True
    assert out["survivors"][-1]["key"] == "brand_new"
    assert out["survivors"][-1]["active"] is None
    assert "未接入" in out["survivors"][-1]["state"]
    assert out["n_active"] == 1
    # 九月休眠但仍在清单(常驻)
    sep = next(s for s in out["survivors"] if s["key"] == "september_sp500")
    assert sep["active"] is False
    assert "54% vs 基率 51%" in sep["edge_plain"] and "微弱偏正" in sep["edge_plain"]


def test_build_caveat_has_honest_frame(tmp_path, monkeypatch):
    web = tmp_path / "web"; web.mkdir()
    monkeypatch.setattr(sl, "WEB", web)
    monkeypatch.setattr(sl, "RAW", tmp_path)
    _autodisc(web, [])
    out = sl.build()
    cav = out["caveat"]
    assert "非预测" in cav and ("OOS" in cav or "未确认" in cav) and "过去≠未来" in cav


def test_build_missing_autodiscovery_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "WEB", tmp_path)           # 空目录,无 autodiscovery.json
    assert sl.build() is None
