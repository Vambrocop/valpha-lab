# Alpha Lab — 美股入场信号分析

[![Refresh market data](https://github.com/Vambrocop/alpha-lab/actions/workflows/refresh-data.yml/badge.svg)](https://github.com/Vambrocop/alpha-lab/actions/workflows/refresh-data.yml)

**Live site → https://vambrocop.github.io/alpha-lab/**

用统计 + 机器学习分析美股（纳斯达克 + 标普500），但和大多数信号站相反：
它**诚实地分清哪些规律是真的、哪些是幻觉**，并用 append-only 实盘日志 + 每模型 vs 硬基线的
benchmark 记分卡公开追踪——说了什么、对了没有，无法事后美化。

## 核心理念：分清真规律 vs 幻觉

我把能想到的维度都试了一遍，然后用严格的样本外方法（walk-forward 块自助 + 2024-2026 干净保留集）
分成两类：

**✅ 真规律（站得住、能用）**
> 波动率可预测（聚集效应，AUC≈0.67）· 股权溢价（20日约 62-66% 上涨，买入持有稳赢现金）·
> 隔夜异象（QQQ 隔夜段年化 +11.2% vs 日内 -2.3%）· 相关性体制（纳指-黄金现转正）·
> BTC 20日动量领先纳指 · VIX 倒挂/大跌后的均值回归。
> 用途：**管理风险、择波动窗口、理解市场结构。**

**❌ 幻觉（再多数据也打不赢市场）**
> 用综合贝叶斯信号预测**短期方向**——样本外打不赢"无脑买入持有"（Tier≥4 平均 -0.3pp）。
> 这不是数据不够或统计不行，是**市场效率**：短期方向是最先被套利定价掉的维度。
> 我们**如实展示这个失败**，不假装能做到。

> 一句话：这是一个"分清真伪"的工具，不是又一个"我的信号很准"。

## 功能

### 信号系统（模型 v2.1）
- **双指数贝叶斯信号** — 纳指（1971+ 先验）和标普（1928+ 先验）各自独立计算；
  月份胜率 × 星期效应 × 月内周次 × 假日效应 × 税季 × 技术因子连乘
- **经验似然比** — 技术因子（MA200/RSI/波动率/BTC动量/美元趋势/VIX期限结构/隔夜动量）
  的权重由 walk-forward 从历史学习（带样本量收缩），不是拍脑袋
- **概率校准** — 原始概率映射到历史同档位的实际20日胜率
- **宏观事件日历** — BLS CPI 和 FOMC 官方日程自动标注"波动放大日"

### 诚实验证（这个项目的灵魂）
- **实盘预测追踪** — 每天记录模型当天的预测（按模型版本），之后用真实行情回填 1d/5d/20d 收益；
  日志 append-only 入 git，无法篡改
- **Walk-forward 滚动验证** — 2000→2024 六折样本外测试，纳指信号用纳指验证（不混用指数）
- **回测注明方法论局限** — 样本内验证、重叠窗口 t 检验 p 值偏乐观，都白纸黑字写在结果里

### 研究面板
- **隔夜 vs 日内收益分解** — 用真实 ETF 价格（SPY/QQQ）验证著名的隔夜收益异象：
  QQQ 隔夜段年化 +11.2%，日内段 -2.3%（2000–2026）
- **事件研究** — 1928+ 历史上加息/降息/贸易战/地缘冲击后30日的实证超额收益
- **个股观察池** — 七姐妹 + 优质龙头（博通/台积电/好市多/礼来/伯克希尔）关键指标与走势对比
- **多元统计** — CCA、SHAP、Prophet、卡尔曼滤波、路径分析（`--full` 模式）
- **市场时钟** — 美东交易时段自动换算为访问者本地时间（含夏令时）

## 架构

```
GitHub Actions（交易日自动跑两次：美东收盘后 + 开盘前）
    │
    ▼
market-analysis/scripts/run_all.py     ← 一键流水线
    fetch_data → long_history → overnight_analysis → analyze
    → timing_analysis → event_study → build_signals(1)
    → backtest → walk_forward → track_predictions → build_signals(2)
    → export_chart_data → export_stocks → 镜像 web/ → docs/
    │
    ▼
docs/  ← GitHub Pages 部署目录（纯静态：HTML + JSON）
```

- 前端：单页应用（`index.html` + `app-1.js`…`app-5.js` + `style.css`），Plotly 图表，无框架无构建（5 个脚本是同一份逻辑按 section 拆开的有序经典脚本，顺序不可重排）
- 数据全部预计算成 JSON，页面零后端

## 本地运行

```bash
pip install -r market-analysis/requirements.txt   # 核心只需 yfinance pandas numpy scipy requests
python market-analysis/scripts/run_all.py         # 完整流水线（约2-3分钟）
python market-analysis/scripts/run_all.py --full  # 含重型ML分析（需 statsmodels/arch/xgboost 等）
```

本地预览：双击 `market-analysis/启动网站.bat`（直接打开 index.html 会因 file:// 协议导致数据加载失败）。

## 数据来源

- Yahoo Finance — 指数/ETF/个股/加密货币/商品
- FRED — 美联储利率 / M2 / CPI / 失业率 / 国债收益率（下载失败自动回退缓存）
- BLS / Federal Reserve — CPI 发布与 FOMC 会议官方日程

## 免责声明

仅供个人学习研究，不构成任何投资建议。所有"信号"本质是历史频率统计，
样本外优势尚未被证实（walk-forward 按部署配置评估，Tier≥4 平均 -0.3pp）——这正是实盘追踪存在的原因。
