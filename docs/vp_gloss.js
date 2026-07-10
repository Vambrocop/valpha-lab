/* vp_gloss.js — Valpha Lab 共享词汇注解组件 v1.1
   依赖：无（dependency-free）。同源自托管，不引境外 CDN。
   用法：
     · 手动模式（原有 6 个页面在用，行为完全不变）：
         <script src="vp_gloss.js"></script>
         vpAnnotate(text) → 返回 HTML 字符串，可直接赋给 innerHTML。
     · 自动全站扫描模式（新增）：
         <script src="vp_gloss.js" data-autoscan></script>
       页面加载后自动对 document.body 扫描一次（DOMContentLoaded）+ 2000ms 后
       再扫一次（接住 fetch 后异步渲染的内容），把 GLOSS 词表中全页首次出现的
       术语原地包上 tooltip。也可手动调用 vpGlossScan(root)（root 默认
       document.body）；重复调用是幂等的，不会对已注解内容做二次处理。
       无 data-autoscan 属性时不触发任何自动行为，与旧版完全一致。
   规则（vpAnnotate 与 vpGlossScan 共通）：
     · 仅标注首次出现的术语（vpGlossScan 是全页范围的首次，跨文本节点全局计数）；
     · 若术语紧跟 （ 或 ( 则跳过（文案已自解释）；
     · 纯 ASCII 术语（OOS/percentile/conformal 等）要求词边界：前后字符都不是英文
       字母/数字才算命中——防止把 BetaShares 里的 "Beta"、VIX3M 里的 "VIX" 错切
       成术语（D3 新增守卫；中文术语不受影响）；
     · 语言（D3 起支持双语）：zh 模式所有词条参与（用中文释义 = 第2元素）；
       en 模式只有带英文释义（第3元素）的词条参与（用英文释义）——v1.1 的纯中文
       旧词条没有第3元素，en 模式下继续完全不注解，行为与旧版一致；
     · vpAnnotate 输入为纯文本（通常是 LLM 输出），先整体转义再注入受控 tooltip
       标记 → XSS 安全；vpGlossScan 只操作页面已有的可信 DOM 文本节点，不引入
       新的不可信输入源。
*/
(function(win){
  "use strict";

  /* ── 词汇表 ─────────────────────────────────────────────────────
     每条：[术语, 一句大白话中文解释（不含新术语、初中生能懂）, 英文解释(可选)]
     · 只有 2 元素 = 仅中文模式注解（v1.1 全部旧词条，措辞已审，不动）；
     · 3 元素 = 双语（D3 起新词条），en 模式下用英文释义注解。

     JUDGMENT POINT — 跳过的术语（说明原因，诚实为先，不猜不收）：
       · "体制"（regime）：本站特定技术词，大白话容易过度简化含义，跳过
       · "共动"（co-movement）：本站特定因子名，平白解释易产生歧义，跳过
       · "尾部"（tail，裸词，不含 EVT/极值前缀）：app-5.js「训练尾部」是 CV 语境下
         "训练集尾段"的意思，跟风险语境的"尾部风险"完全不是一回事——同一裸词两种
         含义会读者被误导，跳过裸词；风险语境已有专属更长词"EVT"覆盖（不产生歧义）
       · vpGlossScan 匹配按词长降序（同一起始位置多个候选词时长词优先，防短词
         抢占本应属于长词的前缀位置）；另外"显著"命中后若紧跟"性"（即常见词
         「显著性」本身，并非本站「显著」这个术语）则跳过该处，继续在文本里
         往后找下一处真正的「显著」——防止把常见词的前缀错切成术语。

     D3 复核（2026-07-09）——"分位"原判定为「本站多处用法不同（百分位 vs 分位数
     vs tier），无统一注解，跳过」：本轮对全站 app-*.js + *.html 重新逐条 grep 复核，
     未找到任何"分位数"(quantile值)或"tier/档位"含义的用法——全部实际出现都是
     "历史百分位排名(0–100)"这一种含义（含 D2 vpPosBar 的"历史分位"标签、regimefwd
     的"10%分位"等）。故本轮解禁收录，见下方词条；若之后发现真的歧义用法，请撤回
     并把这条 note 换回跳过态。 */
  var GLOSS = [
    ["VIX",      "衡量市场恐慌情绪的指数，越高说明投资者越害怕"],
    ["收益率曲线", "把不同期限国债的利率连成一条线，倒挂（短期高于长期）常被当作经济放缓的预警"],
    ["信用利差",  "企业借钱比政府借钱贵多少，越大说明市场越担心企业还不上钱"],
    ["相关性",   "两只股票涨跌是否同步，相关性高意味着它们经常一起涨、一起跌"],
    ["分散性",   "各股票涨跌分化的程度，分化越大说明不同股票走势差异越明显"],
    ["波动率",   "股价上下幅度有多大的度量，波动率越高意味着短期内价格变化越剧烈"],
    ["动量",     "股价近期持续上涨或下跌的惯性，动量策略就是顺着这个方向押注"],
    ["季节性",   "某段时间（如特定月份）在历史上反复出现的涨跌规律"],
    ["回撤",     "从最高点跌了多少，比如从 100 跌到 80 就是 20% 回撤"],
    ["夏普",     "每承担一份风险能赚多少回报，夏普越高说明风险调整后收益越好"],
    ["置信",     "结论有多可靠的把握程度，置信度高说明这个判断经过了更严格的统计检验"],
    ["样本外", "用没参与建模的数据来检验,防止模型只是把历史答案背下来"],
    ["回测",   "用历史数据模拟「假如当时这么做」会怎样;历史表现好不代表未来也好"],
    ["胜率",   "历史上上涨(或判断正确)的次数占比"],
    ["基率",   "不挑时机、随便一天的平均胜率,用来对比「信号日」是否真的更好"],
    ["p值",    "如果规律纯属巧合,能看到这么极端结果的概率;越小越不像巧合,但不代表效果大"],
    ["显著",   "统计上「不太可能是巧合」的意思,不代表效果大、也不保证未来重演"],
    ["FDR",   "同时检验很多条规律时,纯靠运气也会冒出几条假规律;FDR 校正就是把这种假阳性压下去"],
    ["均线",   "最近 N 天收盘价的平均,常用来看趋势方向"],
    ["金叉",   "短期均线从下往上穿过长期均线,历史上常被当作趋势转强的标志(不是买入指令)"],
    ["置换检验", "把数据顺序打乱很多次重新计算,看真实结果是否比「乱序世界」更极端"],
    ["块自助", "把历史数据切成小段反复抽样重算,估计结果有多不稳定(保留时间上的连续性)"],
    ["保形区间", "用历史误差算出「未来大概落在这个范围」的区间;给范围、不给方向"],
    ["贝叶斯", "把历史经验(先验)和新数据结合起来更新判断的统计方法"],
    // ── D3 新增(2026-07-09)：候选来自规格(β/Beta、分位/percentile、校准、保形/conformal、
    //    块自助/bootstrap、样本外/OOS、夏普、年化波动、EVT、隐含波动率、期限结构)，逐条先
    //    grep 全站确认页面文本真出现过、再收录（"Beta" 只在 BetaShares 商号里出现→不收；
    //    "最大回撤"由旧词条"回撤"前缀覆盖→不重复收）。措辞只解释概念，绝不带方向暗示。
    //    英文变体词(percentile/conformal/bootstrap/OOS/calibration/Sharpe)只收小写/正写形式，
    //    句首大写的 "Conformal/Calibration" 不另立词条（词典别为大小写膨胀；漏注可接受）。
    //    数组顺序纪律：长词在前(年化波动率→年化波动、百分位→分位)——vpAnnotate 按数组序
    //    匹配，防短词抢长词前缀。 ──
    ["β", "衡量个股相对大盘的波动敏感度，β大于1代表通常比大盘涨跌更剧烈，小于1则更平稳",
          "How sensitive a stock is to the broad market: beta above 1 means it tends to swing harder than the market, below 1 means milder swings"],
    ["校准", "把模型自称的把握度和实际发生的频率做对比，校准好=说80%有信心时真的大约80%会命中",
          "Comparing a model's stated confidence with how often it actually turns out right — well calibrated means \"80% confident\" calls come true about 80% of the time"],
    ["calibration", "把模型自称的把握度和实际发生的频率做对比，校准好=说80%有信心时真的大约80%会命中",
          "Comparing a model's stated confidence with how often it actually turns out right — well calibrated means \"80% confident\" calls come true about 80% of the time"],
    ["保形", "用历史预测误差倒推区间宽度的方法，让「未来落在这个区间内」的实际概率接近承诺的水平",
          "A method that sizes prediction intervals from past errors, so outcomes actually fall inside the interval about as often as promised"],
    ["conformal", "用历史预测误差倒推区间宽度的方法，让「未来落在这个区间内」的实际概率接近承诺的水平",
          "A method that sizes prediction intervals from past errors, so outcomes actually fall inside the interval about as often as promised"],
    ["年化波动率", "把每天的涨跌幅度换算成一年尺度方便比较，数值越高说明短期起伏越大",
          "Daily price swings rescaled to a one-year horizon so assets can be compared; higher means bumpier"],
    ["年化波动", "把每天的涨跌幅度换算成一年尺度方便比较，数值越高说明短期起伏越大",
          "Daily price swings rescaled to a one-year horizon so assets can be compared; higher means bumpier"],
    ["隐含波动率", "从期权价格倒推出的市场对未来波动的预期，不是已经发生过的实际波动",
          "The market's expectation of future volatility, backed out from option prices — an expectation, not the volatility that already happened"],
    ["期限结构", "同一指标在不同到期时间上的对比(如VIX期限结构=短期恐慌预期 vs 远期)，正常状态通常是远月更高",
          "The same gauge compared across expiry horizons (e.g. VIX term structure = near-term vs longer-term fear); in the usual state the far months sit higher"],
    ["EVT", "一种专门估计「很少发生、一旦发生跌幅很深」极端行情的统计方法，不是估计日常波动",
          "Extreme Value Theory: statistics built for rare-but-severe moves (the tail), not for everyday volatility"],
    ["百分位", "把当前数值放进历史所有取值里排序，看它处于百分之几的位置(比如「第90百分位」=比过去90%的时候都高)",
          "Where today's value ranks within its own history, as a percentage (90th percentile = higher than 90% of past readings)"],
    ["分位", "把当前数值放进历史所有取值里排序，看它处于百分之几的位置(比如「90分位」=比过去90%的时候都高)",
          "Where today's value ranks within its own history, as a percentage (90th percentile = higher than 90% of past readings)"],
    ["percentile", "把当前数值放进历史所有取值里排序，看它处于百分之几的位置",
          "Where today's value ranks within its own history, as a percentage (90th percentile = higher than 90% of past readings)"],
    ["OOS", "样本外(out-of-sample)的缩写:用没参与建模的数据来检验,防止模型只是把历史答案背下来",
          "Out-of-sample: testing on data the model never saw during building, to guard against it just memorizing history"],
    ["bootstrap", "把历史数据切成小段反复抽样重算,估计结果有多不稳定(保留时间上的连续性)",
          "Resampling chunks of history many times and recomputing, to gauge how unstable an estimate is (block bootstrap keeps time-order inside each chunk)"],
    ["Sharpe", "每承担一份风险能赚多少回报，夏普比率越高说明风险调整后收益越好",
          "Return earned per unit of risk taken; higher means better risk-adjusted performance"]
  ];

  /* ── 内部工具 ────────────────────────────────────────────────── */

  /** 对任意字符串做 HTML 转义，防 XSS */
  function escHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function(c) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
    });
  }

  /** 读当前语言（兼容隐私模式 localStorage 抛错） */
  function getLang() {
    try { return localStorage.getItem("valpha_lang") || "zh"; } catch(e) { return "zh"; }
  }

  /** 生成 tooltip 标记的 HTML 字符串 —— vpAnnotate 与 vpGlossScan 唯一共用的生成点。
      term / exp 只会来自本文件内的 GLOSS 常量（不接受外部输入），无需再转义。 */
  function tooltipMarkup(term, exp) {
    return '<span class="vp-term" tabindex="0">' +
             term +
             '<span class="vp-tip" role="tooltip">' + exp + '</span>' +
           '</span>';
  }

  /* ── ASCII 词边界守卫（D3）────────────────────────────────────────
     纯英文/数字术语要求前后字符都不是 [A-Za-z0-9]，防 BetaShares→"Beta"、
     VIX3M→"VIX" 这类前缀/中缀误切；中文术语（含 β 等非 ASCII 符号）不受影响。 */
  var ASCII_TERM = /^[A-Za-z0-9]+$/;
  function isWordChar(c) { return !!c && /[A-Za-z0-9]/.test(c); }
  function failsAsciiBoundary(term, before, after) {
    return ASCII_TERM.test(term) && (isWordChar(before) || isWordChar(after));
  }

  /* ── 主函数：vpAnnotate ─────────────────────────────────────────
     zh 模式与 v1.1 逐字节同逻辑，仅新增两点（都是防误注，不改既有正确注解）：
     ① ASCII 词边界守卫；② en 模式从"完全不注解"升级为"只用带英文释义的词条
     注解"（旧纯中文词条无第3元素 → en 下依旧不注解，与旧版一致）。 */

  /**
   * vpAnnotate(text) → HTML 字符串
   *
   * 将来自 LLM 的纯文本 text 转换为带 hover tooltip 的 HTML：
   *   · 先对整段做 HTML 转义（text 视为不可信）；
   *   · 仅首次出现的术语加 tooltip span；
   *   · 术语后紧跟 （ 或 ( 时跳过（LLM 已自解释）；
   *   · 语言：zh 用词条第2元素（全部词条），en 用第3元素（仅双语词条）。
   *
   * 返回值可直接赋给 element.innerHTML。
   */
  function vpAnnotate(text) {
    if (!text) return "";
    var lang = getLang();
    var safe = escHtml(text);          // 先对整段转义；之后只插入受控常量标记
    var expIdx = lang === "en" ? 2 : 1;

    var marked = {};                   // 已注解的术语集合，确保仅首次
    for (var i = 0; i < GLOSS.length; i++) {
      var term = GLOSS[i][0];
      var exp  = GLOSS[i][expIdx];
      if (!exp || marked[term]) continue;   // en 模式下无英文释义的旧词条自然跳过

      /* 在已转义文本中查找术语（术语为中文/ASCII，HTML 转义不影响它们） */
      var pos = safe.indexOf(term);
      if (pos < 0) continue;

      /* 检查术语后一个字符 —— （ 和 ( 不受 HTML 转义影响，直接检查 */
      var after = safe.charAt(pos + term.length);
      if (after === "（" || after === "(") continue; // LLM 已自解释，跳过
      if (failsAsciiBoundary(term, safe.charAt(pos - 1), after)) continue; // 词中缀，跳过

      /* 仅替换当前找到的第一次出现（term / exp 来自常量，无需再转义） */
      safe = safe.slice(0, pos) + tooltipMarkup(term, exp) + safe.slice(pos + term.length);
      marked[term] = true;
      /* 注：下一轮 indexOf 会在新字符串中重新搜索，天然跳过刚插入的标记 */
    }

    return safe;
  }

  /* ── vpGlossScan：全站自动扫描模式 ──────────────────────────────

     设计要点（供后续维护参考）：
     · 术语来源与 vpAnnotate 共用同一个 GLOSS 数组（新增词只需维护一处，两边
       同时生效）；但扫描时用的是按词长降序排好的独立副本（sortedGloss），
       不改动 GLOSS 本身的顺序，因此不影响 vpAnnotate 既有的匹配/输出顺序。
     · "全页每词只注首次"靠模块级常驻的 seenTerms 记录，不随每次调用重置——
       DOMContentLoaded 与 setTimeout(2000) 两次扫描共享同一份 seenTerms，
       跨调用仍然只注一次。
     · 幂等的第二道保险：已生成的 tooltip 元素带 vp-term class；扫描时会跳过
       祖先命中 .vp-term 的文本节点（含 tooltip 气泡自身的文字），重复调用
       不会对已注解处做二次处理。
     · 跳过的容器：script/style/svg/canvas/code/pre/a/button/input/textarea/
       select/option、[data-no-gloss]、Plotly 图表容器（class 含子串
       "js-plotly-plot" 或 "plotly"）。
     · 匹配算法："从左到右扫描位置 × 词长降序尝试" 天然实现两条规则：
         (a) 词长降序——同一起始位置多个候选词时，长词先试、先赢；
         (b) 跳过后继续找下一处——命中但因『后跟（/(』或『显著+性』被判定跳过
             时，只放弃这一个位置，同一个词在文本后面别处仍可能被注解
             （而不是像 vpAnnotate 那样直接放弃整个词）。
  ── ──────────────────────────────────────────────────────────── */

  /* 按语言过滤 + 词长降序的词表缓存（D3 起分语言）：
     zh → 全部词条 [term, 中文释义]；en → 仅双语词条 [term, 英文释义]。 */
  var sortedGlossCache = {};
  function getSortedGloss(lang) {
    var key = lang === "en" ? "en" : "zh";
    if (!sortedGlossCache[key]) {
      var expIdx = key === "en" ? 2 : 1;
      var list = [];
      for (var i = 0; i < GLOSS.length; i++) {
        if (GLOSS[i][expIdx]) list.push([GLOSS[i][0], GLOSS[i][expIdx]]);
      }
      sortedGlossCache[key] = list.sort(function(a, b) {
        return b[0].length - a[0].length;
      });
    }
    return sortedGlossCache[key];
  }

  /* 特例表：命中该术语时若紧跟指定字符，则视为本处未命中（防止把常见词/长词的
     前缀错切成术语）：
       · "显著"+"性"：「显著性」是常见词，不是本站「显著」术语；
       · "年化波动"+"率"：那是「年化波动率」——长词首次出现时长词自己会赢
         （词长降序），此守卫防的是长词已注解过之后，短词把后续出现的
         「年化波动率」拦腰切成「年化波动|率」；
       · "保形"+"区"：同理防拦腰切「保形区间」。 */
  var SKIP_IF_FOLLOWED_BY = { "显著": "性", "年化波动": "率", "保形": "区" };

  /* 模块级常驻，跨多次 vpGlossScan 调用共享 —— 保证幂等（全页每词只注一次）。
     D3 起值存"活的 tooltip 元素"而非 true：动态面板（个股分析卡/D3a 展开卡等）重画时
     innerHTML 会连注解 span 一起抹掉，若 seenTerms 只记布尔，重画后该词永远无法再注解
     （标记还在、span 没了）。每次 vpGlossScan 先清扫：记录的元素已不在文档里(isConnected
     为 false) → 删除标记，让该词在新内容里可以重新注上。"全页每词只有一个活注解"的
     不变量不变。 */
  var seenTerms = {};
  function sweepDeadSeenTerms() {
    for (var k in seenTerms) {
      var v = seenTerms[k];
      if (v && v !== true && v.isConnected === false) delete seenTerms[k];
    }
  }

  var SKIP_TAGS = {
    SCRIPT: 1, STYLE: 1, SVG: 1, CANVAS: 1, CODE: 1, PRE: 1,
    A: 1, BUTTON: 1, INPUT: 1, TEXTAREA: 1, SELECT: 1, OPTION: 1
  };

  /** 沿祖先链判断该元素是否位于应跳过的容器内 */
  function hasSkipAncestor(el) {
    while (el && el.nodeType === 1) {
      if (SKIP_TAGS[el.tagName]) return true;
      if (el.hasAttribute && el.hasAttribute("data-no-gloss")) return true;
      var cls = el.className;
      if (typeof cls === "string" && cls) {
        if (cls.indexOf("vp-term") !== -1) return true; /* 已注解过（幂等） */
        if (cls.indexOf("plotly") !== -1) return true;  /* js-plotly-plot / plotly* 容器 */
      }
      el = el.parentElement;
    }
    return false;
  }

  /**
   * 在给定文本里从头查找下一个应注解的命中。
   * 抽成纯函数（不碰 DOM），方便脱离浏览器环境单测。
   * 返回 {pos, term, exp} 或 null（找不到）。
   */
  function findNextMatch(text, sortedTerms, seen) {
    for (var i = 0; i < text.length; i++) {
      for (var t = 0; t < sortedTerms.length; t++) {
        var term = sortedTerms[t][0];
        if (seen[term]) continue;
        if (i + term.length > text.length) continue;
        if (text.slice(i, i + term.length) !== term) continue;

        var nextChar = text.charAt(i + term.length);
        if (nextChar === "（" || nextChar === "(") continue;   // 已自解释，跳过该处
        if (SKIP_IF_FOLLOWED_BY[term] === nextChar) continue;  // 防误切，跳过该处
        if (failsAsciiBoundary(term, text.charAt(i - 1), nextChar)) continue; // 词中缀，跳过该处

        return { pos: i, term: term, exp: sortedTerms[t][1] };
      }
    }
    return null;
  }

  /** 把 tooltip 标记解析为真实 DOM 节点（复用 tooltipMarkup 这一份生成逻辑） */
  function buildTooltipNode(term, exp) {
    var tmp = document.createElement("span");
    tmp.innerHTML = tooltipMarkup(term, exp);
    return tmp.firstChild;
  }

  /** 处理单个文本节点：反复 splitText，把命中片段原地换成 tooltip 元素 */
  function processTextNode(textNode) {
    var terms = getSortedGloss(getLang());
    var current = textNode;
    while (current && current.nodeValue) {
      var found = findNextMatch(current.nodeValue, terms, seenTerms);
      if (!found) break;

      /* current: 命中前的文本；afterMatch: 命中起到节点末尾 */
      var afterMatch = current.splitText(found.pos);
      /* afterMatch 收窄为恰好等于命中词；rest: 命中后剩余文本 */
      var rest = afterMatch.splitText(found.term.length);

      var tipNode = buildTooltipNode(found.term, found.exp);
      afterMatch.parentNode.replaceChild(tipNode, afterMatch);

      seenTerms[found.term] = tipNode;   // 存活元素引用（重画抹掉后可被 sweep 回收重注）
      current = rest;
    }
  }

  /**
   * vpGlossScan(root) — 全页自动扫描（root 默认 document.body）。
   * 幂等：可重复调用，已注解内容不会被二次处理。
   */
  function vpGlossScan(root) {
    root = root || document.body;
    if (!root) return;
    // D3 起 en 模式也扫，但只用带英文释义的双语词条（getSortedGloss("en")）；
    // 旧纯中文词条在 en 模式下依旧完全不注解。
    if (!getSortedGloss(getLang()).length) return;
    sweepDeadSeenTerms();   // 回收"注解 span 已被面板重画抹掉"的词，允许重新注上

    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function(node) {
        if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        if (hasSkipAncestor(node.parentElement)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });

    /* 先收集全部候选文本节点，再逐个处理——避免在遍历过程中做 splitText/
       replaceChild 打乱 TreeWalker 自身的遍历状态。 */
    var nodes = [];
    var n;
    while ((n = walker.nextNode())) nodes.push(n);

    for (var i = 0; i < nodes.length; i++) {
      processTextNode(nodes[i]);
    }
  }

  /* ── 自动模式：<script src="vp_gloss.js" data-autoscan></script> ──
     DOMContentLoaded 跑一遍 + 2000ms 后再跑一遍（接住 fetch 后异步渲染的内容）。
     无 data-autoscan 属性时不触发任何自动行为，6 个手动调用的老页面零影响。 */
  var selfScript = document.currentScript;
  if (selfScript && selfScript.hasAttribute("data-autoscan")) {
    var runScan = function() {
      try { vpGlossScan(document.body); }
      catch (e) { /* 扫描失败不应影响页面其余脚本 */ }
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", runScan);
    } else {
      runScan(); // 脚本晚于 DOMContentLoaded 才执行时，立即跑一次
    }
    setTimeout(runScan, 2000);
  }

  /* 暴露到全局 */
  win.vpAnnotate = vpAnnotate;
  win.vpGlossScan = vpGlossScan;
  /* 供单测/调试复用的内部纯函数（可选依赖，不影响生产路径） */
  win.vpGlossInternal = { findNextMatch: findNextMatch, getSortedGloss: getSortedGloss };
  /* win.vpGloss 仅供调试，生产不依赖 */
  win.vpGloss = GLOSS;

}(window));
