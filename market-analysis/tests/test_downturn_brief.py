"""test_downturn_brief.py — 大跌日诚实数据包（W4a）单测。

全部合成数据 monkeypatch（不联网、不碰真实 web/*.json、不落真实账本）。
覆盖任务规格 5 类 + 补充边界：
①-2.5% 触发 / -1% 不触发  ②VXSMH 复合条件  ③同日第二次不重推(幂等)
④未配置 token 不落账不消费  ⑤消息含"非投资建议"+具体日期
"""
import csv

import pytest

import downturn_brief as db


# ── fixtures 工厂 ──────────────────────────────────────────────────────
def _market(nasdaq_d1=-0.5, sp500_d1=-0.5, vix=17.0, vix_d1=2.0, date="2026-07-17"):
    return {"date": date, "nasdaq_d1": nasdaq_d1, "sp500_d1": sp500_d1,
            "vix": vix, "vix_d1": vix_d1}


def _autodisc():
    """连跌/长跨度族各造几条候选，含存活与未存活，验证 _family_survival 真实计数。"""
    return {
        "context_states": {
            "asof": "2026-07-17",
            "indices": {
                "nasdaq": {"down_streak": 2,
                          "trailing": {"63d": {"ret": 0.05, "pctile": 60.0, "zone": "mid"}}},
                "sp500": {"down_streak": 3,
                         "trailing": {"63d": {"ret": 0.03, "pctile": 55.0, "zone": "mid"}}},
            },
        },
        "candidates": [
            {"family": "streak_down", "verdict": "dead"},
            {"family": "streak_down", "verdict": "dead"},
            {"family": "streak_break", "verdict": "dead"},
            {"family": "trailing_extreme", "verdict": "dead"},
            {"family": "trailing_extreme", "verdict": "survive"},   # 刻意放一个存活，验证不是硬编码0
            {"family": "rebound", "verdict": "survive"},            # 无关族不应计入
        ],
    }


def _risk(vxsmh_status="ok", vxsmh_close=62.3):
    vxsmh = {"status": vxsmh_status}
    if vxsmh_status == "ok":
        vxsmh.update({"close": vxsmh_close, "date": "2026-07-16", "launch_date": "2025-09-16",
                      "n_days": 209, "pctile_since_launch": 98.1})
    return {
        "horizon": 20,
        "vxsmh": vxsmh,
        "downside_by_vix": [
            {"vix_lo": 9.1, "vix_hi": 13.9, "downside_q05_pct": -5.37},
            {"vix_lo": 13.9, "vix_hi": 17.5, "downside_q05_pct": -6.86},
            {"vix_lo": 17.5, "vix_hi": 22.9, "downside_q05_pct": -11.61},
            {"vix_lo": 22.9, "vix_hi": 82.7, "downside_q05_pct": -12.01},
        ],
    }


def _ovr_signal(triggered=False):
    return {
        "q_pctile": 5.0, "threshold_pct": -1.838,
        "today": {"date": "2026-07-17", "ret_pct": -1.01, "triggered": triggered},
        "modern_stat": {"bounce_next_pct": 0.284, "other_next_pct": 0.019,
                        "p_value": 0.000999, "pct_negative": 46.3},
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    """隔离 LOG，喂全套合成 json 数据源，_send 换成记录器（默认成功），配好假 token。"""
    log = tmp_path / "downturn_brief_log.csv"
    monkeypatch.setattr(db, "LOG", log)
    monkeypatch.setattr(db, "_load_autodiscovery", lambda: _autodisc())
    monkeypatch.setattr(db, "_load_risk_dashboard", lambda: _risk())
    monkeypatch.setattr(db, "_load_overreaction_signal", lambda: _ovr_signal())
    monkeypatch.setattr(db, "_load_overreaction_full", lambda: {})
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    sent = []
    monkeypatch.setattr(db, "_send", lambda text: sent.append(text) or True)

    class Env:
        pass
    e = Env()
    e.log, e.sent = log, sent
    return e


def _rows(log):
    with open(log, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ── ①机械阈值：-2.5% 触发 / -1% 不触发（直测 check_trigger 纯函数）───────
def test_check_trigger_big_drop_boundary():
    triggered, reasons = db.check_trigger(_market(nasdaq_d1=-2.5), None)   # 边界含等号
    assert triggered and any("①" in r for r in reasons)

    triggered, reasons = db.check_trigger(_market(nasdaq_d1=-2.9, sp500_d1=-2.0), None)
    assert triggered and any("纳指" in r for r in reasons)

    triggered, reasons = db.check_trigger(_market(nasdaq_d1=-1.0, sp500_d1=-1.0, vix_d1=0.0), None)
    assert not triggered and reasons == []


# ── ②VXSMH 复合条件：两个子条件都要满足才触发 ─────────────────────────
def test_check_trigger_vxsmh_compound():
    m = _market(nasdaq_d1=-1.6, vix_d1=0.0)
    triggered, reasons = db.check_trigger(m, 65.0)               # VXSMH≥60 且纳指≤-1.5% → 触发
    assert triggered and any("②" in r for r in reasons)

    triggered, _ = db.check_trigger(m, 55.0)                     # VXSMH 不够高 → 不触发
    assert not triggered

    m2 = _market(nasdaq_d1=-1.0, vix_d1=0.0)                     # VXSMH 够高但纳指跌幅不够
    triggered, _ = db.check_trigger(m2, 65.0)
    assert not triggered

    triggered, _ = db.check_trigger(m, None)                     # VXSMH 数据缺失 → 直接判不触发
    assert not triggered


# ── VIX 单日涨幅阈值 ────────────────────────────────────────────────────
def test_check_trigger_vix_spike():
    triggered, reasons = db.check_trigger(_market(vix_d1=15.0), None)
    assert triggered and any("③" in r for r in reasons)
    triggered, _ = db.check_trigger(_market(vix_d1=14.9), None)
    assert not triggered


# ── 未触发 → 零行为(不建账本、不推送) ───────────────────────────────────
def test_run_no_trigger_zero_behavior(env, monkeypatch):
    monkeypatch.setattr(db, "_load_market", lambda: _market())   # 温和日
    out = db.run()
    assert out == {"triggered": False}
    assert not env.log.exists()
    assert env.sent == []


# ── ③同日第二次不重推(幂等) ─────────────────────────────────────────────
def test_run_idempotent_same_day(env, monkeypatch):
    monkeypatch.setattr(db, "_load_market", lambda: _market(nasdaq_d1=-2.9))
    out1 = db.run()
    assert out1 == {"triggered": True, "pushed": True}
    assert len(_rows(env.log)) == 1
    assert len(env.sent) == 1

    out2 = db.run()                                              # 同日再跑
    assert out2 == {"triggered": True, "skipped_dup": True}
    assert len(_rows(env.log)) == 1                              # 未重复记
    assert len(env.sent) == 1                                    # 未重复推


# ── ④未配置 token → 完全跳过不落账不消费；有 token 后仍可首推 ───────────
def test_no_token_skips_without_consuming(env, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    monkeypatch.setattr(db, "_load_market", lambda: _market(nasdaq_d1=-2.9))
    out = db.run()
    assert out == {"triggered": True, "pushed": False, "skipped_no_token": True}
    assert not env.log.exists() and env.sent == []               # 没落账、没消费

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")        # 环境恢复(如切到 CI)
    out2 = db.run()
    assert out2 == {"triggered": True, "pushed": True}
    assert len(_rows(env.log)) == 1 and len(env.sent) == 1


# ── 推送失败 → pushed=False 落账，下轮同日不重试 ─────────────────────────
def test_push_failure_logs_false_and_no_retry(env, monkeypatch):
    monkeypatch.setattr(db, "_load_market", lambda: _market(nasdaq_d1=-2.9))
    monkeypatch.setattr(db, "_send", lambda text: False)          # 网络闪断
    out = db.run()
    assert out == {"triggered": True, "pushed": False}
    rows = _rows(env.log)
    assert rows[0]["pushed"] == "False"

    monkeypatch.setattr(db, "_send", lambda text: True)           # 恢复能力
    out2 = db.run()
    assert out2 == {"triggered": True, "skipped_dup": True}       # 同日不重试
    assert len(_rows(env.log)) == 1


# ── ⑤消息含"非投资建议"+具体日期(防披露被删/防"今天"糊弄) ────────────────
def test_message_contains_disclaimer_and_concrete_date(env, monkeypatch):
    market = _market(nasdaq_d1=-2.9, date="2026-07-17")
    monkeypatch.setattr(db, "_load_market", lambda: market)
    db.run()
    assert len(env.sent) == 1
    msg = env.sent[0]
    assert "非投资建议" in msg
    assert "2026-07-17" in msg                                   # 具体交易日日期
    assert "今天" not in msg                                     # 不用无具体日期的模糊"今天"


# ── 族存活计数是真算的，不是硬编码 30/14（改数据 → 消息跟着变）───────────
def test_family_survival_counts_are_real_not_hardcoded(env, monkeypatch):
    monkeypatch.setattr(db, "_load_market", lambda: _market(nasdaq_d1=-2.9))
    db.run()
    msg = env.sent[0]
    # fixture 里 streak 族 3 条全 dead → 0/3；trailing 族 2 条 1 存活 → 1/2（不是生产环境的 0/30、0/14）
    assert "0/3 过校正" in msg
    assert "1/2 过校正" in msg


# ── 条件下行分位按当前 VIX 落档，不是固定档 ──────────────────────────────
def test_downside_bin_matches_current_vix(env, monkeypatch):
    monkeypatch.setattr(db, "_load_market", lambda: _market(nasdaq_d1=-2.9, vix=20.0))
    db.run()
    msg = env.sent[0]
    assert "[17.5-22.9]" in msg and "-11.61%" in msg               # 20.0 落在这档


def test_downside_bin_helper_clamps_out_of_range():
    bins = _risk()["downside_by_vix"]
    assert db._downside_bin(5.0, bins) == bins[0]                 # 低于最低档 → 钳到首档
    assert db._downside_bin(90.0, bins) == bins[-1]                # 高于最高档 → 钳到尾档
    assert db._downside_bin(20.0, bins) == bins[2]


# ── 无 combined_prices 数据 → 安静跳过 ───────────────────────────────────
def test_no_market_data_returns_none(env, monkeypatch):
    monkeypatch.setattr(db, "_load_market", lambda: None)
    assert db.run() is None
    assert not env.log.exists()
