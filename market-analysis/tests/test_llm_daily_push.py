"""test_llm_daily_push.py — verify TG_DAILY_PUSH gating + dedup logic.

Tests do NOT call real Telegram.  notify_telegram.send is monkeypatched to
record calls.  The read-log append (wrote / _append_log) is NOT modified by
these tests — we only probe the PUSH branch.

Cases:
  1. TG_DAILY_PUSH unset (or empty)  → no push, no state file written
  2. TG_DAILY_PUSH="true" + new day  → push attempted, state file updated
  3. TG_DAILY_PUSH="true" + same day → dedup skips push, no second send()
  4. State file corrupt/missing       → treated as "not pushed", no crash
"""
import datetime
import json
import os
import sys
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import llm_daily_read as ldr


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_env(tmp_path, monkeypatch):
    """Redirect module-level paths and stub away LLM + Telegram."""
    web  = tmp_path / "web";  web.mkdir()
    data = tmp_path / "data"; data.mkdir()
    processed = data / "processed"; processed.mkdir()

    monkeypatch.setattr(ldr, "WEB",          web)
    monkeypatch.setattr(ldr, "LOG",          data / "llm_read_log.csv")
    monkeypatch.setattr(ldr, "TG_PUSH_STATE", processed / "tg_daily_push_state.json")

    # Stub util_io.write_json so llm_read.json doesn't need real WEB/DOCS
    import util_io
    monkeypatch.setattr(util_io, "WEB",  web)
    monkeypatch.setattr(util_io, "DOCS", tmp_path / "docs")
    (tmp_path / "docs").mkdir()

    # Write minimal composite_read.json so run() can proceed
    cr = {
        "date": "2026-06-25", "asof": "2026-06-25",
        "stance": "偏积极", "score": 0.22,
        "action": "偏积极", "confidence_level": "中",
        "factors": [
            {"name": "VIX", "reason": "VIX=18, 低波动"},
            {"name": "趋势", "reason": "上涨趋势"},
            {"name": "信用", "reason": "利差偏低"},
            {"name": "季节", "reason": "六月偏积极"},
            {"name": "羊群", "reason": "市场情绪中性"},
        ],
    }
    (web / "composite_read.json").write_text(json.dumps(cr, ensure_ascii=False), encoding="utf-8")

    # LLM key + stub
    monkeypatch.setattr(ldr, "_llm_key", lambda: "fake-key")
    monkeypatch.setattr(ldr, "_active_model", lambda: "test-model")
    monkeypatch.setattr(ldr, "_llm", lambda _p: "今日市场偏积极，风险较低。（这是数据读数不是预测，会错，过去不代表未来）")

    return {"web": web, "data": data, "processed": processed, "tmp": tmp_path}


def _fake_notify_module(calls: list):
    """Return a fake notify_telegram module that records calls."""
    mod = types.ModuleType("notify_telegram")
    def send(text, parse_mode=None, tag="msg"):
        calls.append({"text": text, "tag": tag})
        return True
    mod.send = send
    # 生产推送路径现在也调用 notify_telegram.footer()，stub 必须提供（否则 footer 抛错被吞→静默不推）
    mod.footer = lambda extra="": "🔗 vambrocop.github.io/valpha-lab/\n" + (extra or "（实验性·会错·已公开计分认账）")
    return mod


# ---------------------------------------------------------------------------
# 1. TG_DAILY_PUSH unset → no push
# ---------------------------------------------------------------------------

def test_no_push_when_flag_unset(fake_env, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "notify_telegram", _fake_notify_module(calls))
    monkeypatch.delenv("TG_DAILY_PUSH", raising=False)

    ldr.run()

    assert calls == [], "push must be skipped when TG_DAILY_PUSH is not set"
    assert not ldr.TG_PUSH_STATE.exists(), "state file must not be created"


def test_no_push_when_flag_empty(fake_env, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "notify_telegram", _fake_notify_module(calls))
    monkeypatch.setenv("TG_DAILY_PUSH", "")

    ldr.run()

    assert calls == []


def test_no_push_when_flag_false(fake_env, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "notify_telegram", _fake_notify_module(calls))
    monkeypatch.setenv("TG_DAILY_PUSH", "false")

    ldr.run()

    assert calls == []


# ---------------------------------------------------------------------------
# 2. TG_DAILY_PUSH=true + new day → push fires, state written
# ---------------------------------------------------------------------------

def test_push_fires_on_new_day(fake_env, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "notify_telegram", _fake_notify_module(calls))
    monkeypatch.setenv("TG_DAILY_PUSH", "true")

    # No state file → treated as "never pushed"
    assert not ldr.TG_PUSH_STATE.exists()

    ldr.run()

    assert len(calls) == 1, "push should fire once on a fresh day"
    assert calls[0]["tag"] == "daily"
    # State file written
    assert ldr.TG_PUSH_STATE.exists()
    state = json.loads(ldr.TG_PUSH_STATE.read_text(encoding="utf-8"))
    assert state["last"] == datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# 3. TG_DAILY_PUSH=true + same day (state already set) → dedup skips
# ---------------------------------------------------------------------------

def test_dedup_skips_same_day(fake_env, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "notify_telegram", _fake_notify_module(calls))
    monkeypatch.setenv("TG_DAILY_PUSH", "true")

    today = datetime.date.today().isoformat()
    ldr.TG_PUSH_STATE.write_text(json.dumps({"last": today}), encoding="utf-8")

    ldr.run()

    assert calls == [], "push must be skipped when today already in state file"


# ---------------------------------------------------------------------------
# 4. State file missing / corrupt → no crash, push proceeds
# ---------------------------------------------------------------------------

def test_corrupt_state_file_no_crash(fake_env, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "notify_telegram", _fake_notify_module(calls))
    monkeypatch.setenv("TG_DAILY_PUSH", "true")

    ldr.TG_PUSH_STATE.write_text("NOT JSON{{{{", encoding="utf-8")

    result = ldr.run()

    assert result is not None, "corrupt state must not crash run()"
    assert len(calls) == 1, "corrupt state treated as 'not pushed' → push fires"


# ---------------------------------------------------------------------------
# 5. Telegram send() raising exception → pipeline not broken
# ---------------------------------------------------------------------------

def test_telegram_exception_no_crash(fake_env, monkeypatch):
    def bad_send(text, parse_mode=None, tag="msg"):
        raise ConnectionError("network down")

    bad_mod = types.ModuleType("notify_telegram")
    bad_mod.send = bad_send
    bad_mod.footer = lambda extra="": "🔗 x\ny"   # 让推送路径走到 send() 才抛(测的是 send 失败不崩)
    monkeypatch.setitem(sys.modules, "notify_telegram", bad_mod)
    monkeypatch.setenv("TG_DAILY_PUSH", "true")

    result = ldr.run()  # must not raise

    assert result is not None, "Telegram failure must not crash run()"
