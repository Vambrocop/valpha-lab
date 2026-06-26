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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPTS = Path(__file__).parent
WEB_DIR = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"   # 仓库根 docs/，GitHub Pages 部署目录

steps = [
    ("下载数据",           "fetch_data.py"),
    ("下载长历史数据",     "long_history.py"),
    ("规律置换检验placebo", "placebo_test.py"),         # P4-1：日历效应防伪（须在 long_history 后，复用其 SP500_long.csv）
    ("季节性原始计数",     "seasonality.py"),          # 补 placebo 没有的原始计数(逐月/任期年/Sell-in-May/世界杯全22届)，复用其数据不重算
    ("反事实事件影响",     "event_causal.py"),         # 方法B：回归反事实+bootstrap（SVB验证事件 + SPCX钩子）
    ("短期反转(过度反应)", "overreaction.py"),         # R3：极端下跌次日反弹检验(描述非建议,全样本vs现代)
    ("极端下跌→次日反弹告警(出格计分)", "overreaction_alert.py"),  # 敢预测敢认账:极端下跌日触发"次日偏涨"信号+Telegram推送+append公开计分+次日自动结算;须在 overreaction 后(引其现代统计);不入 light(盘后触发一次即可)
    ("风险仪表盘",         "risk_dashboard.py"),       # 方法D：VXN-VIX价差 + 条件下行(测风险不测方向)
    ("市场风险体制(R1)",   "market_regime.py"),        # R1：当前风险环境(VIX/收益率曲线/期限结构,描述非预测)
    ("收益区间(保形)",     "conformal.py"),            # 方法E：split-conformal 覆盖区间(测不确定性,非方向)
    ("周期检验(谱)",       "cycles.py"),               # 方法F：periodogram + AR1红噪声(测周期真伪,非预测周期延续)
    ("隔夜vs日内分析",     "overnight_analysis.py"),   # 产出隔夜动量因子数据
    ("基础统计分析",       "analyze.py"),
    ("买卖时机分析",       "timing_analysis.py"),
    ("历史事件研究",       "event_study.py"),
    ("持有期基率(长期视角)", "horizon_stats.py"),  # 复活:产 horizon_stats.json,由 build_signals 嵌入;须在 build_signals 前
    ("生成每日信号",       "build_signals.py"),
    ("回测验证",           "backtest.py"),
    ("滚动样本外验证",     "walk_forward.py"),
    ("因子样本外尸检",     "factor_pruning.py"),   # P2-5：因子记分卡 + 靶子探针（研究面板）
    ("跨检验族FDR收口",    "fdr_crossfamily.py"),  # P4-#5：汇池全站显著性主张做多重比较（须在 factor_pruning 后）
    ("自生长自动发现(出格)", "autodiscovery.py"),   # v1.5 Phase1b：42预声明候选(日历/反弹/因子)路由真统计→双栏BY-FDR三态裁决；须在 walk_forward+factor_pruning 后；不入 light(盘前/盘后全量才跑、同数据裁决不闪烁)；独立统计审 GO-WITH-FIXES(P1全清)
    ("过拟合概率PBO",      "cpcv.py"),             # 方法G：CSCV/PBO 量化因子选择过拟合风险(升级验证、不加模型)
    ("波动率状态原型",     "vol_model.py"),        # P2-6：高信噪比靶子（研究面板）
    ("市场结构解释",       "market_structure.py"), # PCA共动 + 相关性体制（研究面板）
    ("实盘预测追踪",       "track_predictions.py"),
    ("Benchmark记分卡",    "benchmark.py"),        # 须在 track_predictions 后，读最新预测命中率；在第二遍 build_signals 前以便嵌入
    ("信号嵌入回测结果",   "build_signals.py"),   # 第二遍：嵌入最新回测/验证/追踪
    ("导出图表数据",       "export_chart_data.py"),
    ("导出货币汇率",       "export_fx.py"),       # fx_rates.json：CGT 计算器"显示货币"切换用(仅显示,不改税务计算)
    ("导出个股数据",       "export_stocks.py"),
    ("个股诚实体检",       "stock_checkup.py"),   # 个股风险画像(块0起)：复用 stocks_prices/combined_prices,非荐股非预测
    ("市场要闻RSS",        "fetch_news.py"),
    ("模拟盘执行",         "paper_trading.py"),
    ("每日盘后简报",       "daily_brief.py"),
    ("统计评估报告",       "weekly_report.py"),
    ("每日诚实摘要",       "daily_digest.py"),    # 三层(事实/留意/探索)诚实摘要;红线门禁禁方向/荐股词,须在体制/信号/模拟盘后
    ("试胆区(玩具预测+计分)", "tipjar.py"),       # 故意下方向判断但公开残酷计分(≈掷硬币),娱乐非建议;须在 fetch_data 后
    ("观点/预测(授权出格区)", "outlook.py"),      # 用户授权:直接给纳指方向+个股看好看淡,带免责;读 signals+动量,须在 build_signals 后
    ("综合读数(出格·加权倾向)", "composite_read.py"),  # 把体制/信用/羊群/季节性/信号按写死透明权重合成当下倾向,每日 append composite_log 计分(自升级地基);须在 market_regime+seasonality+build_signals 后
    ("LLM大白话日读(出格)", "llm_daily_read.py"),   # 把 composite_read 真因子喂 Gemini→一段人话解读;须在 composite_read 后;无 GEMINI_API_KEY 则静默跳过;喂真数据防瞎编、带计分
    ("BTC动量→纳指回测(出格)", "btc_nasdaq_backtest.py"),  # 红线审计🟡#1:唯一穿过FDR的方向规律,诚实回测(条件分布/带成本overlay/多体制/计分);读 combined_prices,独立审 GO-WITH-FIXES已修
    ("体制→前向分布(出格)", "regime_forward.py"),   # 红线审计🟡#2:倒挂/VIX/信用利差→SP500前向收益分布(重标独立事件段);读 combined_prices,描述性
    ("内部人买入取数(SEC Form4)", "fetch_insider.py"),  # 抓近期开市买入P写insider.json;SEC daily-index,需 SEC_UA_CONTACT(secret);SEC失败静默退0不阻断;不入light(日更一次即可)
    ("内部人买入→前向计分(出格)", "insider_signal.py"),  # 跟内部人买的诚实前向公开计分:append notable买入+到期vs SPY自动结算;须在 fetch_insider 后;读yfinance(结算出错不阻断);不入light
    ("公开计分/校准卡(吸收)", "scorecard.py"),   # 4站调研吸收:汇 prediction_log/composite/tipjar + walk_forward OOS校准成公开战绩卡(按置信分桶看实际命中=护城河);须在 track_predictions/composite_read/walk_forward 后
    ("证据库总览(吸收)", "evidence_ledger.py"),   # 把已测规律族汇成单一诚实总览(每族 scope+证据+裁决+详情链接·没证据不进库);须在 autodiscovery/placebo/btc/regime 后
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
    "export_chart_data.py", "export_fx.py", "export_stocks.py", "fetch_news.py",
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
