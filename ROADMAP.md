# Alpha Lab 优化路线图 + 实施指导（合并版 v2）

> 2026-06-11。由两轮独立审查合并而成：
> **A 轮**（深度修复轮）：修了 5 个产生错误数据的 bug + 7 个 Required 级（成交价门禁、情绪盘、XSS、告警风暴、CI 竞争、标普前瞻假技术状态等），已全部落地（commit 78a537d）。
> **B 轮**（全项目健康度审查）：健康分 84/100，新增模型方法论、防回归、信息架构发现。
>
> **工作模式约定**：本文档由高推理强度的审查轮产出，写得足够具体（改哪个文件、怎么改、怎么验收），
> 后续用普通强度会话按阶段机械执行即可——执行轮不需要重新分析，遇到与本文档矛盾的代码现状再升级讨论。

---

## 两轮意见合并结论

| A 轮提议 | B 轮裁定 | 合并结果 |
|---|---|---|
| 页面布局 5 标签重组（今日/计划/实验/研究/我的） | 同意，优于 B 轮的 4 分组方案（"计划"独立是对的，决策节奏不同） | → P1，采用 5 标签 + B 轮的细节清单 |
| signals.json 瘦身 1.8MB→350KB | 已核实确为 1,836KB，主因是 2000 年起全量 daily_signals | → P1 |
| CI 加 --light 盘中模式 | 同意，已核实盘中每小时跑全量（含回测）；注意 CI 是无状态 checkout，需配 actions/cache | → P1 |
| 布局重组排第一优先 | **修正**：先花 1-2 天搭防回归安全网（P0）。A 轮自己修的 5 个 bug 就是没有测试的代价；瘦身和 --light 都要动 build_signals，更需要安全网 | → P0 先行 |
| 动量调仓边界/市场时钟假日/2027日历 | 同意，小项 | → P3 |
| （未提及） | **B 轮补充**：验证的模型 ≠ 部署的模型、"概率"无明确事件定义、胜率比当贝叶斯因子、因子相关性重复计数等方法论问题 | → P2（模型 v3.0） |
| （两轮都漏了） | **本次合并新发现**：假日表缺六月节（见 P0-0，**6月19日下周五就会出错**） | → P0-0 立即修 |

A 轮对"做得对的地方"的确认（shift(1) 防前视、全概率公式反推、收缩估计、append-only 账本）B 轮独立得出了相同结论，可信。

---

## P0 — 立即修复 + 防回归安全网（1-2 天）

> ✅ **全部完成（2026-06-11）**：P0-0 `4fd17da` / P0-1 `a195857` / P0-2 `3e122c1` / P0-3 `38c70aa`。
> 走收缩配置后 walk-forward Tier≥4 样本外 -1.38pp → **-0.32pp**（仍无证实优势，但旧数字低估了部署模型）。
> 下一步：P1（前端五标签重组 + 瘦身 + CI --light），普通强度会话按文档执行即可。

### P0-0 假日表缺六月节（Juneteenth）— 一行级补丁，先修

**现状**：`build_signals.py` `_us_holidays()`（约 166-178 行）只列了 9 个假日。
NYSE 自 2022 年起六月节（6月19日）休市。**2026-06-19 是周五**，当前代码把它当交易日：
`find_next_opportunities` 会为它生成信号、未来日历会显示它、6月18日拿不到节前效应 LR。

**改法**：`_us_holidays(year)` 返回的集合里加：
```python
# Juneteenth：NYSE 自 2022 年起休市
if year >= 2022:
    holidays.add(_adjust_weekend(date(year, 6, 19)))
```
（按该函数现有写法是返回字面集合，需先改成具名变量再条件加入。）

**验收**：`python -c` 验证 `date(2026,6,19) in _us_holidays(2026)` 为 True、
`date(2021,6,19)` 不在 2021 集合中；重跑流水线后 `signals.json` 的 `all_forecast` 不含 2026-06-19。
**同时**：P3 的"前端市场时钟假日"应消费同一份假日表（见 P3-2），不要在 JS 里再抄一份。

### P0-1 抽共享模型模块 `scripts/signal_model.py`

**现状**：`_tier`、贝叶斯更新、`_week_of_month`、RSI、因子阈值（BTC ±5%、波动 0.25/0.15、RSI 75/35、DXY ±1%）
在 `build_signals.py` 与 `walk_forward.py` 各实现一份。已知实质分歧：
- 生产用 `_SHRINK_N=200` 收缩 LR（build_signals.py:261-273），walk-forward 的 `score_row` 用未收缩 LR（walk_forward.py:258-293）
- 生产日历因子用硬编码表（`DOW_LR`/`_WOM_LR`/`MONTHLY_PRIOR`），walk-forward 用各折学习值

**改法**：
1. 新建 `signal_model.py`，迁入：`_tier`、`bayesian_update`、`_week_of_month`、`_rsi`、
   全部阈值常量（命名为 `THRESH_BTC_MOM=0.05` 等）、`_us_holidays`/`_HOLIDAY_SET`、
   收缩函数 `shrink_lr(lr, n, k=200)`。
2. 两个文件改为 import，删除本地副本。
3. `walk_forward.score_row` 对学到的 LR 套用 `shrink_lr` 后再打分——让验证跑的就是部署配置。
4. 重跑 walk_forward，**结果数字会变，属预期**；把新旧 Tier≥4 平均差距记进 commit message。

**验收**：`grep -n "def _tier" market-analysis/scripts/*.py` 只出现在 signal_model.py；
全流水线跑通；`signals.json` 的 `walk_forward.summary` 已更新。

### P0-2 pytest 测试 + CI 门禁

**新建 `market-analysis/tests/`**，纯函数优先（不需要 mock、不需要网络）：

| 测试 | 关键断言 |
|---|---|
| `test_holidays.py` | 2024-2026 对照 NYSE 官方休市表（含 Good Friday、六月节、圣诞调休） |
| `test_calendar.py` | `_week_of_month` 月首/月末边界；`_tier` 在 0.40/0.60/0.80 边界值 |
| `test_calibrate.py` | `calibrate_prob` 端点外插值不越界、单点退化 |
| `test_final_day.py` | `is_final_trading_day`：美东 16:05 前/后、周末、半日市样例 |
| `test_dedup.py` | track_predictions 去重：同日同指数同版本；`"2.0"` 字符串 vs 浮点回读陷阱 |
| `test_shrink.py` | `shrink_lr(lr,0)==1.0`、n→∞ 趋近原值 |

**CI**：`refresh-data.yml` 在 "Run pipeline" 之前加一步
`pip install pytest && python -m pytest market-analysis/tests -q`，失败则整个 job 失败（不提交数据）。

**验收**：本地 `py -m pytest market-analysis/tests -q` 全绿；故意改坏 `_tier` 边界，CI 红。

### P0-3 仓库卫生

- `.gitignore` 加 `node_modules/`；根目录 `generate_report.js`、`package.json`、`package-lock.json`、
  `scripts/_check_opp.py`、`scripts/_audit_frontend.py`：移入 `tools/`（README 注明用途）或删除。
- `requirements.txt` 给核心依赖加版本上界（yfinance 接口变动是流水线最常见外部断点）。
- 清理过时注释：`build_signals.us_today()` 的"用户在澳洲(UTC+9:30)"、fetch_data 的"AUD（用户在澳洲）"。

---

## P1 — 前端重组 + 数据瘦身 + CI 分级（A 轮主推，约 1 周）

> ✅ **全部完成（2026-06-11）**：P1-2 `820f7c0` / P1-5 `b90e760` / P1-3 `3d31268` / P1-1+4+6 `81bfc53`。
> 实际效果：signals.json 1,836KB→204KB；Plotly 3.6MB→1.4MB；五视图导航（"我的"做成第5个标签而非独立
> tools.html，与 A 轮原方案一致）；--light 本地 153 秒跑通。
> 有意留到 P3 的：IntersectionObserver 滚动懒渲染、inline style 收敛、字号体系（随 app.js 拆模块一起做）。
> 下一步：**P2 模型方法论（建议切 xhigh 执行）**。

### P1-1 五标签信息架构

顶部 sticky 标签栏，现有面板按下表归位（id 不变，只动容器与显隐逻辑）：

| 标签 | 收纳的现有面板 |
|---|---|
| **今日** | 信号环+日期选择、每日简报、双指数+市场时钟、情绪仪表盘、卖出信号、今日要闻、事件叠加 |
| **计划** | 未来60天日历、最佳操作窗口（动态）、最佳窗口（静态）、经济日历、档位说明 |
| **实验** | 模拟盘五策略（**补净值曲线图**：paper.json 的 `curve.dates/equity` 已有数据，Plotly 一条 trace 一个策略）、我的模拟盘、实盘追踪、预测准确率回溯、模型体检报告、回测/walk-forward |
| **研究** | 隔夜分解、月度胜率、假日效应、熊市目录、多元分析、日历规律、四资产走势、个股观察池 |
| **我的** | 持仓计算器、CGT、SpaceX —— 建议直接独立成 `tools.html`（公开站不该混个人资产界面） |

手机端默认只渲染"今日"标签（首屏面板数 23 → 6）。

### P1-2 文案与数据一致性（半天，全是确定性小改）

- "四策略竞技"（index.html 模拟盘面板标题）与 `paper_trading.py` note"四个策略"→ 实为五个，三处统一
- "未来60天信号日历"（index.html:210）、"未来45个交易日"（index.html:167）、`n_days=130`（build_signals.py:852）
  → 统一为 **40 个交易日**（技术因子冻结的合理寿命），超出部分若保留需注明"仅日历先验"
- 档位阈值单一来源：build_signals 往 signals.json 写 `tier_thresholds`，
  app.js `TIER_META` 与 index.html 档位图例改为由 JS 从 JSON 渲染（删掉 HTML 里手写的五行图例）

### P1-3 signals.json 瘦身（1,836KB → ~350KB）

- `daily_signals` / `daily_signals_sp500` 只保留 2024-01-01 之后；更早部分写入 `signals_history.json`
- app.js：`renderSignalHistory` 和日期选择器选到老日期时 `fetch("signals_history.json")` 懒加载（带模块级缓存）
- **验收**：首屏网络面板 signals.json < 400KB；选 2010 年某日仍能显示信号；历史轨迹图完整

### P1-4 性能与可访问性

- Plotly 完整版 CDN（~3.5MB）→ `plotly.js-basic-dist-min`（散点/柱状/热力够用）；
  若热力图缺失则退一档用 `plotly.js-cartesian-dist-min`
- 首屏外图表用 IntersectionObserver 懒渲染（标签页已有懒加载机制，推广到滚动方向）
- 标签页 div+onclick → `<button role="tab" aria-selected>`；涨跌/档位加 ▲▼ 文字符号，不只靠红绿
- index.html 大量 inline style 收进 class；字号从十几档收敛到 4 档，正文不小于 0.78rem

### P1-5 CI 分级：`--light` 盘中模式

- `run_all.py` 加 `--light`：只跑 `fetch_data → build_signals(1遍) → track_predictions → paper_trading → daily_brief → verify_output → 镜像`
  （track/paper 已有官方收盘门禁，盘中跑是安全的空转）
- 跳过的重型步骤（long_history/事件研究/回测/walk_forward/overnight/weekly_report）依赖上次产物：
  **CI 无状态，必须配 `actions/cache`** 缓存 `market-analysis/data/`，key 按日期，收盘后全量 job 刷新缓存
- workflow：盘中小时 cron（`30 14-20 * * 1-5`）传 `--light`，收盘后与开盘前 cron 跑全量
- 顺带解决：盘中每小时重学 LR 造成的信号日内漂移
- **验收**：light 运行 < 2 分钟；卖出面板/时机摘要在 light 模式下非空（证明缓存生效）

### P1-6 SPCX 面板加"IPO 周期视角"子块（用户提出）

SpaceX 级别的全民可参与大型 IPO 历来被当作周期情绪指标（"无门槛吸钱 = 顶部信号"说法的可检验版本）。
在 SPCX 详情区（或"研究"标签）加一个小面板，用静态数据回答两个问题：
- **史上最大 IPO 上市时点 vs 其后 12 个月大盘表现**：Blackstone 2007-06、Glencore 2011-05、
  Coinbase 2021-04、Rivian 2021-11（贴顶）；Visa 2008-03、Alibaba 2014-09、Google 2004-08（非顶部）——
  做成散点/时间轴，标注"IPO 当月"与"其后大盘最大回撤"
- **年度 IPO 数量与平均首日涨幅**（Jay Ritter 公开数据，IPO 热度是 Baker-Wurgler 情绪指数成分）
  vs 其后 3 年标普收益
结论写在 insight 框：这是情绪温度计（领先 0-18 个月、有反例），不是择时按钮——与本站"校准概率代替情绪"的理念一致。

---

## P2 — 模型方法论 v3.0（核心价值，1-2 周，建议用高推理强度会话执行）

> 背景：walk-forward 显示 Tier≥4 样本外 -1.3pp——当前模型没有被证实的优势。
> 以下按对结论影响排序。改完任何一条都要 bump `MODEL_VERSION`（成绩单按版本分开追踪，设计上支持）。

1. **把"概率"定义成一个事件**：现在 `MONTHLY_PRIOR`（整月上涨）× `DOW_LR`（当日上涨）×
   walk-forward 验证（20日上涨）三个时间尺度连乘，输出数字无明确含义。
   统一目标 = **P(未来20日上涨)**：先验与全部日历 LR 都改从 `learn_lrs`（已按 fwd_up_20d 估计）取，
   删掉硬编码的 `MONTHLY_PRIOR/DOW_LR/_WOM_LR`——这同时消灭"生产用硬编码表、验证用学习值"的分歧。
   前端所有概率旁标注"20日窗口"。

2. **胜率比 ≠ 贝叶斯因子**：`bayesian_update` 在 log-odds 里加的是 `log(wr_on/base)`，
   数学上应为 odds-ratio `log[(wr/(1-wr))/(base/(1-base))]`（52.4%→49.3% 应为 0.88 而非 0.94）。
   **推荐直接跳方案 B**：L2 逻辑回归（sklearn 已在依赖）替换手搓连乘——
   特征 = 现有全部二值因子 + month/dow/wom one-hot；按 walk-forward 同样的折训练验证；
   系数即对数胜算比，天然处理因子相关性（恐慌期 RSI 超卖/MA200 下方/高波动/VIX 倒挂同时触发，
   朴素贝叶斯把同一份证据算四次）。前端因子分解改为展示各特征的 log-odds 贡献。

3. **只展示校准后概率，档位用校准值**：现状"58.3% 第3档·中性"与"校准后65%"（落在第4档）并排自相矛盾。
   原始输出降级为内部得分；校准曲线改用 walk-forward 各折**测试期**预测拼成（现在是样本内）；
   `_tier()` 吃校准值。

4. **显著性换块自助法**：重叠 20 日窗口使 t 检验 p 值乐观约一个数量级（代码注释已自知）。
   circular block bootstrap（块长 20，B=2000）重算 backtest/walk-forward 置信区间；
   日历异象表加 Benjamini-Hochberg 校正。

5. **按样本外证据修剪因子**：对每个因子统计各折方向一致性，不一致的移出信号链路。
   主观事件 LR（halving 1.15、gold_spike 0.88 等）保留为前端"what-if 叠加"玩具，但必须标注"主观估计，未经验证"。

---

## P3 — 小项与持续工程

1. 动量策略月度调仓边界（缺价、并列排名、月首无交易日）补测试再修
2. **市场时钟与前端假日**：build_signals 把 `_HOLIDAY_SET`（未来 12 个月切片）写进 signals.json，
   app.js 市场时钟/日历消费它——别在 JS 里第二份假日表（P0-0 的教训）
3. 宏观日历续期机制：`verify_output.py` 加检查"MACRO_EVENTS 最后日期距今 < 60 天则告警"，
   到期前 CI 会自己喊（2027 日历到时候手工补）
4. app.js（2,743 行 / ~85 全局函数）按五标签拆 ES modules：`today.js / plan.js / lab.js / research.js / tools.js + lib.js`，`<script type="module">`，不引构建工具
5. 两遍 build_signals 改单遍：信号计算（写 processed/）与站点装配（写 web/signals.json）拆成两个脚本，流水线变纯单向 DAG

---

## 不建议做的（明确排除）

- **不加新因子**：11 个因子样本外合计 -1.3pp，问题在方法论不在因子数量
- **不上深度学习**：日频 ~6,500 样本、低信噪比，过拟合是必然；`--full` 的 XGBoost/Prophet 留研究面板，不进信号链路
- **不引前端框架**：无构建静态站是部署优势，拆 ES modules 就够

---

## 执行协议（给后续会话）

1. 按 P0-0 → P0 → P1 → P2 → P3 顺序，每个编号任务 = 一次独立提交，commit message 引用任务号（如 `P0-1`）
2. 改流水线的任务，提交前必须本地全量跑通 `py market-analysis/scripts/run_all.py`（设 `PYTHONUTF8=1`）+ pytest 全绿
3. P2 每完成一条 bump `MODEL_VERSION` 并重跑 walk_forward，新旧指标对比写进 commit message
4. 与本文档矛盾的代码现状（比如已被别的会话改过）→ 停下来在会话里说明，不要硬改
