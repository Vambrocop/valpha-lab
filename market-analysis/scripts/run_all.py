"""
run_all.py — 一键运行所有分析并生成网站
"""
import subprocess, sys
from pathlib import Path

SCRIPTS = Path(__file__).parent

steps = [
    ("下载数据",       "fetch_data.py"),
    ("基础统计分析",   "analyze.py"),
    ("高级ML分析",     "advanced_analysis.py"),
    ("生成网站",       "build_dashboard.py"),
]

for label, script in steps:
    print(f"\n{'='*55}")
    print(f"  ▶  {label}  ({script})")
    print(f"{'='*55}")
    r = subprocess.run([sys.executable, str(SCRIPTS / script)])
    if r.returncode != 0:
        print(f"\n✗ [{label}] 失败，已终止")
        sys.exit(1)

print("\n✓ 全部完成！打开 web/index.html 查看仪表盘")
