"""util_io.py — 统一的 JSON 产物写出助手。

去重各脚本里重复的样板：
    for d in (WEB, DOCS):
        if d.exists():
            (d / "x.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), ...)

write_json(name, payload) 把 payload 以 ensure_ascii=False, indent=2 写到 web/ 与 docs/
（两者存在才写——沿用各脚本原行为；run_all 末步仍会再镜像一次 web→docs）。
WEB/DOCS 从本文件位置推导，与各脚本原先 BASE/"web"、BASE.parent/"docs" 的口径一致。
"""
import json
from pathlib import Path

WEB = Path(__file__).parent.parent / "web"            # market-analysis/web
DOCS = Path(__file__).parent.parent.parent / "docs"   # 仓库根 docs/（GitHub Pages）


def write_json(name, payload, *, indent=2):
    """把 payload 写成 name 到 web/ 与 docs/（目录存在才写）。返回实际写入的目录列表。

    序列化与各脚本原先一致：json.dumps(payload, ensure_ascii=False, indent=indent)。
    """
    text = json.dumps(payload, ensure_ascii=False, indent=indent)
    written = []
    for d in (WEB, DOCS):
        if d.exists():
            (d / name).write_text(text, encoding="utf-8")
            written.append(d)
    return written
