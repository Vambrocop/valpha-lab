/* vp_gloss.js — Valpha Lab 共享词汇注解组件 v1.0
   依赖：无（dependency-free）。同源自托管，不引境外 CDN。
   用法：<script src="vp_gloss.js"></script>
         vpAnnotate(text) → 返回 HTML 字符串，可直接赋给 innerHTML。
   规则：
     · 仅标注首次出现的术语；
     · 若术语紧跟 （ 或 ( 则跳过（LLM 已自解释）；
     · 当前语言为 'en' 时安全转义后原样返回（不注解）；
     · 输入为纯文本（LLM 输出），先整体转义再注入受控 tooltip 标记 → XSS 安全。
*/
(function(win){
  "use strict";

  /* ── 词汇表 ─────────────────────────────────────────────────────
     每条：[术语, 一句大白话解释（不含新术语、初中生能懂）]

     JUDGMENT POINT — 跳过的术语（说明原因，诚实为先，不猜不收）：
       · "体制"（regime）：本站特定技术词，大白话容易过度简化含义，跳过
       · "共动"（co-movement）：本站特定因子名，平白解释易产生歧义，跳过
       · "分位"：本站多处用法不同（百分位 vs 分位数 vs tier），无统一注解，跳过
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
    ["置信",     "结论有多可靠的把握程度，置信度高说明这个判断经过了更严格的统计检验"]
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

  /* ── 主函数 ──────────────────────────────────────────────────── */

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

      /* 构造 tooltip 标记（term 和 exp 均来自常量，无需再转义） */
      var tooltip =
        '<span class="vp-term" tabindex="0">' +
          term +
          '<span class="vp-tip" role="tooltip">' + exp + '</span>' +
        '</span>';

      /* 仅替换当前找到的第一次出现 */
      safe = safe.slice(0, pos) + tooltip + safe.slice(pos + term.length);
      marked[term] = true;
      /* 注：下一轮 indexOf 会在新字符串中重新搜索，天然跳过刚插入的标记 */
    }

    return safe;
  }

  /* 暴露到全局 */
  win.vpAnnotate = vpAnnotate;
  /* win.vpGloss 仅供调试，生产不依赖 */
  win.vpGloss = GLOSS;

}(window));
