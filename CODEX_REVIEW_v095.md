# CODEX_REVIEW_v095.md

Date: 2026-06-18

## 给 Claude Code 的复核要点

这次 Codex 在 `cd58579` 之后做的是一轮小而硬的前端/CI 加固。重点不是改模型逻辑，而是让站点更接近可上 CSP 的结构，并把移动端布局审计放进 GitHub Actions。

## 已完成

1. CI 移动端审计
   - `.github/workflows/refresh-data.yml` 新增 Playwright Chromium 安装。
   - refresh pipeline 现在会跑桌面和移动端：
     - `python tools/site_audit.py --ci`
     - `python tools/site_audit.py --mobile --ci`
   - `tools/site_audit.py` 现在发现 overflow、console error/warning、failed request 会非零退出。
   - 本地 `--ci` 会优先 Chromium，缺失时 fallback 到 Edge，方便 Windows 复核。

2. CSP 第一阶段
   - `market-analysis/web/index.html` 静态 `onclick/oninput` 已移除。
   - `app-2.js/app-3.js/app-4.js` 动态模板里的 inline handler 已迁到 `data-*` 属性。
   - `app-5.js` 新增 `bindStaticControls()`，集中做静态绑定和动态事件代理。
   - `docs/` 已同步。
   - 当前检查：
     - `rg "onclick=|oninput=" market-analysis/web docs --glob "index.html" --glob "app-*.js"` 无结果。

3. 移动端溢出补丁
   - 严格 audit 抓到 `Benchmark 记分卡` 移动端 overflow。
   - 已在 `renderBenchmark()` 内加横向滚动 wrapper 和表格最小宽，外层 panel 不再撑破视口。

4. audit 脚本 Windows 兼容
   - `tools/site_audit.py` 增加 stdout UTF-8 fallback，避免 Windows GBK 控制台打印 emoji/CJK 时崩。

## 请重点复核

1. 事件迁移是否漏行为
   - 主导航切换。
   - 刷新按钮。
   - 新手引导关闭。
   - 长周期按钮。
   - forecast / multivariate / calendar tabs。
   - SPCX 输入、SPCX 报价按钮。
   - 持仓刷新、自动刷新、成本价设置。
   - 个股表点击、试胆小游戏买/卖/重置。
   - 市场时钟时区切换、隔夜指数切换、登记簿“展开”跳转。

2. CI 成本
   - Playwright `install --with-deps chromium` 会拉浏览器依赖，refresh job 时间会增加。
   - 如果太慢，可把浏览器 audit 只放到 push/PR 或每日 full refresh，不放到 30 分钟 light refresh。

3. CSP 下一步
   - 现在 event handler 基本干净，但 inline style 仍很多。
   - 建议下一步先上 report-only CSP，并暂时允许 `style-src 'unsafe-inline'`。
   - 若要完全严格 CSP，需要把大量 inline style 抽到 CSS class。

## 验证实据

```powershell
node --check E:\finance\market-analysis\web\app-1.js
node --check E:\finance\market-analysis\web\app-2.js
node --check E:\finance\market-analysis\web\app-3.js
node --check E:\finance\market-analysis\web\app-4.js
node --check E:\finance\market-analysis\web\app-5.js
$env:PYTHONUTF8='1'; py -m pytest -q
$env:PYTHONUTF8='1'; py E:\finance\market-analysis\scripts\verify_output.py
py E:\finance\tools\site_audit.py
py E:\finance\tools\site_audit.py --mobile
py E:\finance\tools\site_audit.py --ci
py E:\finance\tools\site_audit.py --mobile --ci
```

结果：

- `169 passed`
- `verify_output.py` 通过。
- node syntax checks 通过。
- desktop/mobile audit 均为 0 容器问题、0 控制台报错/警告、0 失败请求。
- CI-mode audit 本地通过；GitHub runner 会安装 Chromium 后使用 Chromium。

## 剩余建议

1. 把 `rg "onclick=|oninput=" ...` 做成轻量 CI 检查，防止后续回归。
2. 给 audit 截图改成 workspace-relative 输出，并在 Actions 上传 artifact。
3. 上 CSP report-only，先观察一周，再决定是否抽 inline style。
