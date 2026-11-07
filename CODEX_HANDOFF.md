# CODEX_HANDOFF.md — Valpha Lab 完整接力手册

**最后核实：2026-11-07**（本文件每条状态都是写入当天实查的，不是从旧文档抄的）

> **这份文件是给谁的**：任何**非 Fable 5 主脑**的会话接手本仓库时的唯一入口 —— 特别是 Codex。
> 它是**自包含**的：读完这一份就能安全开工，不必先读完另外 18 个 .md。
> 需要细则时再按 §12 的文件地图去翻。
>
> **历史文件别当现状**：`CLAUDE_HANDOFF.md` / `CODEX_REVIEW_v095.md` 是 2026-06-18 那次
> Codex↔Claude 一次性交接笔记；`HANDOVER.md` 是活文档但任务队列停在 2026-07-07。
> **以本文件为准。**

---

## 0. 开工顺序（照做，别跳）

1. 读本文件 §1（当前阻塞）→ §3（环境）→ §5（地雷册）
2. 读 `CLAUDE.md`（项目约定 / 方向定调 / 铁律全文）
3. **先查后动（用户铁律）**：收到「做 X」先报
   「之前做过没 / 做成啥样 / 有无结果」，**再**动手。
   查的地方：`DAILY_LOG.md` · `OPTIMIZATION_LOG.md` §2 计划记档 / §4c 试过但否决 /
   🪦坟场 / 📋登记簿 · 本文件 §7 任务队列。
   > 为什么是铁律：2026-08-25 用户指出我照着一份停在 06-19 的清单念菜单，
   > 他点了才发现「早做完了」—— **核实成本让用户的额度买单**。
4. 动手前确认这件事属于 §7（可做）还是 §8（**只有用户能拍板，不许替他定**）

---

## 1. 🚨 当前唯一硬阻塞：GitHub Actions 被账号计费锁

**状态（2026-11-07 11:04 UTC 实查）：仍然锁着。**

自 **2026-11-05 20:23 UTC** 起，仓库自定义的所有工作流 100% 失败。
job 在**创建阶段**就被拒：3~6 秒、**0 个步骤**、没分配到 runner。

错误原文（从公开 API 的 **check-run annotations** 端点读到）：

```
The job was not started because your account is locked due to a billing issue.
```

### 怎么自己查到这条（以后 CI 红一律先走这步）

公开仓库**不需要 token** 就能读到 job 的失败原文 —— 这是本仓库 2026-11-06 才学会的，
之前只看 run/job 两层，漏了 annotation 层，白绕了一大圈：

```bash
# ① 列最近运行，定位失败的 commit
curl -s "https://api.github.com/repos/Vambrocop/valpha-lab/actions/runs?per_page=10"

# ② 用那个 commit 列 check-runs，拿 annotations_url
curl -s "https://api.github.com/repos/Vambrocop/valpha-lab/commits/<SHA>/check-runs"

# ③ 读 annotations —— job 的真实报错在这里
curl -s "https://api.github.com/repos/Vambrocop/valpha-lab/check-runs/<CHECK_ID>/annotations"
```

> Windows 上 curl 输出直接进管道会被编码弄坏 → **先 `-o` 落盘再用 py 解析**。

### 已排除的假设（都有证据，别重复排查）

| 假设 | 否掉它的证据 |
|---|---|
| 有欠款/逾期 | 账单页：gross $0.97、included 折扣 $0.97、**净额 0**、无付款历史、无 next payment due |
| 仓库 private → 分钟数用尽 | API 实查：名下 **7 个仓库全 public** → 公开仓 Actions 无限免费 |
| GitHub 官方事故 | 11-05 16:50–17:42 确有 Actions 事故，但**失败发生在它修复之后**；状态页现全绿 |
| 工作流配置坏了 | YAML 能解析（否则是 `startup_failure` 不是 `failure`）；**GitHub 内置 `pages build and deployment` 在同一提交上成功** |
| GitHub Education 会解开 | **实测否**：办了 Education 之后用 push 当探针，`Site audit` 仍 4 秒失败、原文一字未变。Student Pack 是「往后免费」，不解除已存在的账号锁 |

### 还剩什么没验（需要用户登录，Codex 做不到）

1. 账单页产品选择器里逐个点 **Actions / Codespaces / Models / Git LFS / Packages**
   —— 那 $0.97 出自哪个产品、它的赠送额度是否已满
2. https://github.com/settings/billing/payment_information —— **有没有绑任何付款方式**
3. 同页 **Budgets and alerts** —— 有没有一个 $0 预算已触顶
4. 三处都正常 → 开工单 https://support.github.com/，附原文 +
   `https://github.com/Vambrocop/valpha-lab/actions/runs/42126790759`

### 这把锁对你的影响（重要）

- ❌ **任何流水线/工作流改动都无法验证** → §7 里 action 版本升级一类任务**必须等解锁**
- ✅ **数据照常每天刷新** —— 2026-11-07 起由**本机计划任务**接管发布，见 §6.3。
  ~~数据不会自动刷新~~
- ✅ **Pages 部署不受影响**（GitHub 内置，不走 Actions 配额）→ 本地跑完推 `docs/` 就能上线
- ✅ `git push` / `git fetch` 正常
- ✅ 解锁后 6 个工作流**都有 `workflow_dispatch` 手动按钮**，可立刻补刷，不用等定时

### 解锁之后要做的收尾（别忘）

1. 点一次 `Refresh market data` → `Run workflow` 补刷
2. **停用本机计划任务**，避免两个发布者打架（本机有锁但管不住 CI）：
   `schtasks /change /tn "ValphaDailyPublish" /disable`
3. 要不要恢复旧的 `ValphaWeeklyRefresh`（它只补 SEC 两源、刻意不推送）：
   `schtasks /change /tn "ValphaWeeklyRefresh" /enable`
   —— 恢复它是合理的，因为 **SEC 封 CI 机房 IP 这件事解锁也不会变**（§6.4）
4. 做 §7 🔴 里那批 action 版本升级（单独一次提交 + CI 实测）

---

## 2. 这个项目是什么

**Valpha Lab** —— 面向**澳洲阿德莱德**（UTC+9:30）一位**投资新手**的中文「诚实统计」股票仪表盘。
用户是**澳洲税务居民**，持有**美股 + 澳股**。网站有**中国境内访客**。
线上：https://vambrocop.github.io/valpha-lab/

规模（2026-11-07 实查）：**111 个脚本 · 106 个测试文件（1142 条测试）· 42 个页面 ·
70 个公开产物 JSON · 15 个 tools · 74 个 CSV 账本**。

### 差异化命门：诚实计分，不是又一个吹票机

早期「不预测 / 不荐股 / 不深度学习」已被用户 2026-06-22 明确解除 —— 那是起步纪律不是永久红线。
**现在要守的不是「不预测」，而是「敢预测就敢认账」**：每个方向判断都留 append-only 的公开战绩。

→ **别再拿「不预测 / 不荐股 / 不深度学习」去拦用户的升级请求**（这是反复犯过的错）。

实例（这就是护城河长什么样，`docs/paper.json`，2026-06-10 起跑各 $10,000）：

| 策略 | 净值 | 收益 | 交易数 |
|---|---|---|---|
| overnight | 10,111 | **+1.11%** | 0 |
| buyhold | 9,660 | −3.40% | 1 |
| trend | 9,660 | −3.40% | 2 |
| signal（🎯本站信号） | 9,219 | **−7.82%** | 1 |
| momentum | 6,151 | **−38.49%** | 4 |

本站自己的信号策略在公开计分里**输给买入持有**，而且照样挂在首页。
**这种事不许粉饰、不许删行、不许改口径让它好看。**

### 自动发现当前状态（`docs/autodiscovery.json`，2026-11-05）

148 条预声明候选，跨族 BY-FDR（q=0.10）裁决：
**survive 7 · faded 7 · inconclusive 5 · dead 129**

存活 7 条：`BTC_mom20_neg` · `BTC_mom20_pos` ·
`legacy_noncomm_pct_oi_lo_h60_nasdaq100` · `monthof_9_sp500` · `p5_h1_nasdaq` ·
`september_sp500` · `world_cup_year_nasdaq`

---

## 3. 运行环境与命令速查（Windows）

```powershell
# ⚠ 用 py，不要用 python（python 指向 Microsoft Store 占位程序）
# ⚠ 跑任何脚本前设 UTF-8，否则 GBK 控制台会让 Unicode 输出崩溃
$env:PYTHONUTF8='1'

py market-analysis/scripts/run_all.py            # 全量流水线（本机实测 ~15 分钟，不是 CLAUDE.md 写的 3 分钟）
py market-analysis/scripts/run_all.py --light     # 盘中轻量
py -m pytest market-analysis/tests -q             # 1142 条，~102s；必须全绿才能提交
py market-analysis/scripts/verify_output.py       # 发布前自检（run_all 第 126 步已含，失败即终止）

py tools/audit_frontend.py                        # 前端改动后：交叉检查 ID/onclick
py tools/interaction_audit.py [--mobile]          # 交互实测（桌面和移动端都要跑）
py tools/csp_audit.py [--mobile]                  # 改 CSP/引新资源后：真浏览器收违规
py tools/ledger_gap_audit.py                      # 怀疑账本丢过数据时（以 git 历史为参照）

# ⭐ CI 被锁期间的发布入口（见 §6.3）—— 它自己跑完整序列 + 全部门禁 + 提交推送
py tools/local_publish.py --dry-run               # 跑全部门禁，不提交不推送（先用这个）
py tools/local_publish.py                         # 门全过则提交 + 推送
```

环境变量（**绝不进仓库/日志/记忆**）：
`GEMINI_API_KEY`（LLM 日读/月读/预测，已配）· `SEC_UA_CONTACT`（SEC 要求 UA 带真实邮箱，已配）·
`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`（本机**未配** → 推送步静默跳过，不影响产物）·
`FRED_API_KEY`（未配，走兜底）

**后台长任务的坑**：Python stdout 进管道会被缓冲 → 几分钟内输出文件是 0 字节。
别以为卡住了，**看产物文件的 mtime 判进度**（`ls -lt market-analysis/web/*.json | head`）。

---

## 4. 架构：五阶段 DAG

`run_all.py` 的 docstring 里有权威版本（**接手先读它**）。骨架：

```
A 取数      fetch_data → long_history → fetch_data_au → fetch_insider/fetch_ipo（SEC）
B 独立统计  placebo / seasonality / event_causal / overreaction / conformal / cycles …
C 信号主链  horizon_stats → build_signals → backtest → walk_forward → factor_pruning
            → fdr_crossfamily → candidate_registry → autodiscovery
D 展示/出格 flicker → survivors_live → LLM 日读/月读/预测 → outlook / composite_read
            → tipjar / ipo_enrich → ipo_alerts → ipo_aftermath
E 封存门禁  ledger_sidecar（74 账本哈希链）→ verify_output（不绿不发布）→ web/→docs/ 镜像
```

### 顺序是语义的，不是摆设

踩过的实例：`survivors_live` 原本排在 `knowledge_base` **之前** → 「读 oos 产物问门本身」
读到的是**上一轮**数据。`flicker` 2026-09-06 被前移，因为 `survivors_live` 要读它。
**改顺序 = [判断]，要审。**

### 单一真相源规则

- **凡引产物数字，一律读 `docs/`，绝不读 `data/processed/`**
  （曾经读了 `data/processed/autodiscovery.json`，那是 **41 天前的快照**，整段结论写错）
- `web/` 改动必须镜像到 `docs/`（`run_all` 末步自动做；**手改记得 `Copy-Item`**）
- `data/raw/` **在 .gitignore 里** —— 见 §5.B

---

## 5. 🧨 地雷册（本手册最有价值的部分）

每条都是本仓库**真实付过代价**的坑。按失败模式归类，因为**同一个模式换个地方会再咬一次** ——
下面有三条就是同一家族的第二、第三次现形。

### A. git 浅克隆 / 无父提交家族 —— 咬了 3 次

**机制**：`actions/checkout@v4` 默认 `fetch-depth: 1` → 仓库只有一个提交、**没有父提交**
→ git 把它当成「引入了整棵树」→ 任何按路径问历史的命令都返回**那个 tip 提交**。

1. **`fe8af0a`（2026-09-04）**：守门测试用 `git show --name-only` 列改动文件，
   浅克隆下列出**整个仓库 556 个文件** → 把刷新干红两天。
   更坏的是它**只在 HEAD 恰好是 bot 提交时**触发，手动 dispatch 时 HEAD 是自己的提交 → 跳过 → **假绿**。
   > **教训：「我手动跑了一次 CI 是绿的」不等于验证过，还得问 HEAD 是什么形状。**
2. **`ffacdea`→2026-10-09**：`_pool_curation_age` 用 `git log -1 --format=%cs -- valpha150.csv`
   算「池子多久没人维护」。浅克隆下它**恒等于 tip 日期** → 页面上那句
   「距上次人工维护 N 天」每天都显示 0~1 天、`>60 天` 红字警告**永远不可能触发**。
   这个指标的全部目的就是让悄悄老化看得见，结果它反过来一直在给人安心。**建成起就在撒谎。**
3. **2026-11-06（第三次）**：修法只拦了 `is-shallow-repository == true`。
   而提交门禁的干净检出是 `git archive` + `git init` + 单提交 → `is-shallow = false` → 绕过守卫，
   `git log -1 -- <path>` 照样返回 tip 日期。
   > **「浅克隆」只是病因之一，病根是「没有父提交」。** 现已改为按
   > `git rev-list --count HEAD < 2` 判，两种形状都拦。

**→ 以后凡是按路径问 git 历史，先问：这个仓库有父提交吗？**

### B. 门禁测试依赖 gitignore 产生的数据 —— 咬了 2 次

`data/raw/` 在 `.gitignore` 里 → **CI 的干净检出里是 0 个文件**。
测试若偷偷读它，本地绿、CI 红。

- **#100–104 连挂根因**（`autodiscovery.py:862` 有明文警告）
- **2026-10-12 我又犯一次**：两条 F2 测试直接调 `ad._regime(...)` / `ad._factor_map(...)`，
  那要读 `data/raw/` → arrays 为 None → 断言失败 → 把周一刷新**连干红两次**。
  两处明文警告（代码注释 + memory）我都没照。
  > **我跑了三遍全量 pytest 都是绿的，因为本机有 `data/raw`。
  > 「本地全绿」对门禁测试完全不构成证据。**

**规矩**：门禁测试不依赖 gitignore 数据。确需真数据 → 缺数据时 `pytest.skip`，
且**同一性质必须另有合成数据版恒跑**
（样例：`test_arrays_exclude_days_without_realized_forward_window`）。

### C. 写入时冻结的健康标志 —— 咬了 2 次

- **`3f6285e`（2026-09-16）**：`^VIX3M` 的 `yf.download` 返回空 → 落到 `Ticker.history("3mo")` 兜底，
  而**该兜底立刻写缓存**，把 6717 行覆盖成 **1 行**。`_record_health` 只查 `rows==0` 和日期新鲜度
  → 写出 `{"rows":1,"status":"ok"}`、前端显示绿字「新鲜 ✓」。
- **2026-11-05（CI 被锁）**：`data_health.json` 的 `summary.freshness` 是**写产物那一刻**算的，
  之后冻住。CI 停了 21 小时，它还一直说 `ok / stale:0`。
  同时 `staleness_watchdog` **跑在它要监控的东西里面**（由 `run_all` 调用、也就是在 CI 里）
  → CI 一红它根本不执行 → 「CI 挂了」它**结构上报不出来**。

**→ 「生成时的状态」不等于「现在的状态」。** 2026-11-06 的修法是把判断挪进**浏览器**
（CI 全挂时唯一还活着的层）：`app-1.js` 的 `vpEtParts` / `vpTradingDaysBehind` / `vpCiStaleDays`，
按**交易日**而非小时判（实测本仓库定时任务常规晚到 3~5 小时，按小时必然天天误报）。

### D. 「低于估计器下限」≠「极显著」—— 咬了 3 次

1. **F1（2026-09-16）**：`p=0.0000` 不是极显著，是**低于估计器能报的最小值**。
   X=0/B=2000 的双侧 95% 上界 ≈0.003，与一条 0.0030 的 dead **统计上分不开**。
2. **`calibrated_p` 的分位原子（2026-10-09）**：`p_obs` 恰好落在分位值上且该值有质量时，
   返回的是**下界**（实测低估 80 倍；表里 12/16 行是会踩中的形状）。
   而**我的测试把这个 bug 钉成了正确行为**，还会挡住修复。
3. **null 侧 B=300（2026-10-09）**：p 格点下限 0.0066，而生产对那条候选用的是加算后的
   B=20000（下限 0.0001）、recent_p=0.0007 → 16 行的 `null_p_min` 全都恰好 =0.0066，**尾巴被截断**。
   拿它判 0.0007，「比所有 null 都极端」其实只是「我的刻度不够密」。

**→ 看到 p=0 或「比所有重采样都极端」，先问：估计器的分辨率下限是多少？**

### E. 块自助的两个结构性问题

1. **`block >= n` 时估计器彻底失效**：`n_blocks=1`，重采样索引退化成**整条序列的循环平移**，
   而 `sel` 与 `y` 共用同一 idx → **每次重采样原样复现观测统计量** → 方差为 0
   → p 恒等于估计器下限。**纯噪声实测拒真率 100%。**
   已装 `walk_forward.MIN_BLOCKS = 10`，块数不足返回 `None` 不给 p（提交 98cb02e5）。
   > 这颗雷**早就武装好了**（oos_gate 的 positioning/trailing 对上 `MIN_OOS_N` 只有 1~2 块），
   > 只是 148 条全 PENDING 还没踩上 —— 同 `fe8af0a` 的教训：没炸不等于没装好。
2. **整套块自助的实际水平是 0.12–0.19，不是名义的 0.10**（旋转 null 逐候选实测，
   `tools/block_calibration.py --real`，跨六族）。**即「q=0.10 的存活线」实际更接近 0.15。**
   `trailing_extreme` 族中位 **.185** 最差（原因是 hold=63/126 的重叠窗口，不是块长）。
   → **登记在册，未动**；动它会改两族已发布口径，必须单独提交 + 独立审。

### F. 撤销结论要和建立结论一样谨慎

**`a2872a3`**：用户质疑「是不是矫枉过正」→ 实测证实我上一版**过头了**。
块必须取在**日历序列**上（mask 随之重采样），此前取在「某档观测子集」的散落数组上
→ 系统性保守 **1.8–2.8 倍**，错撤了 SP500 Tier≥4（p .209→.017）等本该显著的结论。

同一教训在「撤」的方向上也生效过：`BTC_mom20_pos` 的实测水平 .2175 超标，
只看水平就该撤它。**但在 α=0.10 处量的数字不能用来否定一个 p=0.0007 的结论**
——跨族 BY 的临界值 `c_1..c_14` = 0.000121~0.001696，根本不在 0.10 附近。补算 null 下尾后保留。

### G. 账本：什么叫「结算」，什么叫「改历史」

`prediction_log.csv` / `paper_ledger.csv` / `autodiscovery_log.csv` / `candidate_registry` /
`kb_ledger` / `ledger_hashchain` 是 **append-only，绝不改历史行**。

但**前向结算是设计内行为**，不是违规。分界：

| 合法 | 违规 |
|---|---|
| 追加新行 | 删除/替换已有行的键 |
| **空**单元格 → 填上值（`ret_5d` / `ret_20d` / `exit_px`） | **非空**单元格的值被改成别的 |
| `settled: False → True`（随 entry/exit 回填一起翻转） | 任何让历史结论变好看的改动 |
| `prev_hash`/`row_hash` 重算（上游行一变必然重算） | — |

验证脚本的写法（2026-11-06 用过，推荐复用）：按键列把 `git show HEAD:<path>` 与工作树
逐单元格比对，分类「新增行 / 空→有值 / **非空→被改**」，第三类逐条人眼看。
注意**别把 `settled` 这种状态位误判成违规**——我第一版就标错了。

> 另有一类现有防线抓不住的：`autodiscovery_log` 曾被 bot 提交删掉 2026-07-06(104行) 与
> 07-11(148行)，**2 个月没人发现**。门比的是工作树 vs origin（坏版本推上去后两边都缺）、
> 哈希链的 `n_rows` 在「删 N 加 N」时净额不变。→ 怀疑时跑 `tools/ledger_gap_audit.py`
> （以 **git 历史**为参照查「曾经出现过的日期现在没了」）。

### H. 测试里写死日期 = 定时炸弹（2026-11-06）

`test_full_clone_reports_the_real_curation_date` 写死 `_pool_curation_age("2026-10-09")`
再断言 `age >= 0`。而 `age = day − last`，被测文件之后又被改过 → `last` 跑到参照日之后
→ age 变负。**10-09 当天 age 恰为 0 侥幸通过，之后每天都更负。**

**→ 测试里的「今天」用 `datetime.date.today()`，不要写死写测试那天。**

### I. 逻辑只存在于 workflow YAML 里 → 本地跑不了 → 只能推上去看红 —— 咬了 2 次

1. **2026-07-24~27**：commit/push 逻辑写在 `refresh-data.yml` 的 `run:` 块里。
   主流水线**连红四天**、全站数据滞留，因为改一次就得推一次等一轮 CI。
   → 抽成 `tools/ci_publish.py`，用**真 git 裸仓**测「无改动 / 正常推 / 推冲突→rebase 重试 /
   门告警」四条路径，**先在本地红**。`OPTIMIZATION_LOG §4c` 第一条就是这个教训。
2. **2026-11-07（我又栽一次）**：`run_all` 之后还有 **7 个脚本**
   （`build_valpha150` / `build_wildpool` / `ticker_ondemand` / `build_ndx` /
   `fetch_earnings` / `fetch_cot` / `fetch_putcall`）+ `check_strict_json` 这道独立的门，
   **也只写在 YAML 里**。我 2026-11-06 手动补数据时只跑了 `run_all`，**这 7 个产物全漏了**
   —— `ndx` 当天恰好被另一个计划任务补上，**纯属巧合**。
   → 抽成 `tools/local_publish.py`，并加守门测试对着 `refresh-data.yml` 核清单，防两处漂移。

**→ 凡是「这段只在 CI 里跑」的逻辑，都是下一次 4 天停更的候选。** 搬进 Python。

### J. 其它单发坑（都已修，别重复踩）

- **`_sign(nan)` 静默返回 −1**（`1361f3c`）：`abs(nan)<1e-12` 与 `nan>0` 都为 False → 落 −1，
  等于给空/退化观测窗**编出一个「看跌」方向号**，还会进公开 JSON 被当既定假说方向判
  confirmed/overturned。旧测试只测了 `None→0`。
- **暖机 NaN 被算进对照组**（F3）：基率被压低、因子边际被系统性夸大。
- **AI 战绩牌基线写错**（`42b4c1c`）：原写「三桶随机基线 1/3」—— 三桶**不等概**（中性 61.5%），
  正确门槛是**多数类基线**。按它比，59.0% 其实**不如**「每天闭眼说中性」（p=0.692）。
- **测表不测行为 —— 咬了 2 次**：
  ① **禁词扫描当守门是假的**（F1 ④）：D9「绝不取两次里更显著的」原本靠禁词扫描，
     审查造的 4 种违规写法**全绿过**（含 `min(r["p"], …)`，禁词表只拦变量恰好叫 p/p1/p2 的）。
     → 改成抽纯函数做**行为测试**，4/4 抓到。
  ② **2026-11-07 我又犯一次**：`local_publish` 要用 `valpha-local-publisher` 身份提交
     （本地发布不是 Actions 跑的，署名成 `github-actions[bot]` 等于让 git 历史撒谎）。
     我的测试只断言「两个常量不相等」→ 绿；而真实提交 `c77b6a90` 的作者**就是**
     `github-actions[bot]`。根因：`ci_publish.publish()` 内部会再 `configure_bot(cwd)`
     一次，把调用前设的身份原样覆盖回默认值。
     → 修法：身份改为 `publish()` 的参数（默认不变 → CI 零影响）；测试换成**真 git
     裸仓 + 真 clone + 真提交**、断言 commit 对象上的 `%an`/`%ae`。
     变异验证：修好后 GREEN，变异回旧行为 **RED(作者=github-actions[bot])**。
     ⚠ `c77b6a90` 已推送，**不改历史**，如实记在这里。
  **→ 守门测试要测行为，不要测常量/字符串。** 尤其警惕「调用前设置了，但被调用方又设一次」。
- **诚实守门测试别断言裸禁词「不存在」**：免责句本身会引用禁词（「绝不回测」/「not a sell signal」）
  → 守 enum 名 + 肯定式短语。
- **并列 bug 我判错过并已收回**：曾怀疑 `bh_reject` 按 rank 下标拒绝会导致「同 p 不同裁决」。
  回放 62 个交易日 × 13 个池：咬到 **0 次**，且**数学上不可能**（BY 临界值 `c_i` 递增，
  并列组内若某 i 满足则所有 j>i 也满足 → k 必覆盖整组）。
  **那段代码是对的，别照我的错判去「修」。**

---

## 6. 发布与门禁

### 6.1 提交会被机器拦（这是好事）

`tools/pre_commit_gate.py` 是 **PreToolUse(Bash) 钩子**，不是 git hook。
它把**索引树** `git archive` 到临时目录、`git init` 复刻 CI 的单提交形状、再跑 pytest。
**树内绿而门禁红 = §5.B 那类问题，提交那一刻就被拦。**

- **门禁 deny 了 → 修根因**，不绕、不改工作流顺序迁就坏测试、`--no-verify` 禁用
- 干净检出会 `pytest.skip` 掉需要真数据的测试，所以**两边数字本来就不同**：
  本机 1142 passed / 干净检出 1134 passed + 9 skipped。**都要绿。**

手动复现干净检出（Windows 上 `tar` 会把 `C:` 当远程主机 → 用 Python 的 `tarfile`）：

```python
import os, shutil, subprocess, tarfile
TMP = r"<临时目录>"
shutil.rmtree(TMP, ignore_errors=True); os.makedirs(TMP)
tree = subprocess.run(["git","write-tree"],capture_output=True,text=True).stdout.strip()
with open(os.path.join(TMP,"_t.tar"),"wb") as f:
    subprocess.run(["git","archive",tree],stdout=f,check=True)
with tarfile.open(os.path.join(TMP,"_t.tar")) as tf: tf.extractall(TMP, filter="data")
for cmd in (["git","init","--quiet"],["git","add","-A"],
            ["git","-c","user.name=ci","-c","user.email=ci@x","commit","--quiet","-m","ci"]):
    subprocess.run(cmd, cwd=TMP, capture_output=True)
# 然后 cd TMP && py -m pytest market-analysis/tests -q
```

### 6.2 正常发布

改流水线 → **提交前全量跑通 + pytest 全绿**。
改模型 → bump `MODEL_VERSION` + 重跑 `walk_forward` + **新旧指标对比写进 commit message**。
改公开统计口径 → **[判断] + 双审 + 新旧对比 + 用户知情**。
push 前先 `git fetch`（CI 正常时每 2 小时自动提交数据）。

### 6.3 ⭐ 本地自动发布（`tools/local_publish.py` + 每日计划任务，2026-11-07 起）

> 历史上 `CLAUDE.md` 有一条「⚠ 本机 VIX3M 历史已丢 → **别把本地产物提交/发布**」。
> **该条 2026-11-06 已撤销** —— 历史后来被某次全量取数拉回来了（VIX3M 现 5110 行 / 2006-07-17 起，
> 20.3y × 252 ≈ 5116 = 完整；行数比 VIX 的 6752 少只是因为 Yahoo 的 ^VIX3M 起始更晚，不是截断）。
> 但**不是无条件放行** —— 门禁见下。

**一条命令就够**（人工时先 `--dry-run` 看一遍）：

```
py tools/local_publish.py --dry-run     # 跑全部门禁，不提交不推送
py tools/local_publish.py               # 门全过则提交 + 推送
```

**每天自动跑**：Windows 计划任务 `ValphaDailyPublish`，每日 10:00 阿德莱德
（美股 16:00 ET 收盘 = 21:00 UTC = 阿德莱德次日约 07:30 → 10:00 跑，前一个美股交易日已定稿）。
外壳是 `tools/local_publish.ps1`（ASCII-only：PS 5.1 无 BOM 时按 GBK 读 .ps1）。
出问题会在**桌面**放一个 `Valpha - PUBLISH NEEDS YOU.txt` + toast；
**桌面上没有那个文件就说明一切正常。**

```
schtasks /query  /tn "ValphaDailyPublish" /v /fo LIST   # 看状态
schtasks /change /tn "ValphaDailyPublish" /disable      # 停（Actions 解锁后要做）
schtasks /delete /tn "ValphaDailyPublish" /f            # 删
```

> 旧的 `ValphaWeeklyRefresh`（7-31 建、Mon/Tue/Fri、只补 SEC 两源、**刻意不提交不推送**）
> 已 **Disabled**。原因：它的步骤是新任务的严格子集（`run_all` 含 fetch_insider +
> insider_signal + ledger_sidecar，`build_ndx` 在 `POST_GATE_SCRIPTS` 里），
> 而且**它没有互斥锁** —— 2026-11-06 它在 10:00:30 跑 `build_ndx`，
> 而我的手动 `run_all` 正在 09:48–10:02 跑，**两个 writer 同时写产物**。

#### 门禁顺序（fail-closed；退出码 0=发布/无事，1=门拦下，2=拒绝启动）

```
门0  工作树只许有「数据产物」改动（口径 = ci_publish.DEFAULT_PATHS），否则 exit 2
      ⚠ tools/pre_commit_gate.py 是 Claude Code 的 PreToolUse 钩子、不是 git hook
        → 计划任务直接调 git commit 不会触发它。所以本脚本自己跑 pytest，
          且拒绝在有代码改动时运行（代码改动才是干净检出门真正要抓的东西）。
      · 未跟踪文件（??）不拦 —— 它们进不了显式暂存。
        （现状：docs_internal/SPEC_FACTOR_OOS.md 长期未跟踪，不该每天把发布拦下来）
取基线  HEAD:docs/autodiscovery.json —— **必须在跑流水线之前**取
门1  不落后 origin（别和别的 writer 打架）
     run_all.py（verify_output 在其第 126 步，失败即终止）
     7 个门后脚本：build_valpha150 / build_wildpool / ticker_ondemand / build_ndx /
       fetch_earnings / fetch_cot / fetch_putcall —— 逐个 fail-soft（照 CI 的 || warning）
门2  check_strict_json（硬门：这 5 个产物不过 verify_output；NaN/Infinity 会让
       浏览器 JSON.parse 整份拒绝 → 前端白屏）
门3  data_health：ok == total 且 shrunk == 0（读不到也拦 —— 「读不到就当过」
       又是一个写入时冻结的 ok，见 §5.C）
门4a 候选池逐族**未缩**（硬门；只拦变少，扩容是正常演进不拦）
门4b 哨兵 vix_backwardation 在 factor 族内（硬门；verdict 无所谓，在不在才关键）
 ※   存活名单 diff —— **报告，不是门**（理由见下）
门5  pytest 全量（硬门）
发布 ci_publish.publish() + ci_ledger_guard（warn-only）→ Pages 自动部署
```

#### ⚠ 为什么「存活名单变了」刻意不拦

必须区分两件根本不同的事：

| | signature | 处置 |
|---|---|---|
| **本地环境塌缩** | 候选池某族成员变少 / 哨兵因子整条消失 | **硬门，拦住不发** |
| **真实统计更新** | 候选池一模一样，只有 verdict 在动 | **只报不拦** |

存活名单本来就该随数据变动 —— 那是整个自动发现系统的目的。
拦住它等于「冻结我们喜欢的结论」，正是本项目反复要防的那种不诚实
（`a2872a3` 的教训在「撤」的方向上也生效过，见 §5.F）。
`test_survivor_list_is_deliberately_NOT_a_gate` 用源码反射钉住这条，**并做了变异验证**
（真实源码 GREEN；两种把它变成门的变异都 RED；删掉调用报「前提没了」）。

#### 它不替代什么

- **不替代人工判断**：门全过只说明「没有本地数据塌缩」，不说明结论对。
  存活名单真变了，日志会大声写出来，**该有人去看**。
- **不替代干净检出门禁**：代码改动一律走人工流程（门0 会拒绝介入）。
- **账本逐单元格验「非空→被改」=0**（§5.G）目前仍是**人工动作**，没进自动门
  —— `ci_ledger_guard` 是 warn-only 的防缩水门，口径不同。改动账本逻辑后要手动验一次。

#### ⚠ 三个已知缺口（相对 CI，如实列出，别以为本地等价）

| 缺口 | 原因 | 现状/怎么补 |
|---|---|---|
| **`earnings.json` 不刷新** | `fetch_earnings.py` 要 `FINNHUB_API_KEY`，CI 里是 Secret，**本机未配** → 打印「未配置，跳过」后 exit 0（设计内 fail-soft） | 实测停在 2026-11-05。本机设一次即可补上：`setx FINNHUB_API_KEY "<key>"`（用户 GitHub Secrets 里有），**绝不写进仓库** |
| **信号告警不发** | `alert_check.py` 要 Telegram token（推送）+ `GH_TOKEN`（建 Issue 发邮件）+ `HOLDINGS`（持仓感知），本机都没有 | **刻意未纳入本地序列** —— 没 token 它做不出任何可发布的东西。解锁后由 CI 恢复 |
| **浏览器审计没人跑** | `tools/site_audit.py --ci` / `--mobile` 此前每次全量 CI 刷新都跑，现在 `site-audit.yml` 也被锁 → **跑在哪儿都没有** | **刻意未纳入自动路径**，理由见下 |

**为什么不把 `site_audit` 塞进每日自动发布**（这是个取舍，不是遗漏）：

- 它防的是**前端改动**引入的布局溢出 / 控制台报错。而**门0 保证自动发布时代码零改动**
  → 前端与 CI 最后一次审过的完全一致，只有 JSON 数据在变。
- 数据能弄坏渲染的主要途径是 NaN/Infinity 让 `JSON.parse` 整份拒绝 → 白屏，
  **那条已由 `check_strict_json` 硬门覆盖**。
- 反过来，把一个真浏览器审计设成硬门，意味着**本机的一次浏览器抖动会拦住唯一的数据发布者**
  —— 代价大于它在「代码零改动」前提下还能多防的那一点。
- 而设成 warn-only 则是**悄悄削弱一道 CI 有的门**，这比不加更糟。

**→ 规矩不变**：任何前端改动后手动跑
`py tools/interaction_audit.py [--mobile]` + `py tools/site_audit.py`（CLAUDE.md 本来就这么要求）。
解锁后 `site-audit.yml` 自动恢复覆盖。

### 6.4 SEC 两个源只能本地补（known-limited，不是 bug）

SEC 封 GitHub Actions 数据中心 IP（住宅 IP 能抓、CI 不能）。
**定案：accept + 诚实标注 + 本地兜底，不花钱不绕封锁**
（proxy 对一个诚实统计站是「规避 SEC 公平访问」的气味问题）。

→ **本地跑 `run_all` 时 `fetch_insider` / `fetch_ipo` 自动补齐**，所以隔 2~3 周本地跑一次即 top-up。
CI 那两步保留（fail-soft 无害），**别指望 CI 修好它**。前端标注读真时间戳、不承诺固定周期。

**这两个产物是滚动窗口不是累积**（`lookback_days` = 5 / 30），所以本地跑完
**变小是正常的**，不要当缩水去「修」：`insider.json` 的 `n_buys` 历史是震荡的
（60→27→35→83→70→49→128→59→214），19 个月的历史在 `insider_signal_log.csv` 那个
append-only 账本里。`ipo_filings.json` 的 `curated_asof`/`n_major` 由 `ipo_enrich`（第 115 步）
**跑完后回填** —— 中途看到 None 只是没跑到。

### 6.5 `senate` 是故意静止的，别去「修」

`senate_signal.json` 的时间戳停在 2026-06-22（4.5 个月），且**不在 `run_all` 也不在 watchdog**。
**这是设计**：`fetch_senate.py` 写明上游免费源（senate-stock-watcher）**2019-12 就停更**、
本地 csv 止于 2020-11，本族是**完结的历史研究（2012–2020）**，
「再抓也是同一份死数据，每日重抓是假逻辑」。
`senate.html` 从 JSON 动态读 `d.caveat`（「数据停 2020-11(历史非实时)」）+ `d.data_range`
—— 页面是诚实的。要做**实时**政治钱信号需换活源（多为付费）= 新立项。

---

## 7. 任务队列（状态 2026-11-07 实查，不是抄旧文档）

### 🔴 等 Actions 解锁才能做（现在动 = 盲推）

- **action 版本升级**：`actions/checkout@v4 → v7.0.1` · `setup-python@v5 → v7.1.0` ·
  `upload-artifact@v4 → v7.0.2`（GitHub 已警告它被强拉到 Node 24）· `cache@v4 → v6.1.0`。
  另：**`ubuntu-latest` 自 2026-10-19 起迁移 Ubuntu 26**，是前向风险。
  → **不许在锁着的时候推**：解锁后第一次跑若失败就得同时 debug 两件事。
- **`requirements-core.lock` 从未生成**：`lock.yml` 仅手动触发、且**必须在 Linux 上解析**
  （本地 Windows 的 `pip freeze` 会混进 pywin32 等，喂给 ubuntu 装不上）。

### 🟡 可以直接做

- **F2 BLOCKER 1 的真修**（**需单独提交 + 独立审 + 用户拍板**，见 §8）：
  按 `c_i` 分级算 null 尾巴、`cal_p` 带分辨率下限
  （`0/R` 且 `1/R > c_i` 时诚实答案是「可达精度内无法确认」）。
  ⚠ 测算指向 `BTC_mom20_pos` 的全段窗口**通不过 `c_14`** → **会动公开存活名单**。
- **`trailing_extreme` 族水平 .185**（全系统最差，已有 H-3 放大仍如此；
  成因是 hold=63/126 的重叠窗口，不是块长）→ 单独提交 + 审，会改两族已发布数字。
- **统计口径两条**（优先级低，当前偏保守、错的方向是「更严」）：
  ① 「主导组一致」用 `argmax`，而 SSB 显著可能由**低**离群组驱动 → 可改「最大 |偏离| 组」；
  ② 近期窗硬编码 5 年（`365*5`），**月份效应因此现代段恒不可测**。
- **`interaction_audit.PAGES` 不含 `ndx.html`**（还有 17 个页面也不在）→ 要不要加由用户定（运行时成本）。

### 🟢 已完成（别再当待办 —— 实查过）

- **T1 `_regime_arrays` 尾窗 bug**（`995a051`+`1cb6734`）：全 104 池零 verdict 翻转，Opus 独立审零 blocker
- **T2 `legacy_noncomm` 观察台描述符** ✅ **已接入**：实查 `survivors_live.json` 现有真状态文案
  （「最新可用 COT 口径…投机仓位在 3 年里 96 分位，未到 ≤10 分位档」），不再是中性兜底
- **T3 app-4.js 全量双语** · 主盘 `app-1..5.js` 已有 **1181 处 `vpL(zh,en)`**（2026-11-07 实查）
- **T6 IPO 自动事实层**（`fetch_ipo` 早在 run_all；策展明星层硬编码在 `ipo.html`，**本质不可自动化**，留人工）
- **F1 全部落地**（2026-09-18）：只换种子时平均改判 **4.55 → 0.69**、名单原样复现 **6.7% → 79.4%**
- **F2 P1 放大 + P2 披露**（2026-10-08/09）：regime +661 / factor +144 / rebound +2
- **CI 监控盲区**（`6398d56f`）：客户端按交易日判数据陈旧（见 §5.C）
- **本地补数据发布规程 + VIX3M 警告撤销**（`bfa2cf98`，见 §6.3）
- **本地自动发布链**（`97cff1f8`，2026-11-07）：`tools/local_publish.py` 把此前**只存在于
  `refresh-data.yml` YAML 里、本地跑不了**的完整序列搬进 Python（run_all + 7 个门后脚本 +
  check_strict_json），加 fail-closed 门禁 + 互斥锁；计划任务 `ValphaDailyPublish` 每日跑。
  30 条全合成测试，含「存活名单刻意不是门」的源码反射守门（已变异验证）
- **CSP 真浏览器实测**（`5cc643e`）：42 页零自伤
- **fail-soft 产物监控**：watchdog CHECKS **20 项**，且规则已自动化
  （`sys.exit(0)` 的脚本若 `write_json` 了产物，该产物必须在 CHECKS 里，否则测试红）

### ⏳ 时间门 —— **但「等什么」必须说准**

> 这个区分很要紧，`CLAUDE.md` 曾把两种处境混成一句「只能等」：
> **触发组不足 = 攒时间就行、一定会到；对照组不足 = 光等不一定来。**

- **KB 晋升**：队列 14 条，**全部 `oos_n = 0`**，卡的是「锚后样本不足（<1000 日）」。
  历史上 `golden_cross_sp500` 曾 `oos_n=33` 过了门槛 30 却仍 pending ——
  当时卡的是**缺对照组**（锚点后标普金叉一天都没断过，`n_ctrl=0`，没有「不成立」的日子可比）。
- **LLM 方向判断力**：`llm_prediction_log.csv` 91 行、已结算 84，但**押方向的只有 5 条**
  （其余 86 条全是「中性」）。**等的是方向样本，攒到的是中性样本。**
  信心分桶其实早就建好了（页面上一直有三桶）。**写代码加速不了。**
- **regime 族门 4 需要锚后 6810 日（约 27 年）**：`MIN_BLOCKS × block = 10 × 681`。
  此前记的约束是「缺对照组」，**现在真正的约束是样本长度**。
- **因子族 15 条是「OOS 待接」** = 真待办（代码没接），**不是时间门，别混为一谈**。
  但接完仍全 pending（锚点 2026-06-26、前向窗 20 日吃掉尾部 → 锚后可观测仅 35 行 < 60，
  **物理上不可能**够判），用户可见变化只有 note 措辞变化 → 价值最低，压最后。
  规格草稿 `docs_internal/SPEC_FACTOR_OOS.md` **未提交**，需按审查的 5 条 BLOCKER 大改。

---

## 8. 🙋 只有用户能拍板（**不许替他定**）

这些是**产品取舍，不是技术判断**。遇到就**停下报告**，别自行决定。

1. **F2 BLOCKER 1 真修会改公开存活名单** —— 用户要选：缩短名单，
   还是保留但标注「可达精度内无法确认」？
2. **Valpha150 池子要不要人工过一遍** —— 已实测漏了 APP / SMCI / VRT / CRWV / DASH。
   **刻意不自动加**（池子带手写中文名/板块，自动加会开天窗并悄悄改变已发布口径）。
3. **横跳规律要不要版面降级** —— `flicker.py` 记的**跨日真实改判史**（与 MC 噪声是两件事）。
   > ⚠ 我 09-16 给的「量化依据」是**错的、方向还反了**：当时报「换种子留在名单上只有 35.9%」，
   > 09-18 加算后是 **90.6%** —— 那个「掷硬币」是**我自己测量的蒙特卡洛噪声**，
   > 不是规律不稳定。按这个尺度**已经没有哪一条该降级**。
   > **2026-11-06 补充实测**：F1 加算后判决翻转从 **2.24/天降到 0.53/天（−76%）**，
   > 世界杯年 5→0、九月 8→0、金叉 2→0。**→ 这条其实已可答「不需降级」。**
4. **两个未跟踪的规格草稿要不要提交**：`SPEC_EVENT_LENS` / `SPEC_V15_SELFGROW`
   （多次刻意排除在提交外）+ `SPEC_FACTOR_OOS.md`
5. **我提过但用户还没点的两件**：
   ① 发布分档模型的 OOS 记分卡（AUC / Tier≥4 边际 / 块自助 CI）——
   现在只在未发布的 `data/processed/walk_forward_results.json` 里；
   ② 给每条 dead/inconclusive 规律**同时显示原始 p 和它的多重比较临界值**，
   好让「差一点」（纳指九月 p=0.017、`term_year3` p=0.04995）与「完全没信号」
   （十月 p=0.96）区分开。**我建议先做 ②**，那正是用户两次提出的问题。
6. **`BTC_mom20_neg` 与 `BTC_mom20_pos` 是同一发现的两面**，并列发布让「发现数」虚高
   —— 候选空间本身的性质，非 F2 引入，另案。

---

## 9. 明确不做 / 别翻案

- **前端框架 / 打包链 / SPA** —— 中国访客 + 同源自托管是硬约束
- **引入境外第三方 CDN**（Plotly 已本地化）
- **多市场 A股/港/日韩** —— 澳洲自 2026-07-12 起已纳入，与这几个区分开
- **给 IPO 打分/评级** —— 那是荐股滑坡的停机点
- **任何绕门禁的捷径**
- **`senate` 每日重抓**（§6.5）
- **用 proxy 绕 SEC 的 IP 封锁**（§6.4）
- **别动统计核心的架构**：`candidate_space → autodiscovery → oos_gate → registry →
  sidecar + git 双锁` 是护城河，结构健康。债主要在 web 层重复与流水线隐式依赖。

---

## 10. 角色、协议与协作风格

### 六步协议（**铁律：审查者 ≠ 建造者 ≠ 同一上下文**）

```
① 写规格 → ② 独立审规格（挑 spec 洞，比建完再改便宜得多）→ ③ 建造
→ ④ 独立审实现 → ⑤ 修复 → ⑥ 验证提交
```

- **审实现按风险分级**：公开统计结论/模型链 = **双审**；常规聚合/展示 = **单审**。别无脑双审。
- **子代理自报完成 ≠ 验收** —— 主脑要亲验关键输出。
- 实证：某次 Opus 代码很干净，但 Fable 审出了 Opus 自测漏掉的 ordering bug ——
  而那个 bug 本可在「审规格」阶段更早抓到。**所以两道审都有价值。**
- **写规格时要预判判断点**，写成「若遇到 X（如校准曲线倒挂/非单调），**停下报告，不要自行决定**」。

### 分工（Claude 侧的班子，供 Codex 理解上下文）

Fable 5 = 军师（谋略/规格/设计方向/统计判断/终审）· Opus 主循环 = 主公（在场决断/调度/终审）·
Sonnet = 执行（样板/测试/格式化/小改动）· Opus 全新上下文 = 审查。

**Codex 接手时**：你同时担任建造与第一道自审，但**公开统计结论类改动仍需另开一个独立上下文复审**
—— 铁律是「审查者 ≠ 建造者」，不是「必须是某个模型」。
只有低层模型可用时，凡标 **[判断]** 的任务**一律不碰**，留言给用户等高层模型。

### 与用户的协作风格（用户明确偏好）

- 用户提建议，**要「考虑 + 平衡最优解」，不是顺着点头**。该踩刹车就踩。
  **诚实的技术异议比虚假认同有价值 —— 这是用户要的。**
- **先给结论/方向，别埋进「非荐股·会错·不确定」到没 takeaway**（反复犯的错）。
  红线已解除，免责归免责，结论要在标题位置。
- **用户提的规律/周期，别凭印象下「没规律」裁决** —— 先真算 + 亮原始计数。
  **实证：大选/世界杯/九月效应都被用户说中、我裁决全错。**
- **「不显著」要说成「看不见」，不要说成「没有」**：
  2026-11 我把十月说成「就是个普通月份」被用户顶回来，他是对的 ——
  p=0.957 配 CI [−1.35, +1.11] pp/月、MDE 1.75 pp/月，
  **CI 上界年化是 +5.9pp**。「测不出来」≠「不存在」。
- **先把已有成果摆出来再动手**（别像没做过）；能测就测，别拿「要动模型」搪塞。
- **大白话**：用户是投资新手 + 生态/农学科研背景，**DiD / placebo 类比沟通最快**。
- 前端任何「今日/今天/today」**都要带具体日期**；读真字段不硬编码；
  数据结论信号的 **as-of 必须可见**。

---

## 11. 诚实红线清单（质量地基）

- 不绕 `verify_output` / `pytest` 门禁
- append-only 账本绝不改历史行（§5.G 有「结算 vs 改历史」的分界）
- **秘钥只走环境变量 / GitHub Secrets，绝不进公开仓库/日志/记忆**
- **公开计分 + 标不确定性** —— 预测越多越要守，这是 Valpha Lab 的护城河
- 每个方向判断带免责 + append-only 计分
- **失败的尝试也是结果** → 进 🪦坟场 或 `OPTIMIZATION_LOG.md §4c`，别只记计划
- LLM 生成**必须喂真算出的数据、防瞎编** + 后置守门拦操作词
- 深度学习可试，但**上线前先用 walk-forward / CPCV 证它真比简单模型强**

---

## 12. 文件地图

### 根目录文档（活 / 历史）

| 文件 | 状态 | 管什么 |
|---|---|---|
| **`CODEX_HANDOFF.md`** | **活·本文件** | 非 Fable 主脑的唯一入口 |
| `CLAUDE.md` | **活** | 项目约定 / 方向定调 / 铁律全文 / F1~F4 实测发现 |
| `HANDOVER.md` | 半活 | 角色分配 §1 与 CI 手册 §4 仍有效；**任务队列 §3/§6 停在 07-07，以本文件 §7 为准** |
| `OPTIMIZATION_LOG.md` | **活** | §2 计划记档 · §4c 试过但否决 · 🪦坟场 · 📋登记簿 |
| `DAILY_LOG.md` | **活** | 每日进展 |
| `ROADMAP.md` | 活 | 任务编号（**每个编号 = 一次提交**，commit message 带任务号） |
| `SELF_GROWING_PLAN.md` | 活 | v1.5 自生长立项 |
| `CLAUDE_HANDOFF.md` · `CODEX_REVIEW_v095.md` | **历史** | 2026-06-18 一次性交接笔记，别当现状 |
| `NEXT_STEPS.md` · `REVIEW.md` · `UI_POLISH_PROPOSAL.md` 等 | 历史 | 6 月快照 |

### 关键代码

| 路径 | 作用 |
|---|---|
| `market-analysis/scripts/run_all.py` | 五阶段 DAG 编排；**docstring 是权威架构图** |
| `.../autodiscovery.py` | 148 候选路由真统计 → 跨族 BY-FDR 三态裁决。H-3 块放大规则在这 |
| `.../walk_forward.py` | 分档块自助；`MIN_BLOCKS = 10` 在这（§5.E） |
| `.../oos_gate.py` | 门 4 裁决 + 「还要等多久」诊断（触发组 vs 对照组要分开说） |
| `.../block_levels.py` + `data/block_levels.json` | 冻结校准表（194 行 × 8 族）；**离线测、生产只读** |
| `.../build_ndx.py` | `_pool_curation_age` 在这（§5.A 三次咬人的地方） |
| `.../fetch_data.py` | `_save_series` 防历史塌缩闸在这（§5.C） |
| `.../staleness_watchdog.py` | CHECKS 20 项；**注意它跑在 CI 里，报不出「CI 挂了」** |
| `.../verify_output.py` | 发布前自检（run_all 第 126 步，失败即终止） |
| `tools/pre_commit_gate.py` | 提交门禁（干净检出 CI 同构，§6.1）。**是 Claude 钩子不是 git hook** |
| **`tools/local_publish.py`** | **CI 被锁期间的发布入口**：完整序列 + fail-closed 门禁 + 互斥锁（§6.3） |
| **`tools/local_publish.ps1`** | 计划任务 `ValphaDailyPublish` 的外壳（ASCII-only + 桌面旗标 + toast） |
| `tools/ci_publish.py` | 提交/推送（显式暂存 `DEFAULT_PATHS`、rebase 重试、真裸仓测过四条路径） |
| `tools/ci_ledger_guard.py` | 防缩水门，**warn-only**（2026-07-28 它以阻断 push 失败过，全站停更四天） |
| `tools/weekly_local_refresh.ps1` | 旧的 SEC 两源本地补（**已 Disabled**，功能被 local_publish 涵盖） |
| `tools/block_calibration.py` | 旋转 null 水平测量（`--controls` / `--real` / `--refine`） |
| `tools/ledger_gap_audit.py` | 以 git 历史查「曾经出现过的日期现在没了」 |
| `scripts/check_strict_json.py` | 拦 NaN/Infinity（那 5 个产物不过 verify_output，前端会白屏） |
| `web/app-1..5.js` + `docs/` 镜像 | 主盘；1181 处 `vpL(zh,en)`；`vpCiStaleDays` 在 app-1 |

### 工作流（6 个，全有 `workflow_dispatch`）

| 文件 | 定时（UTC） |
|---|---|
| `refresh-data.yml` | `30 21 * * 1-5`（盘后）+ `0 13 * * 1-5`（盘前）+ `0,30 14-20 * * 1-5`（盘中） |
| `quick-quotes.yml` | `*/10 13-20 * * 1-5` |
| `weekend-refresh.yml` | `0 13,21 * * 6,0` |
| `weekly-review.yml` | `0 14 * * 6` |
| `site-audit.yml` | push 触发 |
| `lock.yml` | 仅手动 |

> **定时任务常规晚到 3~5 小时**（盘后 cron 名义 16:30 ET，实际落在 19:42~22:00 ET）
> —— 任何「数据是否陈旧」的判断**按交易日，不按小时**，否则天天误报。

---

## 13. 最近一次会话留下的现场（2026-11-06/07）

- 工作树干净，只有 `market-analysis/docs_internal/SPEC_FACTOR_OOS.md` **未跟踪**（等用户定）。
  门0 刻意不拦未跟踪文件，所以它不会每天把自动发布拦下来。
- 有一个 **stash**：`stash@{0} "local artifacts"` —— 7 周前的本地产物，
  `insider.json` 净删 2505 行（**比 origin 还少**），**不是可用素材，别拿它覆盖**。留着未删。
- **发布已自动化**（2026-11-07）：计划任务 `ValphaDailyPublish` 每日 10:00 阿德莱德，
  旧 `ValphaWeeklyRefresh` 已 Disabled。详见 §6.3。
  **Actions 仍锁** —— 解锁后记得做 §1 末尾那 4 步收尾（尤其是停掉这个计划任务）。
- **2026-11-05 是一次大跌**（站上数据之前正冻在它之前）：
  纳指 **−5.52%** · 标普 −4.36% · **VIX +69.7% 到 28.18（88.2 分位）** ·
  VIX 期限结构**倒挂**（近月恐慌 > 远月）。
  半导体为首：SNDK −22.3% MU −17.5% AMD −17.3% TSM −10.8% AVGO −10.4% NVDA −9.3%；
  防御股几乎未动：COST **+1.83%** KO −0.07% BRK-B −1.17%。
  已交叉验证**不是取数故障**（这种横截面结构 + VIX 暴涨是自洽的；故障会随机或全体一致）。
