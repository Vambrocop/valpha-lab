"""test_staleness_watchdog.py — 看门狗守门:超期检测阈值 / 缺失视同卡住 / 按日去重 / 发失败不记 dedup。
全合成数据 + mock notify_telegram.send,不联网、不碰真 web/data(CI 干净检出安全)。"""
import datetime
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import staleness_watchdog as wd

NOW = datetime.datetime(2026, 7, 7, 12, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture()
def fake_web(tmp_path, monkeypatch):
    """三个产物指到 tmp,默认全新鲜;state 也指到 tmp。"""
    web = tmp_path / "web"; web.mkdir()
    files = {"signals": "signals.json", "llm_daily": "llm_read.json", "llm_weekly": "llm_weekly.json"}
    checks = [
        ("signals",    web / "signals.json",    "generated", 3, "信号流水线 signals.json", "live"),
        ("llm_daily",  web / "llm_read.json",   "generated", 4, "大白话日读 llm_read.json", "live"),
        ("llm_weekly", web / "llm_weekly.json", "generated", 9, "本周回顾 llm_weekly.json", "live"),
        ("insider",    web / "insider.json",    "generated", 21, "内部人买入 insider.json", "known-limited"),
    ]
    files["insider"] = "insider.json"
    monkeypatch.setattr(wd, "CHECKS", checks)
    # WEB 也必须指到 tmp:find_shrunk() 读 WEB/"data_health.json"。
    # 不 patch 的话它读**真实**的 market-analysis/web/,而往那儿写 fixture 会覆盖已发布产物
    # —— 2026-09-16 我就这么干过一次(前端读的 data_health 被改成 1 条源的假数据)。
    monkeypatch.setattr(wd, "WEB", web)
    state = tmp_path / "watchdog_state.json"
    monkeypatch.setattr(wd, "STATE", state)

    def write(key, ts):
        (web / files[key]).write_text(json.dumps({"generated": ts}), encoding="utf-8")

    write("signals", "2026-07-07")                    # 0 天
    write("llm_daily", "2026-07-07T03:52:34Z")        # 0 天
    write("llm_weekly", "2026-07-05T04:34:54Z")       # 2 天
    write("insider", "2026-07-07T00:00:00Z")          # 0 天(known-limited·默认新鲜,免污染既有断言)
    return {"write": write, "state": state, "web": web}


def test_all_fresh_no_alert(fake_web):
    assert wd.find_stale(NOW) == []


def test_threshold_boundaries(fake_web):
    w = fake_web["write"]
    w("signals", "2026-07-04")            # 恰 3 天 = 不超(>3 才告)
    assert wd.find_stale(NOW) == []
    w("signals", "2026-07-03")            # 4 天 > 3 → 告
    assert [s[0] for s in wd.find_stale(NOW)] == ["signals"]
    w("signals", "2026-07-07")
    w("llm_weekly", "2026-06-27T15:21:06Z")   # 9 天(周读 W26 实况) = 不超(>9 才告,正常周期内)
    assert wd.find_stale(NOW) == []
    w("llm_weekly", "2026-06-26T15:00:00Z")   # 10 天 → 告
    assert [s[0] for s in wd.find_stale(NOW)] == ["llm_weekly"]


def test_missing_or_bad_file_counts_as_stale(fake_web):
    (fake_web["web"] / "llm_read.json").unlink()                       # 缺文件
    (fake_web["web"] / "signals.json").write_text("{not json", encoding="utf-8")  # 坏 JSON
    keys = [s[0] for s in wd.find_stale(NOW)]
    assert "llm_daily" in keys and "signals" in keys
    assert all(s[2] is None for s in wd.find_stale(NOW) if s[0] in ("llm_daily", "signals"))


def test_run_sends_and_dedups_same_day(fake_web, monkeypatch):
    monkeypatch.setattr(wd, "CHECKS", [c for c in wd.CHECKS if c[0] == "llm_daily"])   # 隔离:只看 llm_daily,免得 +7 天时别的项也过期干扰 snooze 断言
    fake_web["write"]("llm_daily", "2026-07-01T00:00:00Z")   # 6 天 > 4 → 告
    calls = []
    import notify_telegram
    monkeypatch.setattr(notify_telegram, "send", lambda text, **kw: calls.append(text) or True)
    first = wd.run(NOW, state_path=fake_web["state"])
    assert len(first) == 1 and len(calls) == 1
    assert "日读" in calls[0] and "6 天" in calls[0]
    # 同日第二班:去重,不再发
    second = wd.run(NOW, state_path=fake_web["state"])
    assert second == [] and len(calls) == 1
    # 次日仍卡:7 天 snooze 窗内不再打扰(此前每天发→改成最多每 SNOOZE_DAYS 天一次·防轰炸)
    third = wd.run(NOW + datetime.timedelta(days=1), state_path=fake_web["state"])
    assert third == [] and len(calls) == 1
    # 满 SNOOZE_DAYS 天仍卡:才再发一条
    fourth = wd.run(NOW + datetime.timedelta(days=wd.SNOOZE_DAYS), state_path=fake_web["state"])
    assert len(fourth) == 1 and len(calls) == 2


def test_send_failure_does_not_record_dedup(fake_web, monkeypatch):
    """发失败(未配置/网络挂)不记 dedup → 下一班还会重试,不会静默丢告警。"""
    fake_web["write"]("llm_daily", "2026-07-01T00:00:00Z")
    import notify_telegram
    monkeypatch.setattr(notify_telegram, "send", lambda text, **kw: False)
    wd.run(NOW, state_path=fake_web["state"])
    assert not fake_web["state"].exists() or "llm_daily" not in json.loads(
        fake_web["state"].read_text(encoding="utf-8"))


# ── 覆盖率守门:顶层 fail-soft 的产物必须有人盯(2026-08-31) ────────────────────
def test_every_failsoft_product_is_watched():
    """**自动**发现"会静默停更"的产物,逼它们进 CHECKS——而不是靠我下次记得手加。

    起因:ndx 烂了 24 天,因为 workflow 用 `|| echo ::warning::` 咽掉失败。08-24 那次是手工
    扫了一遍 workflow 补监控;但同一个陷阱还有**另一个入口**——脚本自己在顶层 `except → sys.exit(0)`。
    run_all 本身是 fail-hard(任一步非零就 sys.exit(1) 让 CI 红),所以只有这类自吞异常的脚本
    才会"绿着跑完但产物没更新"。本测试把这条规则自动化:

      脚本里出现 sys.exit(0)/SystemExit(0)  ∧  它 write_json 了某个产物  ⇒  该产物必须被 watchdog 盯

    新写一个 fail-soft 脚本时这条会自动变红,提醒作者"要么盯它,要么在 EXEMPT 里写明为什么不盯"。
    hermetic:只读脚本源码文本,不跑脚本、不联网、不读 data/。
    """
    import re
    from pathlib import Path
    scripts = Path(__file__).parent.parent / "scripts"
    failsoft = re.compile(r"sys\.exit\(0\)|SystemExit\(0\)")
    writes = re.compile(r'write_json\(\s*["\']([\w./-]+\.json)["\']')

    watched = {p.name for _k, p, *_ in wd.CHECKS}
    EXEMPT = {
        # ipo_enrich 只是给 fetch_ipo 的同一份产物加料;ipo_filings.json 已被 ("ipo", …) 盯着。
        "ipo_filings.json",
    }

    missing = {}
    for f in sorted(scripts.glob("*.py")):
        src = f.read_text(encoding="utf-8")
        if not failsoft.search(src):
            continue
        for out in sorted(set(writes.findall(src))):
            name = Path(out).name
            if name not in watched and name not in EXEMPT:
                missing.setdefault(name, []).append(f.name)

    assert not missing, (
        "这些产物由顶层 fail-soft 脚本生成(失败也不会让 CI 红)却无人监控,会像 ndx 那样悄悄发霉:\n  "
        + "\n  ".join(f"{k}  ←  {', '.join(v)}" for k, v in missing.items())
        + "\n修法:加进 staleness_watchdog.CHECKS;确有理由不盯就写进本测试的 EXEMPT 并注明原因。"
    )


# ── 历史塌缩告警（2026-09-16 事故之后补）────────────────────────────
# 为什么单开一组：塌缩与"超期"是**两种不同的坏**。超期=文件不更新(年龄检查能抓)；
# 塌缩=文件很新、内容没了 → 上面那套年龄检查**一个都不会响**。
# 实测事故：^VIX3M 的取数回退把 6717 行缓存覆盖成 1 行，data_health 报
# "rows: 1, status: ok"，时间戳全新。取数侧的闸只让前端显示 ⚠；
# 维护者侧此前没有任何出口 —— 而本项目最贵的教训就是"静默两个月"。
def _health(web, sources):
    (web / "data_health.json").write_text(
        json.dumps({"sources": sources, "summary": {"total": len(sources)}}, ensure_ascii=False),
        encoding="utf-8")


def test_no_health_file_is_silent(fake_web):
    """缺 data_health 不在这里报(产物缺失由年龄检查兜底) —— 免得同一件事报两遍。"""
    assert wd.find_shrunk() == []


def test_healthy_sources_no_shrink_alert(fake_web):
    _health(wd.WEB, {"asset:VIX": {"name": "VIX", "rows": 6717, "status": "ok",
                                   "shrink_blocked": None}})
    assert wd.find_shrunk() == []


def test_blocked_shrink_is_alerted_with_both_counts(fake_web):
    """告警里必须带"取到多少 / 保留多少"两个数 —— 只说"塌缩了"没法判断严重程度。"""
    _health(wd.WEB, {"asset:VIX3M": {"name": "VIX3M", "rows": 6717, "status": "shrunk",
                                     "shrink_blocked": [1, 6717]}})
    got = wd.find_shrunk()
    assert len(got) == 1
    key, label, age, detail, kind = got[0]
    assert kind == "shrunk" and age is None
    assert "VIX3M" in label
    assert "1" in detail and "6717" in detail
    assert key == "shrunk:asset:VIX3M", "key 要按源区分,否则多个源塌缩会互相顶掉去重状态"


def test_shrink_alert_wording_is_not_stuck(fake_web, monkeypatch):
    """塌缩项 age 恒为 None，若 shrunk 分支没排在 `age is None` 之前，
    会被误报成"缺失或时间戳不可读" —— 那会把排查方向带到"流水线卡住"上去，全错。"""
    monkeypatch.setattr(wd, "CHECKS", [])          # 隔离:只看塌缩这一路
    _health(wd.WEB, {"asset:VIX3M": {"name": "VIX3M", "rows": 6717, "status": "shrunk",
                                     "shrink_blocked": [1, 6717]}})
    sent = {}
    import notify_telegram
    monkeypatch.setattr(notify_telegram, "send", lambda msg, tag=None: sent.setdefault("msg", msg) or True)
    wd.run(NOW, state_path=fake_web["state"])        # state 只落 tmp,绝不在 data/ 留文件
    msg = sent.get("msg", "")
    assert "缺失或时间戳不可读" not in msg, "塌缩被误报成缺失 —— 排查方向会被带错"
    assert "取数在坏" in msg, "表头没跟'数据卡住'分开"
    assert "6717" in msg and "1" in msg


def test_run_combines_stale_and_shrunk(fake_web, monkeypatch):
    """两类告警走同一套去重/Telegram，别只接一路。"""
    _health(wd.WEB, {"asset:VIX3M": {"name": "VIX3M", "rows": 6717, "status": "shrunk",
                                     "shrink_blocked": [1, 6717]}})
    kinds = {s[4] for s in (wd.find_stale(NOW) + wd.find_shrunk())}
    assert "shrunk" in kinds


def test_fixture_isolates_web_dir(fake_web, tmp_path):
    """守门:fixture 必须把 wd.WEB 指到 tmp。

    2026-09-16 实测事故(我自己犯的):新加的塌缩测试用 `_health(wd.WEB, ...)` 写 fixture,
    而当时 fixture 只 patch 了 CHECKS/STATE、**没 patch WEB** →
    直接把真实的 `market-analysis/web/data_health.json`(前端读的已发布产物)
    覆盖成了一条源的假数据。差一点提交出去。
    这条钉住隔离,以后往 wd.WEB 写东西的测试都落在 tmp 里。
    """
    assert tmp_path in wd.WEB.parents or wd.WEB.parent == tmp_path, (
        f"wd.WEB 没被隔离到 tmp(现为 {wd.WEB}) —— 写 fixture 会污染真实 web/ 产物")
    assert wd.STATE.parent == tmp_path or tmp_path in wd.STATE.parents, (
        f"wd.STATE 没被隔离到 tmp(现为 {wd.STATE}) —— 会在 data/ 留残留文件")
