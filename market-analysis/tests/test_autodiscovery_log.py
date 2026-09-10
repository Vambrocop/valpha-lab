"""test_autodiscovery_log.py — Phase2 裁决账本：append-only + 同日幂等 + schema/None 处理。

守住"盘前+盘后同日不重复记"(幂等)与"None→空串不写 nan"，避免污染前向史账本。
"""
import csv
import io

import pytest

import autodiscovery as ad


def _fake(n=3):
    return [{"candidate_id": f"c{i}", "key": f"k{i}", "family": "calendar",
             "verdict": "dead", "p": 0.5, "recent_p": None} for i in range(n)]


def test_append_then_idempotent(tmp_path):
    log = tmp_path / "adlog.csv"
    assert ad._append_log(_fake(3), path=log) is True       # 首记一批
    assert ad._append_log(_fake(3), path=log) is False      # 同日再调 → 幂等、不改历史行
    rows = list(csv.reader(open(log, encoding="utf-8")))
    assert rows[0] == ["date", "candidate_id", "key", "family", "verdict", "p", "recent_p"]
    assert len(rows) == 1 + 3                                # 表头 + 仅一批 3 行
    assert ad._log_days(path=log) == 1


def test_none_pvalue_blank(tmp_path):
    log = tmp_path / "adlog.csv"
    ad._append_log([{"candidate_id": "c0", "key": "k", "family": "factor",
                     "verdict": "inconclusive", "p": None, "recent_p": None}], path=log)
    rows = list(csv.reader(open(log, encoding="utf-8")))
    assert rows[1][5] == "" and rows[1][6] == ""            # None → 空串(不写 nan)


def test_log_days_empty(tmp_path):
    assert ad._log_days(path=tmp_path / "nope.csv") == 0


# ── 账本完整性:某天整块消失要能被发现(2026-09-10·事故驱动) ──────────────
def test_no_silently_lost_day_recorded_in_git_history():
    """账本里**曾经存在过**的日期,现在不许消失。

    起因:2026-07-07 一个 bot 的 `chore: auto-refresh market data` 提交把 2026-07-06
    整天的 104 行删了(`+0/-104`),根因是缓存回灌 + `git add -A`(同 08-27 抹掉用户
    自选组合配置、06-22 删掉 Valpha150 四只票的那个 bug)。**没人发现,直到 2 个月后
    我顺手扫 811 个 bot 提交才查出来。**

    为什么现有防线都抓不住:
      · `ci_ledger_guard` 比的是「工作树 vs origin」—— 一旦坏版本已经推上 origin,
        两边都缺,它就看不出来;
      · 哈希链记了 `n_rows`,但删 104 行的同一次运行又追加了 104 行,净额还在涨;
      · 跨账本交叉验证也不行(composite_log 那天同样没有记录)。
    唯一可靠的参照是 **git 历史本身**:某个日期只要在任何历史版本里出现过,它就该一直在。

    hermetic 降级:浅克隆/无 git 时自动跳过,不误红。
    """
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    rel = "market-analysis/data/autodiscovery_log.csv"
    cur = root / rel
    if not cur.exists():
        pytest.skip("账本不存在")

    shas = subprocess.run(["git", "log", "--format=%H", "--", rel], cwd=str(root),
                          capture_output=True, text=True, encoding="utf-8").stdout.split()
    if len(shas) < 2:
        pytest.skip("没有足够的 git 历史(浅克隆),跳过")

    def dates_of(text):
        return {r["date"] for r in csv.DictReader(io.StringIO(text)) if r.get("date")}

    now = dates_of(cur.read_text(encoding="utf-8"))
    ever = set()
    # **必须扫全部版本,不能只取最近 N 个**:2026-09-10 我第一版写的是 shas[:40],
    # 变异测试(把恢复的 07-06 再删掉)竟然通过了 —— 因为 07-06 只存在于七月的提交里,
    # 早滚出了 40 的窗口。滑动窗口的守门等于摆设。实测全扫 61 个版本仅 ~3 秒,不值得省。
    for sha in shas:
        t = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=str(root),
                           capture_output=True, text=True, encoding="utf-8").stdout
        if t:
            ever |= dates_of(t)

    lost = sorted(ever - now)
    assert not lost, (
        f"这些日期在 git 历史里出现过,但现在从账本里消失了: {lost} —— "
        "append-only 账本不该丢日期。查是不是又被自动提交的缓存回灌删掉了"
        "(2026-07-06 就是这么没的,见本测试 docstring)。"
        "确认是误删就从历史版本把那几天的行**追加到文件末尾**恢复"
        "(必须追加而非插入:防缩水门要求 origin 的身份序列是本地的前缀)。")
