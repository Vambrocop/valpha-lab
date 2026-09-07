"""pre_commit_gate.py — PreToolUse(Bash) 门禁：git commit 前跑 pytest，不绿则拦截(deny)。

机器强制"提交前 pytest 全绿"，不靠 agent 记得。
2026-07-07 升级为 **CI 同构·干净检出**：把索引树 `git archive` 到临时目录再跑 pytest——
干净检出里没有 gitignore 的生成数据(data/raw/ 等)，测试若偷偷依赖它们，提交那一刻就拦下，
不用等 CI 红(#100–104 连挂教训：本地绿 CI 红，根因正是这类依赖)。
干净检出自身出 infra 错 → 降级为在树内跑(仍是门禁)；再出错 → 放行(fail-open，
不因 infra 卡死正常提交)。pytest 真失败才 deny。
配在 .claude/settings.json 的 hooks.PreToolUse[matcher=Bash, if=Bash(git commit:*)]。
"""
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile


def allow():
    sys.exit(0)                       # 无 deny 输出 → 正常放行


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}, ensure_ascii=False))
    sys.exit(0)


def _pytest(env, cwd=None):
    return subprocess.run([sys.executable, "-m", "pytest", "market-analysis/tests", "-q"],
                          capture_output=True, text=True, env=env, timeout=150, cwd=cwd)


# CI 的 checkout 形状:actions/checkout@v4 默认 `--depth=1`,所以工作区里是
# **单个提交、没有父提交**,而 schedule 跑的 HEAD 常常是 bot 的自动数据提交。
_BOT_NAME = "github-actions[bot]"
_BOT_EMAIL = "github-actions[bot]@users.noreply.github.com"


def _make_shallow_like_repo(tmp, timeout=60):
    """把临时目录变成一个「单提交·无父提交·HEAD 作者=bot」的 git 仓库。

    ## 为什么非得有 .git(2026-09-06 事故驱动)

    原来这里只 `git archive` 索引树,临时目录**根本没有 .git**。于是任何读 git 历史的测试
    在门禁里的行为都与 CI 不同 —— 我 09-04 写的一条守门测试正是这样:它在 CI 的浅克隆下
    把「单个无父提交的 commit」当成根提交,`git show --name-only` 列出**整个仓库 556 个文件**,
    断言必然失败;而门禁里没有 .git,那条测试走的是完全另一条分支,**一路放行**。
    结果:本地绿、门禁绿、CI 红,数据刷新停了。

    ## 为什么不是简单换成 `git clone --depth=1`

    克隆拿到的是 **HEAD(上一个提交)**,而 pre-commit 门禁必须测**即将提交的内容**(索引树)。
    换成克隆等于测错了东西。所以两件事都要做:先归档索引树(内容正确),
    再在临时目录里 init + 提交一次(git 形状正确)。

    ## 为什么把作者设成 bot

    那条 bug **只在 HEAD 作者是 github-actions[bot] 时**触发(测试按 `--author=github-actions` 筛)。
    我手动跑 CI 时 HEAD 都是自己的提交,恰好绕开 —— 假绿。门禁要拦的是最坏情况,
    所以这里直接复刻最坏形状。

    失败不抛给调用方之外的地方:任何一步出错都 raise,由 main() 降级处理(fail-open)。
    """
    base = ["git", "-c", f"user.name={_BOT_NAME}", "-c", f"user.email={_BOT_EMAIL}",
            "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
    steps = [
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["commit", "-q", "--no-verify", "-m", "chore: auto-refresh market data [skip ci]"],
    ]
    for st in steps:
        r = subprocess.run(base + st, cwd=tmp, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(f"git {st[0]} (CI 形状复刻): {(r.stderr or r.stdout).strip()[:200]}")


def _clean_checkout_pytest(env):
    """索引树 → 临时目录干净检出 + 复刻 CI 的浅克隆形状 → pytest。

    双重同构:**内容**=即将提交的索引树(不是 HEAD);**git 形状**=单提交无父提交、作者是 bot。
    干净检出还顺带保证测试不偷偷依赖 gitignore 的生成数据(data/raw/ 等)。
    """
    tree = subprocess.run(["git", "write-tree"], capture_output=True, text=True, timeout=30)
    if tree.returncode != 0:
        raise RuntimeError(f"git write-tree: {tree.stderr.strip()}")
    tmp = tempfile.mkdtemp(prefix="ci_parity_")
    tar_path = os.path.join(tmp, "_tree.tar")
    with open(tar_path, "wb") as f:
        ar = subprocess.run(["git", "archive", tree.stdout.strip()], stdout=f, timeout=120)
    if ar.returncode != 0:
        raise RuntimeError("git archive failed")
    with tarfile.open(tar_path) as tf:
        tf.extractall(tmp, filter="data")
    os.remove(tar_path)
    _make_shallow_like_repo(tmp)
    return _pytest(env, cwd=tmp), tmp


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        allow()
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if "git commit" not in cmd:       # 双保险：非 commit 放行(即便 if 漏过)
        allow()
    env = {**os.environ, "PYTHONUTF8": "1"}
    tmp, mode = None, "干净检出(CI同构)"
    try:
        try:
            r, tmp = _clean_checkout_pytest(env)
        except Exception:
            mode = "树内(干净检出infra失败,降级)"
            r = _pytest(env)
    except Exception as e:
        print(json.dumps({"systemMessage": f"pre-commit pytest 门禁未能运行({e})，已放行；请手动确认测试。"},
                         ensure_ascii=False))
        sys.exit(0)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    if r.returncode == 0:
        allow()
    tail = (r.stdout or "").strip().splitlines()
    summary = tail[-1] if tail else "pytest failed"
    deny(f"提交被拦截：pytest[{mode}] 未全绿（{summary}）。"
         "若树内绿而这里红=测试依赖了 gitignore 生成数据(CI 也会红)。修复后再提交。")


if __name__ == "__main__":
    main()
