// ═══════════════════════════════════════════════════════
//  预测 vs 实际结果 — 准确率回溯
// ═══════════════════════════════════════════════════════
function renderPredictionAccuracy() {
  if (!SIGNALS || !SIGNALS.daily_signals) return;
  const nDays = parseInt(document.getElementById("accuracy-days-select")?.value || 40);

  // Collect last N days that have actual return data
  const allDays = Object.entries(SIGNALS.daily_signals)
    .filter(([, v]) => v.ret != null)
    .sort(([a], [b]) => a.localeCompare(b));

  const recent = allDays.slice(-nDays);
  if (!recent.length) return;

  // Build result objects
  const DOW_CN = ["周一","周二","周三","周四","周五","周六","周日"];
  const rows = recent.map(([date, v]) => {
    const prob    = v.prob;
    const ret     = v.ret;           // actual % return
    const actualUp = ret > 0;
    const tier    = v.tier;
    // Signal direction: only "call" when signal is in tier 4+ (≥0.60) or tier 1-2 (≤0.40)
    let predicted = "neutral";
    if      (prob >= 0.60) predicted = "up";
    else if (prob <= 0.40) predicted = "down";
    const hasCall = predicted !== "neutral";
    const correct  = hasCall
      ? ((predicted === "up" && actualUp) || (predicted === "down" && !actualUp))
      : null;
    return { date, prob, tier, ret, actualUp, predicted, hasCall, correct, dow: v.dow };
  });

  // ── Summary stats ──────────────────────────────────────────────
  const called   = rows.filter(r => r.hasCall);
  const correct  = called.filter(r => r.correct);
  const tier45   = rows.filter(r => r.tier >= 4);
  const t45ok    = tier45.filter(r => r.correct);
  const tier12   = rows.filter(r => r.tier <= 2);
  const t12ok    = tier12.filter(r => r.correct);
  const overall  = called.length > 0 ? (correct.length / called.length * 100) : null;
  const h4Acc    = tier45.length  > 0 ? (t45ok.length  / tier45.length  * 100) : null;
  const l2Acc    = tier12.length  > 0 ? (t12ok.length  / tier12.length  * 100) : null;

  function accColor(pct) {
    if (pct == null) return "var(--muted)";
    if (pct >= 65) return "#27ae60";
    if (pct >= 55) return "#2ecc71";
    if (pct >= 45) return "#f1c40f";
    return "#e74c3c";
  }

  const summaryEl = document.getElementById("accuracy-summary");
  if (summaryEl) summaryEl.innerHTML = [
    { label:`第4-5档信号准确率`,   val:h4Acc,   n:tier45.length,  hint:"概率≥60%时，预测上涨是否正确" },
    { label:`第1-2档信号准确率`,   val:l2Acc,   n:tier12.length,  hint:"概率≤40%时，预测下跌是否正确" },
    { label:`总体有效信号准确率`,   val:overall, n:called.length,  hint:"所有非中性预测的综合准确率" },
    { label:`近${nDays}天上涨天数`, val: rows.filter(r=>r.actualUp).length / rows.length * 100,
      n:rows.length, hint:"实际市场上涨天数占比" },
  ].map(c => `
    <div class="acc-card">
      <div class="acc-card-num" style="color:${accColor(c.val)}">${c.val!=null ? c.val.toFixed(1)+"%" : "—"}</div>
      <div class="acc-card-label">${c.label}<br><span style="opacity:.7">n=${c.n}</span></div>
    </div>`).join("");

  // ── Timeline Plotly chart ───────────────────────────────────────
  const dates  = rows.map(r => r.date);
  const probs  = rows.map(r => +(r.prob * 100).toFixed(1));
  const rets   = rows.map(r => +r.ret.toFixed(2));
  const barColors = rows.map(r => {
    if (!r.hasCall) return "rgba(139,148,158,.35)";
    return r.correct ? "rgba(46,204,113,.75)" : "rgba(231,76,60,.75)";
  });
  const hoverText = rows.map(r => {
    const callStr = r.predicted === "up" ? "📈看多" : r.predicted === "down" ? "📉看空" : "中性";
    const outStr  = r.actualUp ? `+${r.ret.toFixed(2)}%↑` : `${r.ret.toFixed(2)}%↓`;
    const res     = r.hasCall ? (r.correct ? "✓正确" : "✗错误") : "中性(不计)";
    return `${r.date}<br>信号: ${callStr} (${(r.prob*100).toFixed(1)}%)<br>实际: ${outStr}<br>${res}`;
  });

  Plotly.newPlot("chart-accuracy", [
    { type:"bar", name:"预测概率%", x:dates, y:probs,
      marker:{ color: barColors },
      text: hoverText, hovertemplate:"%{text}<extra></extra>",
      width: 0.7 },
    { type:"scatter", name:"实际涨跌%", x:dates, y:rets,
      mode:"lines+markers", yaxis:"y2",
      line:{ color:"rgba(52,152,219,.8)", width:1.5 },
      marker:{ size:4, color: rets.map(r => r>0?"#2ecc71":"#e74c3c") },
      hovertemplate:"%{x}<br>实际: %{y:.2f}%<extra></extra>" },
    { type:"scatter", name:"60% 基准线", x:[dates[0],dates[dates.length-1]], y:[60,60],
      mode:"lines", line:{color:"rgba(46,204,113,.4)",dash:"dot",width:1}, hoverinfo:"skip" },
  ], {
    ...DARK,
    yaxis:  { ...DARK.yaxis, title:"预测概率 %", range:[35,90] },
    yaxis2: { overlaying:"y", side:"right", title:"实际涨跌 %", zeroline:true,
               zerolinecolor:"#444", gridcolor:"transparent", tickformat:".1f" },
    legend: { orientation:"h", y:1.08, font:{size:10} },
    margin: { t:10, b:55, l:55, r:55 },
    hovermode:"x unified",
    xaxis:  { ...DARK.xaxis, tickangle:-40, tickfont:{size:9} },
  }, { responsive:true });

  // ── Recent rows table (last 14) ───────────────────────────────
  const tableEl = document.getElementById("accuracy-table");
  if (!tableEl) return;
  const last14 = rows.slice(-14).reverse();
  const headerStyle = "color:var(--muted);font-size:0.72rem;padding:.2rem .5rem;";
  const cellStyle   = "padding:.3rem .5rem;white-space:nowrap;";
  tableEl.innerHTML = `
    <table style="width:100%;border-collapse:collapse;min-width:480px;">
      <thead><tr style="border-bottom:1px solid var(--border);">
        <th style="${headerStyle}text-align:left">日期</th>
        <th style="${headerStyle}text-align:right">预测方向</th>
        <th style="${headerStyle}text-align:right">概率</th>
        <th style="${headerStyle}text-align:right">实际涨跌</th>
        <th style="${headerStyle}text-align:center">结果</th>
      </tr></thead>
      <tbody>
      ${last14.map(r => {
        const signalStr = r.predicted === "up"
          ? `<span style="color:#2ecc71">📈 看多(T${r.tier})</span>`
          : r.predicted === "down"
          ? `<span style="color:#e74c3c">📉 看空(T${r.tier})</span>`
          : `<span style="color:var(--muted)">→ 中性(T${r.tier})</span>`;
        const retColor  = r.ret > 0 ? "#2ecc71" : r.ret < 0 ? "#e74c3c" : "var(--muted)";
        const retStr    = `<span style="color:${retColor}">${r.ret > 0 ? "+" : ""}${r.ret.toFixed(2)}%</span>`;
        const resultStr = !r.hasCall ? `<span style="color:var(--muted)">—</span>`
          : r.correct ? `<span style="color:#2ecc71;font-weight:700">✓</span>`
          : `<span style="color:#e74c3c;font-weight:700">✗</span>`;
        const todayBg   = r.date === localDateStr() ? "background:rgba(52,152,219,.07);" : "";
        return `<tr style="border-bottom:1px solid var(--border-faint);${todayBg}">
          <td style="${cellStyle}">${r.date} <span style="color:var(--muted);font-size:0.72rem">${DOW_CN[r.dow||0]}</span></td>
          <td style="${cellStyle}text-align:right">${signalStr}</td>
          <td style="${cellStyle}text-align:right;font-weight:700">${(r.prob*100).toFixed(1)}%</td>
          <td style="${cellStyle}text-align:right">${retStr}</td>
          <td style="${cellStyle}text-align:center">${resultStr}</td>
        </tr>`;
      }).join("")}
      </tbody>
    </table>
    <div style="font-size:0.72rem;color:var(--muted);margin-top:.5rem;line-height:1.5;">
      ✓/✗ 仅统计信号概率≥60%（看多）或≤40%（看空）的有效预测。中性区间(40-60%)不纳入准确率计算。
      <br>注意：本模型预测的是"统计上有利的入场时机"，不是逐日涨跌预测——单日准确率参考意义有限，多日累积效果更重要。
    </div>`;
}

// ── 回测验证图表 ──
function renderBacktestCharts() {
  // 新格式按指数分组（NASDAQ/SP500），旧格式平铺；面板展示纳指回测
  const bt = SIGNALS?.backtest?.NASDAQ || SIGNALS?.backtest;
  if (!bt || !bt.by_tier) return;

  const tiers   = bt.by_tier || [];
  const base20  = bt.baseline?.["20d"]?.win_rate || 63.1;
  const TIER_COLOR = { 1:"#e74c3c", 2:"#e74c3c", 3:"#f1c40f", 4:"#2ecc71", 5:"#27ae60" };
  const TIER_LABEL = { 1:"第1档", 2:"第2档", 3:"第3档", 4:"第4档", 5:"第5档" };

  // ── 图1：各档位实际20日胜率 ──────────────────────────────────
  const horizons = ["1d","5d","10d","20d","30d"];
  const hLabels  = ["1日","5日","10日","20日","30日"];
  const traces = tiers.map(t => ({
    type: "scatter", mode: "lines+markers",
    name: TIER_LABEL[t.tier] + `（n=${t.n}）`,
    x: hLabels,
    y: horizons.map(h => t.horizons[h]?.win_rate ?? null),
    line: { color: TIER_COLOR[t.tier] || "#3498db", width: 2 },
    marker: { size: 7 },
    hovertemplate: `<b>Tier ${t.tier} %{x}</b><br>胜率: %{y:.1f}%<extra></extra>`,
  }));
  // 基准线
  traces.push({
    type: "scatter", mode: "lines",
    name: `基准（全样本 ${base20}%）`,
    x: hLabels, y: hLabels.map(() => base20),
    line: { color: "#8b949e", dash: "dot", width: 1.5 },
    hoverinfo: "skip",
  });

  Plotly.newPlot("chart-backtest-tier", traces, {
    ...DARK,
    yaxis: {...DARK.yaxis, title: "实际上涨胜率 (%)", range: [25, 80]},
    xaxis: {...DARK.xaxis, title: "持有天数"},
    margin: {t: 20, b: 50, l: 60, r: 20},
    legend: {orientation: "h", y: 1.12},
  }, {responsive: true});

  // ── 图2：校准曲线（模型预测 vs 实际20日胜率）────────────────
  const cal = bt.calibration_20d || [];
  if (cal.length > 0) {
    const calX = cal.map(c => c.bucket);
    const calY = cal.map(c => c.actual_wr_20d);
    const calN = cal.map(c => c.n);
    const calColors = calY.map(y => y >= base20 + 3 ? "#2ecc71" : y >= base20 ? "#f1c40f" : "#e74c3c");
    Plotly.newPlot("chart-backtest-cal", [{
      type: "bar",
      x: calX, y: calY,
      marker: { color: calColors },
      text: cal.map(c => `n=${c.n}`),
      hovertemplate: "<b>预测概率区间: %{x}</b><br>实际20日胜率: %{y:.1f}%<br>%{text}<extra></extra>",
    }, {
      type: "scatter", mode: "lines",
      x: calX, y: calX.map(() => base20),
      line: { color: "#8b949e", dash: "dot", width: 1.5 },
      name: "基准", hoverinfo: "skip",
    }], {
      ...DARK,
      yaxis: {...DARK.yaxis, title: "实际胜率 (%)", range: [45, 75]},
      xaxis: {...DARK.xaxis, title: "模型预测概率区间"},
      margin: {t: 10, b: 50, l: 60, r: 20},
      showlegend: false,
    }, {responsive: true});
  }

  // ── Insight 文字 ──────────────────────────────────────────────
  const s4 = bt.tier4_strategy || {};
  const t4 = tiers.find(t => t.tier === 4);
  const t2 = tiers.find(t => t.tier === 2);
  const t3 = tiers.find(t => t.tier === 3);
  const sig4 = t4?.horizons?.["20d"]?.significant;
  const sig2 = t2?.horizons?.["5d"]?.significant;

  document.getElementById("backtest-insight").innerHTML =
    `<strong>历史回测结论（2000-2026，${SIGNALS.backtest?.NASDAQ?.baseline?.["20d"]?.n ?? Object.values(SIGNALS.daily_signals).length}个交易日）：</strong><br><br>
     <span style="color:#2ecc71">▲ 第4档信号（≥60%，n=${t4?.n||0}天）：</span>
     20日实际胜率 <strong style="color:#2ecc71">${t4?.horizons?.["20d"]?.win_rate||"?"}%</strong>，
     高于全样本基准 ${base20}%（+${t4?.horizons?.["20d"]?.diff_vs_baseline||"?"}pp），
     <strong>p=${t4?.horizons?.["20d"]?.p_value||"?"}</strong>${sig4?" ✓统计显著":""}<br>
     <span style="color:#e74c3c">▼ 第2档信号（≤40%，n=${t2?.n||0}天）：</span>
     5日胜率仅 <strong style="color:#e74c3c">${t2?.horizons?.["5d"]?.win_rate||"?"}%</strong>，
     远低于基准（${t2?.horizons?.["5d"]?.diff_vs_baseline||"?"}pp），
     <strong>p=${t2?.horizons?.["5d"]?.p_value||"?"}</strong>${sig2?" ✓统计显著":""}<br>
     <span style="color:#f1c40f">△ 第3档信号：</span>
     20日胜率 ${t3?.horizons?.["20d"]?.win_rate||"?"}%，略低于基准（几乎中性）<br><br>
     <span style="color:var(--muted);font-size:0.79rem">
       ${(() => {
         if (!cal.length) return "校准曲线：数据不足，暂无法评估单调性。";
         const calMonotonic = cal.every((c, i) => i === 0 || c.actual_wr_20d >= cal[i - 1].actual_wr_20d);
         return calMonotonic
           ? "校准曲线：模型预测概率越高 → 实际胜率确实更高，信号有单调性。"
           : "校准曲线：分段胜率非单调（高置信区间 ≠ 更准），需谨慎解读概率区间。";
       })()}<br>
       「仅Tier≥4入场」策略 20日胜率 ${s4.win_rate_20d||"?"}% vs 随时买入 ${s4.baseline_win_rate||"?"}%，
       p=${s4.p_value||"?"}${s4.significant === undefined ? "" : s4.significant ? "（<strong>统计显著</strong>）" : "（<strong>未达显著，纯噪声区间</strong>）"}。绝对差距 +${s4.diff||"?"}pp。
     </span>`;
}

// ── 今日操作建议 ──
// adjustedProb: pass event-adjusted probability from updateSignal so the box stays in sync
function renderTodayRec(adjustedProb) {
  const el = document.getElementById("today-rec");
  if (!el || !SIGNALS) return;
  const dateStr = selectedDate || localDateStr();
  const isFuture = dateStr > localDateStr();
  let prob, tierNum, isForecast = false;

  if (isFuture) {
    const allFc = SIGNALS.next_opportunities?.all_forecast || [];
    const fc = allFc.find(d => d.date === dateStr) ||
               (allFc.length ? allFc.reduce((best, d) =>
                 Math.abs(new Date(d.date) - new Date(dateStr)) <
                 Math.abs(new Date(best.date) - new Date(dateStr)) ? d : best, allFc[0]) : null);
    if (!fc) { el.innerHTML = ""; return; }
    prob = adjustedProb !== undefined ? adjustedProb : fc.prob;
    isForecast = true;
  } else {
    const rec = SIGNALS.daily_signals?.[dateStr];
    if (!rec) { el.innerHTML = ""; return; }
    prob = adjustedProb !== undefined ? adjustedProb : rec.prob;
  }

  // 模型无样本外区分度时，不输出"档位/买卖"建议——否则与中性信号环自相矛盾
  if (SIGNALS.calibration_flat) {
    const br = Math.round((SIGNALS.base_rate_20d ?? 0.62) * 100);
    el.innerHTML = `
      <div style="background:rgba(241,196,15,.07);border:1px solid #f1c40f44;border-radius:8px;padding:.85rem 1rem;">
        <div style="font-size:0.72rem;color:var(--muted);margin-bottom:.3rem;">今日操作建议</div>
        <div style="font-size:1.05rem;font-weight:700;color:#f1c40f">⏸ 无样本外优势 · 不输出档位</div>
        <div style="font-size:0.8rem;color:var(--text);margin-top:.4rem;line-height:1.55">
          walk-forward 块自助验证未发现该信号有样本外区分度——任意一天的 20 日上涨概率都≈基率 ${br}%。
          这是实验性研究工具，不构成择时建议。</div>
      </div>`;
    return;
  }

  tierNum = tier(prob);

  const map = {
    5: { color:"#27ae60", bg:"rgba(39,174,96,.12)", icon:"🟢", action:"积极加仓",
         desc:"多重指标全面支撑，历史最强信号。适合以较大仓位买入美股/主流加密货币。" },
    4: { color:"#2ecc71", bg:"rgba(46,204,113,.09)", icon:"✅", action:"适合买入",
         desc:"信号偏多，可以正常仓位入场。美股ETF（QQQ/SPY）或BTC/ETH均合适。" },
    3: { color:"#f1c40f", bg:"rgba(241,196,15,.09)", icon:"⏸",  action:"观望持有",
         desc:"信号中性，不是最佳入场时机。现有持仓无需操作，等待更强信号出现。" },
    2: { color:"#e67e22", bg:"rgba(230,126,34,.09)", icon:"⚠️", action:"谨慎等待",
         desc:"偏空信号。不建议新建仓位，可考虑减少高风险持仓，保留现金等待机会。" },
    1: { color:"#e74c3c", bg:"rgba(231,76,60,.09)", icon:"🔴", action:"规避风险",
         desc:"信号极弱，多重负面因素叠加。建议低仓位或空仓，等待市场企稳。" },
  };
  const c = map[tierNum] || map[3];
  const tag = isForecast ? `<span style="color:var(--muted);font-size:0.72rem">（预测）</span>` : "";
  el.innerHTML = `
    <div style="background:${c.bg};border:1px solid ${c.color}55;border-radius:8px;padding:.85rem 1rem;">
      <div style="font-size:0.72rem;color:var(--muted);margin-bottom:.3rem;">今日操作建议${tag}</div>
      <div style="font-size:1.05rem;font-weight:700;color:${c.color}">${c.icon} 第${tierNum}档 · ${c.action}</div>
      <div style="font-size:0.8rem;color:var(--text);margin-top:.4rem;line-height:1.55">${c.desc}</div>
      <div style="font-size:0.72rem;color:var(--muted);margin-top:.4rem">上涨概率 ${Math.round(prob*100)}% · 仅供参考，不构成投资建议</div>
    </div>`;
}

// ── 未来60天信号日历 ──
function renderForecastCalendar() {
  const el = document.getElementById("forecast-calendar");
  if (!el || !SIGNALS) return;
  const allFc = SIGNALS.next_opportunities?.all_forecast || [];
  if (!allFc.length) { el.innerHTML = `<span style="color:var(--muted);font-size:0.82rem">暂无预测数据</span>`; return; }

  const TC = { 5:"#27ae60", 4:"#2ecc71", 3:"#f1c40f", 2:"#e67e22", 1:"#e74c3c" };
  const TB = { 5:"rgba(39,174,96,.22)", 4:"rgba(46,204,113,.18)", 3:"rgba(241,196,15,.18)", 2:"rgba(230,126,34,.18)", 1:"rgba(231,76,60,.18)" };

  // Group by ISO week (Monday-based) — parse date string directly to avoid UTC/local timezone issues
  const weeks = {};
  allFc.forEach(d => {
    const [y, m, day] = d.date.split('-').map(Number);
    const dt = new Date(y, m - 1, day); // local date, no timezone shift
    const dow = dt.getDay(); // 0=Sun
    const diff = dow === 0 ? -6 : 1 - dow;
    const mon = new Date(y, m - 1, day + diff);
    const key = `${mon.getFullYear()}-${String(mon.getMonth()+1).padStart(2,'0')}-${String(mon.getDate()).padStart(2,'0')}`;
    if (!weeks[key]) weeks[key] = [];
    weeks[key].push(d);
  });

  const today = localDateStr();
  // Legend
  let html = `<div style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:.5rem;font-size:0.72rem;">
    <span style="color:var(--muted)">颜色说明：</span>
    <span><span style="color:#2ecc71">■</span> 强势买入(T4-5)</span>
    <span><span style="color:#f1c40f">■</span> 中性观望(T3)</span>
    <span><span style="color:#e74c3c">■</span> 偏弱谨慎(T1-2)</span>
    <span style="color:var(--muted)">· 今日有发光边框</span>
  </div>`;
  html += `<div style="display:flex;flex-direction:column;gap:5px;">`;
  Object.keys(weeks).sort().forEach(wk => {
    const days = weeks[wk].sort((a,b) => a.date.localeCompare(b.date));
    const [, wm, wd] = wk.split('-');
    const wkLabel = `${wm}/${wd}`;
    html += `<div style="display:flex;align-items:center;gap:4px;">
      <span style="font-size:0.68rem;color:var(--muted);width:38px;flex-shrink:0">${wkLabel}</span>`;
    days.forEach(d => {
      const dom = parseInt(d.date.slice(8, 10)); // parse directly — timezone-safe
      const isToday = d.date === today;
      const border = isToday ? `2px solid ${TC[d.tier]}` : `1px solid ${TC[d.tier]}44`;
      html += `<div title="${d.date}  概率${Math.round(d.prob*100)}%  第${d.tier}档${d.macro ? "  ⚠"+d.macro : ""}（点击查看操作计划）"
        role="button" tabindex="0" data-forecast-date="${d.date}"
        style="width:36px;height:36px;border-radius:5px;background:${TB[d.tier]};border:${border};cursor:pointer;
               display:flex;flex-direction:column;align-items:center;justify-content:center;
               ${isToday ? "box-shadow:0 0 0 3px "+TC[d.tier]+"66;" : ""}">
        <span style="font-size:0.65rem;color:var(--muted);line-height:1">${dom}日</span>
        <span style="font-size:0.7rem;font-weight:700;color:${TC[d.tier]};line-height:1.3">${Math.round(d.prob*100)}%</span>
      </div>`;
    });
    html += `</div>`;
  });
  html += `</div>`;

  const strong = allFc.filter(d => d.tier >= 4).length;
  const weak   = allFc.filter(d => d.tier <= 2).length;
  const neut   = allFc.length - strong - weak;
  html += `<div style="font-size:0.75rem;color:var(--muted);margin-top:.6rem;display:flex;gap:1rem;flex-wrap:wrap;">
    <span>共 ${allFc.length} 个交易日</span>
    <span style="color:#2ecc71">强势: ${strong}天</span>
    <span style="color:#f1c40f">中性: ${neut}天</span>
    <span style="color:#e74c3c">偏弱: ${weak}天</span>
  </div>`;

  el.innerHTML = html;
}

// ── 重要经济日历 ──
function renderEconCalendar() {
  const el = document.getElementById("econ-calendar-list");
  if (!el) return;
  const today = localDateStr();
  // 特殊事件（手工维护）
  const events = [
    { date:"2026-06-11", emoji:"⚽", label:"世界杯开幕",          type:"event", note:"美/加/墨主办，Fox Corp受益" },
    { date:"2026-06-12", emoji:"🚀", label:"SpaceX SPCX 上市",    type:"ipo",   note:"Nasdaq，发行价US$135，通过CommSec" },
    { date:"2026-07-02", emoji:"📊", label:"6月非农就业数据",      type:"nfp",   note:"超预期→加息压力→短期利空" },
    { date:"2026-07-19", emoji:"⚽", label:"世界杯决赛",           type:"event", note:"冠军国股市往往短暂上涨" },
  ];
  // 官方宏观日历（CPI/FOMC，来自 signals.json，由 BLS/Fed 日程生成）
  (SIGNALS?.macro_calendar || []).forEach(m => {
    const isCpi = m.label.includes("CPI");
    events.push({
      date: m.date,
      emoji: isCpi ? "📊" : "🏦",
      label: m.label,
      type: isCpi ? "cpi" : "fed",
      note: isCpi ? "美东8:30发布·当日波动放大" : "美东14:00决议·当日波动放大",
    });
  });
  events.sort((a, b) => a.date.localeCompare(b.date));
  const typeColor = { ipo:"#2ecc71", fed:"#3498db", nfp:"#e67e22", cpi:"#e67e22", event:"#9b59b6" };
  const upcoming = events.filter(e => e.date >= today).slice(0, 6);
  el.innerHTML = upcoming.map(e => {
    const diff = Math.round((new Date(e.date) - new Date(today)) / 86400000);
    const urgency = diff <= 3 ? "#e74c3c" : diff <= 7 ? "#e67e22" : "var(--muted)";
    const diffLabel = diff === 0 ? "今天" : diff === 1 ? "明天" : `${diff}天后`;
    return `<div style="display:flex;align-items:flex-start;gap:.6rem;padding:.4rem 0;border-bottom:1px solid var(--border-faint);">
      <span style="font-size:1rem;flex-shrink:0">${e.emoji}</span>
      <div style="flex:1;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="font-weight:600;color:${typeColor[e.type]||"var(--text)"}">${e.label}</span>
          <span style="color:${urgency};font-size:0.72rem;font-weight:700;flex-shrink:0">${diffLabel}</span>
        </div>
        <div style="color:var(--muted);font-size:0.72rem">${e.date}${e.note ? " · " + e.note : ""}</div>
      </div>
    </div>`;
  }).join("") || `<div style="color:var(--muted);font-size:0.8rem">近期无重要事件</div>`;
}

// ── 我的持仓计算器 ──
const PORTFOLIO_KEY = "alpha_portfolio_v2";
const COIN_IDS = { BTC:"bitcoin", ETH:"ethereum", XLM:"stellar", DOGE:"dogecoin", HOME:"home", SOL:"solana", BNB:"binancecoin" };
let portfolioPrices = {};
function escPortfolio(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function loadPortfolio() {
  try { return JSON.parse(localStorage.getItem(PORTFOLIO_KEY)) || defaultPortfolio(); }
  catch { return defaultPortfolio(); }
}
function savePortfolio(p) { localStorage.setItem(PORTFOLIO_KEY, JSON.stringify(p)); }
function defaultPortfolio() {
  return [
    { ticker:"BTC",  qty:0.002,    priceUSD:null, costUSD:null,  type:"crypto" },
    { ticker:"ETH",  qty:0.0103,   priceUSD:null, costUSD:null,  type:"crypto" },
    { ticker:"XLM",  qty:503.78,   priceUSD:null, costUSD:null,  type:"crypto" },
    { ticker:"DOGE", qty:1360.5,   priceUSD:null, costUSD:null,  type:"crypto" },
    { ticker:"HOME", qty:100,      priceUSD:null, costUSD:null,  type:"crypto" },
    { ticker:"SPCX", qty:0,        priceUSD:135,  costUSD:135,   type:"stock",  note:"IPO发行价US$135" },
  ];
}

let _portAudRate = 0.71;

function renderPortfolioTable(audRate) {
  if (audRate && audRate > 0) _portAudRate = audRate;
  const port = loadPortfolio();
  const body = document.getElementById("portfolio-body");
  const foot = document.getElementById("portfolio-foot");
  if (!body) return;
  let total = 0, totalCost = 0;
  body.innerHTML = port.map((item, i) => {
    const rawPrice = portfolioPrices[item.ticker] ?? item.priceUSD;
    const p = Number.isFinite(Number(rawPrice)) ? Number(rawPrice) : null;
    const qty = Number.isFinite(Number(item.qty)) ? Number(item.qty) : 0;
    const pAUD = p && _portAudRate ? p / _portAudRate : null;
    const val = pAUD ? qty * pAUD : null;
    if (val) total += val;
    // P&L
    const costUSD = Number.isFinite(Number(item.costUSD)) ? Number(item.costUSD) : null;
    const costAUD = (costUSD && _portAudRate) ? (costUSD / _portAudRate * qty) : null;
    if (costAUD) totalCost += costAUD;
    const plAUD = (val && costAUD) ? val - costAUD : null;
    const plPct = (plAUD != null && costAUD > 0) ? plAUD / costAUD * 100 : null;
    const plStr = qty <= 0 ? "" :
      plAUD != null
      ? `<br><span class="${plAUD >= 0 ? 'pl-up' : 'pl-dn'}">${plAUD >= 0 ? '+' : ''}A$${plAUD.toFixed(0)} (${plPct >= 0 ? '+' : ''}${(plPct||0).toFixed(1)}%)</span>`
      : `<br><span class="cost-link" role="button" tabindex="0" data-cost-index="${i}">设置成本价</span>`;
    const valStr = val ? `A$${val.toFixed(2)}` : "—";
    const pStr  = p   ? `$${p < 1 ? p.toFixed(4) : p.toFixed(2)}` : "—";
    const ticker = escPortfolio(item.ticker);
    const note = item.note ? escPortfolio(item.note) : "";
    return `<tr style="border-bottom:1px solid var(--border-faint);">
      <td style="padding:.35rem .4rem;font-weight:600;color:var(--text)">${ticker}${note?`<br><span style="font-size:0.68rem;color:var(--muted);font-weight:400">${note}</span>`:""}</td>
      <td style="text-align:right;padding:.35rem .4rem;color:var(--muted)">${qty}</td>
      <td style="text-align:right;padding:.35rem .4rem">${pStr}</td>
      <td style="text-align:right;padding:.35rem .4rem;font-weight:600;color:${val?'var(--green)':'var(--muted)'}">${valStr}${plStr}</td>
    </tr>`;
  }).join("");
  const plTotal = (total > 0 && totalCost > 0) ? total - totalCost : null;
  const plTotalPct = plTotal != null && totalCost > 0 ? plTotal / totalCost * 100 : null;
  const plTotalStr = plTotal != null
    ? `<span class="${plTotal >= 0 ? 'pl-up' : 'pl-dn'}" style="font-size:0.8rem;margin-left:.5rem">${plTotal >= 0 ? '+' : ''}A$${plTotal.toFixed(0)} (${plTotalPct >= 0 ? '+' : ''}${(plTotalPct||0).toFixed(1)}%)</span>` : "";
  foot.innerHTML = total > 0 ? `<tr style="border-top:1px solid var(--border);">
    <td colspan="3" style="padding:.4rem;font-weight:700;color:var(--muted)">总计</td>
    <td style="text-align:right;padding:.4rem;font-weight:800;font-size:1rem;color:var(--green)">A$${total.toFixed(2)}${plTotalStr}</td>
  </tr>` : "";

  // Signal overlay
  const sigEl = document.getElementById("portfolio-signal");
  if (sigEl && SIGNALS) {
    const t = SIGNALS.latest_tier || 3;
    const tColor = {5:"#27ae60",4:"#2ecc71",3:"#f1c40f",2:"#e67e22",1:"#e74c3c"};
    const tText  = {5:"全力持有",4:"可以加仓",3:"观望，不追高",2:"考虑减仓",1:"建议减仓保现金"};
    sigEl.innerHTML = `<div style="font-size:0.78rem;color:var(--muted);">当前信号第${t}档 →
      <strong style="color:${tColor[t]||"#f1c40f"}">${tText[t]||"观望"}</strong></div>`;
  }
}

function setPortfolioCost(i) {
  const port = loadPortfolio();
  const item = port[i];
  if (!item) return;
  const fallback = item.costUSD ?? item.priceUSD ?? portfolioPrices[item.ticker] ?? "";
  const input = prompt(`设置 ${item.ticker || "资产"} 的 USD 成本价`, fallback);
  if (input === null) return;
  const cost = Number(input);
  if (!Number.isFinite(cost) || cost <= 0) {
    alert("请输入有效的正数成本价。");
    return;
  }
  item.costUSD = cost;
  savePortfolio(port);
  renderPortfolioTable(_portAudRate);
}

async function fetchPortfolioPrices() {
  const btn = document.getElementById("portfolio-refresh-btn");
  if (btn) btn.textContent = "⏳ 获取中...";
  try {
    // 优先用同源 quotes.json（服务端 quick_quotes 抓的 CoinGecko）——中国访客不必直连境外 API
    if (typeof loadQuotes === "function") { try { await loadQuotes(); } catch (e) { /* 用已有 QUOTES */ } }
    let crypto = QUOTES?.crypto, audRate = QUOTES?.aud_rate, src = "同源";
    if (!crypto || !Object.keys(crypto).length) {
      // 兜底：直连 CoinGecko（境外，可能 CORS/被墙；仅当同源缺失时）
      const ids = Object.values(COIN_IDS).join(",");
      const r = await fetch(`https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd,aud`);
      const data = await r.json();
      crypto = {}; src = "直连";
      Object.entries(COIN_IDS).forEach(([ticker, id]) => {
        if (data[id]?.usd) crypto[ticker] = data[id].usd;
        if (!audRate && data[id]?.usd && data[id]?.aud) audRate = data[id].usd / data[id].aud;
      });
    }
    Object.assign(portfolioPrices, crypto);
    const updEl = document.getElementById("portfolio-updated");
    if (updEl) updEl.textContent = `1 AUD ≈ US$${audRate ? audRate.toFixed(4) : "?"}（${src}报价）`;
    renderPortfolioTable(audRate || 0.71);
    renderSPCXTracker();
    updateSPCXCalc();
  } catch (e) {
    console.warn("Portfolio price fetch failed:", e);
    renderPortfolioTable(0.71);
  } finally {
    if (btn) btn.textContent = "🔄 更新价格";
  }
}

// ── 大跌抄底指南 ──
function renderDipGuide() {
  const dipEl = document.getElementById("chart-dip-recovery");
  const vixEl = document.getElementById("chart-vix-entry");
  if (!dipEl || !vixEl) return;

  // S&P 500历史跌幅→恢复天数（1928-2026统计）
  const dipData = [
    { drop:"-5%",   days:22,  n:94 }, { drop:"-10%",  days:115, n:47 },
    { drop:"-15%",  days:130, n:28 }, { drop:"-20%",  days:280, n:19 },
    { drop:"-30%",  days:450, n:11 }, { drop:"-40%+", days:700, n:6  },
  ];
  const dipColors = dipData.map(d => d.days < 100 ? "#2ecc71" : d.days < 300 ? "#f1c40f" : "#e74c3c");
  Plotly.newPlot(dipEl, [{
    type:"bar", x:dipData.map(d=>d.drop), y:dipData.map(d=>d.days),
    marker:{color:dipColors},
    text:dipData.map(d=>`${d.days}天<br>n=${d.n}次`),
    textposition:"outside", cliponaxis:false,
    hovertemplate:"<b>%{x}</b><br>平均恢复 %{y} 天<extra></extra>",
  }], {
    ...DARK, margin:{t:10,b:40,l:45,r:10},
    // y 轴顶部留 18% 余量，给最高柱(700天)的 outside 文字留位置
    yaxis:{...DARK.yaxis, title:"平均恢复天数", range:[0, 700*1.18]},
    // 必须强制分类轴："-5%" 会被 Plotly 自动当数字解析（parseFloat 截断），
    // "-40%+" 解析失败 → 整根柱子凭空消失 + translate(NaN) 报错
    xaxis:{...DARK.xaxis, type:"category"},
  }, {responsive:true});

  // VIX水平→未来3个月胜率
  const vixData = [
    { range:"< 15",   wr:52, label:"过度乐观" }, { range:"15-20", wr:58, label:"正常" },
    { range:"20-30",  wr:65, label:"担忧"     }, { range:"30-40", wr:78, label:"恐慌" },
    { range:"> 40",   wr:89, label:"极度恐慌" },
  ];
  const vixColors = vixData.map(d => d.wr >= 75 ? "#27ae60" : d.wr >= 65 ? "#2ecc71" : d.wr >= 58 ? "#f1c40f" : "#e67e22");
  Plotly.newPlot(vixEl, [{
    type:"bar", x:vixData.map(d=>d.range), y:vixData.map(d=>d.wr),
    marker:{color:vixColors},
    text:vixData.map(d=>`${d.wr}%`),
    textposition:"outside", cliponaxis:false,
    hovertemplate:"<b>VIX %{x}</b><br>3月胜率 %{y}%<extra></extra>",
  }], {
    ...DARK, margin:{t:10,b:40,l:40,r:10},
    yaxis:{...DARK.yaxis, title:"3个月胜率%", range:[45,100]},
    xaxis:{...DARK.xaxis, type:"category"},   // "15-20" 会被自动解析成数字 15，同 dip 图
    shapes:[{type:"line",x0:-0.5,x1:4.5,y0:58,y1:58,line:{color:"#555",dash:"dot",width:1}}],
  }, {responsive:true});

  document.getElementById("dip-insight").innerHTML =
    `<strong>抄底黄金法则：</strong>跌幅越大、VIX越高，历史胜率越高，但恢复时间也越长。<br>
     <span style="color:#27ae60">VIX > 30</span>时买入，3个月胜率达 <strong>78%+</strong>；
     <span style="color:#f1c40f">VIX < 15</span>（现在）市场过于乐观，<strong>不是抄底时机</strong>，是减少新仓的时机。<br>
     <span style="color:var(--muted);font-size:0.78rem">数据来源：S&P 500 1928-2026历史统计，非投资建议。</span>`;
}

// ── 市场情绪仪表盘 ──
function renderSentimentPanel() {
  const el = document.getElementById("sentiment-gauges");
  if (!el || !SIGNALS) return;
  const tech = SIGNALS.next_opportunities?.latest_tech || {};

  // VIX: use VIX from daily_signals (latest available) or fallback
  const allDays = SIGNALS.daily_signals || {};
  const latestKey = Object.keys(allDays).sort().pop();
  // nasdaq_vol is annualized realized vol; derive a rough VIX proxy
  // We store actual VIX in prices.json; use latest_tech nasdaq_vol as proxy if no direct VIX
  const nasVol  = tech.nasdaq_vol;  // e.g. 0.0916 = 9.16% 20-day realized vol
  const rsi     = tech.nasdaq_rsi;  // e.g. 77.1
  const btcMom  = tech.btc_mom20;   // e.g. -0.1946

  function gauge(label, val, min, max, zones, unit, note) {
    if (val == null) return "";
    const pct = Math.max(0, Math.min(100, (val - min) / (max - min) * 100));
    let color = "#8b949e", zoneLabel = "";
    for (const z of zones) {
      if (val >= z.from && val < z.to) { color = z.color; zoneLabel = z.label; break; }
    }
    return `<div>
      <div style="display:flex;justify-content:space-between;margin-bottom:.25rem;">
        <span style="color:var(--muted)">${label}</span>
        <span style="font-weight:700;color:${color}">${typeof val==="number"?val.toFixed(1):val}${unit}
          <span style="font-size:0.72rem;font-weight:400"> ${zoneLabel}</span></span>
      </div>
      <div style="height:6px;background:var(--border);border-radius:3px;overflow:hidden;">
        <div style="width:${pct}%;height:100%;background:${color};border-radius:3px;transition:width .4s"></div>
      </div>
      ${note ? `<div style="font-size:0.7rem;color:var(--muted);margin-top:.2rem">${note}</div>` : ""}
    </div>`;
  }

  // nasdaq_vol 在 build_signals 里已经年化过（std*sqrt252），这里只换百分比
  // ——之前重复年化导致显示 276 并永远"极度恐慌"
  const vixProxy = nasVol ? +(nasVol * 100).toFixed(1) : null;
  const vixZones = [
    {from:0,   to:15,  color:"#f1c40f", label:"过度乐观 ⚠️"},
    {from:15,  to:20,  color:"#2ecc71", label:"正常"},
    {from:20,  to:30,  color:"#e67e22", label:"担忧"},
    {from:30,  to:999, color:"#e74c3c", label:"极度恐慌 → 买入机会"},
  ];
  const rsiZones = [
    {from:0,  to:30,  color:"#e74c3c", label:"超卖 → 可能反弹"},
    {from:30, to:50,  color:"#e67e22", label:"弱势"},
    {from:50, to:70,  color:"#2ecc71", label:"正常偏多"},
    {from:70, to:100, color:"#f1c40f", label:"超买 ⚠️"},
  ];
  const btcPct = btcMom != null ? +(btcMom * 100).toFixed(1) : null;
  const btcZones = [
    {from:-100, to:-20, color:"#e74c3c", label:"极度疲弱"},
    {from:-20,  to:-5,  color:"#e67e22", label:"偏弱"},
    {from:-5,   to:5,   color:"#8b949e", label:"横盘"},
    {from:5,    to:20,  color:"#2ecc71", label:"偏强"},
    {from:20,   to:999, color:"#27ae60", label:"强势"},
  ];
  // 💵 美元强弱(DXY 趋势)——与美股通常负相关；颜色按"对股市的含义"上色(走强=承压)
  const dxyPct = tech.dxy_trend != null ? +(tech.dxy_trend * 100).toFixed(1) : null;
  const dxyZones = [
    {from:-100, to:-1, color:"#2ecc71", label:"美元走弱 → 股市顺风"},
    {from:-1,   to:1,  color:"#8b949e", label:"美元横盘"},
    {from:1,    to:100, color:"#e67e22", label:"美元走强 → 股市承压"},
  ];

  el.innerHTML = [
    gauge("VIX（波动率/恐慌指数）", vixProxy, 10, 50, vixZones, "",
      vixProxy ? `<30=恐慌买入机会 · <15=过度乐观需谨慎 · 数据截至 ${SIGNALS.generated}` : ""),
    gauge("纳指RSI（超买超卖）", rsi, 0, 100, rsiZones, "",
      "RSI>70超买，<30超卖；现在" + (rsi>70?"偏高，注意回调":rsi<30?"极度超卖，反弹概率大":"正常区间")),
    gauge("BTC 20日动量", btcPct, -50, 50, btcZones, "%",
      "BTC往往领先美股科技股1-2周，负值代表近期加密偏弱"),
    gauge("💵 美元强弱 (DXY趋势)", dxyPct, -5, 5, dxyZones, "%",
      "美元指数与美股通常负相关：美元强→外资回流美债、股市承压；美元弱→股市常受益。统计相关、非因果铁律"),
  ].filter(Boolean).join("");

  // Summary line
  const warning = (vixProxy && vixProxy < 15) || (rsi && rsi > 75);
  const bullish  = (vixProxy && vixProxy > 30) || (rsi && rsi < 30);
  const summary = bullish
    ? `<div style="color:#2ecc71;font-size:0.78rem;margin-top:.4rem">📈 恐慌信号出现 → 历史上往往是逆向买入机会</div>`
    : warning
    ? `<div style="color:#f1c40f;font-size:0.78rem;margin-top:.4rem">⚠️ 市场情绪偏乐观，短线注意回调风险</div>`
    : `<div style="color:var(--muted);font-size:0.78rem;margin-top:.4rem">情绪中性，无极端信号</div>`;
  el.innerHTML += summary;
}

