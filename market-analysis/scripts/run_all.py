"""
run_all.py — 一键运行完整流水线并同步部署目录

顺序很重要：
  1. 抓数据（fetch_data / long_history）
  2. 基础统计 + 时机分析 + 事件研究（build_signals 的输入）
  3. build_signals 第一遍（生成 daily_signals，供回测读取）
  4. backtest / walk_forward（写 data/processed/*.json）
  5. build_signals 第二遍（把最新回测/滚动验证结果嵌入 signals.json）
  6. export_chart_data（prices.json / charts_extra.json）
  7. 把 web/ 镜像到仓库根 docs/（GitHub Pages 部署目录）

加 --full 参数会额外跑重型 ML 分析（advanced_analysis / multivariate）。
"""
import subprocess, sys, shutil
from pathlib import Path

SCRIPTS = Path(__file__).parent
WEB_DIR = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"   # 仓库根 docs/，GitHub Pages 部署目录

steps = [
    ("下载数据",           "fetch_data.py"),
    ("下载长历史数据",     "long_history.py"),
    ("基础统计分析",       "analyze.py"),
    ("买卖时机分析",       "timing_analysis.py"),
    ("历史事件研究",       "event_study.py"),
    ("生成每日信号",       "build_signals.py"),
    ("回测验证",           "backtest.py"),
    ("滚动样本外验证",     "walk_forward.py"),
    ("实盘预测追踪",       "track_predictions.py"),
    ("信号嵌入回测结果",   "build_signals.py"),   # 第二遍：嵌入最新回测/验证/追踪
    ("导出图表数据",       "export_chart_data.py"),
    ("导出个股数据",       "export_stocks.py"),
    ("隔夜vs日内分析",     "overnight_analysis.py"),
]

full_steps = [
    ("高级ML分析",         "advanced_analysis.py"),
    ("多元统计分析",       "multivariate_analysis.py"),
    ("导出多元分析数据",   "export_multivariate_json.py"),
]

if "--full" in sys.argv:
    # 重型分析放在导出图表数据之前
    steps = steps[:-1] + full_steps + steps[-1:]

for label, script in steps:
    print(f"\n{'='*55}")
    print(f"  ▶  {label}  ({script})")
    print(f"{'='*55}")
    r = subprocess.run([sys.executable, str(SCRIPTS / script)])
    if r.returncode != 0:
        print(f"\n✗ [{label}] 失败，已终止")
        sys.exit(1)

# ── 同步部署目录：web/ → 仓库根 docs/ ──────────────────────────
print(f"\n{'='*55}")
print(f"  ▶  同步部署目录  web/ → {DOCS_DIR}")
print(f"{'='*55}")
DOCS_DIR.mkdir(exist_ok=True)
for f in WEB_DIR.iterdir():
    if f.is_file():
        shutil.copy2(f, DOCS_DIR / f.name)
        print(f"  ✓ {f.name}")

print("\n✓ 全部完成！打开 web/index.html 查看仪表盘，git push 后部署生效")
