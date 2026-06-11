# tools/ — 一次性/辅助工具（不属于流水线）

| 文件 | 用途 |
|---|---|
| `generate_report.js` | 用 `docx` 包生成《美股投资分析报告.docx》。`npm install` 后 `node generate_report.js` |
| `audit_frontend.py` | 前端审计：HTML ID / onclick 与 app.js 交叉检查，找渲染不出来的面板 |
| `check_opp.py` | 在终端快速打印 signals.json 的最佳买入/减仓窗口 |

流水线本体在 `market-analysis/scripts/`，由 `run_all.py` 编排。
