# 刻意不写 shebang:Windows 的 py 启动器会遵循它转交 `python3`,而本机 python3 指向
# Microsoft Store 占位程序 → 静默退出 49、stdout/stderr 全空。同 ci_publish.py 的取舍。
"""local_publish.py — CI 被锁期间的**本地自动发布**（fail-closed 门禁）。

## 为什么需要它（2026-11-07）

GitHub Actions 自 2026-11-05 20:23 UTC 起被**账号级计费锁**挡住：job 在创建阶段
就被拒（3~4 秒、0 步骤、无 runner），错误原文
`The job was not started because your account is locked due to a billing issue.`
代码侧修不了（见 `CODEX_HANDOFF.md` §1）。但 **GitHub Pages 的部署不走 Actions 配额**
—— 本地跑完把 `docs/` 推上去，站点照常更新。

于是本地成了唯一的发布者。而**完整发布序列此前只存在于 `refresh-data.yml` 的 YAML 里**：
`run_all` 之后还有 7 个脚本（valpha150 / wildpool / ticker_ondemand / ndx / earnings /
cot / putcall）+ `check_strict_json` 这道独立的门。**YAML 里的逻辑本地跑不了**
—— 这正是 2026-09-03 把 commit/push 抽成 `ci_publish.py` 时记下的同一个教训
（`OPTIMIZATION_LOG §4c` 第一条：「CI 专属逻辑本地测不了就别直接上线」）。
本文件把那段序列也搬进 Python。

> **实证代价**：我 2026-11-06 那次手跑只跑了 `run_all`，**漏了这 7 个产物**。
> ndx 当天恰好被 `weekly_local_refresh.ps1` 的计划任务补上了，纯属巧合。

## 复用而非重写

- 提交/推送 → `ci_publish.publish()`（真 git 裸仓测过四条路径、显式暂存、rebase 重试）
- 防缩水门 → `ci_ledger_guard.py`（warn-only；2026-07-28 它以阻断 push 的方式失败过，
  把全站停更四天，代价远大于它防的稀有丢行）
- NaN/Infinity → `check_strict_json.py`
- insider/ndx 新鲜度 → `validate_refresh.py`

## 本文件新增的东西：**本地环境塌缩**对照门

CI 不需要它（CI 的环境就是基准）。本地需要，因为本地可能缺历史数据
—— `3f6285e` 那次 `^VIX3M` 缓存被覆盖成 1 行就是这类事故。

**要区分两件根本不同的事**（这是本文件最重要的设计判断）：

| | signature | 处置 |
|---|---|---|
| **本地环境塌缩** | 候选池某族成员变少 / 某个因子整条消失 | **硬门，拦住不发** |
| **真实统计更新** | 候选池一模一样，只有 verdict 在动 | **只报不拦** |

→ 所以 **存活名单的变化绝不作为门**。它本来就该随数据变动，那是整个系统的目的；
拦住它等于「冻结我们喜欢的结论」，正是本项目要防的那种不诚实。
变化会被大声记进日志让人看见，但不阻断发布。

## 用法

    py tools/local_publish.py --dry-run     # 跑全部门禁，不提交不推送
    py tools/local_publish.py               # 门全过则提交 + 推送
    py tools/local_publish.py --skip-pipeline   # 用现有产物只测门禁（开发用）
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "market-analysis" / "scripts"
WEB = ROOT / "market-analysis" / "web"
LOGDIR = ROOT / "tools" / "refresh_logs"          # 已在 .gitignore（日志若入库会把自己变成"非数据改动"）
LOCK = LOGDIR / ".publish.lock"
LOCK_STALE_HOURS = 6                               # 超过这么久的锁视为上次崩了，接管

sys.path.insert(0, str(ROOT / "tools"))
import ci_publish                                  # noqa: E402  复用发布逻辑

# 本地发布者的 git 身份：**刻意不用** ci_publish 默认的 github-actions[bot]
# —— 这不是 GitHub Actions 跑的，署名成它会让 git 历史对「这次改动从哪来」撒谎。
LOCAL_BOT_NAME = "valpha-local-publisher"
LOCAL_BOT_EMAIL = "valpha-local-publisher@users.noreply.github.com"

# `run_all` 的 verify_output 门**之后**才生成的产物（口径照 refresh-data.yml）。
# 逐个 fail-soft：单个源挂掉不该让整次发布泡汤（照 CI 的 `|| warning`）。
POST_GATE_SCRIPTS = [
    "build_valpha150.py", "build_wildpool.py", "ticker_ondemand.py",
    "build_ndx.py", "fetch_earnings.py", "fetch_cot.py", "fetch_putcall.py",
]
# 上面前 5 个脚本的产物不过 verify_output → 由 check_strict_json 单独把关（硬门）。
STRICT_JSON_TARGETS = ["valpha150.json", "wildpool.json", "ticker_ondemand.json",
                       "ndx.json", "earnings.json"]

CANARY_KEY = "vix_backwardation"      # 历史塌缩最先咬掉的那条因子
CANARY_FAMILY = "factor"


# ─────────────────────────── 纯函数（可测，零 I/O） ───────────────────────────

def classify_worktree(status_lines, allowed_prefixes=None):
    """把 `git status --porcelain` 的行分成「数据产物」与「其它」。

    **为什么要这道前置门**：本脚本只负责发布**数据产物**。若工作树里还有代码改动，
    那条路该走正常的、带提交门禁（`tools/pre_commit_gate.py` 干净检出）的人工流程。

    ⚠ 关键：`pre_commit_gate` 是 **Claude Code 的 PreToolUse 钩子，不是 git hook**
    —— 计划任务直接调 git commit **不会**触发它。所以本脚本必须自己跑 pytest（见 §10），
    并且拒绝在有代码改动时运行（代码改动才是干净检出门真正要抓的东西）。

    返回 (data_only: bool, offenders: list[str])。未跟踪文件（`??`）不算违规
    —— 它们进不了 `ci_publish` 的显式暂存，不会被发布。
    """
    allowed = list(ci_publish.DEFAULT_PATHS if allowed_prefixes is None else allowed_prefixes)
    offenders = []
    for raw in status_lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        code, _, rest = line[:2], line[2:3], line[3:]
        path = rest.strip().strip('"')
        if "->" in path:                       # 重命名 "old -> new"，取新名
            path = path.split("->")[-1].strip().strip('"')
        if code.strip() == "??":               # 未跟踪：不会被暂存，无害
            continue
        if not any(path == p or path.startswith(p.rstrip("/") + "/") for p in allowed):
            offenders.append(f"{code} {path}")
    return (not offenders), offenders


def pool_by_family(doc):
    """候选池逐族规模。整族变少 = 本地缺数据的特征signature。"""
    out = {}
    for c in (doc or {}).get("candidates") or []:
        out[c.get("family") or "?"] = out.get(c.get("family") or "?", 0) + 1
    return out


def pool_collapse(before, after):
    """硬门：候选池**不许缩**。返回问题列表（空 = 过）。

    只拦「变少」：候选空间扩容（N_DECLARED 增长）是正常演进，不该被拦。
    """
    problems = []
    fb, fa = pool_by_family(before), pool_by_family(after)
    for fam in sorted(set(fb) | set(fa)):
        b, a = fb.get(fam, 0), fa.get(fam, 0)
        if a < b:
            problems.append(f"{fam} 族候选从 {b} 掉到 {a}（少了 {b - a} 条）")
    return problems


def canary_present(doc, key=CANARY_KEY, family=CANARY_FAMILY):
    """硬门：那条哨兵因子必须还在它的族里（verdict 是什么无所谓，在不在才是关键）。"""
    for c in (doc or {}).get("candidates") or []:
        if c.get("key") == key:
            return (c.get("family") == family), c.get("family")
    return False, None


def survivor_diff(before, after):
    """**只报不拦**：存活名单的进出。它本来就该随数据变（见模块 docstring）。"""
    def surv(d):
        return {c.get("key") for c in (d or {}).get("candidates") or []
                if c.get("verdict") == "survive"}
    b, a = surv(before), surv(after)
    return sorted(b - a), sorted(a - b)


def health_problems(health):
    """硬门：data_health 必须 total==ok、shrunk==0。"""
    s = (health or {}).get("summary") or {}
    total, ok = s.get("total"), s.get("ok")
    problems = []
    if not isinstance(total, int) or not isinstance(ok, int) or total <= 0:
        return [f"data_health.summary 读不到 total/ok：{s!r}"]
    if ok != total:
        problems.append(f"{total - ok} 个序列非 ok（{ok}/{total}）")
    if s.get("shrunk"):
        problems.append(f"{s['shrunk']} 个序列被判 shrunk（历史塌缩守卫报警）")
    if s.get("missing"):
        problems.append(f"{s['missing']} 个序列缺失")
    return problems


# ─────────────────────────── I/O 辅助 ───────────────────────────

class Log:
    def __init__(self, path):
        self.path = path
        self.lines = []

    def __call__(self, msg):
        line = f"{datetime.datetime.now():%H:%M:%S}  {msg}"
        print(line, flush=True)
        self.lines.append(line)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def _run(cmd, log, cwd=None, env=None, label=None):
    """跑子进程，输出进日志。返回 returncode。"""
    label = label or " ".join(str(c) for c in cmd)
    log(f"--- {label} ---")
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    if env:
        e.update(env)
    p = subprocess.run(cmd, cwd=str(cwd or ROOT), env=e,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()
    for ln in tail[-25:]:                       # 只留尾部，完整输出太长
        log(f"    {ln}")
    log(f"--- {label} → exit {p.returncode} ---")
    return p.returncode


def _git_out(*args):
    p = subprocess.run(["git", *args], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "")


def head_docs_json(name):
    """读 **git HEAD 里的** docs/<name>（= 当前已发布版本），作对照基线。"""
    rc, out = _git_out("show", f"HEAD:docs/{name}")
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


def web_json(name):
    try:
        return json.loads((WEB / name).read_text(encoding="utf-8"))
    except Exception:
        return None


def acquire_lock(log):
    """互斥锁。**2026-11-06 实际撞过**：`ValphaWeeklyRefresh` 在 10:00:30 跑 build_ndx，
    而我的手动 run_all 正在 09:48–10:02 之间跑 —— 两个 writer 同时写产物。"""
    LOGDIR.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            info = json.loads(LOCK.read_text(encoding="utf-8"))
            age_h = (time.time() - float(info.get("ts", 0))) / 3600
        except Exception:
            info, age_h = {}, 999
        if age_h < LOCK_STALE_HOURS:
            log(f"!! 已有发布在跑（pid={info.get('pid')} 开始于 "
                f"{info.get('started')}，{age_h:.1f}h 前）→ 本次退出，不并发写产物")
            return False
        log(f"发现陈旧锁（{age_h:.1f}h > {LOCK_STALE_HOURS}h，上次大概崩了）→ 接管")
    LOCK.write_text(json.dumps({"pid": os.getpid(), "ts": time.time(),
                                "started": datetime.datetime.now().isoformat(timespec="seconds")}),
                    encoding="utf-8")
    return True


def release_lock():
    try:
        LOCK.unlink()
    except Exception:
        pass


# ─────────────────────────── 主流程 ───────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description="CI 被锁期间的本地自动发布（fail-closed）")
    ap.add_argument("--dry-run", action="store_true", help="跑全部门禁但不提交不推送")
    ap.add_argument("--skip-pipeline", action="store_true",
                    help="跳过 run_all 与门后脚本，用现有产物只测门禁（开发用）")
    ap.add_argument("--skip-tests", action="store_true",
                    help="跳过 pytest（**只给开发用**；计划任务绝不加这个）")
    a = ap.parse_args(argv)

    LOGDIR.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}"
    log = Log(LOGDIR / f"local_publish_{stamp}.log")
    log(f"=== 本地发布 START ({stamp}) ===")
    log(f"repo: {ROOT}   dry_run={a.dry_run}")

    if not acquire_lock(log):
        return 0                                  # 不是错误：另一个实例在跑
    try:
        return _run_gates(a, log)
    finally:
        release_lock()


def _run_gates(a, log):
    fail = []

    # ── 门 0：工作树必须只有数据产物改动 ──────────────────────────────
    rc, st = _git_out("status", "--porcelain")
    data_only, offenders = classify_worktree(st.splitlines())
    if not data_only:
        log("!! 工作树里有**非数据产物**的改动 → 拒绝自动发布：")
        for o in offenders:
            log(f"     {o}")
        log("   代码改动请走人工流程（带 tools/pre_commit_gate.py 的干净检出门禁）。")
        _summary(log, False, ["工作树含代码改动，自动发布拒绝介入"])
        return 2
    log(f"门0 工作树只有数据产物改动 ✓（{len(st.splitlines())} 行状态）")

    # ── 对照基线：**先**取 HEAD 里已发布的版本，再跑流水线 ─────────────
    before = head_docs_json("autodiscovery.json")
    if before is None:
        log("!! 读不到 HEAD:docs/autodiscovery.json → 没有对照基线，拒绝发布")
        _summary(log, False, ["拿不到对照基线"])
        return 2
    log(f"对照基线：HEAD:docs/autodiscovery.json generated={before.get('generated')}")

    # ── 门 1：不落后 origin（别和别的 writer 打架） ────────────────────
    _git_out("fetch", "--quiet")
    rc, counts = _git_out("rev-list", "--left-right", "--count", "HEAD...origin/main")
    try:
        ahead, behind = (int(x) for x in counts.split())
    except Exception:
        ahead, behind = -1, -1
    if behind != 0:
        log(f"!! 落后 origin {behind} 个提交 → 先 pull 再说，本次不发布")
        _summary(log, False, [f"落后 origin {behind} 个提交"])
        return 2
    log(f"门1 与 origin 同步 ✓（ahead={ahead} behind={behind}）")

    # ── 流水线 ────────────────────────────────────────────────────────
    if a.skip_pipeline:
        log("（--skip-pipeline：跳过 run_all 与门后脚本）")
    else:
        if _run([sys.executable, str(SCRIPTS / "run_all.py")], log, label="run_all.py") != 0:
            log("!! run_all 失败（verify_output 在其第 126 步，失败即终止）→ 不发布")
            _summary(log, False, ["run_all 失败"])
            return 1
        log("run_all ✓（含 verify_output）")

        # 门后脚本：逐个 fail-soft，照 CI 的 `|| warning` 口径
        soft = []
        for s in POST_GATE_SCRIPTS:
            if _run([sys.executable, str(SCRIPTS / s)], log, label=s) != 0:
                soft.append(s)
        if soft:
            log(f"(警告) 门后脚本失败 {len(soft)} 个（非致命，下次重试）：{soft}")

        # 硬门：那 5 个产物不过 verify_output → NaN/Infinity 会让浏览器整份拒绝 → 白屏
        if _run([sys.executable, str(SCRIPTS / "check_strict_json.py"), *STRICT_JSON_TARGETS],
                log, label="check_strict_json.py") != 0:
            log("!! strict-JSON 门未过（产物含 NaN/Infinity，会让前端白屏）→ 不发布")
            _summary(log, False, ["strict-JSON 门未过"])
            return 1
        log("门2 strict-JSON ✓")

    # ── 门 3：data_health ─────────────────────────────────────────────
    hp = health_problems(web_json("data_health.json"))
    if hp:
        log("!! data_health 门未过 → 不发布：")
        for p in hp:
            log(f"     {p}")
        _summary(log, False, ["data_health 门未过"] + hp)
        return 1
    log("门3 data_health 全 ok、0 shrunk ✓")

    # ── 门 4：本地环境塌缩对照（硬门） ────────────────────────────────
    after = web_json("autodiscovery.json")
    if after is None:
        log("!! 读不到本地 autodiscovery.json → 不发布")
        _summary(log, False, ["本地 autodiscovery.json 读不到"])
        return 1
    coll = pool_collapse(before, after)
    if coll:
        log("!! 候选池缩了 → 本地缺历史数据的特征，拒绝发布：")
        for p in coll:
            log(f"     {p}")
        _summary(log, False, ["候选池塌缩"] + coll)
        return 1
    log(f"门4a 候选池未缩 ✓（{sum(pool_by_family(after).values())} 条，逐族比对）")

    ok, fam = canary_present(after)
    if not ok:
        log(f"!! 哨兵因子 {CANARY_KEY} 不在 {CANARY_FAMILY} 族（实为 {fam!r}）"
            f" → 历史塌缩的典型表现，拒绝发布")
        _summary(log, False, [f"哨兵 {CANARY_KEY} 掉出 {CANARY_FAMILY} 族"])
        return 1
    log(f"门4b 哨兵 {CANARY_KEY} 在 {CANARY_FAMILY} 族内 ✓")

    # ── 报告（**不是门**）：存活名单的进出 ────────────────────────────
    gone, new = survivor_diff(before, after)
    if gone or new:
        log("※ 存活名单有变动（**只报不拦** —— 它本来就该随数据变；拦它等于冻结结论）：")
        for k in gone:
            log(f"     ➖ 掉出：{k}")
        for k in new:
            log(f"     ➕ 新进：{k}")
        log("   候选池未缩 + 哨兵在位 → 判定为真实统计更新，不是本地数据塌缩。")
    else:
        log("※ 存活名单无变动")

    # ── 门 5：pytest（必须自己跑 —— pre_commit_gate 是 Claude 钩子，计划任务不触发）
    if a.skip_tests:
        log("(警告) --skip-tests：跳过 pytest。计划任务绝不该用这个。")
    else:
        if _run([sys.executable, "-m", "pytest", "market-analysis/tests", "-q"],
                log, label="pytest") != 0:
            log("!! pytest 未全绿 → 不发布")
            _summary(log, False, ["pytest 未全绿"])
            return 1
        log("门5 pytest 全绿 ✓")

    # ── 发布 ──────────────────────────────────────────────────────────
    if a.dry_run:
        log("=== --dry-run：全部门禁已过，但不提交不推送 ===")
        _summary(log, True, [], dry=True)
        return 0

    # ⚠ 身份必须**传给 publish()**，不能只在调用前 configure_bot ——
    #   publish() 内部会再 configure_bot 一次，把外面设的覆盖掉。
    #   2026-11-07 第一版就栽在这里：提交 c77b6a90 被错标成 github-actions[bot]。
    msg = (f"chore: 本地自动发布数据 {datetime.date.today():%Y-%m-%d} [skip ci]\n\n"
           f"CI 的 Actions 被账号计费锁挡住（见 CODEX_HANDOFF.md §1），本地代为发布。\n"
           f"过的门：工作树只含数据产物 · 不落后 origin · run_all(含 verify_output) · "
           f"strict-JSON · data_health 全 ok/0 shrunk · 候选池未缩 · 哨兵因子在位 · pytest 全绿。\n"
           f"存活名单变动：掉出 {gone or '无'} / 新进 {new or '无'}（只报不拦）。")
    rc = ci_publish.publish(ROOT, msg, guard=str(ROOT / "tools" / "ci_ledger_guard.py"),
                            empty_note="数据无变化,跳过提交",
                            bot_name=LOCAL_BOT_NAME, bot_email=LOCAL_BOT_EMAIL)
    if rc != 0:
        log("!! 推送失败（ci_publish 已重试过一次）")
        _summary(log, False, ["推送失败"])
        return 1
    log("=== 发布完成 ===")
    _summary(log, True, [], gone=gone, new=new)
    return 0


def _summary(log, ok, problems, dry=False, gone=None, new=None):
    """写人话摘要 + 成功标记。PowerShell 外壳据此决定要不要在桌面放旗标。"""
    now = f"{datetime.datetime.now():%a %Y-%m-%d %H:%M}"
    lines = ["=" * 60, f"  Valpha 本地自动发布  -  {now}", "=" * 60, ""]
    if ok:
        lines.append("  结果：全部门禁通过" + ("（--dry-run，未推送）" if dry else "，已提交并推送"))
        if gone or new:
            lines.append(f"  存活名单变动：掉出 {gone or '无'} / 新进 {new or '无'}")
        lines += ["", "  你不需要做任何事。站点会由 GitHub Pages 自动部署",
                  "  （Pages 不走 Actions 配额，所以计费锁不影响它）。"]
    else:
        lines.append("  结果：**没有发布**（门禁拦下了）")
        lines.append("")
        for p in problems:
            lines.append(f"    - {p}")
        lines += ["", "  需要你做的：看下面的日志，判断是真问题还是本地环境问题。",
                  "  产物改动还留在工作树里，没有被推送。要丢弃：git checkout -- ."]
    lines += ["", f"  完整日志：{log.path}", "=" * 60]
    txt = "\n".join(lines)
    print("\n" + txt)
    try:
        (LOGDIR / "LATEST_PUBLISH.txt").write_text(txt, encoding="utf-8")
        if ok and not dry:
            (LOGDIR / ".last_publish").write_text(f"{datetime.date.today():%Y-%m-%d}",
                                                  encoding="ascii")
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
