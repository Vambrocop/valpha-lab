# 个股诚实体检页 —— 实施 SPEC（自走 loop 的北极星）

> 每轮 loop：读本文件 → 挑**下一个未完成块** → 走 /new-method 六步 → 提交推送 → 继续。
> 完成的块在下面打 ✅ 并附 commit 短哈希。

## 🎯 目标（done 定义）
选一只美股 → 看它的**风险画像 + 规律真伪**，描述"它是什么样"，
**绝不预测涨跌、绝不给买卖/持股建议**。全部复用现有统计机器（risk_dashboard / conformal /
placebo+FDR / stats_util）。数据不足的模块**如实标 insufficient/inconclusive，绝不编造**。

## 🔴 红线（每块每步守，违反即停下问用户）
- 不预测方向、不荐股、不给买卖点/目标价/仓位"该买多少"。只回答"风险多大/规律真伪/区间多宽"。
- 任何措辞暗示"这只票会涨/值得买/比别的好" = 违规。verdict 用中性风险/真伪语言。
- 失败/空/无定论照样上页面（登记簿灵魂）。三态：real / inconclusive / insufficient。

## 📦 数据与精选清单
- 精选清单 = export_stocks.py 已追踪的大盘龙头 + KO（流动性好、历史长）：
  `AAPL MSFT GOOGL AMZN NVDA META TSLA AVGO TSM COST LLY BRK-B KO`
  （KO=可口可乐：几十年历史、低 β 防御股，与科技龙头形成对照、诊断满检验力）
- `stock_checkup.py` 自抓**全量日线**（yfinance，仿 conformal._sp_prices / risk_dashboard），
  **不是** stocks.json 的周线（那是图表降采样）。优先复用 data/raw 缓存，缺失才下载。
- **检验力门（每票每模块）**：样本不足该模块就标 insufficient（EVT 需 ~2000+ 天、保形需数年、
  placebo 日历需几十年→单股几乎必然 insufficient/inconclusive）。这正是诚实卖点，不是缺陷。
- `SEED = 20260613`，所有随机用 `np.random.default_rng(SEED)`。

## 🏗️ 架构（静态 JSON，全站一致，无实时后端）
- 后端：`market-analysis/scripts/stock_checkup.py` → `stock_checkup.json`（写 PROC+WEB+DOCS 三处，
  `json.dump(..., ensure_ascii=False, indent=2, allow_nan=False)`）。顶层 `{generated, caveat, tickers:{TICKER:{...}}}`。
- 复用：`stats_util`（含 calibration_drift 模式）/ `risk_dashboard.evt_tail, path_drawdown` /
  `conformal.split_conformal, nonoverlap_fwd_returns` / placebo 置换逻辑。**不重写已审过的统计**。
- 前端：`index.html` 新面板 `#stock-checkup`（chart-wrap + chart-header，badge="风险与规律真伪 · 非荐股非预测"）
  + `app-2.js` `loadStockCheckup()`（票**选择器** `<select>` → 渲染该票各模块）
  + `app-5.js` `lazyRender("stock-checkup", ...)` + 登记簿搬迁数组 + `loadHonestRegistry` 一行（verdict 实时取）。
  - esc() 任何外部串；分隔线 var(--border-faint)；数字 tabular-nums 右对齐；缺数据显"…数据不足"。
- `run_all.py`：在 `export_stocks.py` 之后插 `("个股诚实体检", "stock_checkup.py")`（复用其宇宙/缓存）。
- `verify_output.py`：§3i 形状门（存在才查、缺失不致命）。

## 🔁 loop 块（每块 = 一次提交，commit 带"块N"；**统计块必独立 Opus 审**）

### 块0 — 脊柱（先立骨架）
- 做：建 `stock_checkup.py`，抓 12 票全量日线 + **数据可行性探针**（每票日线天数、起始日）；
  先只算**基础风险**：年化波动、历史最深回撤、与纳指 β（OLS 斜率）。写 `stock_checkup.json`。
  前端建 `#stock-checkup` 面板 + 选择器 + 渲染基础风险表。run_all 接入。verify §3i。test。
- 验收：12 票出基础风险；次新股天数少也不崩；前端选择器切换正常；node-check + pytest + verify 全绿。
- 判断岔路停下：某票全量日线都拿不到（退市/代码变更）→ 标该票 data unavailable，**不要让整脚本失败**。

### 块1 — EVT 尾部风险（复用 risk_dashboard.evt_tail）
- 做：每票算 EVT VaR/ES + 尾部 ξ；样本不足 → status insufficient。
- 验收：老票出 ξ/VaR/ES；次新股显 insufficient；ES≥VaR。**独立审**。
- 停下：ξ 出现极不稳（>1 或拟合失败）→ 报告，不自行决定怎么钳。

### 块2 — 市场依赖度
- 做：β、R²（市场解释的方差占比）、滚动相关、**特质风险占比**（1−R²）。
  诚实框架："这只票 X% 的波动只是跟着大盘；特质部分 Y%"。
- 验收：β/R² 合理（R²∈[0,1]）；BRK-B/COST 这种低β能体现差异。**独立审**。
- 停下：无。

### 块3 — 规律真伪（单股 placebo + FDR）
- 做：对该票做日历/简单因子的置换检验 + BH/BY 校正（复用 placebo 机器）。预期多为 null/inconclusive。
- 验收：输出每效应 p/q + 三态；单股几乎都 inconclusive/rejected（如实）。**独立审**。
- ⚠️ 判断岔路停下：**若某单股出现 FDR 校正后仍显著的"真规律"→ 停下报告**，不自动发布
  （单股层面这极可能是数据窥探，需人工审视是否真实 vs 多重比较残留）。

### 块4 — 保形区间（给范围不给方向）
- 做：每票 N 日收益的 split-conformal 区间 + 实测覆盖（复用 conformal）；够数据才按体制条件化。
- 验收：区间 L<U；覆盖如实（偏离即标注非平稳，仿 VIX 体制版）。**独立审**。
- 停下：覆盖严重偏离（如低 VIX 那种 0.6）→ 照诚实呈现 + caveat，不隐藏。

### 块5 — 裁决卡 + 登记簿整合 + caveat 终审
- 做：把各模块汇成每票**三态裁决卡**（风险画像 + 有无可检出 OOS 边际 + 规律真伪），
  进诚实登记簿（一行，verdict 从 JSON 实时取）。统一 caveat 措辞。
- 验收：卡片措辞**逐字过红线检查表**（无方向/无买卖/无"更好"）；登记簿行正确。**独立审（措辞重点）**。
- 停下：任何措辞过不了红线 → 改到过为止；拿不准 → 问用户。

### 块6 — 风险型异动监测（描述性，非信号）
- 做：每票判定**当前是否处于异常风险体制**——① 波动突变/当前波动落在历史高分位（如 ≥95pct）；
  ② 与纳指**脱钩**（滚动相关骤降 = 特质风险骤升）。跨票/跨日做 **FDR 控假阳性**（复用 stats_util BH/BY）。
- 🔴 红线措辞死守：**"异动 = 风险升高，请重新审视你的仓位风险，不是交易信号/机会"**。
  被动展示（点开某票才看到的"当前风险状态"），**不做主动弹窗雷达、不做跨股票'什么最热'扫描器**。
- 验收：异常判定有统计依据（分位/相关阈值）+ FDR 校正；措辞逐字过红线表；正常票显示"无异常"。**独立审（红线+统计双重点）**。
- 停下：若做法滑向"机会发现/择时" → 停下问用户。

## ⛔ loop 只为这三种情况停下留言（别的不停，按 spec 推进）
1. 踩红线（措辞/功能暗示方向或买卖）
2. 某块数据不可行（诚实跳过 + 记 LOOP_DECISIONS + 进登记簿"数据不足"，绝不编造）
3. 任何门禁/审查 BLOCKER 不过（pytest / verify_output / 独立审 / node-check / audit_frontend）

## ✅ 每块完成清单（缺一不可）
- [ ] `$env:PYTHONUTF8='1'` 后跑脚本，核对 JSON 输出
- [ ] 统计块：全新上下文 `agent-skills:code-reviewer` 独立审（审查者≠建造者），修完 BLOCKER/SHOULD-FIX
- [ ] `py -m pytest market-analysis/tests -q` 全绿
- [ ] `py market-analysis/scripts/verify_output.py` 通过
- [ ] 改过的 app-*.js 过 `node --check` + `py tools/audit_frontend.py`
- [ ] web→docs 镜像（Edit 改的手动 cp；脚本写三处的已自镜像）
- [ ] 提交（commit 带"块N + 块名"）→ `git pull --rebase origin main` → push

## 进度
- [x] 块0 脊柱 ✅（stock_checkup.py 基础风险:波动/最深回撤/β + 选择器面板;13票含KO;139测试绿）
- [x] 块1 EVT ✅（每票 ξ/日VaR-ES，复用 evt_tail；13票 ξ∈[0.04,0.32]；独立审 APPROVE，补"非规律间隔"caveat + ξ提示修正）
- [x] 块2 市场依赖度 ✅（R²=市场解释方差占比 + 特质=1−R²；KO/LLY ~11% 市场驱动 vs MSFT 57%。初等描述、红线安全→风险分级下自审，独立审保留给块3起）
- [x] 块3 规律真伪 ✅（星期几/月份 SSB置换 + 跨票FDR + 分半 + 近期持续 三关;六态real/faded/hist_robust/data_snoop/inconclusive/rejected;独立审 REQUEST_CHANGES→修月份faded误判bug。结果:0真规律,AAPL星期=faded被套利。前端分段呈现全样本/前后半/近5年）
- [x] 块4 保形区间 ✅（每票 20日90% split-conformal 双边区间+实测覆盖;复用 conformal.py;宽度随波动 KO17%→TSLA60%;独立审 APPROVE→补 n_test 真分母 + "无条件非预测"caveat + 带符号边界）
- [ ] 块5 裁决卡 + 登记簿
- [ ] 块6 风险型异动监测

---

## 🛣️ 下一轨（个股体检全部完成后才开）：市场风险体制 + 理论检验
用户 2026-06-16 批准"两者都做、主脑排序"。**先做完上面体检 6 块，再开本轨。** 红线同上（描述/证伪，非预测）。
- **R1 信用/流动性体制盘**（Minsky 金融不稳定 + Soros 反身性 + 信用周期）：复用已有 HY 利差/VIX/收益率曲线，
  做描述性"当前风险环境"（利差分位 + 历史上该体制随后回撤多深）——**描述风险非预测方向**。最高契合。
- **R2 Fed model 证伪**（纯登记簿）：盈利收益率 vs 债券收益率，学术已证伪(Asness 2003 相关通胀非真实价值)→ 诚实登记"流行但不成立"。
- **R3 行为金融过度反应/羊群**：短期反转检验 + 相关性骤升当羊群代理（PCA 已有底子），预期弱/无的诚实结论。
- ❌ **不做**蒙代尔不可能三角（间接宏观透镜、无法干净识别对个股的因果，装饰性过度延伸）；CAPM/APT 已被块0 β+因子覆盖；Gordon DDM 偏方向、契合低。
