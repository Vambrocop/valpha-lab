/* vp_spark.js — D2 微图表层：零依赖内联 SVG 微图（sparkline + 位置条）。
   用途：①倾向分30日走势(index/dashboard hero) ②模型概率60日走势(dashboard 信号面板)
        ③体制成分历史分位位置条(market_regime) ④恐惧贪婪7点走势(app-4 恐贪卡)。
   语义纪律：走势线只用中性色(--acc/--mut)——绝不因"最近在涨"染红绿（装饰不造信号感）；
   位置条属描述性成分（自带体制 label），极端分位允许 --amb 引起注意（注意≠红绿灯）。
   镜像：vp_*.js 前缀被 tools/check_docs_mirror.py 自动守卫——改动后必须 cp 到 docs/。 */
(function () {
  "use strict";

  // vpSpark(el, values, opts) — 内联 SVG 折线。
  // values: 数值数组（NaN/null 跳过但保留时间轴间距）；≤1 个有效点 → 不画（el 留空，不装样子）。
  // opts: { color(线色,默认 var(--acc)), fill(true=半透明面积), w,h(默认 120×28),
  //         refLine(可选水平参考线值，纳入值域) }
  window.vpSpark = function (el, values, opts) {
    if (!el) return;
    el.innerHTML = "";
    opts = opts || {};
    var w = opts.w || 120, h = opts.h || 28, pad = 2.5;
    var hasRef = opts.refLine !== null && opts.refLine !== undefined && isFinite(Number(opts.refLine));
    var pts = [];
    (values || []).forEach(function (v, i) {
      var n = Number(v);
      if (v !== null && v !== undefined && v !== "" && isFinite(n)) pts.push([i, n]);
    });
    if (pts.length <= 1) return;                       // 数据不足 → 留空
    var ys = pts.map(function (p) { return p[1]; });
    var lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys);
    if (hasRef) { lo = Math.min(lo, Number(opts.refLine)); hi = Math.max(hi, Number(opts.refLine)); }
    if (hi - lo < 1e-9) { hi += 0.5; lo -= 0.5; }      // 全平线也画得出（水平居中）
    var span = Math.max(1, (values || []).length - 1);
    var X = function (i) { return (pad + (w - 2 * pad) * (i / span)).toFixed(1); };
    var Y = function (v) { return (h - pad - (h - 2 * pad) * ((v - lo) / (hi - lo))).toFixed(1); };
    var color = opts.color || "var(--acc)";
    var d = pts.map(function (p, k) { return (k ? "L" : "M") + X(p[0]) + " " + Y(p[1]); }).join("");
    var svg = '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + " " + h +
      '" aria-hidden="true" style="display:block;max-width:100%;overflow:visible">';
    if (opts.fill) {
      svg += '<path d="' + d + "L" + X(pts[pts.length - 1][0]) + " " + (h - pad) +
        "L" + X(pts[0][0]) + " " + (h - pad) + 'Z" style="fill:' + color + ';opacity:.12;stroke:none"></path>';
    }
    if (hasRef) {
      var ry = Y(Number(opts.refLine));
      svg += '<line x1="' + pad + '" y1="' + ry + '" x2="' + (w - pad) + '" y2="' + ry +
        '" stroke-dasharray="3 3" style="stroke:var(--mut);opacity:.45;stroke-width:1"></line>';
    }
    svg += '<path d="' + d + '" style="fill:none;stroke:' + color +
      ';stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round"></path>';
    var last = pts[pts.length - 1];
    svg += '<circle cx="' + X(last[0]) + '" cy="' + Y(last[1]) + '" r="2" style="fill:' + color + '"></circle>';
    el.innerHTML = svg + "</svg>";
  };

  // vpPosBar(el, pct, opts) — 水平轨道 + 游标点（历史分位 0–100 的当前位置，非时间序列）。
  // opts: { color(游标色,默认 var(--acc)), label(aria-label/title 说明), w(默认 84) }
  window.vpPosBar = function (el, pct, opts) {
    if (!el) return;
    el.innerHTML = "";
    var n = Number(pct);
    if (!isFinite(n)) return;                          // 无分位 → 留空
    n = Math.max(0, Math.min(100, n));
    opts = opts || {};
    var color = opts.color || "var(--acc)";
    var w = opts.w || 84;
    var lbl = String(opts.label || Math.round(n) + "/100").replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
    el.innerHTML =
      '<span role="img" aria-label="' + lbl + '" title="' + lbl + '"' +
      ' style="position:relative;display:inline-block;vertical-align:middle;width:' + w + 'px' +
      ';max-width:100%;height:6px;border-radius:3px;background:var(--border,rgba(255,255,255,.14))">' +
      '<span style="position:absolute;top:50%;left:' + n.toFixed(1) + '%;transform:translate(-50%,-50%);' +
      'width:8px;height:8px;border-radius:50%;background:' + color + '"></span></span>';
  };

  // vpRangeBar(chartId, opts) — D3 复用组件：Plotly 图表时间范围切换条。
  // 用途：日期轴较长的图(chart-price 26年/chart-signal-history/chart-equity/chart-stock 等)
  // 上方注入 1月/6月/1年/5年/全部 五档按钮；点击只 Plotly.relayout() 改显示范围，纯前端、
  // 绝不重拉数据——图上任何均线/统计标注都是全量算好的常量，relayout 只是缩放视窗，不触发
  // 任何重算（这是红线：若哪天有人在这个按钮的回调里加了指标重算，那是 bug）。
  // opts: { dates(推荐显式传入的日期数组——用图自己的 x 轴数组，比反射 Plotly 内部状态更可靠可控;
  //         不传时退化为读 el.data 里第一条含 x 的 trace，尽力而为) }
  // 语义纪律：范围起点＝数据末日往回推（取 dates 数组末值，不用「今天」——数据可能滞后）；
  // 数据跨度不足某档时该档 disabled 置灰、不接受点击；"全部"用 xaxis.autorange:true。
  // 挂载位置：紧邻图表容器*正上方*的兄弟节点（不写进图表 div 内部）——Plotly.newPlot 每次
  // 重画都会清空目标 div 的全部内容，塞进去的按钮会被一并吃掉；挂在兄弟节点上则重画完全不
  // 影响它。调用方只需在每次 Plotly.newPlot(chartId,...) 之后固定调用一次 vpRangeBar(chartId,
  // opts)：首次挂载会创建按钮行；之后每次重画后再调用同一 chartId 都会原地刷新（数据末日/
  // 语言/可用档位都可能变了），不会重复插入——chart-stock 换股重画同理"保活"。
  window.vpRangeBar = function (chartId, opts) {
    var chartEl = document.getElementById(chartId);
    if (!chartEl || typeof window.Plotly === "undefined") return;
    opts = opts || {};

    var barId = chartId + "-rangebar";
    var bar = document.getElementById(barId);
    if (!bar) {
      bar = document.createElement("div");
      bar.id = barId;
      bar.className = "vp-rangebar";
      bar.setAttribute("role", "group");
      if (chartEl.parentNode) chartEl.parentNode.insertBefore(bar, chartEl);
    }

    // 日期来源：优先 opts.dates（调用方已有的 x 数组，最可靠）；否则尽力从 el.data 读第一条
    // 含 x 的 trace（Plotly.newPlot 内部会同步把 traces 挂到 el.data 上）。
    var xs = (opts.dates && opts.dates.length > 1) ? opts.dates : null;
    if (!xs) {
      var traces = chartEl.data || [];
      for (var i = 0; i < traces.length; i++) {
        if (traces[i] && traces[i].x && traces[i].x.length > 1) { xs = traces[i].x; break; }
      }
    }
    if (!xs || xs.length < 2) { bar.innerHTML = ""; bar.style.display = "none"; return; } // 数据不足 → 不装样子

    var endD = new Date(xs[xs.length - 1]);
    var startD = new Date(xs[0]);
    if (isNaN(endD.getTime()) || isNaN(startD.getTime())) { bar.innerHTML = ""; bar.style.display = "none"; return; }
    bar.style.display = "flex";

    // 按月回退：先归到月初再减月份，避免月末日期"跳月"漂移
    // （例：1/31 减 1 月不该落到 2/31 这种不存在的日期，应落到 2 月最后一天）。
    function shiftBack(d, months) {
      var r = new Date(d.getTime());
      var day = r.getDate();
      r.setDate(1);
      r.setMonth(r.getMonth() - months);
      var lastDay = new Date(r.getFullYear(), r.getMonth() + 1, 0).getDate();
      r.setDate(Math.min(day, lastDay));
      return r;
    }
    function isoDate(d) { return d.toISOString().slice(0, 10); }

    var TOL_MS = 3 * 86400000; // 3天容差：交易日历与自然月/年边界错位（周末/节假日）不误判"跨度不足"
    var TIERS = [
      { key: "1m", months: 1 },
      { key: "6m", months: 6 },
      { key: "1y", months: 12 },
      { key: "5y", months: 60 },
      { key: "all", months: null },
    ];
    var LABELS = {
      "1m": function () { return vpL("1月", "1M"); },
      "6m": function () { return vpL("6月", "6M"); },
      "1y": function () { return vpL("1年", "1Y"); },
      "5y": function () { return vpL("5年", "5Y"); },
      "all": function () { return vpL("全部", "All"); },
    };
    function vpL(zh, en) {
      // 复用全站 vpL；未加载时（理论上不会——vp_i18n.js 先于 vp_spark.js 加载）退化中文，不崩。
      return (typeof window.vpL === "function") ? window.vpL(zh, en) : zh;
    }

    // 存到 bar 上，供下面"只绑定一次"的委托点击处理器随时读最新值——避免 chart-stock 换股后
    // 用到上一次挂载时的旧闭包（stale endD/startD/chartId）。
    bar._vpState = { chartId: chartId, endD: endD, startD: startD, shiftBack: shiftBack, isoDate: isoDate, tol: TOL_MS };

    function renderButtons(activeTier) {
      bar.innerHTML = "";
      TIERS.forEach(function (t) {
        var disabled = false;
        if (t.months != null) {
          var tierStart = shiftBack(endD, t.months);
          disabled = tierStart.getTime() < (startD.getTime() - TOL_MS);
        }
        var active = t.key === activeTier;
        var b = document.createElement("button");
        b.type = "button";
        b.className = "vp-rangebar-btn" + (active ? " active" : "");
        b.dataset.tier = t.key;
        b.textContent = LABELS[t.key]();
        b.disabled = disabled;
        b.setAttribute("aria-pressed", active ? "true" : "false");
        bar.appendChild(b);
      });
    }
    renderButtons("all"); // 每次挂载都紧跟在 Plotly.newPlot 之后——图刚画完是默认全量视图，当前档＝"全部"

    if (!bar._vpBound) {
      bar.addEventListener("click", function (e) {
        var b = e.target.closest("button[data-tier]");
        if (!b || b.disabled) return;
        var st = bar._vpState;
        if (!st || typeof window.Plotly === "undefined") return;
        var tier = b.dataset.tier;
        if (tier === "all") {
          window.Plotly.relayout(st.chartId, { "xaxis.autorange": true });
        } else {
          var months = { "1m": 1, "6m": 6, "1y": 12, "5y": 60 }[tier];
          var s = st.shiftBack(st.endD, months);
          if (s.getTime() < st.startD.getTime()) s = st.startD;
          window.Plotly.relayout(st.chartId, { "xaxis.range": [st.isoDate(s), st.isoDate(st.endD)] });
        }
        // 高亮切到当前档：直接刷新按钮状态，不必重新挂载整条组件。
        Array.prototype.forEach.call(bar.querySelectorAll("button[data-tier]"), function (bb) {
          var isActive = bb.dataset.tier === tier;
          bb.classList.toggle("active", isActive);
          bb.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
      });
      bar._vpBound = true;
    }
  };
})();
