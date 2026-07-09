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
})();
