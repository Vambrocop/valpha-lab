"""test_ipo_alerts.py — IPO 重大事件预警（A3）单测。

全部 canned fixtures·不碰网络（monkeypatch 掉 _send 推送）。
覆盖任务规格 6 类：①新 major 首录+推送 ②同 (cik,stage) 幂等 ③状态迁移 filed→priced
④推送失败 pushed=False 落账·下轮不重推 ⑤空 major 集零行为 ⑥历史行逐字节不变（append-only）。
"""
import csv
import json

import pytest

import ipo_alerts as ia


# ── fixtures 工厂 ──────────────────────────────────────────────────────
def _row(cik, company, form, *, tier="major", ticker="TST", filed="2026-07-10",
         reasons=("amount",), adsh=None):
    return {"company": company, "ticker": ticker, "cik": cik, "form": form,
            "filed": filed, "foreign": False, "tier": tier,
            "tier_reasons": list(reasons), "adsh": adsh}


def _write_filings(path, *, filed=(), priced=(), listing=(), adr=()):
    payload = {"filed": list(filed), "priced": list(priced),
               "listing": list(listing), "adr": list(adr)}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """隔离 SRC/LOG 到 tmp，_send 换成记录器（默认成功）。
    设假 TELEGRAM token——run() 对「未配置 token」是完全跳过不落账（见 ipo_alerts 文件头
    取舍），既有测试要走完整推送+落账路径必须让配置检查过关；未配置路径单独测（⑦）。"""
    src = tmp_path / "ipo_filings.json"
    log = tmp_path / "ipo_alert_log.csv"
    monkeypatch.setattr(ia, "SRC", src)
    monkeypatch.setattr(ia, "LOG", log)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    sent = []
    monkeypatch.setattr(ia, "_send", lambda text: sent.append(text) or True)

    class Env:
        pass
    e = Env()
    e.src, e.log, e.sent = src, log, sent
    return e


def _rows(log):
    with open(log, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ── ① 新 major → append + 推送调用 ─────────────────────────────────────
def test_new_major_appends_and_pushes(env):
    _write_filings(env.src, filed=[_row("0001", "BigCo Inc.", "S-1")])
    out = ia.run()
    assert out == {"n_new": 1, "pushed": True}
    rows = _rows(env.log)
    assert len(rows) == 1
    r = rows[0]
    assert (r["cik"], r["stage"], r["form"]) == ("0001", "filed", "S-1")
    assert r["company"] == "BigCo Inc." and r["ticker"] == "TST"
    assert r["tier_reasons"] == "amount" and r["pushed"] == "True"
    assert len(env.sent) == 1
    msg = env.sent[0]
    assert "BigCo Inc." in msg and "已递交招股书(S-1)" in msg
    assert "事实通报" in msg and "非荐股" in msg and "上市≠值得买" in msg


# ── ② 同 (cik,stage) 第二轮：不重推、不重记 ────────────────────────────
def test_same_cik_stage_idempotent(env):
    _write_filings(env.src, filed=[_row("0001", "BigCo Inc.", "S-1/A")])
    ia.run()
    out2 = ia.run()
    assert out2 == {"n_new": 0, "pushed": False}
    assert len(_rows(env.log)) == 1
    assert len(env.sent) == 1                     # 第二轮零推送


# ── ③ 状态迁移 filed→priced：新行 + 新推 ──────────────────────────────
def test_stage_transition_filed_to_priced(env):
    _write_filings(env.src, filed=[_row("0001", "BigCo Inc.", "S-1")])
    ia.run()
    _write_filings(env.src,
                   filed=[_row("0001", "BigCo Inc.", "S-1")],
                   priced=[_row("0001", "BigCo Inc.", "424B4", filed="2026-07-12")])
    out = ia.run()
    assert out == {"n_new": 1, "pushed": True}
    rows = _rows(env.log)
    assert [(r["stage"], r["form"]) for r in rows] == [("filed", "S-1"), ("priced", "424B4")]
    assert len(env.sent) == 2
    assert "已定价/生效(424B4)" in env.sent[1]
    # priced 已录后同一 json 再跑 → 最高档 priced 已在账,filed 也在账 → 零新增
    assert ia.run() == {"n_new": 0, "pushed": False}


# ── ④ 配置了 token 但发送失败 → pushed=False 落账;下轮不重推(失败=错过,留痕可审计)──
def test_push_failure_logs_false_and_no_retry(env, monkeypatch):
    monkeypatch.setattr(ia, "_send", lambda text: False)      # 网络闪断/401(token 已配置)
    _write_filings(env.src, listing=[_row("0002", "ListCo", "8-A12B", ticker="LST",
                                          reasons=("home_mktcap",))])
    out = ia.run()
    assert out == {"n_new": 1, "pushed": False}
    rows = _rows(env.log)
    assert rows[0]["pushed"] == "False" and rows[0]["stage"] == "listed"
    # 下轮恢复推送能力 → 该 (cik,stage) 已在账,不重推不重记
    calls = []
    monkeypatch.setattr(ia, "_send", lambda text: calls.append(text) or True)
    assert ia.run() == {"n_new": 0, "pushed": False}
    assert calls == [] and len(_rows(env.log)) == 1


# ── ⑤ 空 major 集 → 零行为(不建账本、不推送)────────────────────────────
def test_no_major_zero_behavior(env):
    _write_filings(env.src,
                   filed=[_row("0003", "SmallCo", "S-1", tier="rest", reasons=()),
                          _row("0004", "MidCo", "F-1", tier="notable",
                               reasons=("foreign_unknown",))],
                   adr=[_row("0005", "AdrOnlyCo", "F-6")])   # major 但 F-6 不算档
    out = ia.run()
    assert out == {"n_new": 0, "pushed": False}
    assert not env.log.exists()
    assert env.sent == []


# ── ⑥ 账本已有历史行 → 只 append,历史行逐字节不变 ──────────────────────
def test_history_rows_byte_identical(env):
    _write_filings(env.src, filed=[_row("0001", "BigCo Inc.", "S-1")])
    ia.run()
    before = env.log.read_bytes()
    _write_filings(env.src,
                   filed=[_row("0001", "BigCo Inc.", "S-1"),
                          _row("0009", "NewCo Ltd", "F-1", ticker=None,
                               reasons=("home_mktcap",), adsh="0001234567-26-000123")])
    out = ia.run()
    assert out["n_new"] == 1
    after = env.log.read_bytes()
    assert after[:len(before)] == before          # 历史前缀逐字节不变(append-only)
    rows = _rows(env.log)
    assert len(rows) == 2
    assert rows[1]["company"] == "NewCo Ltd" and rows[1]["ticker"] == ""
    assert rows[1]["adsh"] == "0001234567-26-000123"


# ── 补充守门:公司级最高档取档 + F-6 不算档 + 代表行取最新 ────────────────
def test_highest_stage_wins_company_level(env):
    _write_filings(env.src,
                   filed=[_row("0007", "MultiCo", "F-1/A", filed="2026-07-06")],
                   priced=[_row("0007", "MultiCo", "424B4", filed="2026-07-10")],
                   listing=[_row("0007", "MultiCo", "8-A12B", filed="2026-07-09")],
                   adr=[_row("0007", "MultiCo", "F-6", ticker=None, filed="2026-07-01")])
    out = ia.run()
    assert out == {"n_new": 1, "pushed": True}    # 一家公司一条事件(最高档)
    rows = _rows(env.log)
    assert len(rows) == 1
    assert rows[0]["stage"] == "listed" and rows[0]["form"] == "8-A12B"
    assert "已注册挂牌(8-A12B)" in env.sent[0]


# ── ⑦ 未配置 token → 完全跳过不落账不消费;配置后同一事件仍可首见推送 ──────
#    (防"本地无 token 抢先消费成 pushed=False、CI 永远推不出去"的集成洞——Fable 直审抓出)
def test_no_token_skips_without_consuming(env, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    _write_filings(env.src, filed=[_row("0008", "PendCo", "S-1")])
    out = ia.run()
    assert out == {"n_new": 1, "pushed": False, "skipped_no_token": True}
    assert not env.log.exists() and env.sent == []            # 没落账、没消费
    # 有 token 的环境(如 CI)随后跑 → 同一事件仍是"新",正常首录+推送
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    out2 = ia.run()
    assert out2 == {"n_new": 1, "pushed": True}
    assert len(_rows(env.log)) == 1 and len(env.sent) == 1


def test_stage_of_form_families():
    assert ia._stage_of_form("S-1") == "filed"
    assert ia._stage_of_form("S-1/A") == "filed"
    assert ia._stage_of_form("F-1/A") == "filed"
    assert ia._stage_of_form("424B4") == "priced"
    assert ia._stage_of_form("424B1") == "priced"
    assert ia._stage_of_form("8-A12B") == "listed"
    assert ia._stage_of_form("8-A12B/A") == "listed"
    assert ia._stage_of_form("F-6") is None       # ADR 存托设施不算档
    assert ia._stage_of_form("S-11") is None      # 形似防御:REIT 注册表≠S-1 家族
    assert ia._stage_of_form(None) is None
