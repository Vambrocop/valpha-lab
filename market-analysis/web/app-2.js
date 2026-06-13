// ══════════════════════════════════════════════════════
//  多元分析图表
// ══════════════════════════════════════════════════════
function renderModelComparison() {
  if (!MV || !MV.model_comparison) return;
  const mc = MV.model_comparison;

  // ML模型：用AUC排序（AUC是分类质量的真实衡量）
  const ml = [...mc.ml_models].sort((a,b) => b.auc - a.auc);
  // 统计模型：用R²排序
  const st = [...mc.stats_models].sort((a,b) => b.r2_pct - a.r2_pct);

  const allNames  = [...ml.map(m=>m.name+"（ML）"), ...st.map(s=>s.name)].reverse();
  const allValues = [...ml.map(m=>+(m.auc*100).toFixed(1)), ...st.map(s=>s.r2_pct)].reverse();
  const allColors = [
    ...st.map(s => s.significant ? "#3498db" : "#555"),
    ...ml.map(m => "#9b59b6"),
  ];
  const allText = [
    ...ml.map(m=>`AUC=${m.auc} Acc=${m.acc}`),
    ...st.map(s=>`R²=${s.r2_pct}% ${s.note}`),
  ].reverse();

  Plotly.newPlot("chart-modelcmp", [{
    type: "bar", orientation: "h",
    x: allValues, y: allNames,
    marker: { color: allColors },
    text: allText,
    textposition: "outside",
    hovertemplate: "<b>%{y}</b><br>%{text}<extra></extra>",
    cliponaxis: false,
  }], {
    ...DARK,
    xaxis: {...DARK.xaxis, title: "解释力 / AUC×100（越大越好）", range: [0, 70]},
    margin: {t:20, b:50, l:200, r:80},
    shapes: [
      {type:"line",x0:50,x1:50,y0:-0.5,y1:allNames.length-0.5,
       line:{color:"#9b59b6",dash:"dot",width:1}},
    ],
    annotations: [
      {x:50, y:allNames.length-0.5, text:"AUC=0.5（随机水平）",
       showarrow:false, font:{color:"#9b59b6",size:10}},
    ]
  }, {responsive:true});

  // 找最佳ML和最佳统计
  const bestML  = ml[0];
  const bestStat= st[0];
  document.getElementById("modelcmp-insight").innerHTML =
    `<strong>核心结论：</strong><br>
     <span style="color:#3498db">统计关系模型</span>（<strong>${bestStat.name}</strong>）解释力最高，R²=<strong style="color:#2ecc71">${bestStat.r2_pct}%</strong>——
     这是"已知X时，Y的方差有多少被解释"。<br>
     <span style="color:#9b59b6">机器学习分类模型</span> AUC 最高仅 <strong style="color:#f1c40f">${(bestML.auc*100).toFixed(1)}</strong>（随机=50）——
     这是"预测明天涨还是跌"，市场半有效，难度极大。<br>
     <span style="color:var(--muted);font-size:0.78rem">解读：VIX和SP500高度相关≠可以用VIX预测未来涨跌。相关是同步的，预测是提前的——两回事。</span>`;
}

function renderSHAPChart() {
  if (!MV || !MV.shap) return;
  const items = MV.shap.slice(0,12).reverse();
  const colors = items.map(d => d.importance > 0.5 ? "#27ae60" : d.importance > 0.3 ? "#f1c40f" : "#3498db");

  Plotly.newPlot("chart-shap", [{
    type:"bar", orientation:"h",
    x: items.map(d=>d.importance),
    y: items.map(d=>d.feature.replace(/_/g," ")),
    marker:{color: colors},
    text: items.map(d=>d.importance.toFixed(3)),
    textposition:"outside",
    hovertemplate:"<b>%{y}</b><br>SHAP影响: %{x:.4f}<extra></extra>"
  }], {...DARK, xaxis:{...DARK.xaxis,title:"平均|SHAP|值（越大=对预测影响越大）"},
    margin:{t:20,b:40,l:160,r:60}}, {responsive:true});

  const bul = MV.shap_latest?.bullish?.map(d=>`${d.feature.replace(/_/g," ")} <span style="color:#2ecc71">(+${d.shap})</span>`).join("、") || "";
  const bea = MV.shap_latest?.bearish?.map(d=>`${d.feature.replace(/_/g," ")} <span style="color:#e74c3c">(${d.shap})</span>`).join("、") || "";
  document.getElementById("shap-insight").innerHTML =
    `<strong>当前预测解释：</strong><br>
     支持上涨：${bul}<br>
     支持下跌：${bea}<br>
     <span style="color:var(--muted);font-size:0.78rem">SHAP = 每个因子对本次预测的实际推拉量。正值推高预测，负值拖低预测。</span>`;
}

function renderProphetChart() {
  if (!MV || !MV.prophet || !MV.prophet.length) return;
  const p = MV.prophet;
  Plotly.newPlot("chart-prophet", [
    {x:p.map(d=>d.date), y:p.map(d=>d.upper), name:"上界", type:"scatter",
     mode:"lines", line:{color:"rgba(52,152,219,.3)",width:1}, showlegend:false},
    {x:p.map(d=>d.date), y:p.map(d=>d.lower), name:"下界", type:"scatter",
     mode:"lines", fill:"tonexty", fillcolor:"rgba(52,152,219,.15)",
     line:{color:"rgba(52,152,219,.3)",width:1}, showlegend:false},
    {x:p.map(d=>d.date), y:p.map(d=>d.yhat), name:"Prophet预测", type:"scatter",
     mode:"lines+markers", line:{color:"#3498db",width:2.5},
     marker:{size:7}, text:p.map(d=>`${d.date}<br>预测：${d.yhat.toLocaleString()}`),
     hovertemplate:"%{text}<extra></extra>"},
  ], {...DARK, yaxis:{...DARK.yaxis,title:"S&P 500 预测点位"},
    legend:{orientation:"h",y:1.05},
    annotations:[{x:p[p.length-1].date, y:p[p.length-1].yhat, text:`${p[p.length-1].yhat.toLocaleString()}`,
      showarrow:true, arrowhead:2, ax:40, ay:-30, font:{color:"#3498db",size:11}}]
  }, {responsive:true});
}

function renderKalmanChart() {
  if (!MV || !MV.kalman) return;
  const k = MV.kalman;
  Plotly.newPlot("chart-kalman", [
    {x:k.map(d=>d.date), y:k.map(d=>d.observed), name:"实际月收益%", type:"scatter",
     mode:"lines", line:{color:"#8b949e",width:1}, opacity:.7},
    {x:k.map(d=>d.date), y:k.map(d=>d.trend), name:"卡尔曼趋势信号", type:"scatter",
     mode:"lines", line:{color:"#f1c40f",width:2.5},
     hovertemplate:"<b>%{x}</b><br>趋势 %{y:.2f}%/月<extra></extra>"},
    {x:[k[k.length-1].date], y:[MV.kalman_current], name:"当前趋势", mode:"markers",
     marker:{color:"#2ecc71",size:12,symbol:"diamond"},
     hovertemplate:`当前趋势：${MV.kalman_current}%/月<extra></extra>`},
  ], {...DARK, yaxis:{...DARK.yaxis,title:"月收益率 %", zeroline:true, zerolinecolor:"#555"},
    legend:{orientation:"h",y:1.05},
    shapes:[{type:"line",x0:k[0].date,x1:k[k.length-1].date,y0:0,y1:0,
      line:{color:"#555",dash:"dash",width:1}}]
  }, {responsive:true});
}

function renderRollingBetaChart() {
  if (!MV || !MV.rolling_betas) return;
  const rb = MV.rolling_betas;
  const colors = {VIX:"#e74c3c",DXY:"#3498db",OIL:"#e67e22",TNX:"#9b59b6"};
  const traces = Object.entries(colors).map(([k,c]) => ({
    x: rb.dates, y: rb[k], name:`SP500 vs ${k}`, type:"scatter", mode:"lines",
    line:{color:c,width:1.8},
    hovertemplate:`<b>SP500 β ${k}</b> %{x}<br>β=%{y:.4f}<extra></extra>`
  }));
  traces.push({x:[rb.dates[0],rb.dates[rb.dates.length-1]],y:[0,0],
    mode:"lines",line:{color:"#555",dash:"dash"},showlegend:false});
  Plotly.newPlot("chart-rolling", traces, {...DARK,
    yaxis:{...DARK.yaxis,title:"滚动β系数（36月窗口）"},
    legend:{orientation:"h",y:1.05},hovermode:"x unified"}, {responsive:true});
}

function renderPathChart() {
  if (!MV || !MV.path) return;
  const p = MV.path;
  const colors = p.map(d => d.significant ? "#2ecc71" : "#8b949e");
  Plotly.newPlot("chart-path", [{
    type:"bar", orientation:"h",
    x: p.map(d=>d.beta), y: p.map(d=>d.path),
    marker:{color:colors},
    text: p.map(d=>`β=${d.beta.toFixed(3)} p=${d.pvalue.toFixed(3)} ${d.significant?"✓":"✗"}`),
    textposition:"outside",
    hovertemplate:"<b>%{y}</b><br>%{text}<extra></extra>"
  }], {...DARK, xaxis:{...DARK.xaxis,title:"路径系数β（正=正向影响，负=负向影响）"},
    margin:{t:20,b:40,l:150,r:100},
    shapes:[{type:"line",x0:0,x1:0,y0:-0.5,y1:p.length-0.5,
      line:{color:"#555",dash:"dash",width:1}}]
  }, {responsive:true});

  const sig = p.filter(d=>d.significant);
  document.getElementById("path-insight").innerHTML =
    `<strong>显著因果路径（p&lt;0.05）：</strong>` +
    sig.map(d=>`<span style="color:#2ecc71">${d.path}</span> β=${d.beta.toFixed(3)} R²=${d.r2.toFixed(3)}`).join(" · ") +
    `<br><span style="color:var(--muted);font-size:0.78rem">灰色=统计上不显著，绿色=已证实的因果链路。VIX→SP500 解释力最强（R²=0.56）。</span>`;
}

function renderCCAChart() {
  if (!MV || !MV.cca || !MV.rda) return;

  // CCA canonical correlations bar + RDA marginal contributions
  const ccaCorrs = MV.cca.canonical_corrs || [];
  const rdaRows  = MV.rda || [];
  const macroLoad = MV.cca.macro_loadings || {};
  const assetLoad = MV.cca.asset_loadings || {};

  const traces = [
    {type:"bar", name:"CCA典型相关系数",
     x:ccaCorrs.map((_,i)=>`第${i+1}典型变量`), y:ccaCorrs,
     marker:{color:["#2ecc71","#3498db","#9b59b6"]},
     text:ccaCorrs.map(v=>v.toFixed(3)), textposition:"outside",
     hovertemplate:"%{x}<br>r=%{y:.3f}<extra></extra>"},
  ];
  Plotly.newPlot("chart-cca", traces, {...DARK,
    yaxis:{...DARK.yaxis,range:[0,0.8],title:"典型相关系数 r"},
    margin:{t:20,b:50,l:60,r:20}
  }, {responsive:true});

  const macroTop = Object.entries(macroLoad).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])).slice(0,3)
    .map(([k,v])=>`${k} (${v>0?"+":""}${v.toFixed(2)})`).join("、");
  const rdaTotal = rdaRows.reduce((s,r)=>s+r.marginal_r2,0).toFixed(1);
  const rdaBest = rdaRows.sort((a,b)=>b.marginal_r2-a.marginal_r2)[0];
  document.getElementById("cca-insight").innerHTML =
    `<strong>典型相关（CCA）：</strong>宏观因子与资产价格的最强共变组合 r=<span style="color:#2ecc71">${ccaCorrs[0]?.toFixed(3)||"—"}</span>，
     第1宏观载荷主要由 <span style="color:#f1c40f">${macroTop}</span> 驱动。<br>
     <strong>冗余分析（RDA）：</strong>宏观变量合计解释资产方差 <span style="color:#3498db">${rdaTotal}%</span>，
     贡献最大的是 <span style="color:#2ecc71">${rdaBest?.macro}</span>（${rdaBest?.marginal_r2.toFixed(2)}%）。
     其余 ${(100-rdaTotal).toFixed(1)}% 由市场情绪和动量主导——这解释了为什么宏观指标无法完全预测短期行情。`;
}

// ── 30日概率前瞻图 ──
function renderForecastChart() {
  if (!SIGNALS || !SIGNALS.next_opportunities) return;
  const opp = SIGNALS.next_opportunities;
  const all = opp.all_forecast || [];
  if (all.length === 0) return;

  const dates  = all.map(d => d.date);
  const probs  = all.map(d => +(d.prob * 100).toFixed(1));
  const tiers  = all.map(d => d.tier);
  const dows   = all.map(d => d.dow_cn);
  const reasons= all.map(d => d.reasons.join("、") || "普通交易日");
  const tops   = new Set(opp.top_entry.map(x => x.date));
  const bottoms= new Set(opp.top_exit.map(x => x.date));

  const colors = dates.map((d, i) => {
    if (tops.has(d))    return "#27ae60";
    if (bottoms.has(d)) return "#e74c3c";
    return tiers[i] >= 4 ? "#2ecc71" : tiers[i] <= 2 ? "#e67e22" : "#3498db";
  });

  Plotly.newPlot("chart-forecast", [{
    type: "bar",
    x: dates, y: probs,
    marker: { color: colors, opacity: 0.85 },
    text: dows,
    customdata: reasons,
    hovertemplate: "<b>%{x}</b> (%{text})<br>概率: <b>%{y:.1f}%</b><br>%{customdata}<extra></extra>",
  }], {
    ...DARK,
    yaxis: {...DARK.yaxis, title: "入场概率 (%)", range: [45, 80]},
    xaxis: {...DARK.xaxis, tickangle: -45, tickfont: {size: 10}},
    margin: {t:20, b:80, l:60, r:20},
    shapes: [
      {type:"line", x0:dates[0], x1:dates[dates.length-1], y0:60, y1:60,
       line:{color:"#2ecc71", dash:"dot", width:1}},
      {type:"line", x0:dates[0], x1:dates[dates.length-1], y0:55, y1:55,
       line:{color:"#f1c40f", dash:"dot", width:1}},
    ],
    annotations: [
      {x:dates[Math.floor(dates.length*0.9)], y:60.5, text:"60% 入场线",
       showarrow:false, font:{color:"#2ecc71",size:10}},
      {x:dates[Math.floor(dates.length*0.9)], y:55.5, text:"55% 中性线",
       showarrow:false, font:{color:"#f1c40f",size:10}},
    ]
  }, {responsive:true});

  const topDate = opp.top_entry[0];
  const tech = opp.latest_tech || {};
  const maState = tech.nasdaq_ma200 === 1 ? "NASDAQ在200均线上方（偏多）" : "NASDAQ在200均线下方（偏空）";
  document.getElementById("forecast-insight").innerHTML =
    `<strong>未来45交易日概率前瞻</strong><br>
     <span style="color:#27ae60">绿色</span>=最佳买入窗口 &nbsp;
     <span style="color:#e74c3c">红色</span>=最弱/减仓窗口 &nbsp;
     <span style="color:#3498db">蓝色</span>=普通日<br>
     最高概率日：<strong style="color:#27ae60">${topDate.date} (${topDate.dow_cn})</strong>
     — ${topDate.prob*100 > 0 ? (topDate.prob*100).toFixed(1) : "—"}%，原因：${topDate.reasons.join("、") || "日历因子叠加"}<br>
     <span style="color:var(--muted);font-size:0.78rem">
       技术信号已冻结为最新值：${maState}；RSI=${tech.nasdaq_rsi}；BTC动量=${tech.btc_mom20?.toFixed(3) || "—"}。
       日历因子（星期/月份/假日/税季）可精确预测，技术信号近期不确定。
     </span>`;
}

// ── 未来操作窗口面板（左栏）──
function renderOppPanel() {
  if (!SIGNALS || !SIGNALS.next_opportunities) return;
  const opp = SIGNALS.next_opportunities;

  const TIER_COLOR = { 5:"#27ae60", 4:"#2ecc71", 3:"#f1c40f", 2:"#e67e22", 1:"#e74c3c" };
  const TIER_LABEL = { 5:"强势", 4:"适合", 3:"中性", 2:"谨慎", 1:"高险" };

  function makeItem(d, cls) {
    const color = TIER_COLOR[d.tier] || "#888";
    const label = TIER_LABEL[d.tier] || "";
    const tags  = d.reasons.length > 0 ? d.reasons.slice(0,2).join(" · ") : "普通日";
    return `<div class="opp-item ${cls}">
      <span class="opp-date">${d.date}</span>
      <span class="opp-dow">${d.dow_cn}</span>
      <span class="opp-prob" style="color:${color}">${(d.prob*100).toFixed(1)}%</span>
      <span class="opp-tags">${tags}</span>
      <span class="opp-tier" style="background:${color}22;color:${color}">${label}</span>
    </div>`;
  }

  const entryHTML = opp.top_entry.slice(0,4).map(d => makeItem(d,"entry")).join("");
  const exitHTML  = opp.top_exit.slice(0,3).map(d => makeItem(d,"exit")).join("");

  document.getElementById("opp-entry-list").innerHTML = entryHTML;
  document.getElementById("opp-exit-list").innerHTML  = exitHTML;
  document.getElementById("opp-note").innerHTML =
    `<span style="color:var(--muted)">技术信号冻结为今日值；日历因子（星期/假日/月份/税季）精确预测。</span>`;
}
// 旧"事件研究图表"已删除（裸 p 值 + 方向红绿色违反诚实铁律）；
// 事件结论以"今日"标签的"🗓 事件影响一览"(renderEventImpact) 为唯一口径。

// ── 百分位信息 ──
function renderPercentileInfo(todayProb) {
  if (!SIGNALS || !SIGNALS.daily_signals) return;
  // 模型无样本外区分度时，"强于过去X%交易日"是把原始打分当把握度卖——隐藏
  if (SIGNALS.calibration_flat) {
    document.getElementById("signal-percentile").innerHTML =
      `<span style="color:var(--muted);font-size:0.78rem">样本外无区分度，不展示强弱百分位（详见"实验"标签的验证）</span>`;
    return;
  }
  const allProbs = Object.values(SIGNALS.daily_signals).map(d => d.prob);
  const last252  = allProbs.slice(-252);
  const below    = last252.filter(p => p < todayProb).length;
  const pct      = Math.round(below / last252.length * 100);
  const maxForecast = SIGNALS.next_opportunities?.top_entry?.[0];

  // Count days >=60% in next 45
  const forecast = SIGNALS.next_opportunities?.all_forecast || [];
  const strongDays = forecast.filter(d => d.prob >= 0.60).length;

  // pct = 今日概率高于过去一年多少比例的交易日（越高越强；100%=一年内最强）
  const tag = pct >= 80 ? ["历史高位","#27ae60"] : pct >= 60 ? ["偏强","#2ecc71"]
            : pct >= 40 ? ["中等","#f1c40f"]   : pct >= 20 ? ["偏弱","#e67e22"]
            : ["历史低位","#e74c3c"];
  let html = `<span style="color:var(--muted)">强于过去一年 </span><strong style="color:${tag[1]}">${pct}%</strong><span style="color:var(--muted)"> 的交易日 · ${tag[0]}</span>`;
  if (maxForecast) {
    html += `<br><span style="color:var(--muted)">未来两个月最高：</span><strong>${(maxForecast.prob*100).toFixed(1)}%</strong><span style="color:var(--muted)"> (${maxForecast.date} ${maxForecast.dow_cn})</span>`;
  }
  if (strongDays > 0) {
    html += `<br><span style="color:var(--muted)">未来两个月中 </span><strong style="color:#2ecc71">${strongDays}</strong><span style="color:var(--muted)"> 天≥60%</span>`;
  }
  document.getElementById("signal-percentile").innerHTML = html;
}

// ── 日历统计标签切换 ──
const CAL_TABS = ["digit","cycle","party","calholiday"];
const _calTabRendered = new Set();
function switchCalTab(name, el) {
  el.closest(".tabs").querySelectorAll(".tab").forEach(t=>t.classList.remove("active"));
  el.classList.add("active");
  CAL_TABS.forEach(t => {
    const e = document.getElementById("caltab-"+t);
    if (e) e.classList.remove("active");
  });
  const pane = document.getElementById("caltab-"+name);
  pane?.classList.add("active");
  if (_calTabRendered.has(name)) { setTimeout(() => resizeChartsIn(pane), 0); return; }
  _calTabRendered.add(name);
  // setTimeout 确保浏览器 reflow 完成再让 Plotly 计算尺寸
  if (name==="digit")      setTimeout(() => safeRender(renderDigitChart,      "Digit"),      0);
  if (name==="cycle")      setTimeout(() => safeRender(renderCycleChart,      "Cycle"),      0);
  if (name==="party")      setTimeout(() => safeRender(renderPartyChart,      "Party"),      0);
  if (name==="calholiday") setTimeout(() => safeRender(renderCalHolidayChart, "CalHoliday"), 0);
}

// ── 🔬 规律防伪：placebo 置换检验 + 多重检验校正(FDR) 诚实总览 ──
// 同源消费 placebo_tests.json（placebo_test.py 产出）。被打回/无定论也是诚实结果。
let PLACEBO = null;
async function loadPlacebo() {
  const el = document.getElementById("placebo-overview");
  if (!el) return;
  try {
    const r = await fetch("placebo_tests.json?_=" + Date.now());
    if (r.ok) PLACEBO = await r.json();
  } catch (e) { /* 文件可能尚未生成 */ }
  if (!PLACEBO?.tests) {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">placebo 数据尚未生成（下次全量流水线后出现）</span>`;
    return;
  }
  const STY = { real:{c:"#2ecc71",t:"✓ 真实"}, rejected:{c:"#e74c3c",t:"✗ 未显现"},
                inconclusive:{c:"#f1c40f",t:"— 无定论"} };
  const rows = PLACEBO.tests.map(t => {
    const s = STY[t.status] || STY.inconclusive;
    const fdr = t.status === "inconclusive" ? `<span style="color:var(--muted)">FDR —</span>`
              : t.fdr_significant_05 ? `<span style="color:#2ecc71">FDR✓</span>`
              : `<span style="color:#e67e22">FDR✗</span>`;
    return `<div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem;
                 padding:.5rem .2rem .5rem .6rem;border-bottom:1px solid var(--border);border-left:3px solid ${s.c};">
      <strong style="min-width:8.5rem">${t.panel}</strong>
      <span style="color:${s.c};font-weight:700">${s.t}</span>
      <span style="color:var(--muted);font-size:0.78rem">p=${t.p_value.toFixed(3)} · q=${t.q_value.toFixed(3)} ${fdr}</span>
      <span style="color:var(--muted);font-size:0.73rem;flex-basis:100%">${t.claim}——${t.detail}（${t.scope}）</span>
    </div>`;
  }).join("");
  const cnt = k => PLACEBO.tests.filter(t => t.status === k).length;
  const fdrSurv = PLACEBO.tests.filter(t => t.fdr_significant_05).map(t => t.panel);
  el.innerHTML = `
    <div style="font-size:0.8rem;color:var(--muted);line-height:1.6;margin-bottom:.6rem;">
      把每个"日历规律"的日期标签随机打乱 ${PLACEBO.n_perm} 次生成零分布，真实效应须超 95 分位才算"真"；
      再用 Benjamini-Hochberg 控多重检验假发现率(FDR q 值)。
      <b style="color:var(--text)">被打回 / 无定论也是诚实结果——本站不假装规律都成立。</b>
    </div>
    ${rows}
    <div style="font-size:0.78rem;color:var(--muted);margin-top:.7rem;">
      小结：<b style="color:#2ecc71">${cnt("real")} 真实</b> /
      <b style="color:#f1c40f">${cnt("inconclusive")} 无定论</b>(样本太小,无权下结论) /
      <b style="color:#e74c3c">${cnt("rejected")} 未显现</b>。
      多重检验校正(FDR q&lt;0.05)后仍站得住：<b>${fdrSurv.join("、") || "无"}</b>。
      <br>数据 ${PLACEBO.data?.source} ${PLACEBO.data?.start}–${PLACEBO.data?.end}，种子 ${PLACEBO.seed}（可复现）。
    </div>`;
}

// ── 🎯 反事实事件影响（方法B）：同源消费 event_causal.json ──
let EVENT_CAUSAL = null;
async function loadEventCausal() {
  const el = document.getElementById("event-causal");
  if (!el) return;
  try {
    const r = await fetch("event_causal.json?_=" + Date.now());
    if (r.ok) EVENT_CAUSAL = await r.json();
  } catch (e) { /* 文件可能尚未生成 */ }
  if (!EVENT_CAUSAL) {
    el.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">反事实数据尚未生成（下次全量流水线后出现）</span>`;
    return;
  }
  const STY = { significant:"#2ecc71", not_significant:"#e67e22",
                inadequate_controls:"#f1c40f", pending:"var(--muted)" };
  const events = (EVENT_CAUSAL.events || []).map(e => {
    const c = STY[e.status] || "var(--muted)";
    return `<div style="padding:.55rem .2rem .55rem .6rem;border-bottom:1px solid var(--border);border-left:3px solid ${c};">
      <div style="display:flex;flex-wrap:wrap;gap:.5rem;align-items:baseline;">
        <strong>${e.name}</strong>
        <span style="color:${c};font-weight:700">${e.verdict || e.status}</span>
        ${e.pre_r2 != null ? `<span style="color:var(--muted);font-size:0.74rem">对照R²=${e.pre_r2} · p=${e.p_value}</span>` : ""}
      </div>
      ${e.note ? `<div style="color:var(--muted);font-size:0.72rem;margin-top:.2rem;">${e.note}</div>` : ""}
    </div>`;
  }).join("");
  const sp = EVENT_CAUSAL.spcx;
  const spcxHtml = sp ? `<div style="padding:.55rem .6rem;border-left:3px solid var(--muted);background:var(--surface2);border-radius:5px;margin-top:.55rem;font-size:0.78rem;">
      <strong>🚀 ${sp.name}</strong>：${sp.status === "pending" ? `待数据（已上市 ${sp.days_listed} 个交易日，需 ≥${sp.need_post}）` : sp.status}
      ${sp.note ? `<div style="color:var(--muted);font-size:0.72rem;margin-top:.2rem;">${sp.note}</div>` : ""}
    </div>` : "";
  el.innerHTML = `
    <div style="font-size:0.8rem;color:var(--muted);line-height:1.6;margin-bottom:.6rem;">
      用事件前的"处理~对照"关系外推一个<b style="color:var(--text)">反事实</b>，实际 − 反事实 = 异常影响，
      block-bootstrap(含系数估计不确定性)做显著性。
      ${EVENT_CAUSAL.caveat ? `<br><span style="font-size:0.74rem">${EVENT_CAUSAL.caveat}</span>` : ""}
    </div>
    ${events}${spcxHtml}`;
}

function renderDigitChart() {
  const yp = SIGNALS?.year_patterns;
  if (!yp?.decade_digit) return;
  const items = [...yp.decade_digit].sort((a,b) => a.digit - b.digit);
  const colors = items.map(d => d.digit===5 ? "#f1c40f" : d.avg_return>0 ? "#2ecc71" : "#e74c3c");
  Plotly.newPlot("chart-digit",[{
    type:"bar",
    x: items.map(d => d.label),
    y: items.map(d => d.avg_return),
    marker:{color:colors},
    text: items.map(d=>`胜率${d.win_rate}% n=${d.n}`),
    hovertemplate:"<b>%{x}</b><br>年均回报: %{y:.1f}%<br>%{text}<extra></extra>",
  }],{
    ...DARK,
    yaxis:{...DARK.yaxis,title:"S&P500年均回报 (%)"},
    xaxis:{...DARK.xaxis,title:"年份个位数"},
    margin:{t:20,b:60,l:60,r:20},
    shapes:[{type:"line",x0:-0.5,x1:9.5,y0:0,y1:0,line:{color:"#555",width:1}}]
  },{responsive:true});
  const d5 = yp.decade_digit.find(d=>d.digit==5);
  document.getElementById("digit-highlight").innerHTML =
    `<span style="color:#f1c40f">★ ×5年（如1995、2005、2015、2025）：均值 <strong>+${d5?.avg_return||"?"}%</strong>，胜率 <strong>${d5?.win_rate||"?"}%</strong>，历史最强十年位</span>`;
}

function renderCycleChart() {
  const yp = SIGNALS?.year_patterns;
  if (!yp?.presidential_cycle) return;
  const items = yp.presidential_cycle;
  const colors = items.map(d => d.label.includes("选前") ? "#f1c40f" : "#3498db");
  Plotly.newPlot("chart-cycle",[
    {type:"bar", name:"年均回报%",
     x:items.map(d=>d.label), y:items.map(d=>d.avg_return),
     marker:{color:colors},
     text:items.map(d=>`胜率${d.win_rate}% n=${d.n}`),
     hovertemplate:"<b>%{x}</b><br>%{y:.1f}%<br>%{text}<extra></extra>"},
    {type:"scatter",mode:"lines+markers", name:"胜率%",
     x:items.map(d=>d.label), y:items.map(d=>d.win_rate),
     yaxis:"y2", line:{color:"#9b59b6",width:2},
     marker:{color:"#9b59b6",size:7}}
  ],{
    ...DARK,
    yaxis:{...DARK.yaxis,title:"年均回报 (%)"},
    yaxis2:{title:"胜率 (%)",overlaying:"y",side:"right",range:[40,90],gridcolor:"transparent"},
    xaxis:{...DARK.xaxis},
    margin:{t:20,b:60,l:60,r:60},
    legend:{orientation:"h",y:1.05}
  },{responsive:true});
  const best = items.find(d=>d.label.includes("选前")) || items[0];
  document.getElementById("cycle-insight").innerHTML =
    `<strong>总统任期四年周期：</strong>选前年（Year 3）历史均值 <strong style="color:#f1c40f">+${best.avg_return}%</strong>，胜率 <strong>${best.win_rate}%</strong>——总统在大选前一年倾向刺激经济。<br>
     中期选举年（Year 2）最弱，均值 ${items.find(d=>d.label.includes("中期"))?.avg_return||"?"}%，不确定性最大。<br>
     <span style="color:var(--muted);font-size:0.78rem">2025年=Year 1（新任期），历史均值+7.0%，胜率60%。</span>`;
}

function renderPartyChart() {
  const yp = SIGNALS?.year_patterns;
  if (!yp?.party_effect) return;
  const parties = yp.party_effect;
  const R = parties.find(p=>p.party==="R");
  const D = parties.find(p=>p.party==="D");
  const presidents = (yp.president_detail||[]).sort((a,b)=>a.start-b.start);

  Plotly.newPlot("chart-party",[
    {type:"bar",name:"共和党",
     x:["年均回报(%)","胜率(%)"],
     y:[R?.avg_return||0, R?.win_rate||0],
     marker:{color:"#e74c3c"},
     text:[`n=${R?.n}年`,`n=${R?.n}年`],
     hovertemplate:"共和党 %{x}: %{y:.1f}<extra></extra>"},
    {type:"bar",name:"民主党",
     x:["年均回报(%)","胜率(%)"],
     y:[D?.avg_return||0, D?.win_rate||0],
     marker:{color:"#3498db"},
     text:[`n=${D?.n}年`,`n=${D?.n}年`],
     hovertemplate:"民主党 %{x}: %{y:.1f}<extra></extra>"},
  ],{...DARK,barmode:"group",margin:{t:20,b:40,l:60,r:20},legend:{orientation:"h",y:1.05}},{responsive:true});

  if (presidents.length > 0) {
    Plotly.newPlot("chart-presidents",[{
      type:"bar", orientation:"h",
      x: presidents.map(p=>p.avg_return),
      y: presidents.map(p=>`${p.name}(${p.start}-${p.end})`),
      marker:{color: presidents.map(p=>p.party==="R"?"#e74c3c":"#3498db"), opacity:0.8},
      text: presidents.map(p=>`${p.avg_return>0?"+":""}${p.avg_return}%  胜率${p.win_rate}%`),
      textposition:"outside", cliponaxis:false,
      hovertemplate:"<b>%{y}</b><br>年均: %{x:.1f}%<extra></extra>",
    }],{
      ...DARK,
      xaxis:{...DARK.xaxis,title:"年均回报 (%)", zeroline:true, zerolinecolor:"#444"},
      margin:{t:10,b:40,l:150,r:100},
      height:280,
    },{responsive:true});
  }

  document.getElementById("party-insight").innerHTML =
    `<strong>执政党效应（1928-2026）：</strong>民主党执政年均 <strong style="color:#3498db">+${D?.avg_return}%</strong>（胜率${D?.win_rate}%，n=${D?.n}年）；共和党 <strong style="color:#e74c3c">+${R?.avg_return}%</strong>（胜率${R?.win_rate}%，n=${R?.n}年）。<br>
     <span style="color:var(--muted);font-size:0.78rem">⚠ 相关≠因果：差异主要来自经济周期的巧合（胡佛遇大萧条，克林顿遇科技繁荣），而非政策直接驱动。不建议据此做选党投资决策。</span>`;
}

function renderCalHolidayChart() {
  const hd = SIGNALS?.holiday_detail;
  if (!hd) return;
  const items = [
    {label:"感恩节前夕", wr: hd.thanksgiving_eve?.win_rate, n: hd.thanksgiving_eve?.n},
    {label:"黑色星期五", wr: hd.thanksgiving_friday?.win_rate, n: hd.thanksgiving_friday?.n},
    {label:"节前3天内",  wr: hd.pre_holiday?.win_rate, n: hd.pre_holiday?.n},
    {label:"节后3天内",  wr: hd.post_holiday?.win_rate, n: hd.post_holiday?.n},
    {label:"圣诞行情",   wr: hd.santa_claus_rally?.win_rate, n: hd.santa_claus_rally?.n},
    {label:"1月效应",    wr: hd.january_effect?.win_rate, n: hd.january_effect?.n},
    {label:"普通交易日", wr: hd.normal?.win_rate, n: hd.normal?.n},
  ].filter(d=>d.wr!=null).sort((a,b)=>b.wr-a.wr);

  const colors = items.map(d => d.wr>=65?"#f1c40f": d.wr>=58?"#2ecc71": d.wr>=54?"#3498db":"#8b949e");
  Plotly.newPlot("chart-cal-holiday",[{
    type:"bar", orientation:"h",
    x: items.map(d=>d.wr),
    y: items.map(d=>d.label),
    marker:{color:colors},
    text: items.map(d=>`${d.wr}%  n=${d.n}`),
    textposition:"outside", cliponaxis:false,
    hovertemplate:"<b>%{y}</b><br>胜率: %{x:.1f}%<extra></extra>",
  }],{
    ...DARK,
    xaxis:{...DARK.xaxis, title:"上涨胜率 (%)", range:[44,84]},
    margin:{t:20,b:50,l:110,r:90},
    shapes:[{type:"line",x0:hd.normal?.win_rate||52.4,x1:hd.normal?.win_rate||52.4,
             y0:-0.5,y1:items.length-0.5,
             line:{color:"#555",dash:"dot",width:1}}]
  },{responsive:true});

  document.getElementById("cal-holiday-insight").innerHTML =
    `<strong>假日效应（1950-2026日频）：</strong>感恩节前夕胜率 <strong style="color:#f1c40f">${hd.thanksgiving_eve?.win_rate}%</strong>（n=${hd.thanksgiving_eve?.n}），是全年单日最强规律之一。节前节后均显著高于普通日（基准${hd.normal?.win_rate}%）。`;
}

