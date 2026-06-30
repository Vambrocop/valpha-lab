"""test_llm_prediction.py — AI 前瞻前向计分:解析/分桶命中口径/结算/去重/无key跳过/初始诚实
（合成数据·不联网:价格用 prices= 注入、LLM 用 _gen= 注入；不落盘 web/docs）。"""
import csv

import numpy as np
import pandas as pd
import pytest

import llm_prediction as lp


def _spy(p0, p1, periods=20, start="2026-05-01"):
    idx = pd.bdate_range(start=start, periods=periods)
    return pd.Series(np.linspace(p0, p1, periods), index=idx)


def _rows():
    with open(lp.LOG, encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def patched(tmp_path, monkeypatch):
    monkeypatch.setattr(lp, "LOG", tmp_path / "pred_log.csv")
    import util_io
    monkeypatch.setattr(util_io, "write_json", lambda *a, **k: None)
    return tmp_path


# ── 解析:严格三行 → dict;方向/信心缺失或非法 → None(不记垃圾)──────────
def test_parse_valid():
    p = lp._parse("方向: 偏多\n信心: 高\n理由: 因为收益率曲线偏陡。")
    assert p == {"direction": "偏多", "confidence": "高", "reason": "因为收益率曲线偏陡。"}


def test_parse_missing_or_illegal_returns_none():
    assert lp._parse("信心: 中\n理由: 没有方向") is None        # 缺方向
    assert lp._parse("方向: 看涨\n信心: 中") is None            # 方向非法词
    assert lp._parse("") is None and lp._parse(None) is None


# ── 分桶命中口径:实际 5 日收益落桶 == 预测方向 → 命中 ────────────────────
def test_bucket_thresholds():
    assert lp._bucket(0.02) == "偏多" and lp._bucket(-0.02) == "偏空"
    assert lp._bucket(0.003) == "中性" and lp._bucket(-0.003) == "中性"   # ±1% 带内=中性


def test_outcome_hit_when_direction_matches_bucket():
    assert lp._outcome(0.02, 0.02, {"direction": "偏多"})["hit"] is True
    assert lp._outcome(0.02, 0.02, {"direction": "偏空"})["hit"] is False
    assert lp._outcome(0.000, 0.0, {"direction": "中性"})["hit"] is True
    assert lp._outcome(0.02, 0.02, {"direction": "偏多"})["bucket"] == "偏多"


# ── 结算:注入 SPY 价格,挂账预测满 5 交易日 → 命中正确 ───────────────────
def _seed_pending(direction, date="2026-05-01"):
    lp.fl.write_log(lp.LOG, lp.HEADER, [{
        "pred_date": date, "symbol": lp.SYMBOL, "direction": direction, "confidence": "中",
        "reason": "测试", "horizon_td": lp.HOLD_TD, "settled": False, "dropped": False}])


def test_settles_and_scores_hit(patched):
    _seed_pending("偏多")
    out = lp.run(write=True, prices={lp.SYMBOL: _spy(100, 110)}, _gen=lambda: None)  # 涨→偏多桶
    r = _rows()[0]
    assert lp.fl.is_true(r["settled"]) and r["bucket"] == "偏多" and lp.fl.is_true(r["hit"])
    assert out["track_record"]["n_settled"] == 1 and out["track_record"]["hit_pct"] == 100.0


def test_settles_and_scores_miss(patched):
    _seed_pending("偏空")                                    # 预测偏空,但实际涨→偏多桶→未命中
    lp.run(write=True, prices={lp.SYMBOL: _spy(100, 110)}, _gen=lambda: None)
    r = _rows()[0]
    assert lp.fl.is_true(r["settled"]) and r["bucket"] == "偏多" and not lp.fl.is_true(r["hit"])


# ── 生成 + 去重:今日只 append 一条;同日重跑不重复 ──────────────────────
def test_generates_one_per_day_and_dedup(patched):
    gen = lambda: {"direction": "中性", "confidence": "低", "reason": "信号混杂"}
    lp.run(write=True, prices={lp.SYMBOL: _spy(100, 101)}, _gen=gen)
    lp.run(write=True, prices={lp.SYMBOL: _spy(100, 101)}, _gen=gen)   # 同日再跑
    today_rows = [r for r in _rows() if r["pred_date"] == __import__("datetime").date.today().isoformat()]
    assert len(today_rows) == 1                              # 一天一条


def test_no_new_row_when_gen_none(patched):
    lp.run(write=True, prices={lp.SYMBOL: _spy(100, 101)}, _gen=lambda: None)  # 无 key/解析失败
    assert _rows() == []                                     # 不记垃圾


def test_settles_bearish_hit_on_decline(patched):
    _seed_pending("偏空")                                    # 预测偏空,实际跌→偏空桶→命中(补 S3:第三个角)
    lp.run(write=True, prices={lp.SYMBOL: _spy(110, 100)}, _gen=lambda: None)
    r = _rows()[0]
    assert r["bucket"] == "偏空" and lp.fl.is_true(r["hit"])


def test_pending_not_elapsed_stays_unsettled(patched):
    # S4:窗口未走完(价格序列止于入场后仅 2 个交易日)→ 必须 pending、绝不结算(前向命门)
    lp.fl.write_log(lp.LOG, lp.HEADER, [{"pred_date": "2026-05-01", "symbol": lp.SYMBOL,
        "direction": "偏多", "confidence": "中", "reason": "x", "horizon_td": lp.HOLD_TD,
        "settled": False, "dropped": False}])
    out = lp.run(write=True, prices={lp.SYMBOL: _spy(100, 102, periods=3, start="2026-05-01")}, _gen=lambda: None)
    assert out["track_record"]["n_settled"] == 0 and out["track_record"]["n_pending"] == 1
    assert not lp.fl.is_true(_rows()[0]["settled"])


def test_by_confidence_scoring(patched):
    # S2:计分牌按信心分桶(高信心是否真更准)——这是诚实卖点,必须有测试。全程喂涨→实际=偏多桶。
    seeds = [("偏多", "高"), ("偏空", "高"), ("偏多", "中"), ("偏空", "低")]  # 高:1对1错、中:对、低:错
    lp.fl.write_log(lp.LOG, lp.HEADER, [{"pred_date": f"2026-05-0{i+1}", "symbol": lp.SYMBOL,
        "direction": d, "confidence": c, "reason": "x", "horizon_td": lp.HOLD_TD,
        "settled": False, "dropped": False} for i, (d, c) in enumerate(seeds)])
    out = lp.run(write=True, prices={lp.SYMBOL: _spy(100, 110, periods=30)}, _gen=lambda: None)
    bc = out["track_record"]["by_confidence"]
    assert bc["高"]["n"] == 2 and bc["高"]["hit_pct"] == 50.0     # 偏多对、偏空错
    assert bc["中"]["hit_pct"] == 100.0 and bc["低"]["hit_pct"] == 0.0


def test_verdict_zero_settled_is_honest(patched):
    out = lp.run(write=True, prices={lp.SYMBOL: _spy(100, 101)},
                 _gen=lambda: {"direction": "中性", "confidence": "低", "reason": "x"})
    assert out["track_record"]["n_settled"] == 0
    assert "0 结算" in out["verdict"]
    assert "非投资建议" in out["caveat"] and "会错" in out["caveat"] and "认账" in out["caveat"]
