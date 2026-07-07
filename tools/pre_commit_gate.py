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


def _clean_checkout_pytest(env):
    """索引树 → 临时目录干净检出 → pytest(与 CI 的 checkout 后测试步同构)。"""
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
