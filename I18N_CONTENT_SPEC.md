# 深度面板内容双语化(#5) — 实现规格(2026-07-03·Fable 定稿·基于只读侦察)

> 范围:`app-1.js ~ app-5.js`(仅被 dashboard.html 引用·已实证)动态渲染的 ~1083 待译行 / ~1300-1500 条离散中文串。
> docs/ 镜像由 post_edit_hook 自动同步,不加倍工作量。注释(~214 行)不译。

## 1. 机制(定稿·与已生产验证的 teaser 范式同构)

- **共享语言源**:dashboard.html 加载 `vp_i18n.js`;`vpLang()` 读 `localStorage "valpha_lang"`(与 lite-shell 同键·无缝)。
- **`vp_i18n.js` 新增一个通用 helper**(单一来源,别每文件复制):
  ```js
  function vpL(zh, en) { return vpLang() === "en" ? en : zh; }
  ```
- **每文件用法**:
  - 短标签:`vpL("卖出窗口","Sell window")`
  - 插值句:**整句双写**(英文语序不同,禁止逐词替换):`vpLang()==="en" ? `tier ${n}` : `第${n}档``
  - Plotly:`title: vpL("胜率 (%)","Win rate (%)")`;hovertemplate 里 `%{x}`/`%{y}` 占位符**原样保留**。
- **唯一接线改动**(第一波做):dashboard.html ~L1126 语言切换按钮,翻转后除 `apply()` 外**再触发 `renderAll()` + 重跑已渲染的懒图**(渲染器幂等·app-5 lazyRender 注册表定位已见图;建造者按实际结构接)。
- `#en-mode-note`:滚动期改为"部分深度面板双语化进行中";全部完成后移除。

## 2. 翻译质量红线(honesty 优先)

1. **免责/诚实框逐句等价**:EN 绝不比 ZH 软(如"非操作建议/会错/过去≠未来"必须同强度出现)。
2. **术语与 dashboard 既有 EN{} 字典(~205 键)一致**(面板标题/badge 已有高质量英译,内文复用同一措辞)。
3. **长 prose 整段重写成地道英文**(app-4 个人观点/IPO 规则等),不逐词。
4. 复数/序数(`${n} days`/`tier ${n}`)、日期(`2026年6月12日`→`Jun 12, 2026`)、货币(A$ 原样)按英文惯例。
5. 数字/统计值只经插值,**绝不在翻译中手写数值**。

## 3. 分波(每波=独立建+验+提交;文件互不重叠可并行)

| 波 | 文件 | 量 | 要点 |
|---|---|---|---|
| W1a | **app-3.js** | 小-中(143行) | 试点:验证 vpL+重渲染接线;含 dashboard 接线改动+vp_i18n 加 vpL |
| W1b | **app-1.js** | 中(149行) | 确立 **Plotly 文案范式**(axis/legend/hover·36处) |
| W2a | app-5.js | 中(233行) | 含 renderAll 本体;factor-audit tooltip |
| W2b | app-2.js | 大(284行) | 45 处图表 + 插值统计长句(执政党效应等整句双写) |
| W3 | app-4.js | 大(274行) | 长 prose/日期/货币 最重压轴;完成后移除 en-mode-note |

- 每波验收(Fable):node --check + audit_frontend + **playwright 实测**(切 EN → 该文件面板全英文·切回 zh 复原·图表 hover 占位符完好)+ 抽查免责等价。
- W1a/W1b 可并行(不同文件);dashboard.html 接线只归 W1a 动,W1b 不碰 dashboard。

## 4. 判断点(builder 遇到即 STOP)

- 某句 EN 化后语义/免责强度存疑 → STOP 列出待 Fable 定。
- 发现某串其实参与逻辑(非纯展示)→ STOP。
- lazyRender 重跑机制若与幂等假设冲突(某图不可重跑)→ STOP。
