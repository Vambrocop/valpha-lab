---
name: new-method
description: 脚手架一个新的"诚实统计"方法,严格遵循本项目六步协议 + 红线/约定。用于给 Alpha Lab 加新的统计/因果检验(新事件研究、新防伪检验、新风险度量等)。Triggers:加方法/新检验/scaffold a new stats method/add method.
---

# new-method —— 诚实统计方法脚手架

给 Alpha Lab 加新统计/因果方法时**严格按此六步**,把项目约定烤进每一步。
已有范例照抄结构:`placebo_test` / `event_causal` / `risk_dashboard` / `conformal` / `cycles` / `fdr_crossfamily`。

## 🔴 红线(每步都守)
- **绝不预测方向**。只回答"真规律 vs 幻觉""风险何时更深""不确定性区间"。任何暗示可交易方向的输出/措辞 = 违规。
- 失败/空/无定论的结果**照样上网页**(诚实登记簿的灵魂)。三态裁决:`real` / `inconclusive`(检验力不足) / `rejected`。
- 数据不可行就**诚实跳过 + 记 LOOP_DECISIONS + 进登记簿"数据不可行"**,绝不用劣质代理硬凑(=编造)。

## 运行环境
- 用 `py`(不是 `python`);跑脚本前 `$env:PYTHONUTF8='1'`。
- 测试 `py -m pytest market-analysis/tests -q`;前端改完 `node --check` + `py tools/audit_frontend.py`。

## 六步协议(每个方法 = 一次提交,commit 带方法名)

### ① 脚本 `market-analysis/scripts/<method>.py`
- 顶部 docstring:**诚实问题** + 方法 + 红线声明 + 依赖。
- `SEED = 20260613`;所有随机用 `np.random.default_rng(SEED)`(已发布统计必可复现——别用无种子全局 RNG)。
- 复用数据 `data/raw/SP500_long.csv` 等;多重比较要校正(BH/BY,见 fdr_crossfamily)。
- 输出 `<method>.json` 到 **PROC_DIR + WEB_DIR + DOCS_DIR** 三处;`json.dump(out, f, ensure_ascii=False, indent=2, allow_nan=False)`(`allow_nan=False` 必加,NaN 在源头报错)。
- JSON 带 `caveat` 写清局限(小样本/样本内/识别假设/不预测方向)+ `generated` 时间戳。

### ② 接入 `run_all.py`
- 合适顺序插 `("<中文名>", "<method>.py")`(依赖前置脚本则排其后)。

### ③ verify_output 形状门(§3x)
- 仿 §3c/§3d/§3e:`<method>.json` 存在则查关键字段/不变式(**存在才查、缺失不致命**)。

### ④ 测试 `market-analysis/tests/test_<method>.py`
- 核心统计逻辑(已知输入→已知输出)、**不变式**(如 BY≤BH)、**确定性**(同种子同结果)、退化输入。
- 有"检出力"概念时测两头:零信号不误报 + 强信号能检出。

### ⑤ 前端面板(研究 / 登记簿视图)
- `index.html`:`<div class="chart-wrap" style="padding:1.25rem;">` + `chart-header` 标题 + `<div id="<method>"></div>`。
- `app-2.js`:`async function load<Method>()` fetch `"<method>.json?_="+Date.now()`,渲染表/卡。
  - **esc() 任何外部字符串**(RSS/API 来的);分隔线 `var(--border-faint)`;muted 小字 `class="u-cap"`;数字右对齐+`tabular-nums`。
  - 诚实呈现:全局结论为准、逐项标注、空/否/红线用判定色;缺数据显"…尚未生成(下次全量流水线后出现)"。
- `app-5.js`:`lazyRender("<method>", load<Method>, "<Name>")`。
- 诚实统计方法:加进登记簿 DOM 搬迁数组(app-5.js renderAll)+ `loadHonestRegistry` 一行(app-2.js;verdict **从 JSON 实时取、别硬编**)。

### ⑥ 验证 + 审 + 提交
- 生成 JSON 核对;`node --check` 改过的 app-*.js;`pytest -q` 全绿;`verify_output.py` 通过;`audit_frontend.py`。
- **公开统计结论 = 必独立审**(`agent-skills:code-reviewer`,全新上下文;重点:统计正确性 + 红线 + 是否会被误读成可预测)。修 reviewer 的 BLOCKER/SHOULD-FIX。
- web→docs 镜像(post_edit_hook 自动;手动 `cp web/x docs/x`)。
- 提交 + push;push 前 `git pull --rebase origin main`(CI 会自动提交数据,防 fast-forward 拒绝)。

## 判断岔路
统计判断点(校准倒挂/非单调/数据不可行)→ **停下报告,不自行决定**,记 LOOP_DECISIONS;与既定原则相左/红线边缘 → 先问用户。
