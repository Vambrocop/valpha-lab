"""post_edit_hook.py — PostToolUse 钩子：编辑命中 market-analysis/web/ 时自动镜像到 docs/。

把"改 web/ 要手动 Copy-Item 到 docs/"变成机器自动做（CLAUDE.md 的镜像约定）。
Claude Code 经 stdin 传 JSON（含 tool_input.file_path）。web/ 与 docs/ 是扁平镜像。
配在 .claude/settings.json 的 hooks.PostToolUse[matcher=Edit|Write]：`py tools/post_edit_hook.py`
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

# 钩子由 Claude Code 调起时不带 PYTHONUTF8，Windows 默认 GBK stdout 会让非 ASCII 输出崩溃 → 强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SRC = "market-analysis/web"
DST = "docs"


def _node_check(p):
    """改了我们写的 .js 就 node --check：一处语法错会让全站白屏 → 编辑后立刻拦住（跳过 vendored plotly）。"""
    if p.suffix != ".js" or p.name.startswith("plotly"):
        return
    node = shutil.which("node")
    if not node:
        return                          # 环境无 node，静默跳过
    r = subprocess.run([node, "--check", str(p)], capture_output=True, text=True)
    if r.returncode != 0:
        _lines = [ln.strip() for ln in r.stderr.splitlines() if ln.strip()]
        err = next((ln for ln in _lines if "Error" in ln), _lines[0] if _lines else "parse error")
        print(f"[hook] !! {p.name} JS 语法错误(提交前必修,否则全站白屏): {err}")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    fp = ((data.get("tool_input") or {}).get("file_path") or "").replace("\\", "/")
    if not fp or SRC not in fp:
        return
    p = Path(fp)
    if not p.exists():
        return
    dst = Path.cwd() / DST / p.name        # 扁平镜像
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        print(f"[hook] mirrored {p.name} -> {DST}/")
    except Exception as e:
        print(f"[hook] mirror failed: {e}")
    _node_check(p)


if __name__ == "__main__":
    main()
