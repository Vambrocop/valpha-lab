# SPEC_LEDGER_GUARD — CI append-only 防缩水门(ci_ledger_guard)

> Fable 主脑亲写(2026-07-24)。缘起:llm_weekly W28/W29 两周真实 LLM 读数在远端丢失——
> 6 个 workflow 并发抢 main,`commit → pull --rebase --autostash → push` 循环里把「每周只写
> 一次」的稀有行挤掉(高频数据文件每次重生成能自愈,稀有的公开计分行不能)。用户 2026-07-24
> 批准「加 append-only 防缩水门」。六步:①规格 → ②审 → ③建 → ④审 → ⑤修 → ⑥亲验+提交。

## 0. 命门(为什么是门,不是自愈)
- **不变式**:每个 append-only 账本,push 前的工作树必须是 origin/main 对应账本的
  **append-only 超集**——origin 的身份列序列必须是本地身份列序列的**前缀**(历史行只增不改序、
  不丢)。违反 = 有历史行被挤掉 → **拒绝 push,job 失败告警**(不静默盖过 origin)。
- **为什么拒绝而非合并**:丢行是**时序竞态**(极少数 run 撞上),不是确定性故障;拒掉这一次坏
  push,下一次(没撞上的)run 从合并后检出正常推。拒绝安全、自限,绝不制造持续停摆。自动合并
  (union 修复+重封)留作 v2——先上最简正确的门。

## 1. 口径复用(不造新语义)
- **身份列 = ledger_sidecar.SPECS 的 core_spec**(单一真相源,import 不复制):settle 只填空的
  forward_ledger 类(pick_ledger 等)身份列=建行即定的列,结算改的是非身份列 → 身份前缀稳定,
  **不误报**;纯 append 类 core_spec=None → 身份=全行。
- **比对用明文身份元组前缀**(非 chain_head):语义与 sidecar「core 前缀链复现」等价,但纯 stdlib
  (csv)、无 pandas、可点名具体丢了哪几行。sidecar 管「文件 vs manifest」,本门管「工作树 vs origin」,
  两把尺同一把柄。
- **不 fetch**:门只比工作树 vs 本地 `origin/main` remote-tracking ref(由 workflow 紧邻的
  `git pull --rebase` 更新)。门内再 fetch 会拉到未整合的更新 → 假缩水。门必须跑在 pull --rebase 之后。

## 2. 纯函数(可脱 git 单测)
`append_only_violation(o_header, o_rows, l_header, l_rows, core_spec) -> str|None`:
- core = core_spec or o_header;
- **schema 变更豁免**:core_spec=None 且 o_header≠l_header → return None(合法代码改表头,非丢行);
  core_spec 指定但某身份列不在两侧表头 → return None(无法比对,不误判为丢行);
- o_ids/l_ids = 各行身份列元组;`o_ids == l_ids[:len(o_ids)]` → None(超集,放行);
- 否则 return 诊断串(点名丢失的前 3 个身份元组)。

## 3. CLI(tools/ci_ledger_guard.py)
- 遍历 SPECS:`_origin_rows(rel)` = `git show origin/main:market-analysis/data/<fname>`(rc≠0 → 该账本
  尚不在 origin,skip);本地读 `DATA/<fname>`(origin 有而本地缺 → 违规)。逐个调纯函数收集违规。
- 有违规 → 打 `::error::` + 逐条点名 → `sys.exit(1)`(阻断 push);无 → 打 OK 退 0。
- 只依赖 stdlib + 从 ledger_sidecar import SPECS/DATA(pandas 经 ledger_hash 载入,5 个目标 workflow
  均已装)。

## 4. 挂接(5 个推 data/账本的 workflow;site-audit 不推→不挂)
每处 `git pull --rebase [--autostash] origin main` **之后、`git push` 之前**插
`python tools/ci_ledger_guard.py &&`。两种现有句式:
- `push || (pull --rebase --autostash && push)` → `guard && push || (pull --rebase --autostash && guard && push)`;
- `if git push; then exit 0; fi; pull --rebase; push` → push 前加 `guard`,retry 的 pull 后加 `guard`。
挂:refresh-data · quick-quotes · weekend-refresh · weekly-review · lock。**不挂 site-audit**(无 git push)。
门失败即 job 失败(GitHub 红 + 现有告警看得到);坏 push 永不发生,origin 上的稀有行受保护。

## 5. 测试(≥7·纯函数不碰 git)
1. 干净追加(local=origin+新行)→ None;
2. 结算改非身份列(pick_ledger:身份元组不变,exit_px 填空)→ None;
3. 丢行(local 缺 origin 一行)→ 违规,串里点名该行;
4. 乱序(local 把 origin 两行调序)→ 违规;
5. 空 origin(新账本)→ 由 CLI skip(纯函数层:o_rows=[] → 前缀恒成立 → None);
6. schema 变更(None spec·表头不同)→ None(豁免);
7. 身份列 core_spec 缺列(schema 漂移)→ None(不误判)。
(CLI 的 git plumbing 靠本地实弹 dry-run 验,不进单测。)

## 停机点
- 想让门「自动合并/重封」放行 → 停(v1 只拒绝告警;union 自愈是 v2,须单独审——自动写账本是命门);
- 想把某账本移出 SPECS 让门别管它 → 停(SPECS 是红线单一真相源,增删须走 sidecar 的既有理由链);
- 门误报导致数据停摆 → 先查是不是「本地落后 origin」(该 fetch/rebase),不是就地放宽门。
