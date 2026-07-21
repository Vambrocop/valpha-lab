"""test_ipo_aftermath.py — 重大 IPO 挂牌后事实档（W4b·A5）单测。

全部合成数据·不碰网络（monkeypatch 掉 _fetch_series）。覆盖任务规格：
①D1/D5/D20 计算(首日收盘基准) ②vs QQQ 同窗差 ③alert_lead_days 符号与三态判定
④幂等不重记(完成度未变) ⑤窗口走完后 append 新行且历史行不变(append-only)
⑥fail-soft(单票无数据跳过不崩) ⑦JSON 输出取每 ticker 最后一行 ⑧零观察对象零行为。
"""
import csv
import json

import pandas as pd
import pytest

import ipo_aftermath as am


# ── fixtures 工厂 ──────────────────────────────────────────────────────
def _alert_row(date_utc, cik, company, ticker, stage, form="424B4"):
    return {"date_utc": date_utc, "cik": cik, "company": company, "ticker": ticker,
            "stage": stage, "form": form, "tier_reasons": "amount", "adsh": "", "pushed": "True"}


def _write_alert_log(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date_utc", "cik", "company", "ticker", "stage",
                                           "form", "tier_reasons", "adsh", "pushed"])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _series(start, prices):
    """business-day 序列，首日=prices[0]。"""
    idx = pd.bdate_range(start=start, periods=len(prices))
    return pd.Series(prices, index=idx)


@pytest.fixture
def env(tmp_path, monkeypatch):
    alert_log = tmp_path / "ipo_alert_log.csv"
    log = tmp_path / "ipo_aftermath_log.csv"
    out = tmp_path / "ipo_aftermath.json"
    monkeypatch.setattr(am, "ALERT_LOG", alert_log)
    monkeypatch.setattr(am, "LOG", log)
    monkeypatch.setattr(am, "OUT", out)

    class Env:
        pass
    e = Env()
    e.alert_log, e.log, e.out = alert_log, log, out
    return e


def _rows(log):
    with open(log, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ── ① D1/D5/D20 计算（首日收盘基准）──────────────────────────────────────
def test_d1_d5_d20_calc(env, monkeypatch):
    _write_alert_log(env.alert_log, [_alert_row("2026-06-01T00:00:00Z", "0001", "AlphaCo", "ALPX", "listed")])
    # 首日100 → D1=110(+10%) → D5=120(+20%) → D20=90(-10%)；25 个交易日供 D20 走完
    prices = [100, 110, 101, 102, 103, 120, 105, 106, 107, 108,
              109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 90] + [91] * 4
    stock = _series("2026-06-10", prices)
    qqq = _series("2026-06-01", [50] * 60)   # QQQ 走平，方便②单独测非零场景
    monkeypatch.setattr(am, "_fetch_series", lambda t, start=am.FETCH_START:
                         stock if t == "ALPX" else qqq)
    out = am.run()
    assert out["n_checked"] == 1 and out["n_new"] == 1
    rows = _rows(env.log)
    assert len(rows) == 1
    r = rows[0]
    assert r["first_trade_date"] == "2026-06-10"
    assert float(r["d1_pct"]) == pytest.approx(10.0)
    assert float(r["d5_pct"]) == pytest.approx(20.0)
    assert float(r["d20_pct"]) == pytest.approx(-10.0)


# ── ② vs QQQ 同窗超额（QQQ 同期也涨，超额 = 差值而非股票自己的涨幅）────────
def test_vs_qqq_d20_diff(env, monkeypatch):
    _write_alert_log(env.alert_log, [_alert_row("2026-06-01T00:00:00Z", "0002", "BetaCo", "BETX", "listed")])
    stock_prices = [100] + [100] * 19 + [120]     # D20 = +20%
    stock = _series("2026-06-10", stock_prices)
    # QQQ 从股票首交易日(06-10)起算窗口：06-10 落在这条 QQQ 序列的第 7 个交易日(pos7)=200，
    # 第 20 个交易日之后(pos27)=220 → +10%（验证的是"从股票首交易日对齐"而非 QQQ 自己的首行）
    qqq_prices = [199] * 7 + [200] + [201] * 19 + [220] + [221] * 5
    qqq = _series("2026-06-01", qqq_prices)
    monkeypatch.setattr(am, "_fetch_series", lambda t, start=am.FETCH_START:
                         stock if t == "BETX" else qqq)
    out = am.run()
    assert out["n_new"] == 1
    r = _rows(env.log)[0]
    assert float(r["d20_pct"]) == pytest.approx(20.0)
    assert float(r["vs_qqq_d20_pct"]) == pytest.approx(10.0)   # 20% - 10%


# ── ③ alert_lead_days 符号 + 三态判定 ────────────────────────────────────
def test_lead_days_sign_and_three_states(env, monkeypatch):
    _write_alert_log(env.alert_log, [
        # 提前预警：账本记录(2026-06-01)早于实际首交易日(2026-06-10)
        _alert_row("2026-06-01T00:00:00Z", "0003", "LeadCo", "LEDX", "priced"),
        # 迟到但已确认挂牌：账本记录(2026-06-15)晚于首交易日(2026-06-10)，stage=listed
        _alert_row("2026-06-15T00:00:00Z", "0004", "LateCo", "LATX", "listed"),
        # 迟到且从未确认挂牌：账本记录(2026-06-15)晚于首交易日(2026-06-10)，stage仅到priced
        _alert_row("2026-06-15T00:00:00Z", "0005", "MissCo", "MISX", "priced"),
    ])
    short = _series("2026-06-10", [100, 101])   # 只需首交易日，够算 lead_days 即可
    monkeypatch.setattr(am, "_fetch_series", lambda t, start=am.FETCH_START: short)
    am.run()
    by_ticker = {r["ticker"]: r for r in _rows(env.log)}
    assert int(by_ticker["LEDX"]["alert_lead_days"]) == 9 and by_ticker["LEDX"]["alert_quality"] == "lead"
    assert int(by_ticker["LATX"]["alert_lead_days"]) == -5 and by_ticker["LATX"]["alert_quality"] == "late"
    assert int(by_ticker["MISX"]["alert_lead_days"]) == -5 and by_ticker["MISX"]["alert_quality"] == "missed"


# ── ④ 幂等：完成度未变(仍只有 D1，D5/D20 窗口未走完) → 不重 append ─────────
def test_idempotent_when_completion_unchanged(env, monkeypatch):
    _write_alert_log(env.alert_log, [_alert_row("2026-06-01T00:00:00Z", "0006", "IdemCo", "IDMX", "listed")])
    short = _series("2026-07-01", [100, 105])    # 只够 D1，D5/D20 pending
    monkeypatch.setattr(am, "_fetch_series", lambda t, start=am.FETCH_START: short)
    out1 = am.run()
    assert out1["n_new"] == 1
    out2 = am.run()                              # 数据源不变 → 完成度不变 → 幂等
    assert out2["n_new"] == 0
    assert len(_rows(env.log)) == 1


# ── ⑤ 窗口走完后 append 新行，历史行逐字节不变（append-only）─────────────
def test_new_row_appended_when_window_completes_history_untouched(env, monkeypatch):
    _write_alert_log(env.alert_log, [_alert_row("2026-06-01T00:00:00Z", "0007", "GrowCo", "GROX", "listed")])
    short = _series("2026-07-01", [100, 105])
    monkeypatch.setattr(am, "_fetch_series", lambda t, start=am.FETCH_START: short)
    am.run()
    before = env.log.read_bytes()

    longer = _series("2026-07-01", [100, 105, 106, 107, 108, 109, 110] + [111] * 15)  # D5 现在可算
    monkeypatch.setattr(am, "_fetch_series", lambda t, start=am.FETCH_START: longer)
    out = am.run()
    assert out["n_new"] == 1
    after = env.log.read_bytes()
    assert after[:len(before)] == before          # 历史前缀逐字节不变
    rows = _rows(env.log)
    assert len(rows) == 2
    assert rows[0]["d5_pct"] == "" and rows[1]["d5_pct"] != ""


# ── ⑥ fail-soft：单票无数据 → 跳过不崩，不影响其它公司 ────────────────────
def test_fail_soft_skips_ticker_with_no_data(env, monkeypatch):
    _write_alert_log(env.alert_log, [
        _alert_row("2026-06-01T00:00:00Z", "0008", "GoodCo", "GOODX", "listed"),
        _alert_row("2026-06-01T00:00:00Z", "0009", "BadCo", "BADX", "listed"),
    ])
    good = _series("2026-06-10", [100, 105])

    def fake_fetch(t, start=am.FETCH_START):
        if t == "GOODX":
            return good
        if t == "BADX":
            return None                            # yfinance 失败/无数据
        return good                                 # QQQ 兜底
    monkeypatch.setattr(am, "_fetch_series", fake_fetch)
    out = am.run()
    assert out["n_checked"] == 1 and out["n_skipped_no_data"] == 1
    rows = _rows(env.log)
    assert len(rows) == 1 and rows[0]["ticker"] == "GOODX"


# ── ⑦ JSON 输出：每 ticker 取账本最后一行 + caveat/disclaimer 齐全 ────────
def test_json_output_latest_row_per_ticker(env, monkeypatch):
    _write_alert_log(env.alert_log, [_alert_row("2026-06-01T00:00:00Z", "0010", "JsonCo", "JSNX", "listed")])
    short = _series("2026-07-01", [100, 105])
    monkeypatch.setattr(am, "_fetch_series", lambda t, start=am.FETCH_START: short)
    am.run()
    longer = _series("2026-07-01", [100, 105, 106, 107, 108, 109, 110] + [111] * 15)
    monkeypatch.setattr(am, "_fetch_series", lambda t, start=am.FETCH_START: longer)
    am.run()

    payload = json.loads(env.out.read_text(encoding="utf-8"))
    assert "caveat" in payload and "zh" in payload["caveat"] and "en" in payload["caveat"]
    assert "disclaimer" in payload and "zh" in payload["disclaimer"] and "en" in payload["disclaimer"]
    assert len(payload["companies"]) == 1
    c = payload["companies"][0]
    assert c["ticker"] == "JSNX"
    assert c["d5_pct"] is not None                 # 取的是最后一行(已补上 D5)，不是第一行


# ── ⑧ 无观察对象（无 listed/priced 带 ticker 的公司）→ 零行为 ─────────────
def test_no_observation_targets_zero_behavior(env, monkeypatch):
    _write_alert_log(env.alert_log, [_alert_row("2026-06-01T00:00:00Z", "0011", "TooEarlyCo", "TEX", "filed")])
    called = []
    monkeypatch.setattr(am, "_fetch_series", lambda t, start=am.FETCH_START: called.append(t) or None)
    out = am.run()
    assert out == {"n_checked": 0, "n_new": 0, "n_skipped_no_data": 0}
    assert not env.log.exists() and not env.out.exists()
    assert called == []                            # 没有观察对象，压根不该发起取价


# ── 补充：alert_log 不存在 → 零行为（区别于"有账本但无合格档位"）────────────
def test_missing_alert_log_zero_behavior(env):
    out = am.run()
    assert out == {"n_checked": 0, "n_new": 0, "n_skipped_no_data": 0}
    assert not env.log.exists() and not env.out.exists()
