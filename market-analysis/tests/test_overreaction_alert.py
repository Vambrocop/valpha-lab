"""test_overreaction_alert.py — 极端下跌→次日反弹告警 的检测/结算/去重逻辑（合成数据·不联网·不推送）。"""
import csv
import numpy as np
import pandas as pd
import pytest

import overreaction_alert as oa


def _series(rets, start="2001-01-02"):
    """从日收益构造收盘价序列（交易日索引）。"""
    idx = pd.bdate_range(start=start, periods=len(rets) + 1)
    px = [100.0]
    for r in rets:
        px.append(px[-1] * (1 + r))
    return pd.Series(px, index=idx)


def _rows():
    with open(oa.LOG, encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def patched(tmp_path, monkeypatch):
    monkeypatch.setattr(oa, "LOG", tmp_path / "sig_log.csv")
    monkeypatch.setattr(oa, "_modern_stat",
                        lambda: {"bounce_next_pct": 0.294, "other_next_pct": 0.018,
                                 "p_value": 0.001, "pct_negative": 46.3})
    import util_io
    monkeypatch.setattr(util_io, "write_json", lambda *a, **k: None)  # 不落盘到 web/docs
    return tmp_path


def test_trigger_on_extreme_drop(patched, monkeypatch):
    rng = np.random.default_rng(0)
    rets = list(rng.normal(0.0005, 0.01, 600)) + [-0.08]      # 末日 -8% 必触发
    monkeypatch.setattr(oa, "_sp_close", lambda: _series(rets))
    out = oa.run(write=True, push=False)
    assert out["today"]["triggered"] is True
    assert out["today"]["ret_pct"] <= out["threshold_pct"]
    rows = _rows()
    assert len(rows) == 1 and rows[0]["signal"] == "next_day_lean_up"
    assert str(rows[0]["settled"]).lower() != "true"          # 触发当日次日未到 → 未结算


def test_no_trigger_on_normal_day(patched, monkeypatch):
    rng = np.random.default_rng(2)
    rets = list(rng.normal(0.0005, 0.01, 600)) + [0.005]      # 末日普通正收益
    monkeypatch.setattr(oa, "_sp_close", lambda: _series(rets))
    out = oa.run(write=True, push=False)
    assert out["today"]["triggered"] is False
    assert len(_rows()) == 0                                  # 无触发无挂账


def test_settlement_hit(patched, monkeypatch):
    rng = np.random.default_rng(1)
    base = list(rng.normal(0.0005, 0.01, 600))
    monkeypatch.setattr(oa, "_sp_close", lambda: _series(base + [-0.08]))
    oa.run(write=True, push=False)                            # 触发(第600日)
    monkeypatch.setattr(oa, "_sp_close", lambda: _series(base + [-0.08, 0.02]))
    out = oa.run(write=True, push=False)                      # 次日 +2% 到来
    rows = _rows()
    assert len(rows) == 1                                     # 未重复触发(同日去重)
    assert str(rows[0]["settled"]).lower() == "true"
    assert str(rows[0]["hit"]).lower() == "true"              # 次日涨 → 命中
    assert out["track_record"]["n_settled"] == 1 and out["track_record"]["n_hit"] == 1


def test_settlement_miss(patched, monkeypatch):
    rng = np.random.default_rng(3)
    base = list(rng.normal(0.0005, 0.01, 600))
    monkeypatch.setattr(oa, "_sp_close", lambda: _series(base + [-0.08]))
    oa.run(write=True, push=False)
    monkeypatch.setattr(oa, "_sp_close", lambda: _series(base + [-0.08, -0.012]))
    out = oa.run(write=True, push=False)                      # 次日 -1.2% → 未中
    rows = _rows()
    assert str(rows[0]["hit"]).lower() == "false"
    assert out["track_record"]["n_settled"] == 1 and out["track_record"]["n_hit"] == 0


def test_append_only_no_duplicate(patched, monkeypatch):
    rng = np.random.default_rng(4)
    rets = list(rng.normal(0.0005, 0.01, 600)) + [-0.08]
    monkeypatch.setattr(oa, "_sp_close", lambda: _series(rets))
    oa.run(write=True, push=False)
    oa.run(write=True, push=False)                            # 同日再跑
    assert len(_rows()) == 1                                  # 不重复记
