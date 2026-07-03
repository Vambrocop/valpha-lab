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
     · 当前语言非 'zh' 时不注解（vpAnnotate 转义后原样返回；vpGlossScan 整体不扫）；
     · vpAnnotate 输入为纯文本（通常是 LLM 输出），先整体转义再注入受控 tooltip
       标记 → XSS 安全；vpGlossScan 只操作页面已有的可信 DOM 文本节点，不引入
       新的不可信输入源。
*/
(function(win){
  "use strict";

  /* ── 词汇表 ─────────────────────────────────────────────────────
     每条：[术语, 一句大白话解释（不含新术语、初中生能懂）]

     JUDGMENT POINT — 跳过的术语（说明原因，诚实为先，不猜不收）：
       · "体制"（regime）：本站特定技术词，大白话容易过度简化含义，跳过
       · "共动"（co-movement）：本站特定因子名，平白解释易产生歧义，跳过
       · "分位"：本站多处用法不同（百分位 vs 分位数 vs tier），无统一注解，跳过
       · vpGlossScan 匹配按词长降序（同一起始位置多个候选词时长词优先，防短词
         抢占本应属于长词的前缀位置）；另外"显著"命中后若紧跟"性"（即常见词
         「显著性」本身，并非本站「显著」这个术语）则跳过该处，继续在文本里
         往后找下一处真正的「显著」——防止把常见词的前缀错切成术语。
  ────────────────────────────────────────────────────────────────── */
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
    ["贝叶斯", "把历史经验(先验)和新数据结合起来更新判断的统计方法"]
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

  /* ── 主函数：vpAnnotate（原有逻辑，逐字节行为不变） ─────────────── */

  /**
   * vpAnnotate(text) → HTML 字符串
   *
   * 将来自 LLM 的纯文本 text 转换为带 hover tooltip 的 HTML：
   *   · 先对整段做 HTML 转义（text 视为不可信）；
   *   · 仅首次出现的术语加 tooltip span；
   *   · 术语后紧跟 （ 或 ( 时跳过（LLM 已自解释）；
   *   · 英文模式：转义后原样返回，不注解。
   *
   * 返回值可直接赋给 element.innerHTML。
   */
  function vpAnnotate(text) {
    if (!text) return "";
    var lang = getLang();
    var safe = escHtml(text);          // 先对整段转义；之后只插入受控常量标记
    if (lang !== "zh") return safe;    // 英文模式：不注解，转义结果直接返回

    var marked = {};                   // 已注解的术语集合，确保仅首次
    for (var i = 0; i < GLOSS.length; i++) {
      var term = GLOSS[i][0];
      var exp  = GLOSS[i][1];
      if (marked[term]) continue;

      /* 在已转义文本中查找术语（术语为中文/ASCII，HTML 转义不影响它们） */
      var pos = safe.indexOf(term);
      if (pos < 0) continue;

      /* 检查术语后一个字符 —— （ 和 ( 不受 HTML 转义影响，直接检查 */
      var after = safe.charAt(pos + term.length);
      if (after === "（" || after === "(") continue; // LLM 已自解释，跳过

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

  var sortedGlossCache = null;
  function getSortedGloss() {
    if (!sortedGlossCache) {
      sortedGlossCache = GLOSS.slice().sort(function(a, b) {
        return b[0].length - a[0].length;
      });
    }
    return sortedGlossCache;
  }

  /* 特例表：命中该术语时若紧跟指定字符，则视为本处未命中（防止把常见词的前缀
     错切成术语）。目前唯一实例："显著"+"性" → 那是「显著性」这个常见词，
     不是本站的「显著」术语。 */
  var SKIP_IF_FOLLOWED_BY = { "显著": "性" };

  /* 模块级常驻，跨多次 vpGlossScan 调用共享 —— 保证幂等（全页每词只注一次）。 */
  var seenTerms = {};

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
    var terms = getSortedGloss();
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

      seenTerms[found.term] = true;
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
    if (getLang() !== "zh") return; // 英文模式整体不扫

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
