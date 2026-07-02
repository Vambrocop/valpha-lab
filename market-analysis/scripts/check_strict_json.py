"""
check_strict_json.py — Valpha150 家族产物严格 JSON 校验（P1-6）

build_valpha150.py / build_wildpool.py / ticker_ondemand.py / build_ndx.py / fetch_earnings.py
这 5 个产物在 refresh-data.yml「Refresh Valpha150 大盘数据」步骤单独生成，
时间上晚于 run_all.py 内的 verify_output 质量门 —— 不经过那道门。
一次 yfinance 抖动产生 NaN，若写出时没显式 allow_nan=False，会被 json.dumps 写成
非法 JSON 字面量 NaN/Infinity/-Infinity —— Python json.load 默认放行（悄悄转成
float('nan') 通过），但浏览器 JSON.parse 会拒绝整份文件 → 前端白屏。
（5 处写出点已在源头加 allow_nan=False；这里是第二道独立防线：写出后再拦一次，
防止未来有人加新写出点时忘记传 allow_nan。）

做法：json.load 的 parse_constant 钩子对 NaN/Infinity/-Infinity 主动抛错
（逻辑与 verify_output.py 里「1c 全部 web JSON 必须是浏览器级严格 JSON」一致）。

作为独立脚本运行（在 web/ 下检查给定文件名；不存在的文件静默跳过 —— 该产物本轮
生成失败已被上一步 `|| echo "::warning..."` 记录，不在本步重复报错/拦截无关旧文件）：
    py market-analysis/scripts/check_strict_json.py valpha150.json wildpool.json ticker_ondemand.json ndx.json earnings.json

也可作为模块导入：
    from check_strict_json import run
    problems = run(["valpha150.json", ...])   # 空列表 = 全部严格合法（或都不存在）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent          # market-analysis/scripts/
_MA_DIR      = _SCRIPTS_DIR.parent            # market-analysis/
WEB_DIR      = _MA_DIR / "web"


def _reject_const(token: str):
    """json.load 的 parse_constant 钩子：拒绝 NaN/Infinity/-Infinity。

    Python 默认对这三个 token 静默放行（转成 float('nan')/float('inf')），
    但它们不是合法 JSON —— 浏览器 JSON.parse 会直接拒绝整份文件。
    """
    raise ValueError(f"非法 JSON 常量 {token}（浏览器 JSON.parse 会拒绝整份文件）")


def run(names: list[str], web_dir: Path = WEB_DIR) -> list[str]:
    """对 web_dir 下给定文件名逐个做严格 JSON 解析。

    不存在的文件静默跳过（不计入失败——本轮该产物可能生成失败，由上一步已记录）。
    返回问题字符串列表；空列表表示全部严格合法（或都不存在，无可校验对象）。
    """
    problems: list[str] = []
    for name in names:
        p = web_dir / name
        if not p.exists():
            print(f"  · {name} 不存在，跳过（本轮可能未生成）")
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                json.load(fh, parse_constant=_reject_const)
            print(f"  ✓ {name} 严格 JSON")
        except Exception as e:
            msg = f"{name}: {e}"
            problems.append(msg)
            print(f"  ✗ {msg}")
    return problems


def main() -> None:
    names = sys.argv[1:]
    if not names:
        print("用法: py check_strict_json.py <file1.json> [file2.json ...]")
        sys.exit(2)
    print("=== check_strict_json: 严格 JSON（拒 NaN/Infinity）校验 ===")
    problems = run(names)
    if problems:
        print(f"\n[FAIL] {len(problems)} 个文件严格 JSON 校验未通过，拦截发布")
        sys.exit(1)
    print("\n[OK] 全部严格 JSON 校验通过")


if __name__ == "__main__":
    main()
