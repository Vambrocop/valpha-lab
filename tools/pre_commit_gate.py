"""pre_commit_gate.py — PreToolUse(Bash) 门禁：git commit 前跑 pytest，不绿则拦截(deny)。

机器强制"提交前 pytest 全绿"，不靠 agent 记得。
仅对 git commit 生效(读 stdin 命令判断)；pytest 通过 / 非 commit / 门禁自身出错 → 放行(fail-open，
不因 infra 卡死正常提交)。pytest 真失败才 deny。
配在 .claude/settings.json 的 hooks.PreToolUse[matcher=Bash, if=Bash(git commit:*)]。
"""
import json
import os
import subprocess
import sys


def allow():
    sys.exit(0)                       # 无 deny 输出 → 正常放行


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}, ensure_ascii=False))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        allow()
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if "git commit" not in cmd:       # 双保险：非 commit 放行(即便 if 漏过)
        allow()
    env = {**os.environ, "PYTHONUTF8": "1"}
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "market-analysis/tests", "-q"],
                           capture_output=True, text=True, env=env, timeout=180)
    except Exception as e:
        print(json.dumps({"systemMessage": f"pre-commit pytest 门禁未能运行({e})，已放行；请手动确认测试。"}))
        sys.exit(0)
    if r.returncode == 0:
        allow()
    tail = (r.stdout or "").strip().splitlines()
    summary = tail[-1] if tail else "pytest failed"
    deny(f"提交被拦截：pytest 未全绿（{summary}）。修复后再提交。")


if __name__ == "__main__":
    main()
