# v3.0 精简模型实验计划（预注册 · rev2）

> 2026-06-13。rev2：按 Opus 独立审查（APPROVE-WITH-CHANGES）修订，改动见 §3/§4/§6。
> 背景：P2 对决证明 15 因子全家桶方向 AUC<0.5（naive 0.445 / logit 0.432，拼接 2012-2024）；
> P2-5 因子尸检：15 个因子里只有 BTC 20 日动量（涨/跌两向）有样本外内容。
> ROADMAP 假设：**只用 BTC 动量 + 日历的稀疏模型，可能真能过 AUC 0.5**。本实验验证之。

## 1. 假设与变体（固定菜单，不允许中途加变体）

| 变体 | 因子集 | 角色 |
|---|---|---|
| **A. v3-sparse** | 日历(month/dow/wom 学习LR) + BTC_mom20_pos + BTC_mom20_neg | **主假设**，唯一进决策 |
| B. calendar-only | 仅 month/dow/wom | 消融对照 |
| C. btc-only | 仅 BTC_mom20_pos/neg | 消融对照 |
| D. v2-full | 现行 15 因子 + 日历 | 参照系（已知 ≈0.445） |

**实现锁死**（rev2）：子集 = **仅删 lrs_dict["factors"] 的 key**；`learn_lrs` 照常全量学习，
`n_total`/`base_win_rate` 一律不动，不得"为干净"重训。score_row 零改动。
阈值（BTC ±5% 等）从 `signal_model` 常量冻结，不重新调参。

**等价性单测（必须三条全锁，不是"跑通"）**：
- (a) 变体 C：对任意行，输出 == 只用 BTC 两因子手算 bayesian_prob（日历 fallback 1.0 不改变结果）；
- (b) val==0 反面还原：构造 BTC_mom20_pos=0 的行，断言子集 A 与全量 D 在该因子上的 inv_lr 贡献相同
  （n_total、factors[col]["n"] 未变）；
- (c) BTC=NaN 行（pre-2015）：断言变体 A 输出 === 变体 B（退化为纯日历）。
- (d) holdout Tier≥4 触发不足 → 输出 null（不是 NaN）。

## 2. 验证协议（嵌套，与 factor_pruning 同款）

- 开发集：purged+embargo(20d) 扩窗折（复用 `factor_pruning._purged_train`）。
- **主口径 = 以下 4 个折元组**（精确列出，禁止按"年≥2016"过滤行）：
  `(2000,2016,2018) (2000,2018,2020) (2000,2020,2022) (2000,2022,2024)`
  ——BTC 全程可观测。副口径：全部 6 折（早期折 A 退化为日历-only，如实报告）。
- 保留集 2024-2026：**仅报告，不进决策**（见 §3 理由）。脚本流程上 dev 先打印锁定、holdout 后算。
- 指标：拼接 pooled AUC + **按折 mean AUC 同时报告**；Tier≥4 触发胜率−基率（块自助，块长20）。
- **regime 伪影预注册**（rev2）：若主口径 pooled AUC 与 mean-of-folds AUC 分歧 > 0.03，
  判定为拼接基率漂移伪影，**不得通过**。

## 3. 决策规则（rev2 重写：dev 硬门槛 + holdout 仅报告 + 部署解耦）

**为什么 holdout 不进决策**：本假设来自 P2-5 尸检，而尸检用过同一个 2024-2026 holdout
确认 BTC 动量方向（BTC_pos +9.2pp / BTC_neg −24.7pp 方向确认）。变体 A 在该 holdout 上
"几乎注定"表现合格——它不提供独立证据力。装进 AND 规则会制造"四道独立关卡"的假象。

**实验通过**（仅 dev 主口径，全部满足）：
1. 主口径拼接 AUC 的**块自助 95% CI 下界 > 0.50**（点估计擦边不算）；
2. mean-of-folds AUC 与 pooled 分歧 ≤ 0.03；
3. Tier≥4 块自助 diff > 0 且 p_boot < 0.05（rev2 从 0.10 收紧——部署级决策）。

**实验通过 ≠ 部署**（rev2 解耦）：
- 通过 → v3-sparse 进入 **benchmark 影子前向追踪**（不动现行部署、不 bump MODEL_VERSION）；
- **前向预注册标准**：前向 ≥120 个交易日 且 Tier≥4 触发 ≥20 次 且 前向 diff > 0
  → 届时才 bump MODEL_VERSION 部署；
- 不通过 → 记录诚实零结果（v3_sparse.json 进 signals.json 研究面板素材），现行模型不动。

## 4. 诚实性声明（输出 JSON 与前端必须带）

- holdout 选择污染：假设在该 holdout 上选出，holdout 结果仅供参考、无确认力；
- holdout 为单一强牛市 regime，对看涨因子确认力本就有限；
- 块自助在拼接折边界处"缝合"不连续序列，p 值可能略乐观（沿用现有实现，记为已知局限）；
- 即使实验通过，结论措辞上限："dev 嵌套验证通过，**待影子前向终审**"。

## 5. 消融解读规则（rev2 预注册，防事后讲故事）

- 若 B(calendar-only) 主口径 AUC ≥ A：判定 **BTC 增量为零**——即便 A 过线也记
  "增益来自日历而非 BTC，与尸检结论矛盾，触发复查"，不进影子前向；
- 若 A < B 或 A < C：记"子集负交互"，同样触发复查；
- B/C/D 永不进部署决策。

## 6. 交付物

1. `market-analysis/scripts/v3_sparse_model.py` → `data/processed/v3_sparse.json`
   （JSON 输出 _clean + allow_nan=False）
2. `build_signals.py`：v3_sparse.json 存在则嵌入 `signals.json.v3_sparse`（仅展示，不进信号链）
3. pytest：§1 的 (a)(b)(c)(d) 四条单测
4. CHANGELOG/ROADMAP 更新；verify_output 全绿后提交

## 7. 建造自查清单

- [ ] 折内学习 LR 用 purged 训练集（复用 _purged_train，不是裸 year<train_end）
- [ ] AUC 块自助 CI：按块重采样拼接序列，单类重采样轮次跳过并计数
- [ ] dev 与 holdout 分函数，先 dev 后 holdout（流程防"看一眼再改"）
- [ ] 每变体每折记录"实际生效因子数"（可观测性差异要可见，防消融被混淆）
- [ ] 输出含全部 4 变体 + 两口径 + 诚实性声明
