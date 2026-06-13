"""post_edit_hook.py — PostToolUse 钩子：编辑命中 market-analysis/web/ 时自动镜像到 docs/。

把"改 web/ 要手动 Copy-Item 到 docs/"变成机器自动做（CLAUDE.md 的镜像约定）。
Claude Code 经 stdin 传 JSON（含 tool_input.file_path）。web/ 与 docs/ 是扁平镜像。
配在 .claude/settings.json 的 hooks.PostToolUse[matcher=Edit|Write]：`py tools/post_edit_hook.py`
"""
import json
import shutil
import sys
from pathlib import Path

SRC = "market-analysis/web"
DST = "docs"


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


if __name__ == "__main__":
    main()
