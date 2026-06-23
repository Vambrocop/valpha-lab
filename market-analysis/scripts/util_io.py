"""util_io.py — 统一的 JSON 产物写出助手。

去重各脚本里重复的样板：
    payload = json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False)
    for d in (PROC, WEB, DOCS):
        if d.exists():
            (d / "x.json").write_text(payload, encoding="utf-8")

write_json(name, payload, ...) 把 payload 写到 web/ + docs/（存在才写——沿用各脚本原行为；
run_all 末步仍会再镜像一次 web→docs）；proc=True 时也写 data/processed/。
四个序列化轴都对应真实调用方，逐字节复刻原内联写法：
    - indent     默认 2；fetch_insider 用 1，quick_quotes 用 None（配 separators 出紧凑）
    - allow_nan  默认 True（早期 7 个出格脚本没传）；其余产物脚本传 False（含 NaN 直接报错而非吐非法 JSON）
    - separators 仅 quick_quotes 用 (",", ":") 出紧凑
    - proc       三处写(PROC+WEB+DOCS)的统计脚本传 True
WEB/DOCS/PROC 从本文件位置推导，与各脚本原先 BASE/"web"、BASE.parent/"docs"、data/processed 口径一致。
"""
import json
from pathlib import Path

_BASE = Path(__file__).parent.parent              # market-analysis
WEB = _BASE / "web"                               # market-analysis/web
DOCS = _BASE.parent / "docs"                      # 仓库根 docs/（GitHub Pages）
PROC = _BASE / "data" / "processed"               # data/processed（部分统计脚本三处之一）


def write_json(name, payload, *, indent=2, allow_nan=True, separators=None, proc=False):
    """把 payload 写成 name 到 web/+docs/（proc=True 再加 data/processed/）。返回实际写入的目录列表。

    序列化与各脚本原内联完全一致：
    json.dumps(payload, ensure_ascii=False, indent=indent, allow_nan=allow_nan, separators=separators)
    """
    text = json.dumps(payload, ensure_ascii=False, indent=indent,
                      allow_nan=allow_nan, separators=separators)
    dirs = ((PROC,) if proc else ()) + (WEB, DOCS)
    written = []
    for d in dirs:
        if d.exists():
            (d / name).write_text(text, encoding="utf-8")
            written.append(d)
    return written
