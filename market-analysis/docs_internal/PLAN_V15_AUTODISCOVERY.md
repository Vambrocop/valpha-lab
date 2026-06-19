# PLAN_V15_AUTODISCOVERY — v1.5「自生长·自动发现闭环」增量实现计划

> 2026-06-19 由规划子代理产出、主脑核对存档。是 `SPEC_SELF_GROWING.md`(v2.0 spec) 的**可落地切片化**版。
> **⚠️ 开工前必须先拍两个 🔴 判断点(见 §5 🔴-A / 🔴-B)** —— 它们决定架构走向。遵守六步协议(判断密集→建后双审)+「先查后动」+红线。

## 现状结论（先查后动）

1. **展示层已成熟，发现层缺失**。`fdr_crossfamily.py:collect()` 从四个已发布 JSON(placebo/event_causal/multivariate/factor_pruning)**被动收集** p 值做 BY/BH/Bonferroni 跨族校正，`self_growing.html` 当"总账"渲染。**没有任何东西"主动生成新候选"**——发现靠人手在 `placebo_test.py` 加 `add(...)`、`factor_pruning.py` 加因子。v1.5 = 补"自动枚举候选 + 喂进这台校正引擎 + 把存活/死亡固化成 append-only 账本 + 持续复测"。

2. **所有质量门机器都已存在、口径统一，不需重造**：置换三态(`placebo_test._verdict`)、每项独立 RNG 流、现代段分段(`recent_cut=2000`,现代≥200才测)、块自助(`block_bootstrap_diff` seed=42)、因子现代段透镜(`_segment_lens`)、BH/BY 单一来源(`stats_util`)、样本外严格裁决(`walk_forward` purged+embargo/holdout)、过拟合概率(`cpcv` PBO)、append-only+hash链(`ledger_hash` + `repair_ledgers` + `verify_output` 硬门)。

3. **缺口/风险**：
   - **`deflated_sharpe.py` 不存在**；DSR 是"收益型"指标，与全站"测风险不测方向、AUC<0.5"灵魂有张力 → 🔴-B。
   - 候选自动枚举后 **m 从约 30 膨胀到几百**；BY step-up 会**自动把现有真存活者(星期/圣诞)也压没**——这是**正确**(更诚实)行为，但改观感 → 🔴-A。
   - `event_causal.py` 已有 `pending` 状态先例(后窗不足不硬估)=「检验力不足→不下结论」现成范式，照搬。

## 总体架构（最终形态，分 phase 落地）

```
candidate_space.py   ── 预注册、有限、可枚举的候选生成器(N 写死常量 + append-only 扩展日志)
        │  产出 candidates[](家族 + 参数 + 稳定 candidate_id + 数据切片描述)
        ▼
quality_gate.py      ── 对【整族】串现有门：placebo置换 → 现代段分段 → 跨族BY-FDR → walk-forward样本外
        │              三态裁决(survive/dead+死因门/inconclusive)，固定种子，m=全部试过的候选数
        ▼
grow_registry.py     ── 存活→registry.csv，死亡→graveyard.csv(append-only+hash链+死因)
        │              长期复测：已入册者重测样本外，衰减→移回坟场(记"曾真现已套利+日期")
        ▼
self_growing.html    ── 现展示层 + 诚实账单(测了N / 期望假阳N×α / 入选M / 复测衰减K)
        ▼
run_all.py           ── 注册为独立慢步骤(非 light)；verify_output 校验账本 hash 链
```
候选引擎**不重算统计**，只做枚举+编排+固化，复用 `placebo_test`/`stats_util`/`block_bootstrap_diff`/`_segment_lens`/`ledger_hash`。

## 1. 候选从哪来（预注册有限空间 + m 全计入分母）

**铁律：候选空间预先声明、可枚举、有限(N 已知写死 + 注释为何这些)，禁无界钓鱼。** 扩 N → append-only 记录。首版只收已有数据能算、统计原语已存在的家族：

| 家族 | 枚举维度(预声明) | 约 N | 复用 |
|---|---|---|---|
| 日历族 | 星期×{纳指,标普}；月份×{纳指,标普}；年尾数；任期年；节假日前后 | ~10 | placebo SS_between/dir_diff + 现代段 |
| 超跌反弹族 | 阈值∈{1,5,10百分位}×持有{1,5日}×{纳指,标普} | ~12 | block_bootstrap_diff + 单边方向门 |
| 简单因子族 | BINARY_FEATURES(15)×{全样本,现代段} | ~30 | factor_scorecard + _segment_lens |

合计首版 **N≈50–60**。**不收**：自由参数扫描、新因子、新事件类型、深度模型。阈值/持有期只允许预声明离散集。
**🔴 m 膨胀全计入分母**：所有候选无论 p 值大小全进 `m_total`；**禁止"先粗筛只喂好看的"**(=forking paths)。`candidate_space` 暴露 `N_DECLARED`，`quality_gate` 断言 `len==N_DECLARED`。

## 2. 质量门（复用现有机器串管线，按序全过才入册）

| 序 | 门 | 复用 | 阈值(预注册写死) |
|---|---|---|---|
| 1 | 置换/块自助显著性 | placebo.perm_test / block_bootstrap_diff | p<0.05(日历)/ p_boot<0.10(自助) |
| 2 | 现代段分段 | placebo recent / _segment_lens | 现代≥200且最小组≥30才下结论 |
| 3 | 跨族 BY-FDR | stats_util.by_reject(经 fdr_crossfamily) | q<0.10(BY,头条) |
| 4 | 样本外 | walk_forward(purged+embargo/holdout) | block_bootstrap_diff p<0.10 |

三态：**存活**=四门全过；**死亡**=任一门不显著(记死因门);**inconclusive**=任一门检验力不足(绝不下存活/证伪)。
DSR/conformal 首版不接(§5 🔴-B)；PBO(`cpcv`)作家族级过拟合体检附账单，不逐候选判。

## 3. 🔴 p-hacking 护栏（焊进设计，非可选）

①全部候选进分母(断言 m_total≥N_DECLARED，禁显著性预筛) ②预注册空间+门槛先写死后跑(禁 HARKing) ③固定种子(每候选独立流 `default_rng([SEED, candidate_id_hash])`) ④现代段分段防"被套利还当真" ⑤检验力不足标 inconclusive ⑥诚实账单常驻(测N/期望假阳N×α/入选M/衰减K) ⑦append-only hash链不可美化。
**> 若实现中想"放宽门让多通过几个"——停下、别做、报告。门是这功能的全部意义。**

## 4. 增量切片（每 phase = 一次可验收提交）

- **🥇 Phase 0(推荐起手)**：`candidate_space.py` 纯枚举 + 单测，**不接任何统计**。验收：`len==N_DECLARED`、candidate_id 稳定唯一、增删维度按预期变化；**代码评审专审"空间是否有界、有无暗藏自由度"**。零统计/零账本风险，先把边界钉死(spec 阶段抓最便宜)。
- **Phase 1**：`quality_gate.py` 串门1–2 + 跨族 FDR(门3)，产出 `autodiscovery.json`(展示用,**不进账本**)。验收：纯噪声家族 BY 校正后入选≈N×q(不爆表)、植入真信号入选、m_total≥N_DECLARED。
- **Phase 2**：`grow_registry.py` append-only registry/graveyard + hash链(复用 ledger_hash + repair_ledgers + verify_output)。验收：hash链 verify、幂等、union 合并可修复。
- **Phase 3**：前端诚实账单(self_growing.html 加区,中英双语/@media/esc/localStorage防抛)。验收：audit_frontend 过 + 浏览器实测 + 红线措辞审。
- **Phase 4**：长期复测 + 衰减移回坟场(留痕"曾真现已套利+日期")。验收：合成"先真后失效"序列断言正确移回。
- **Phase 5(可选,需 🔴-B 拍板)**：DSR 门。

## 5. 判断点（停下问，别自行决定）

- **🔴-A(最该先拍)候选膨胀后现有真存活者被压没，接受吗？** N 从约30→约55，BY 阈值收紧，**很可能现有存活者(星期/圣诞)全跌出 q<0.10**(结果=自动发现后全站真存活可能=0)。这**更诚实**但会让 🌱 页从"有几条真规律"变"诚实地说一条都不稳健"。**要这个更冷的诚实结果，还是家族内FDR+跨族FDR 双栏并列保留信息？** 决定 `collect()` 要不要把自动候选与手动候选合并进同一分母。
- **🔴-B DSR 要不要做？** 与"不测方向"红线张力，且无脚本。建议**首版不接**(BY-FDR+样本外+PBO 已够)，需确认 spec 的 DSR 门可降级/缓做。
- **C** 现代已淡候选：算"存活带⚠️衰减标"还是判死进坟场？
- **D** 自动候选 vs 人工主张：替换 or 并存(去重防双重计入分母)？
- **E** 复测频率：每次 run_all 全量 or 按周？

## 6. 验证策略（证明引擎不自欺）

1. **纯噪声家族→校正后入选≈期望假阳率**(最关键):造K个纯噪声候选,断言 BY 后 `n_survive ≤ ceil(K×0.10)+小余量`;扫 K∈{50,200,1000} 断言不随K线性膨胀。 2. **植入真信号必入选**(对称护栏)。 3. **检验力不足→inconclusive**(照搬 test_placebo/test_factor_segment)。 4. **分母完整性** `m_total==N_DECLARED`。 5. **种子可复现**(两次跑逐字一致)。 6. **账本性质**(hash链/幂等/union修复/衰减留痕)。 7. **冒烟+不变式** `n_survive_by ≤ n_survive_bh`。一律 `write=False`/临时df，不污染生产 JSON。

## 7. 诚实红线

产物措辞描述性(登记簿="经得起跨族校正的规律"非"信号/策略";坟场="试过但没站住")；存活≠未来重演≠可交易;不预测方向(自生长**不在** 📈观点页例外内);承认"真规律也会死"(衰减移回留痕);inconclusive 是合法结论。

## 8. 风险与缓解

m 膨胀压没真存活(→🔴-A 先拍/双栏)、DSR 越界(→🔴-B 首版不接)、双重计入分母(→candidate_id 去重)、慢(→非light步骤;实测置换1.2万次仅2.9s,N≈55可接受)、账本无限增长(→append-only本就如此;🔴-E定频率)、隐性自由度溜入(→Phase 0 单独成审专审有界性)、CI union破坏hash链(→repair_ledgers)。

## 推荐起手式

先拍 **🔴-A**(膨胀后真存活归零是否接受/要不要双栏)和 **🔴-B**(DSR 是否越界/可否缓做)；拍完即可开 **Phase 0(candidate_space.py 纯枚举 + 有界性单审)**——零统计/零账本风险，把候选空间边界钉死，是整个闭环最便宜也最关键的第一刀。
