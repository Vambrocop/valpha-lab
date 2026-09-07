"""纳指成分进出账本 + 池子维护年龄(2026-09-07)。

## 起因

`valpha150.csv` 是 152 只的**人工策展**池,最后一次维护 2026-06-22 —— 到今天 77 天没人动。
问题不是"坏票堆积"(实测 152 只全部正常抓到,零覆盖漂移),而是**新晋大市值进不来**。

而原来的成分变动追踪帮不上忙:`added`/`removed` 只是"跟上一份快照比"的**瞬时差分**,
绝大多数日子是空的;一旦真有进出,当天没人看 ndx.json 就**永远看不见了**——快照已被覆盖。
**变动本身没留痕**,所以没人知道该去维护池子。这就是"悄悄老化"的机制。

## 刻意不做的事

不自动重写 valpha150.csv。池子带手写中文名/板块,外部无权威名单可抓;自动加票会让
name_cn 开天窗,还会悄悄改变已发布的统计口径(幸存者偏差也跟着变)。
所以只做两件事:**给变动留账本** + **把"多久没人管"摆出来**,纳不纳入由人决定。

hermetic:临时目录 + 假数据,不联网、不碰真账本。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_ndx as bn  # noqa: E402


@pytest.fixture
def tmp_log(tmp_path, monkeypatch):
    monkeypatch.setattr(bn, "LOG", tmp_path / "ndx_membership_log.csv")
    return tmp_path / "ndx_membership_log.csv"


def test_changes_are_appended_with_action(tmp_log):
    bn._append_changes("2026-09-07", ["AAA"], ["BBB"])
    df = pd.read_csv(tmp_log, dtype=str)
    assert set(df.columns) == {"date", "ticker", "action"}
    assert set(zip(df["ticker"], df["action"])) == {("AAA", "added"), ("BBB", "removed")}


def test_same_day_rerun_is_idempotent(tmp_log):
    """同日重复跑不许写重 —— CI 一天可能跑很多次。"""
    bn._append_changes("2026-09-07", ["AAA"], [])
    bn._append_changes("2026-09-07", ["AAA"], [])
    assert len(pd.read_csv(tmp_log)) == 1


def test_history_is_never_rewritten(tmp_log):
    """append-only 铁律:新变动只追加,旧行一个字节都不动。"""
    bn._append_changes("2026-09-01", ["OLD"], [])
    before = tmp_log.read_text(encoding="utf-8")
    bn._append_changes("2026-09-07", ["NEW"], [])
    after = tmp_log.read_text(encoding="utf-8")
    assert after.startswith(before.rstrip("\n")), "历史行被改写了"
    assert "OLD" in after and "NEW" in after


def test_no_changes_writes_nothing(tmp_log):
    """绝大多数日子没有进出 —— 不许因此产生空写/噪声行。"""
    assert bn._append_changes("2026-09-07", [], []) == []
    assert not tmp_log.exists()


def test_recent_changes_window_hides_ancient_and_keeps_fresh(tmp_log):
    """窗口要够宽才看得见稀疏变动,但陈年旧事不该一直挂着。"""
    bn._append_changes("2025-01-01", ["ANCIENT"], [])
    bn._append_changes("2026-09-01", ["FRESH"], [])
    got = {r["ticker"] for r in bn._recent_changes("2026-09-07", days=180)}
    assert "FRESH" in got and "ANCIENT" not in got


def test_recent_changes_empty_without_log(tmp_log):
    """账本还不存在(首跑)→ 空列表,不炸。"""
    assert bn._recent_changes("2026-09-07") == []


def test_pool_curation_age_reads_git_not_mtime():
    """池子年龄必须按 **git 最后修改日**算,不能用文件 mtime。

    干净检出里 mtime = 检出时间,会把"77 天没维护"显示成"今天刚维护过"——
    正好把要暴露的问题掩盖掉。(同 staleness_watchdog 不用 mtime 的理由。)
    """
    src = (ROOT / "scripts" / "build_ndx.py").read_text(encoding="utf-8")
    i = src.index("def _pool_curation_age")
    body = src[i:i + 900]
    assert "git" in body and "%cs" in body, "没走 git log 取最后修改日"
    assert "mtime" not in body and "getmtime" not in body, "用了 mtime —— 干净检出里会谎报"


def test_focused_gap_not_the_whole_43():
    """只报"近期新进指数**且**池子没有"的,不报全部"在 NDX 不在池子"。

    后者当前有 43 只,多半是策展时**刻意**没收的中盘;报出来只会被当噪声忽略,
    而一条被忽略的警告等于没有警告。
    """
    src = (ROOT / "scripts" / "build_ndx.py").read_text(encoding="utf-8")
    assert "recent_added_missing" in src
    i = src.index("recent_added_missing = ")
    expr = src[i:i + 260]
    assert 'r["action"] == "added"' in expr and "not in v150" in expr, \
        "聚焦缺口的口径变了:应是「近期新进 ∧ 池子没有」"
