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
加 --light 参数只刷数据和信号（盘中小时级 CI 用）：跳过长历史/回测/walk-forward/
隔夜分析等重型步骤，复用上次全量运行的 data/ 产物（CI 里靠 actions/cache 恢复；
没有缓存时 build_signals 会退化到手设 LR，信号数字会与全量运行有出入）。
"""
import subprocess, sys, shutil
from pathlib import Path

SCRIPTS = Path(__file__).parent
WEB_DIR = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"   # 仓库根 docs/，GitHub Pages 部署目录

steps = [
    ("下载数据",           "fetch_data.py"),
    ("下载长历史数据",     "long_history.py"),
    ("规律置换检验placebo", "placebo_test.py"),         # P4-1：日历效应防伪（须在 long_history 后，复用其 SP500_long.csv）
    ("反事实事件影响",     "event_causal.py"),         # 方法B：回归反事实+bootstrap（SVB验证事件 + SPCX钩子）
    ("风险仪表盘",         "risk_dashboard.py"),       # 方法D：VXN-VIX价差 + 条件下行(测风险不测方向)
    ("收益区间(保形)",     "conformal.py"),            # 方法E：split-conformal 覆盖区间(测不确定性,非方向)
    ("周期检验(谱)",       "cycles.py"),               # 方法F：periodogram + AR1红噪声(测周期真伪,非预测周期延续)
    ("隔夜vs日内分析",     "overnight_analysis.py"),   # 产出隔夜动量因子数据
    ("基础统计分析",       "analyze.py"),
    ("买卖时机分析",       "timing_analysis.py"),
    ("历史事件研究",       "event_study.py"),
    ("生成每日信号",       "build_signals.py"),
    ("回测验证",           "backtest.py"),
    ("滚动样本外验证",     "walk_forward.py"),
    ("因子样本外尸检",     "factor_pruning.py"),   # P2-5：因子记分卡 + 靶子探针（研究面板）
    ("跨检验族FDR收口",    "fdr_crossfamily.py"),  # P4-#5：汇池全站显著性主张做多重比较（须在 factor_pruning 后）
    ("过拟合概率PBO",      "cpcv.py"),             # 方法G：CSCV/PBO 量化因子选择过拟合风险(升级验证、不加模型)
    ("波动率状态原型",     "vol_model.py"),        # P2-6：高信噪比靶子（研究面板）
    ("市场结构解释",       "market_structure.py"), # PCA共动 + 相关性体制（研究面板）
    ("实盘预测追踪",       "track_predictions.py"),
    ("Benchmark记分卡",    "benchmark.py"),        # 须在 track_predictions 后，读最新预测命中率；在第二遍 build_signals 前以便嵌入
    ("信号嵌入回测结果",   "build_signals.py"),   # 第二遍：嵌入最新回测/验证/追踪
    ("导出图表数据",       "export_chart_data.py"),
    ("导出个股数据",       "export_stocks.py"),
    ("市场要闻RSS",        "fetch_news.py"),
    ("模拟盘执行",         "paper_trading.py"),
    ("每日盘后简报",       "daily_brief.py"),
    ("统计评估报告",       "weekly_report.py"),
    ("发布前自检",         "verify_output.py"),   # 失败则终止，不发布坏数据
]

full_steps = [
    ("高级ML分析",         "advanced_analysis.py"),
    ("多元统计分析",       "multivariate_analysis.py"),
    ("导出多元分析数据",   "export_multivariate_json.py"),
]

# 盘中轻量模式：只保留"数据刷新 + 信号 + 前端产物"链路，分析类产物吃缓存
LIGHT_STEPS = {
    "fetch_data.py", "build_signals.py", "track_predictions.py",
    "export_chart_data.py", "export_stocks.py", "fetch_news.py",
    "paper_trading.py", "daily_brief.py", "weekly_report.py", "verify_output.py",
}

if "--full" in sys.argv:
    # 重型分析放在导出图表数据之前
    steps = steps[:-1] + full_steps + steps[-1:]
elif "--light" in sys.argv:
    steps = [(label, s) for label, s in steps if s in LIGHT_STEPS]
    print("※ light 模式：跳过长历史/回测/walk-forward/隔夜分析，复用上次全量产物")

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
web_names = set()
for f in WEB_DIR.iterdir():
    if f.is_file():
        shutil.copy2(f, DOCS_DIR / f.name)
        web_names.add(f.name)
        print(f"  ✓ {f.name}")
# 清理 docs/ 里 web/ 已不存在的部署文件（如拆分后残留的旧 app.js）；保留 .nojekyll 等点文件
for f in DOCS_DIR.iterdir():
    if f.is_file() and not f.name.startswith(".") and f.name not in web_names:
        f.unlink()
        print(f"  ✗ 清理残留 {f.name}")

print("\n✓ 全部完成！打开 web/index.html 查看仪表盘，git push 后部署生效")
