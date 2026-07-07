"""
check_docs_mirror.py — web/ ↔ docs/ 镜像同步守卫

比较 market-analysis/web/ 中的手写源文件与 docs/ 镜像是否字节一致。
- 只比对 .html / .css 以及已知手写的 .js（排除 pipeline 生成的 .json 和第三方库）
- docs/ 不存在时静默跳过（不崩溃），便于本地纯前端开发环境
- 作为独立脚本运行：py market-analysis/scripts/check_docs_mirror.py
- 也可作为模块导入：from check_docs_mirror import run; problems = run()
  run() 返回问题字符串列表；空列表表示全部同步

比对范围（web/ → docs/）:
  *.html        所有手写页面
  *.css         所有样式表（vp.css, style.css …）
  手写 *.js     仅 vp_gloss.js 和 app-1..N.js（排除 plotly-*.min.js 等第三方打包）
  .nojekyll     GitHub Pages 标志文件

不比对:
  *.json        pipeline 生成的数据文件，时序上合法不同步
  plotly-*.js   第三方库，字节不变但非本地手写
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# 路径常量
# --------------------------------------------------------------------------- #
_SCRIPTS_DIR = Path(__file__).parent          # market-analysis/scripts/
_MA_DIR      = _SCRIPTS_DIR.parent            # market-analysis/
_REPO_ROOT   = _MA_DIR.parent                 # repo root (e.g. E:\finance)
WEB_DIR      = _MA_DIR / "web"
DOCS_DIR     = _REPO_ROOT / "docs"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_handwritten_js(name: str) -> bool:
    """True for hand-authored JS we want to guard; False for third-party bundles.

    规则(白名单式,自解释)：手写核心一律 `vp_*.js`（vp_gloss / vp_i18n / 未来新增 vp_ 核心
    自动纳入，不再靠显式点名——2026-07-07 补 vp_i18n.js 漏网的教训）与 `app-<N>.js`；
    厂商打包(plotly-*.min.js 等)按命名前缀天然排除。
    """
    if not name.endswith(".js"):
        return False
    if name.startswith("vp_"):        # vp_gloss.js / vp_i18n.js / 未来 vp_ 核心
        return True
    if name.startswith("app-"):       # app-1.js … app-N.js
        return True
    return False                       # plotly-cartesian-*.min.js 等厂商包


def _should_compare(path: Path) -> bool:
    """Return True if this web/ file should be mirrored byte-for-byte in docs/."""
    name   = path.name
    suffix = path.suffix.lower()

    if suffix == ".html":
        return True
    if suffix == ".css":
        return True
    if suffix == ".js":
        return _is_handwritten_js(name)
    if name == ".nojekyll":
        return True
    # .json and everything else: skip
    return False


def run() -> list[str]:
    """
    Compare hand-authored web/ assets against docs/.

    Returns a list of problem strings (empty = all in sync).
    If docs/ does not exist, returns [] (graceful skip).
    """
    if not DOCS_DIR.exists():
        print("  · docs/ 目录不存在，跳过镜像同步检查（可能是纯开发环境）")
        return []

    if not WEB_DIR.exists():
        return [f"web/ 目录不存在: {WEB_DIR}"]

    problems: list[str] = []

    for src in sorted(WEB_DIR.iterdir()):
        if not src.is_file():
            continue
        if not _should_compare(src):
            continue

        mirror = DOCS_DIR / src.name

        if not mirror.exists():
            msg = f"MISSING in docs/: {src.name}"
            problems.append(msg)
            print(f"  ✗ {msg}")
            continue

        src_hash    = _sha256(src)
        mirror_hash = _sha256(mirror)

        if src_hash != mirror_hash:
            msg = f"DRIFT  web/{src.name} ≠ docs/{src.name}"
            problems.append(msg)
            print(f"  ✗ {msg}")
        else:
            print(f"  ✓ {src.name} 同步")

    return problems


def main() -> None:
    print("=== check_docs_mirror: web/ ↔ docs/ 镜像同步检查 ===")
    problems = run()
    if problems:
        print(
            f"\n[FAIL] {len(problems)} 个文件未同步"
            f"（手动编辑 web/ 后请运行镜像步骤或 run_all.py）"
        )
        sys.exit(1)
    print("\n[OK] web/ ↔ docs/ 全部同步")


if __name__ == "__main__":
    main()
