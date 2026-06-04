"""
run_all.py
一键运行：下载数据 → 统计分析 → 生成网站
"""
import subprocess, sys

steps = [
    ("下载数据",   "fetch_data.py"),
    ("统计分析",   "analyze.py"),
    ("生成网站",   "build_dashboard.py"),
]

for label, script in steps:
    print(f"\n{'='*50}")
    print(f"  {label}...")
    print(f"{'='*50}")
    result = subprocess.run([sys.executable, script], cwd=str(__file__).replace("run_all.py", ""))
    if result.returncode != 0:
        print(f"✗ {label} 失败，终止")
        sys.exit(1)

print("\n✓ 全部完成！打开 web/index.html 查看仪表盘")
