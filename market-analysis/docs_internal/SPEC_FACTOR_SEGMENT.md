# SPEC — #5 分段透镜推广到 factor_audit（因子"现代段"存活）

> 六步协议 **①写计划**。建造前需 **②独立审计划**。判断密集（公开统计结论）→ 建后**双审**（Fable + 全新 Opus/Codex）。
> 写于 2026-06-18，趁热定。明天先看 🔴 判断点。

## 目标
placebo 已有"全样本 vs 2000 后现代段"分段透镜——揭示唯二过 FDR 的日历效应（星期/圣诞）在 2000 后已被套利、测不到。
本任务把同一透镜推广到 **因子尸检（factor_pruning）**：回答 **"这个因子在现代段还工作吗，还是也被套利了？"**——描述性、非预测、同 placebo 口径。

## 现状（已核实，2026-06-18）
- `factor_pruning.py`：每个因子在 dev(2000-2023) 学 LR，holdout(2024-2026) 报样本外；输出 verdict（INFORMATIVE/FRAGILE/MISLEADING/NOISE）+ `holdout_diff_pp` + `sign_agree_frac`。
- 前端 `renderFactorAudit`（app-5.js）显示每因子：方向 / holdout_diff / sign_agree / verdict。
- **即：已有"训练 / 样本外"split，但没有 placebo 那种"全段 vs 现代段"并排对比**（口径不同，holdout 只 ~2 年、是 train/test 不是 segment lens）。

## 🔴 判断点（建造前必须停下问用户，别自行决定）
**"现代段"怎么切？** 因子数据从 2000 起，placebo 的"2000 后"口径套不进来。候选：
- **(A)** 全段(2000–now) vs 最近段（最近 5 年 / 8 年）
- **(B)** 前半(2000–2012) vs 后半(2012–now)
- **(C)** 复用现有 holdout(2024–2026) 作"现代段"——但样本太短(~2 年)、检验力弱
→ **停下报告三者的检验力 / 样本量权衡，让用户拍 A/B/C + 具体年限。** 同 placebo 的诚实：现代段每折/每组 n 够不够，不够就标 **inconclusive**，别误判"被套利"。

## 实现（口径定了之后）
1. `factor_pruning.py`：每因子额外算"现代段"同口径指标（块自助 AUC diff / sign-agree），与全段并排；factor_audit json 加 `segment` 字段。
2. verdict 扩展三态：**现代仍有效 / 现代已失效（疑被套利）/ 现代检验力不足**（套 placebo 的 `recent_min_group_n` 门）。
3. 前端 `renderFactorAudit`：每因子加"现代段"列/徽章（`esc` 转义，CSP 友好——用 data-* 不用 inline onclick）。
4. 红线：措辞描述性（"现代测不到"≠"会失效"），"被套利"软化为"很可能"，标注口径与个股块不同。

## 验收 / 审
- **pytest**：给现代段逻辑补单测（合成数据：造一个"全段显著、现代消失"的因子，断言判 inconclusive/失效；再造一个"两段都稳"的，断言仍有效）。
- **verify_output**：factor_audit json 形状门加 `segment` 字段检查。
- **双审**：Fable 建 → 全新 Opus/Codex 审（公开统计结论；**口径 + 检验力**是审查重点）。
- 全量 run_all + 前端 audit + **浏览器验证**（配 site_audit）。

## 不做
- 不加新因子、不上模型——只给**现有**因子加"现代段透镜"。

## 参照（先查后动）
- placebo 的分段实现：`placebo_test.py`（全样本 vs 2000 后 + recent_min_group_n 检验力门）——直接抄口径。
- OPTIMIZATION_LOG §4c "cycles 分段→否决"：长历史才有意义的别硬切——factor 同理，现代段太短就标 inconclusive。
