# Valpha Lab — 后续路线图（2026-06-22 红线解除后）

红线已从"测风险不测方向"重定调为 **"诚实打底 + 逐步纳入预测/荐股/DL/LLM，守公开计分"**（见 `CLAUDE.md`「方向与边界」）。
**本会话已落地**：LLM 大白话日读(Gemini·已配 Secret)、纳指100成分追踪(build_ndx)、Telegram 告警推送、
红线遗留审计、调色板统一灰底 + 键盘 a11y + 骨架屏、双路独立审查修复批。

---

## 0. 零散收尾（快 / 需用户动作）
- [ ] **轮换暴露的 Gemini key**（聊天里露过；AI Studio 删旧建新 → 告诉我，我换 Secret）— 用户动作
- [x] ✅**Telegram 已通**（@Valphabot · 两 Secret 配好 · 修了"空串 LLM_PROVIDER 击穿 .get 默认"的 CI bug → 日推从不发的根因 · 日推已加料：数据日期 + 买/持/避结论 + 纳指方向 + 大白话 + 链接）
- [ ] **NDX 展示页/卡**：把 `ndx.json`（季度 5进5出 + valpha150 缺口）显示出来 — ~0.5 天
- [ ] 考虑补缺口大票进 valpha150：SHOP / PDD / APP / AXON / DASH / CDNS / SNPS 等 — 用户拍板

## 阶段 1 — 挖"被红线憋回的真规律"（红线审计 🟡；判断密集，强编排 + 独立审）
1. ⭐ **BTC 动量 → 纳指 诚实回测**（最高价值 · 全站唯一穿过 FDR + 现代段 + holdout 的信号，三流水线一致）
   - ① 定义信号（BTC 20日动量分档）② 带**交易成本**的前向持有回测 ③ **多体制稳健性**（FRAGILE=跨折符号一致性 0.8 非 1.0 → 必须确认方向在不同体制下站得住，别假设）④ 完整下跌分布 ⑤ 公开 append 计分 ⑥ 独立审（出公开方向结论 = 双审）
2. **体制 → 前向收益分布**（曲线倒挂 / VIX / 信用利差 → 给定体制下标普前向收益 / 回撤分布；ROADMAP P4-5 KM 为模板；少数体制样本少，诚实门控）
3. **R3 跌后反弹** 改述：从"绝不抄底建议"→"小条件边际(现代 +0.28pp) + 完整下跌分布(46% 仍跌 / 最差 -20%) + 成本可能吃掉"

## 阶段 2 — 另类数据 / 聪明钱族（alt-data · 诚实检验 + 可选跟单 + 公开计分）
4. ⭐ **议员 / 总统持股深挖**（QuiverQuant 概念 · 用户点名）— 详见下方专节
5. **SEC 内部人**（`fetch_insider.py` 已建数据底座）收尾成诚实检验族
6. **社交情绪**（Reddit / X 散户热度）：是信号 / 反向指标 / 噪声，诚实测

## 阶段 3 — LLM / 决策升级
7. **决策仪表盘升级**：composite 倾向 → 更明确"买/持/避"（带置信 + 免责 + 计分）
8. **Agent 问股**（多轮 · grounded 在真数据 · 防瞎编）— 较重，靠后
9. **DL 实验**：小模型 vs 现有 LR，**CPCV 验证，赢了才上**（小样本易过拟合，诚实工程异议≠拒绝）

## 阶段 4 — 自生长续（时间门控 · 需账本攒天数）
10. **Phase4 衰减追踪**（`autodiscovery_log` 攒够 → verdict 随时间翻转可视化）
11. **A2 建议器自升级**（`composite_log` / `llm_read_log` 攒前向史 → OOS 权重校准）

---

## ⭐ 专节：议员 / 总统持股工具（QuiverQuant 概念）— 深挖评估

**值得做，且正好契合新方向**（另类数据 + 诚实 OOS 检验 + 可选跟单 + 公开计分）。这是项目没有的新数据，
且与 SEC 内部人族同源，能合成一个"聪明钱/政治钱"诚实检验大族。

**诚实角度（命门）**：美国《STOCK Act》要求议员申报交易，但有 **~45 天披露滞后** → **不是抢跑**。
所以真正能测的是："**披露之后再跟，OOS 还有没有 edge**"，并按议员 / 委员会 / 党派拆解。大概率结论可能是
"滞后后 edge 被磨平 / 个别委员会有信息优势" —— 测出来才有价值（和测世界杯/任期年一个路子）。

**落地步骤**：
1. **可行性 spike**（先做，别直接建）：找**够长历史 + 澳洲可达 + 免费或廉价**的数据源
   - QuiverQuant：有 API，**付费**（congress 数据要订阅）
   - 原始披露（House Clerk / Senate eFD）：**免费但乱**（PDF / 半结构化），解析重
   - 第三方（Unusual Whales / Capitol Trades）：覆盖好，API 多付费
   - GitHub 上有人爬好的历史数据集（免费，需核对新鲜度/质量）
   - **判断点**：拿不到够长可回测的历史就别硬上（没历史的"信号"不如不做）
2. **诚实检验**：披露日 + 滞后 → 前向收益 vs 基率，过 FDR；按议员/委员会拆
3. **可选跟单信号** + append 计分（守"敢预测敢认账"护城河）
4. 与 `fetch_insider.py`（SEC Form 4）并族，进自生长候选空间（bump N_DECLARED，走双审）

**总统持股**：披露但更新慢、单人、可操作性弱 → 优先级低于议员交易；可作附带展示，不单独建大工程。

---

## 网站吸收清单（2026-06-22，4 站调研：midas诊股 / daily_stock_analysis / 期权助手 / aihot）

**贯穿洞察**：四站都在做「AI 告诉你买」，没一个敢亮自己的战绩/校准——midas、daily_stock 甚至把追踪机器造好了却不显示仪表盘。**这个空白 = Valpha Lab 护城河。** 三层镜头(数据/思想/呈现)：

### 🥇 第一梯队（做实护城河）
1. **公开计分/校准卡**（来自 daily_stock 的 decision_signal_outcome）：把 prediction_log / tipjar / composite_log / llm_read_log 各预测**汇成一张公开计分卡**；冻结(日期/方向/期限/置信)→ 1/3/5/10日对前向打 hit/miss/neutral(2%死区)、不可验证标 `unable`；**多走一步=按置信分桶看实际命中率(校准)**。← 正在做
2. **LLM 数据质量门→强制降置信**（daily_stock 的 AnalysisContextPack + 期权助手的 LLM 纪律）：喂 Gemini 前算每项输入覆盖/新鲜度分；prompt 写死「覆盖差→最多'弱'倾向 + 渲染数据限制块」。把诚实变机械强制。

### 🥈 第二梯队
3. **单框诊股 UX + 自选 watchlist**（midas）：输美股代码→出**诚实**报告(风险画像+哪些规律过 placebo/FDR)。接 stock_checkup。
4. **规律卡强制 regime+evidence 字段**（daily_stock YAML schema）：每条野蛮/季节规律必带 scope + 证据(测几年/原始计数)，没回测不能存在。
5. **DeepSeek 当便宜 LLM 层**（midas）：比 Gemini 便宜+中文好，日读省钱杠杆。

### 🥉 第三梯队
6. ✅**完成**：🎓 **期权教学沙盒** `options.html`（payoff 搭腿 + BSM 希腊字母沙盒 + 为什么大多数人亏；BSM 对过 scipy 5 位小数 + put-call parity）— `83a48ec`。
7. ⏭️**跳过（已评估）**：📊 呈现/分类 chips — 证据库只 6 卡 / 6 族（1 对 1 = 纯 chrome），其他多项页已可按板块筛 → 不为凑数造装饰（enforce-simplicity）。将来若某页真的拥挤再说。
8. ✅**完成**：📱 **持仓感知告警**（扩 `alert_check.py`）— 只在你持有的票深度回撤才单独提醒，私密走 `HOLDINGS` Secret，措辞守红线（风险提示非买卖）— `5451147`。
9. 🔌 **Finnhub 免费 US 源**（用户 2026-06-24 重新点名要用）。实测 free tier(60 calls/min)：✅免费 = 实时 quote / 个股新闻 company-news / **财报日历 earnings calendar** / 分析师推荐趋势 / 内部人交易；❌ **stock candle(历史 OHLCV) 2024 起转付费** → **不能拿它做价格回测**。**最佳用法(都不需历史)**：① **财报日历 → 个股"N 天后财报"风险标**(高价值·无需回测) ② 个股新闻 ③ 分析师 buy/hold/sell 快照(透明展示;要"测它准不准"得攒历史)。需用户拿免费 key → 加 `FINNHUB_API_KEY` Secret(同 LLM no-key 静默)。
10. 🤖 **Kronos 评估（用户 2026-06-24 发 github.com/shiyu-coder/Kronos）**：开源金融 K 线**基础模型**(decoder-only transformer · 45+ 交易所 OHLCV 预训练 · mini 4M~large 499M · MIT · HF · AAAI2026)；输入历史 OHLCV → 预测未来 OHLCV。**契合用户 DL 野心**，但**诚实工程异议**：价格预测 ≠ 可交易 edge(市场近有效，多数此类模型扣成本后跑不赢随机游走)。**正确做法(项目铁律)**：当**带公开计分的实验**——Kronos-mini 跑几只美股，**walk-forward 比 naive(随机游走/last) OOS 扣成本后真赢了才上**，且像一切**公开认账**；别当"它能预测"直接上 UI。是真 DL 候选，但要先建验证 harness = **单独立项 + 重审**。

### ❌ 别碰
aihot 数据(不相关) · midas 无计分 AI 裁决 · 期权推荐引擎(没历史没法计分+对初学者太险) · adanos 付费情绪(改用免费 Reddit/Polymarket 提及数走自己 placebo) · A股适配器 · 6 渠道推送 · 15 图表策略当信号(只当靶子证伪)。

---

## 🧹 去重待办（2026-06-22 用户提·第三梯队做完后统一做一次，别中途churn）

快速建出一堆诚实分析后积累的重复（已扫描量化，**不影响功能、纯 DRY**）：
1. ✅**完成**：`scripts/util_io.py` 的 `write_json`（4 轴 indent/allow_nan/separators/proc·test_util_io 5 例逐字节等价）已替掉**全部 25 个多目录写者**（7 近期 + 5 口径不同 daily_digest/outlook/tipjar/fetch_insider/quick_quotes + 13 个 `(PROC,WEB,DOCS)` 三写统计脚本）。样板 `for d in (...): if d.exists(): write_text` 全收成一行，**行为零变化**（pytest 229 绿 + outlook/market_regime spot-run 仅时间戳/活数据变、无重排）。
2. ✅**完成**：`util_io.append_daily_log(path, header, rows, *, date)`（rows 支持多行·同日去重**绝不改历史**）替掉 6 处 `_append_log`/`_log`（llm/autodiscovery/composite/regime/senate/btc；event_causal 是误报·scorecard 只读不写）+ 删 4 个变空的 `import csv`。逐字节核对：test_util_io 3 例 + **真账本 temp 副本**实测（同日 no-op／新日 append／多行排序／None→""），真账本未触碰。pytest 232 绿。
3. ✅**完成**：`stats_util.forward_returns(prices, h)` = `price[t+h]/price[t]-1` 单一审计实现，替掉 btc(×2 内部重复)/regime_forward/risk_dashboard 共 4 处内联 `s.shift(-h)/s-1`。**语义不同的按你说的留各自**：factor_pruning/vol_model 前向 rolling-vol、advanced_analysis 前向累积、factor_model/overreaction 次日方向/收益——都没碰。test_stats_util 加等价+无前视 NaN 尾测试，pytest 233 绿。
4. ✅**完成（轻量·用户选）**：抽共享 `web/vp.css`（8 页逐字节一致的灰底调色板 8 变量 + box-sizing + focus/reduced-motion a11y + #lang），btcread/senate/regimefwd/scorecard/evidence/ondemand/wildpool/options 各 `<link>` 它、删内联重复；页面特有 `--amber/--warn` 与 body/table/.card 等**留各自**。同源自托管（随 web→docs 镜像）。**可静态证逐字节等价**（规则原样搬进先加载的 vp.css·无层叠冲突）；CI site-audit 浏览器审计把关。JS 共享外壳按用户判断**不做**（自包含对静态页更简单）。
顺序：先做完第三梯队（期权教育/呈现/持仓告警/Finnhub），再一次性抽这 4 个 + 改所有调用点（每个改动 node-check/pytest 验）。

---

## 协作铁律（不变）
- 判断密集 / 出公开结论 = **强编排**（详细 spec + 独立审，审查者 ≠ 建造者）
- 守质量地基：pytest / verify_output 门禁、append-only 账本绝不手改、秘钥只走 Secrets、公开计分
- **先查后动**（DAILY_LOG / OPTIMIZATION_LOG §4c 试过但否决 / 🪦坟场 / 📋登记簿）
