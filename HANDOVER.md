# HANDOVER.md — Fable 缺席时的接力手册

更新:2026-07-07(Fable 5 起草)。**触发条件:本会话主脑模型不是 Fable 5 → 先读完本文件再动手。**
(哪怕是 Fable 自己回来,也从 §3 任务队列对表开工;做完任何一项就更新队列。)

## 0. 任何模型开工前必读(顺序)

1. `CLAUDE.md`(约定+方向定调+铁律)
2. 本文件(角色分配+任务队列+CI 手册)
3. `DAILY_LOG.md` 最近几天 + `OPTIMIZATION_LOG.md` §2(计划记档)·§4c(试过但否决)·🪦坟场·📋登记簿
4. **先查后动铁律**:收到"做 X"→ 先报"之前做过没/做成啥样/有无结果"→ 再动手

## 1. 角色分配(按当天可用的最高模型)

| 场景 | 主脑(编排/判断/终审) | 建造 | 审查 |
|---|---|---|---|
| Fable 5 可用 | Fable 5 | Sonnet(机械)/Fable(判断密集) | Opus(全新上下文) |
| 只有 Opus+Sonnet | **Opus 接任主脑** | Sonnet | **另一个全新上下文的 Opus** |
| 只有 Sonnet | 不设主脑 | 只做队列里标 **[机械]** 的任务 | 单审(另一个 Sonnet 全新上下文) |

- 铁律不变:**审查者 ≠ 建造者 ≠ 同一上下文**;公开统计结论/模型链 = 双审,常规聚合展示 = 单审
- 六步协议不变:①写规格 → ②独立审规格 → ③建造 → ④独立审实现 → ⑤修复 → ⑥验证提交
- 只有 Sonnet 时,凡标 **[判断]** 的任务一律不碰,留言给用户等高层模型
- 与用户协作风格(用户明确偏好):**考虑+平衡最优解,不顺着点头**;诚实技术异议 > 虚假认同;
  遇判断点(口径选择/结果反直觉/规格有洞)**停下报告,不要自行决定**

## 2. 铁律速查(细则见 CLAUDE.md)

- append-only 账本**绝不改历史行**:prediction_log / paper_ledger / autodiscovery_log /
  candidate_registry / kb_ledger / ledger_hashchain(sidecar 哈希链 + git-HEAD 门 4c 双锁在守,别绕)
- 不绕 verify_output / pytest 门禁;`--no-verify` 禁用;门禁 deny 了修根因,不是找路绕
- 秘钥只走环境变量 / GitHub Secrets,绝不进仓库/日志/记忆
- Windows:用 `py` 不用 `python`;先 `$env:PYTHONUTF8='1'`
- web/ 改动镜像到 docs/(Edit 后手动 Copy-Item;提交前 `git status` 核对 docs/ 同步)
- 前端不引境外 CDN(中国访客);资源同源自托管
- 改公开统计口径 = [判断] + 双审 + commit message 附新旧指标对比 + bump MODEL_VERSION(若动模型)
- push 前先 fetch(CI 每 2 小时自动提交数据)

## 3. 任务队列(2026-07-07 快照;做完一项更新一项)

**T1 [判断·双审] `_regime_arrays` 尾窗 y=0 同款 bug** — 优先
- 现象:`autodiscovery._regime_arrays` 对尾部未实现前向窗 `(NaN>0)→False` 捏造 y=0
  (与 #7 审④抓的 positioning/optsent 同类;那两处是新代码当场修了,这处是**既有代码**,
  会移动已发布的 golden_cross 等 regime 族 p → 属公开统计口径变更)
- 流程:写 spec(改法+影响面+新旧 p 对比表)→ 独立审 spec → 修 → 双审 → 提交附对比
- 顺手做 §5-R2 全库尾窗清扫,一次审干净
- **停机条件:若 p 变动翻转任何已发布 verdict → 停下报用户**
**T2 [中·单审] 新存活者 survivors_live 描述符**
- `legacy_noncomm_pct_oi_lo_h60_nasdaq100`(COT 纳指仓位极空)现在观察台是"未接入"中性兜底
- 要 usable_from 感知的当前状态计算(点时间纪律:可用日=report_date+4 交易日,别用 report_date)
- 参考:survivors_live 现有描述符写法 + `_positioning_arrays` 的状态定义
**T3 [机械·Sonnet 可做] #5 W3:app-4.js 全量双语**
- 模式已定型(参照 d571f76 的 app-5/app-2):`vpL(zh,en)` 双写、模块级常量 getter 化、
  Plotly `%{x}` 占位符保留、语言切换后清 tab 缓存再 renderAll
- 完后:en-mode-note 重写 + playwright 实测切换 + `py tools/audit_frontend.py`
- 后端自由散文 i18n **不在本任务**(用户单独决定)
**T4 [判断·日历 ~2026-08 初] #2 KB 首批晋升验收**
- 锚 2026-06-26 + 2026-07-05;min_oos_n=30 攒够后 kb_ledger 首批晋升
- 验收=亲验 oos_gate 裁决合理性(逐条看数字),不是看它跑完
**T5 [判断·日历 ~2026-08] #3 AI 预测页增强**(等 ~20+ 结算样本)
**T6 [机械·小] IPO 数据定期更新自动化**
**T7 [大工程] v1.5 自生长自动发现闭环 — 单独立项+重审,不要顺手做**(用户定过调;Fable 在场时做)

**CI 观察哨**:07-07 已修 #100–104 测试红(见 §4);下一班 schedule 确认转绿;
COT/P·C fetch 步骤(每交易日盘后一次)CI 尚未首跑——fail-soft 只出 warning,跑后查 warning。

## 4. CI 红处置手册(2026-07-07 教训固化)

1. **查**:公开 API(无需 gh/token)——
   `Invoke-RestMethod ".../repos/Vambrocop/valpha-lab/actions/runs?per_page=10"` → 定位失败 run
   → 取其 `jobs_url` → 看哪个 step failure(job 日志 API 要授权,不用管它)
2. **复现**:`git archive HEAD` 解到临时目录 → `PYTHONUTF8=1 py -m pytest market-analysis/tests -q`
   ("本地绿 CI 红"九成 = 测试依赖了 gitignore 生成数据;CI 的数据缓存恢复在测试**之后**)
3. **修根因**,不绕门禁、不改工作流顺序迁就坏测试
4. **防复发已固化**:`tools/pre_commit_gate.py` 现在就是干净检出跑 pytest(CI 同构)——
   树内绿而门禁红 = 同款问题,提交那一刻就会被拦
5. 规矩:门禁测试不依赖 `data/raw/` 等 gitignore 数据;确需真数据的测试 → 缺数据 `pytest.skip`,
   同一性质必须另有合成数据版恒跑(样例:`test_arrays_exclude_days_without_realized_forward_window`)

## 5. 架构评估与升级路线(Fable 2026-07-07;供接手者排期,非本日任务)

**总判断**:统计核心(candidate_space → autodiscovery → oos_gate → registry → sidecar+git 双锁)
是护城河,结构健康,**别动它的架构**;债主要在 web 层重复与流水线隐式依赖。

- **R1 [小·automation-first]** docs/ 镜像漂移自动门:verify_output 加 web/↔docs/ 关键文件
  一致性检查(镜像 DRIFT 已人肉抓过≥2 次,该上机器门)
- **R2 [小·并入 T1]** 尾窗 NaN 全库清扫:grep 所有前向窗构造点(`fwd`/`> 0`/`astype(float)`),
  列清单逐一判定是否同款 bug,一次审干净
- **R3 [中]** `build_feature_df` 多脚本重复构建 → 参数哈希缓存(parquet);**先测量耗时占比再做**
- **R4 [中·克制]** web 公共微工具收敛(_fetchJson/esc/localStorage 防抛已有雏形→vp_core.js 统一);
  **不做** SPA/前端框架/构建链(中国访客+同源自托管是硬约束)
- **R5 [小]** run_all.py 阶段 DAG 注释显式化(哪步产出谁消费——新模型接手最缺这张图)
- **R6 [观察]** CI 每 2h 数据提交 → 仓库历史膨胀;暂不动(Pages 吃 main),clone 变慢再议 data 分支
- **R7** = T7(自生长闭环,单独立项)

**明确不做**(设计定调,别翻案):前端框架/打包链引入、多市场(A股/港/日韩)、任何绕门禁的捷径。
