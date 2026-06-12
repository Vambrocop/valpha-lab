"""
split_appjs.py — 把 web/app.js 切成有序经典脚本 app-1..5.js（一次性工具）

安全契约：
  concat(app-1.js .. app-5.js, 按序) == app.js  逐字节相等
切点都在列0的 // ═══ section 头，保持原顺序不动一行。
切完用 node --check 逐个验证语法。
"""
import subprocess
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "market-analysis" / "web"
SRC = WEB / "app.js"

# 历史一次性工具：app.js 已于拆分后删除。重跑会找不到源文件——这是预期的。
if not SRC.exists():
    raise SystemExit(
        "app.js 已不存在：拆分早已完成，源文件已删除。\n"
        "现在的前端源是 web/app-1.js .. app-5.js（有序经典脚本，拼回 == 原 app.js）。\n"
        "本脚本仅留作记录，说明当初是怎么切的；无需再跑。")

# 1-indexed inclusive 行边界（已核对：均为列0 section 头，前一行空行）
PARTS = [
    ("app-1.js", 1, 970),     # 核心库 + 今日 + 信号 + 图表底座
    ("app-2.js", 971, 1447),  # 价格/相关/月度/GARCH/Granger/年度/历史图
    ("app-3.js", 1448, 2095), # 组合表 + SPCX 追踪 + 工具面板
    ("app-4.js", 2096, 3119), # 选股/简报/论文/报告/新闻/隔夜 + 市场时钟
    ("app-5.js", 3120, 3594), # benchmark + init().then 引导 + 视图/研究渲染
]

# 保留行尾符（CRLF/LF 原样），保证逐字节可拼回
with open(SRC, "r", newline="", encoding="utf-8") as fh:
    lines = fh.readlines()
n = len(lines)
print(f"app.js 共 {n} 行")
assert PARTS[-1][2] == n, f"最后一段结尾 {PARTS[-1][2]} != 总行数 {n}"

# 边界连续性自检：上一段 end+1 == 下一段 start
for (a, b) in zip(PARTS, PARTS[1:]):
    assert a[2] + 1 == b[1], f"边界不连续: {a} -> {b}"
assert PARTS[0][1] == 1

written = []
for name, start, end in PARTS:
    chunk = "".join(lines[start - 1:end])  # 1-indexed -> 0-indexed slice
    out = WEB / name
    with open(out, "w", newline="", encoding="utf-8") as fh:
        fh.write(chunk)
    written.append(out)
    print(f"  {name}: 行 {start}-{end}  ({end-start+1} 行, {len(chunk)} 字节)")

# 安全契约：拼回 == 原文（逐字节）
recombined = "".join("".join(lines[s - 1:e]) for _, s, e in PARTS)
original = "".join(lines)
assert recombined == original, "✗✗✗ 拼接不等于原文！中止"
print("✓ 拼接逐字节 == 原 app.js")

# node --check 逐个验证语法
allok = True
for out in written:
    r = subprocess.run(["node", "--check", str(out)], capture_output=True, text=True)
    status = "✓" if r.returncode == 0 else "✗"
    if r.returncode != 0:
        allok = False
        print(f"  {status} {out.name} 语法错误:\n{r.stderr}")
    else:
        print(f"  {status} {out.name} node --check 通过")

if not allok:
    sys.exit("✗ 有文件语法检查未通过")
print("\n[OK] 切分完成，5 个文件语法合法，拼回等于原文")
