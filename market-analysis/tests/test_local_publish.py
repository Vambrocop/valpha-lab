"""`tools/local_publish.py` 的门禁行为测试（2026-11-07）。

## 为什么这些测试是**全合成**的

本仓库栽过两次「测试偷偷依赖 gitignore 产生的数据」：`data/raw` 在 .gitignore 里，
CI 干净检出里是 **0 个文件** → 本地全绿、CI 红（#100–104；以及 2026-10-12 我的两条
F2 测试把周一刷新连干红两次）。
→ **本文件零 I/O、零 git、零真实产物**，只喂手搓的 dict 与 porcelain 文本行。

## 这些测试真正在守什么

`local_publish` 是**无人复核就往公开站点推送**的代码，所以它的门必须钉死：

- 哪些是**硬门**（拦住不发）：工作树含代码改动 · 候选池缩了 · 哨兵因子掉族 ·
  data_health 非全 ok/有 shrunk
- 哪个**刻意不是门**：**存活名单的变化**。它本来就该随数据变 —— 那是整个系统的目的；
  拦住它等于「冻结我们喜欢的结论」，正是本项目要防的不诚实。
  最后一条测试用源码反射把这件事钉住（同 `test_quality_gate` 的做法）。
"""
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import local_publish as lp  # noqa: E402


# ───────────────────── 门0：工作树只许有数据产物 ─────────────────────

def test_data_artifact_changes_are_allowed():
    ok, bad = lp.classify_worktree([
        " M docs/autodiscovery.json",
        " M market-analysis/web/signals.json",
        " M market-analysis/data/processed/prediction_log.csv",
        " M .benchmark-history.json",
    ])
    assert ok and bad == []


def test_source_code_change_blocks_publish():
    """命门：有代码改动就不许自动发布 —— 那条路该走带干净检出门禁的人工流程。

    `tools/pre_commit_gate.py` 是 **Claude Code 的 PreToolUse 钩子，不是 git hook**，
    计划任务直接调 git commit **不会**触发它。所以这道门是代码改动的唯一拦截点。
    """
    ok, bad = lp.classify_worktree([
        " M docs/signals.json",
        " M market-analysis/scripts/autodiscovery.py",
    ])
    assert not ok
    assert any("autodiscovery.py" in b for b in bad)


def test_workflow_and_doc_changes_also_block():
    """工作流 / CLAUDE.md 一类改动同样不许被自动提交顺走。"""
    ok, bad = lp.classify_worktree([
        " M .github/workflows/refresh-data.yml",
        " M CLAUDE.md",
    ])
    assert not ok and len(bad) == 2


def test_untracked_files_do_not_block():
    """未跟踪文件进不了 ci_publish 的显式暂存 → 无害，不该拦发布。

    （实际现状：`market-analysis/docs_internal/SPEC_FACTOR_OOS.md` 长期未跟踪，
    等用户拍板。它不该每天把自动发布拦下来。）
    """
    ok, bad = lp.classify_worktree([
        "?? market-analysis/docs_internal/SPEC_FACTOR_OOS.md",
        "?? scratch.py",
        " M docs/brief.json",
    ])
    assert ok and bad == []


def test_renamed_path_is_judged_by_its_new_name():
    ok, _ = lp.classify_worktree(['R  docs/a.json -> docs/b.json'])
    assert ok
    ok2, bad2 = lp.classify_worktree(['R  docs/a.json -> tools/b.py'])
    assert not ok2 and bad2


def test_allowed_prefixes_come_from_ci_publish_single_source():
    """口径必须与 `ci_publish.DEFAULT_PATHS` 同源 —— 两处各写一份必然漂移。

    `ci_publish` 那份清单有自己的覆盖率守门（对着真实提交历史核），
    所以跟着它走就自动继承了那道保护。
    """
    import ci_publish
    assert lp.classify_worktree([" M docs/x.json"])[0]
    # 伪造一份不含 docs 的清单 → 同样的行应当被判违规，证明真在用传入的清单
    ok, bad = lp.classify_worktree([" M docs/x.json"],
                                   allowed_prefixes=["market-analysis/web"])
    assert not ok and bad
    assert "docs" in ci_publish.DEFAULT_PATHS


# ───────────────────── 门4a：候选池不许缩 ─────────────────────

def _doc(cands, generated="2026-11-07"):
    return {"generated": generated, "candidates": cands}


def _c(key, family, verdict="dead"):
    return {"key": key, "family": family, "verdict": verdict}


def test_identical_pool_passes():
    d = _doc([_c("a", "factor"), _c("b", "calendar")])
    assert lp.pool_collapse(d, d) == []


def test_family_losing_members_is_blocked():
    """这是本地缺历史数据的 signature：某族的输入序列太短 → 成员掉出。"""
    before = _doc([_c("a", "factor"), _c("b", "factor"), _c("c", "calendar")])
    after = _doc([_c("a", "factor"), _c("c", "calendar")])
    probs = lp.pool_collapse(before, after)
    assert len(probs) == 1 and "factor" in probs[0] and "2" in probs[0] and "1" in probs[0]


def test_whole_family_disappearing_is_blocked():
    before = _doc([_c("a", "factor"), _c("z", "regime")])
    after = _doc([_c("a", "factor")])
    assert any("regime" in p for p in lp.pool_collapse(before, after))


def test_pool_growth_is_NOT_blocked():
    """候选空间扩容（N_DECLARED 增长）是正常演进，拦它会冻住项目的自生长。"""
    before = _doc([_c("a", "factor")])
    after = _doc([_c("a", "factor"), _c("new", "factor"), _c("n2", "streak_down")])
    assert lp.pool_collapse(before, after) == []


def test_verdict_changes_alone_do_not_trip_the_pool_gate():
    """只有裁决在动、池子不变 → 真实统计更新，必须放行。"""
    before = _doc([_c("a", "factor", "dead"), _c("b", "factor", "survive")])
    after = _doc([_c("a", "factor", "survive"), _c("b", "factor", "faded")])
    assert lp.pool_collapse(before, after) == []


def test_pool_by_family_counts_and_handles_missing_family():
    d = _doc([_c("a", "factor"), _c("b", "factor"), {"key": "c", "verdict": "dead"}])
    assert lp.pool_by_family(d) == {"factor": 2, "?": 1}


def test_pool_helpers_tolerate_empty_and_none():
    assert lp.pool_by_family(None) == {}
    assert lp.pool_by_family({}) == {}
    assert lp.pool_collapse({}, {}) == []


# ───────────────────── 门4b：哨兵因子 ─────────────────────

def test_canary_present_in_right_family_passes():
    ok, fam = lp.canary_present(_doc([_c(lp.CANARY_KEY, "factor", "dead")]))
    assert ok and fam == "factor"


def test_canary_verdict_is_irrelevant_only_membership_matters():
    """它线上长期是 dead（p≈0.94）。要守的是「在不在族里」，不是它显不显著。"""
    for v in ("dead", "survive", "faded", "inconclusive"):
        ok, _ = lp.canary_present(_doc([_c(lp.CANARY_KEY, "factor", v)]))
        assert ok, v


def test_canary_missing_is_blocked():
    """`3f6285e` 那次 ^VIX3M 缓存被覆盖成 1 行，最先咬掉的就是这条。"""
    ok, fam = lp.canary_present(_doc([_c("something_else", "factor")]))
    assert not ok and fam is None


def test_canary_in_wrong_family_is_blocked():
    ok, fam = lp.canary_present(_doc([_c(lp.CANARY_KEY, "regime")]))
    assert not ok and fam == "regime"


# ───────────────────── 门3：data_health ─────────────────────

def test_health_all_ok_passes():
    assert lp.health_problems({"summary": {"total": 45, "ok": 45, "shrunk": 0,
                                           "missing": 0, "stale": 0}}) == []


def test_health_shrunk_is_blocked():
    """`shrunk` 正是 `_save_series` 防历史塌缩闸打出来的标记 —— 它一响就别发。"""
    probs = lp.health_problems({"summary": {"total": 45, "ok": 44, "shrunk": 1}})
    assert len(probs) == 2 and any("shrunk" in p for p in probs)


def test_health_not_all_ok_is_blocked():
    probs = lp.health_problems({"summary": {"total": 45, "ok": 40, "shrunk": 0}})
    assert any("5" in p for p in probs)


def test_health_unreadable_is_blocked_not_silently_passed():
    """读不到就当过 = 又一个「写入时冻结的 ok」。必须拦。"""
    for bad in (None, {}, {"summary": {}}, {"summary": {"total": 0, "ok": 0}}):
        assert lp.health_problems(bad), bad


# ───────────────────── 存活名单：只报不拦 ─────────────────────

def test_survivor_diff_reports_both_directions():
    before = _doc([_c("keep", "f", "survive"), _c("goes", "f", "survive")])
    after = _doc([_c("keep", "f", "survive"), _c("comes", "f", "survive")])
    gone, new = lp.survivor_diff(before, after)
    assert gone == ["goes"] and new == ["comes"]


def test_survivor_diff_empty_when_stable():
    d = _doc([_c("a", "f", "survive"), _c("b", "f", "dead")])
    assert lp.survivor_diff(d, d) == ([], [])


def test_survivor_list_is_deliberately_NOT_a_gate():
    """⚠ 设计判断的守门测试：存活名单的变化**绝不**阻断发布。

    理由（也写在 local_publish 的模块 docstring 里）：存活名单本来就该随数据变动，
    那是整个自动发现系统的目的。拦住它等于「冻结我们喜欢的结论」，
    正是本项目反复要防的那种不诚实（a2872a3 的教训在「撤」的方向上也生效过）。

    做法同 `test_quality_gate` 对 `adjudicate` 的源码反射：断言从 `survivor_diff`
    被调用处到**下一个门分隔注释**之间没有任何 return —— 也就是它影响不了控制流。

    ⚠ 边界锚点用结构性的 `# ──`（各门之间的分隔注释），不要用 "门5" 之类的文案：
    第一版我写 `src.index("门5", i)`，而源码里是「门 5」带空格，于是匹配到了后面
    那行成功日志 `log("门5 pytest 全绿")`，把 pytest 的 return 划进了区间 → 假红。
    """
    src = inspect.getsource(lp._run_gates)
    assert "survivor_diff" in src, "门禁里不再调用 survivor_diff？本测试的前提没了"

    i = src.index("survivor_diff(")
    j = src.index("# ──", i)                  # 下一个门分隔注释 = 报告段的结束
    between = src[i:j]
    assert "pytest" not in between, "锚点划错了：区间越过了 pytest 那道门"
    assert "return" not in between, (
        "存活名单的变化被接进了控制流 —— 它成了门。"
        f"违规片段：\n{between}")


def test_hard_gates_each_have_a_blocking_return():
    """反向守门：上面那些**该拦**的门，必须真的有 return（别被改成只打印）。"""
    src = inspect.getsource(lp._run_gates)
    for marker in ("pool_collapse(", "canary_present(", "health_problems(",
                   "classify_worktree("):
        assert marker in src, f"{marker} 不在门禁流程里了"
        seg = src[src.index(marker):]
        head = seg[:seg.index("# ──")] if "# ──" in seg else seg
        assert "return" in head, f"{marker} 之后没有阻断路径 —— 它变成只打印了"


# ───────────────────── 杂项不变量 ─────────────────────

def test_post_gate_scripts_match_the_workflow():
    """门后那批脚本必须与 `refresh-data.yml` 一致 —— 漏一个就是漏一个产物不刷新。

    实证：我 2026-11-06 那次手跑只跑了 run_all，**这 7 个全漏了**。
    """
    wf = (ROOT / ".github" / "workflows" / "refresh-data.yml").read_text(encoding="utf-8")
    for s in lp.POST_GATE_SCRIPTS:
        assert s in wf, f"{s} 不在 refresh-data.yml 里 —— 两处口径漂移了"
    for s in ("build_valpha150.py", "build_ndx.py", "fetch_cot.py", "fetch_putcall.py"):
        assert s in lp.POST_GATE_SCRIPTS, f"{s} 在工作流里却不在本地序列里"


def test_strict_json_targets_match_the_workflow():
    wf = (ROOT / ".github" / "workflows" / "refresh-data.yml").read_text(encoding="utf-8")
    line = next(l for l in wf.splitlines() if "check_strict_json.py" in l and "python" in l)
    # 工作流里是 `python ... check_strict_json.py a.json b.json ...`（折行写法）
    block = wf[wf.index("check_strict_json.py"):]
    for t in lp.STRICT_JSON_TARGETS:
        assert t in block[:400], f"{t} 与工作流的 strict-JSON 清单不一致"
    assert line


def test_local_publisher_does_not_impersonate_github_actions():
    """git 历史不许对「这次改动从哪来」撒谎 —— 本地发布不是 Actions 跑的。"""
    import ci_publish
    assert lp.LOCAL_BOT_NAME != ci_publish.BOT_NAME
    assert "github-actions" not in lp.LOCAL_BOT_NAME
    assert "local" in lp.LOCAL_BOT_NAME


def test_log_dir_is_gitignored():
    """日志若入库，它自己就成了「非数据产物改动」，下一次运行会被门0 拦下。"""
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "tools/refresh_logs/" in gi
    assert lp.LOGDIR.name == "refresh_logs"


def test_lock_constants_are_sane():
    assert lp.LOCK.parent == lp.LOGDIR
    assert 1 <= lp.LOCK_STALE_HOURS <= 24
