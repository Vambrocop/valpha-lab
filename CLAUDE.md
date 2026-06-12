# Alpha Lab — Claude Code 工作约定

## 用户与访客（别当过时信息清理）

- 用户在**澳洲阿德莱德**（UTC+9:30）：AUD 持仓计算器、澳洲 CGT 计算器、"本地日期比美东快一天"的注释都是真实需求
- 网站有**中国境内访客**：前端资源同源自托管（Plotly 已本地化），不要引入境外第三方 CDN 依赖

## 当前状态（2026-06-11 更新）

- ✅ P0 防回归安全网、✅ P1 前端五视图+瘦身+CI分级 —— 均已完成并推送
- **下一步：P2 模型方法论（v3.0）**，详细任务清单和验收标准见 `ROADMAP.md` 的 P2 节
- P2 建议用 xhigh 推理强度执行（统计判断密集）；P3 杂项用 high 即可

## 运行环境（Windows）

- 用 `py`（Python 3.12），**不要用 `python`**（指向 Microsoft Store 占位程序）
- 跑任何脚本前设 `$env:PYTHONUTF8='1'`（GBK 控制台会让 Unicode 输出崩溃）
- 全量流水线：`py market-analysis/scripts/run_all.py`（约3分钟）；盘中轻量：加 `--light`
- 测试：`py -m pytest market-analysis/tests -q`（必须全绿才能提交流水线改动）
- 前端改动后跑 `py tools/audit_frontend.py` 交叉检查 ID/onclick

## 模型分层委派（用户授权，自主判断不必先问）

角色按"档位"定义而非模型名——**编排与思考永远由用户当下可用的最高级模型担任**
（2026-06 是 Fable 5，以后可能是 Opus 4.8/5.0……自动随版本演进）：

- **最高档（主会话）**：方法论、统计判断、架构、写实施指导、任务分配、与用户讨论
- **中档子代理（如 Sonnet）**：按既定指导机械改代码、批量小修、跑验证链（自包含且工作量大于交代成本才委派）
- **低档子代理（如 Haiku）**：重命名/复制/格式化级琐事
- **强推理子代理（如 Opus）**：代码审查（agent-skills:code-reviewer）、安全审查（security-auditor）

## 执行协议

- 按 ROADMAP.md 任务编号干活，**每个编号 = 一次提交**，commit message 带任务号
- 改流水线 → 提交前全量跑通 + pytest 全绿；改模型 → bump `MODEL_VERSION` 并重跑 walk_forward，
  新旧指标对比写进 commit message
- web/ 改动要镜像到 docs/（run_all 末步会自动做；手改记得 Copy-Item）
- 提交后 push 到 origin main（GitHub Pages 自动部署；CI 每小时也会自动提交数据，push 前先 fetch）

## 不要做的事

- 不加新因子、不上深度学习、不引前端框架（理由见 ROADMAP"不建议做"节）
- 不要绕过 verify_output / pytest 门禁
- prediction_log.csv 和 paper_ledger.csv 是 append-only 账本，绝不手改历史行
