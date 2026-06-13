// ═══════════════════════════════════════════════════════
//  Benchmark 记分卡（SIGNALS.benchmark）
//  每个模型 vs 它的诚实基线：硬基线 · 样本外/前向 · 前向不足不判输赢
// ═══════════════════════════════════════════════════════
function renderBenchmark() {
  const el = document.getElementById("benchmark");
  if (!el) return;
  const bm = SIGNALS && SIGNALS.benchmark;
  if (!bm || !Array.isArray(bm.rows) || !bm.rows.length) {
    el.innerHTML = `<span style="color:var(--muted)">运行一次完整流水线后显示</span>`;
    return;
  }
  // verdict → 颜色（✅绿 / ➖黄 / ❌红 / ⏳灰；数据缺失也用灰）
  const VC = {
    "✅打败": "#2ecc71", "➖持平": "#f1c40f",
    "❌未达": "#e74c3c", "⏳数据不足": "#8b949e", "数据缺失": "#8b949e",
  };
  const fmt = v => (v === null || v === undefined) ? "—" : esc(String(Number(v)));
  const fmtDelta = v => {
    if (v === null || v === undefined) return "—";
    const n = Number(v);
    return esc((n > 0 ? "+" : "") + n);
  };
  const rows = bm.rows.map(r => {
    const color = VC[r.verdict] || "#8b949e";
    return `<tr style="border-top:1px solid var(--border)33;" title="${esc(r.note)}">
      <td style="padding:.3rem .5rem;">${esc(r.name)}</td>
      <td style="padding:.3rem .5rem;color:var(--muted);">${esc(r.metric)}</td>
      <td style="padding:.3rem .5rem;text-align:right;">${fmt(r.model_value)}</td>
      <td style="padding:.3rem .5rem;text-align:right;color:var(--muted);">${esc(r.baseline_label)} ${fmt(r.baseline_value)}</td>
      <td style="padding:.3rem .5rem;text-align:right;">${fmtDelta(r.delta)}</td>
      <td style="padding:.3rem .5rem;text-align:center;"><span style="color:${color};font-weight:600;">${esc(r.verdict)}</span></td>
      <td style="padding:.3rem .5rem;color:var(--muted);font-size:0.72rem;">${esc(r.basis)}</td>
    </tr>`;
  }).join("");
  const s = bm.summary || {};
  el.innerHTML = `
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr style="color:var(--muted);font-size:0.72rem;">
        <th style="padding:.3rem .5rem;text-align:left;">项目</th>
        <th style="padding:.3rem .5rem;text-align:left;">指标</th>
        <th style="padding:.3rem .5rem;text-align:right;">模型值</th>
        <th style="padding:.3rem .5rem;text-align:right;">基线</th>
        <th style="padding:.3rem .5rem;text-align:right;">差值</th>
        <th style="padding:.3rem .5rem;text-align:center;">判定</th>
        <th style="padding:.3rem .5rem;text-align:left;">依据</th>
      </tr></thead><tbody>${rows}</tbody>
    </table>
    <div style="display:flex;gap:.65rem;flex-wrap:wrap;margin-top:.7rem;font-size:0.72rem;color:var(--muted);">
      <span>✅ 打败 ${Number(s.beats ?? 0)}</span>
      <span>➖ 持平 ${Number(s.ties ?? 0)}</span>
      <span>❌ 未达 ${Number(s.loses ?? 0)}</span>
      <span>⏳ 数据不足 ${Number(s.insufficient ?? 0)}</span>
    </div>
    ${bm.drift ? `<div style="margin-top:.5rem;font-size:0.75rem;color:${(bm.drift.degraded_count||0)>0?"#e74c3c":"var(--muted)"};">
      📡 漂移监控：${esc(bm.drift.status)}${(bm.drift.changes||[]).length?"（"+bm.drift.changes.map(c=>esc(c.name)+":"+esc(c.from)+"→"+esc(c.to)).join("；")+"）":""}</div>` : ""}
    <div class="insight" style="margin-top:.85rem;">
      <strong>${esc(bm.headline)}</strong><br>
      <span style="color:var(--muted);font-size:0.75rem;">原则：${esc(bm.principle)}</span>
    </div>`;
}

function safeRender(fn, name) {
  try { fn(); } catch(e) { console.warn("renderError ["+name+"]:", e); }
}

// ── IntersectionObserver 懒渲染 ──
// Plotly 在 display:none 容器里画图会按默认 700px 宽计算（甚至给文字标签算出 NaN 坐标），
// 之前靠切视图后 Plots.resize 补救。懒渲染让隐藏视图的图表在首次可见时才画，一次画对，
// 顺带省掉首屏 10+ 张看不见的图的渲染时间。
const _lazyJobs = new Map();   // containerId -> {fn, name}
const _lazyObserver = new IntersectionObserver(entries => {
  const fired = new Set();     // 同一批回调里多个容器共用一个渲染函数时只跑一次
  for (const en of entries) {
    if (!en.isIntersecting) continue;
    const job = _lazyJobs.get(en.target.id);
    if (!job) continue;
    _lazyJobs.delete(en.target.id);
    _lazyObserver.unobserve(en.target);
    if (fired.has(job.fn)) continue;
    fired.add(job.fn);
    safeRender(job.fn, job.name);
  }
}, { rootMargin: "250px" });

function lazyRender(containerId, fn, name) {
  const el = document.getElementById(containerId);
  if (!el) return;
  // offsetParent 为 null = 自己或祖先 display:none（隐藏视图）→ 挂观察器等可见
  if (el.offsetParent !== null) { safeRender(fn, name); return; }
  _lazyJobs.set(containerId, { fn, name });
  _lazyObserver.observe(el);
}

// 启动渲染序列。抽成具名函数以支持"🔄 手动刷新"：所有渲染器都是幂等覆盖，
// 重新 init()（拉最新 JSON）后再跑一遍即完成无整页刷新的数据更新。
function renderAll() {
  safeRender(renderDOWPanel,        "DOW");
  safeRender(renderSellPanel,       "Sell");
  safeRender(renderOppPanel,        "Opp");
  safeRender(renderForecastChart,   "Forecast");
  safeRender(renderTodayRec,        "TodayRec");
  safeRender(renderForecastCalendar,"ForecastCal");
  safeRender(renderSentimentPanel,  "Sentiment");
  safeRender(renderEconCalendar,    "EconCal");
  lazyRender("chart-dip-recovery",  renderDipGuide, "DipGuide");
  safeRender(renderSPCXTracker,     "SPCX");
  lazyRender("chart-accuracy",      renderPredictionAccuracy, "PredAccuracy");
  safeRender(renderIndicesCompare,  "IndicesCompare");
  safeRender(renderLiveTracking,    "LiveTracking");
  safeRender(renderMarketClock,     "MarketClock");
  loadStocksPanel();
  lazyRender("chart-overnight",     loadOvernightPanel, "Overnight");
  loadNewsPanel();
  loadBriefPanel();
  loadPaperPanel();
  loadReportPanel();
  safeRender(renderBenchmark,       "Benchmark");
  fetchFearAndGreed();
  loadQuotes();   // 盘中轻量报价（10分钟级），SPCX 监视卡优先消费
  lazyRender("chart-spcx-ipo",      renderSPCXDetail, "SPCXDetail");
  // Sync SPCX inputs with localStorage
  const savedShares = localStorage.getItem("spcx_shares");
  const savedPrice  = localStorage.getItem("spcx_price");
  if (savedShares) { const el = document.getElementById("spcx-shares-input"); if (el) el.value = savedShares; }
  if (savedPrice)  { const el = document.getElementById("spcx-price-input");  if (el) el.value = savedPrice; }
  renderPortfolioTable(0.71);  // render with fallback rate; user can refresh for live prices
  _mainTabRendered.add("forecast");
  _calTabRendered.add("digit");  // digit 是日历组默认标签，由懒渲染负责首画
  lazyRender("placebo-overview", loadPlacebo, "Placebo");   // 🔬 规律防伪诚实总览
  lazyRender("event-causal", loadEventCausal, "EventCausal"); // 🎯 反事实事件影响(方法B)
  lazyRender("risk-dashboard", loadRiskDashboard, "RiskDash"); // 📉 风险仪表盘(方法D)
  lazyRender("chart-digit", renderDigitChart, "Digit");
  lazyRender("chart-ipo-cycle", renderIPOCycle, "IPOCycle");
  lazyRender("factor-audit", renderFactorAudit, "FactorAudit");
  lazyRender("vol-model", renderVolModel, "VolModel");
  lazyRender("market-structure", renderMarketStructure, "MarketStructure");
  lazyRender("event-impact", renderEventImpact, "EventImpact");
  lazyRender("quant-methodology", renderQuantMethodology, "QuantMethodology");
  lazyRender("chart-horizon", renderHorizonView, "Horizon");
  // 恢复上次浏览的视图（默认"今日"）；手动刷新时 savedView==当前视图，顺带触发图表重算尺寸
  const savedView = localStorage.getItem("alpha_view");
  if (savedView && savedView !== "today") {
    const btn = document.querySelector(`.view-btn[data-view="${savedView}"]`);
    if (btn) switchView(savedView, btn);
  }
}
init().then(renderAll);

// ═══════════════════════════════════════════════════════
//  ⏳ 长期视角：持有期基率统计（SIGNALS.horizon_stats）
// ═══════════════════════════════════════════════════════
const _HZ_ORDER = ["6mo", "1y", "3y", "5y", "10y"];
const _HZ_CN = { "6mo": "6个月", "1y": "1年", "3y": "3年", "5y": "5年", "10y": "10年" };
const _HZ_COLORS = { SP500: "#3498db", NASDAQ: "#2ecc71", SOX: "#e67e22" };

function renderHorizonView() {
  const hs = SIGNALS?.horizon_stats;
  if (!hs?.indices) return;

  // ① 分组柱状图：P(涨) by 持有期 × 指数
  const traces = Object.entries(hs.indices).map(([key, idx]) => ({
    type: "bar", name: `${idx.label}（${idx.start.slice(0,4)}起）`,
    x: _HZ_ORDER.filter(h => idx.horizons[h]).map(h => _HZ_CN[h]),
    y: _HZ_ORDER.filter(h => idx.horizons[h]).map(h => +(idx.horizons[h].p_positive * 100).toFixed(1)),
    marker: { color: _HZ_COLORS[key] || "#888" },
    text: _HZ_ORDER.filter(h => idx.horizons[h]).map(h => (idx.horizons[h].p_positive * 100).toFixed(0) + "%"),
    textposition: "outside", cliponaxis: false,
    hovertemplate: "<b>%{x}</b> " + idx.label + "<br>历史上涨概率 %{y}%<extra></extra>",
  }));
  Plotly.newPlot("chart-horizon", traces, {
    ...DARK, barmode: "group",
    yaxis: { ...DARK.yaxis, title: "历史上涨概率 (%)", range: [0, 108] },
    xaxis: { ...DARK.xaxis, type: "category" },
    legend: { orientation: "h", y: 1.08 },
    margin: { t: 30, b: 40, l: 55, r: 15 },
    shapes: [{ type: "line", x0: -0.5, x1: 4.5, y0: 50, y1: 50,
               line: { color: "#888", dash: "dot", width: 1 } }],
    annotations: [{ x: 4.4, y: 52, text: "抛硬币线", showarrow: false,
                    font: { color: "#888", size: 10 } }],
  }, { responsive: true });

  // ② 每指数明细表
  const fm = v => (v >= 0 ? "+" : "") + v.toFixed(1) + "%";
  const tables = Object.values(hs.indices).map(idx => {
    const rows = _HZ_ORDER.filter(h => idx.horizons[h]).map(h => {
      const r = idx.horizons[h];
      const pc = r.p_positive >= 0.9 ? "#27ae60" : r.p_positive >= 0.75 ? "#2ecc71"
               : r.p_positive >= 0.65 ? "#f1c40f" : "#e67e22";
      return `<tr style="border-top:1px solid var(--border)33;">
        <td style="padding:.3rem .5rem;font-weight:600;">${_HZ_CN[h]}</td>
        <td style="padding:.3rem .5rem;text-align:right;color:${pc};font-weight:700;">${(r.p_positive*100).toFixed(0)}%</td>
        <td style="padding:.3rem .5rem;text-align:right;">${fm(r.ann_median)}</td>
        <td style="padding:.3rem .5rem;text-align:right;color:var(--muted);">${fm(r.ann_p25)} ~ ${fm(r.ann_p75)}</td>
        <td style="padding:.3rem .5rem;text-align:right;color:#e74c3c;">${fm(r.worst_total)}</td>
        <td style="padding:.3rem .5rem;text-align:right;color:var(--muted);">${(r.p_loss_gt_20*100).toFixed(0)}%</td>
      </tr>`;
    }).join("");
    return `<div style="margin-bottom:1rem;">
      <div style="font-size:0.85rem;font-weight:700;margin-bottom:.3rem;">
        ${idx.label} <span style="color:var(--muted);font-weight:400;font-size:0.72rem;">${idx.start.slice(0,4)}–${idx.end.slice(0,4)} · ${idx.years}年</span></div>
      <table style="width:100%;border-collapse:collapse;font-size:0.78rem;">
        <thead><tr style="color:var(--muted);">
          <th style="text-align:left;padding:.25rem .5rem;">持有期</th>
          <th style="text-align:right;padding:.25rem .5rem;">P(涨)</th>
          <th style="text-align:right;padding:.25rem .5rem;">年化中位</th>
          <th style="text-align:right;padding:.25rem .5rem;">年化 25~75 分位</th>
          <th style="text-align:right;padding:.25rem .5rem;">最差总回报</th>
          <th style="text-align:right;padding:.25rem .5rem;">P(亏&gt;20%)</th>
        </tr></thead><tbody>${rows}</tbody></table></div>`;
  }).join("");
  document.getElementById("horizon-tables").innerHTML = tables;

  document.getElementById("horizon-honesty").innerHTML =
    `<strong>读这张表的正确姿势：</strong>${(hs.honesty || []).map(h => `<br>· ${h}`).join("")}`;

  renderHorizonStocks();
}

// 观察池长期质量表（依赖 STOCKS，可能晚于本视图渲染 → 两边都调一次，幂等）
function renderHorizonStocks() {
  const el = document.getElementById("horizon-stocks");
  if (!el || !STOCKS?.stocks) return;
  const rows = Object.entries(STOCKS.stocks).map(([sym, s]) => {
    const st = s.stats;
    const c = v => v == null ? "—"
      : `<span style="color:${v >= 0 ? "#2ecc71" : "#e74c3c"}">${v > 0 ? "+" : ""}${v}%</span>`;
    return `<tr style="border-top:1px solid var(--border)33;">
      <td style="padding:.3rem .5rem;font-weight:600;">${sym}<span style="color:var(--muted);font-weight:400;font-size:0.68rem;"> ${s.label}</span></td>
      <td style="padding:.3rem .5rem;text-align:right;">${c(st.ytd)}</td>
      <td style="padding:.3rem .5rem;text-align:right;">${c(st.chg_1y)}</td>
      <td style="padding:.3rem .5rem;text-align:right;">${c(st.from_high_52w)}</td>
      <td style="padding:.3rem .5rem;text-align:right;color:var(--muted);">${st.vol20_ann}%</td>
      <td style="padding:.3rem .5rem;text-align:center;">${st.above_ma200 ? '<span style="color:#2ecc71">✓</span>' : '<span style="color:#e74c3c">✗</span>'}</td>
    </tr>`;
  }).join("");
  el.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:0.78rem;">
    <thead><tr style="color:var(--muted);">
      <th style="text-align:left;padding:.25rem .5rem;">股票</th>
      <th style="text-align:right;padding:.25rem .5rem;">YTD</th>
      <th style="text-align:right;padding:.25rem .5rem;">近1年</th>
      <th style="text-align:right;padding:.25rem .5rem;">距52周高点</th>
      <th style="text-align:right;padding:.25rem .5rem;">年化波动</th>
      <th style="text-align:center;padding:.25rem .5rem;">MA200上方</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
}

// ── 🔄 手动刷新：重新拉取全部 JSON 并重渲染（不整页刷新，滚动位置和视图保留）──
let _refreshing = false;
async function refreshData(btn) {
  if (_refreshing) return;
  _refreshing = true;
  if (btn) btn.textContent = "⏳";
  try {
    // 清空懒渲染缓存，已打开过的子标签下次点击时用新数据重画
    try { _calTabRendered.clear(); } catch(e) {}
    try { _mainTabRendered.clear(); } catch(e) {}
    try { if (typeof _mvTabRendered !== "undefined") _mvTabRendered.clear(); } catch(e) {}
    await init();
    renderAll();
    if (btn) { btn.textContent = "✓ 已更新"; setTimeout(() => btn.textContent = "🔄 刷新", 2000); }
  } catch(e) {
    console.warn("refreshData 失败", e);
    if (btn) { btn.textContent = "✗ 失败"; setTimeout(() => btn.textContent = "🔄 刷新", 2500); }
  } finally {
    _refreshing = false;
  }
}

// ═══════════════════════════════════════════════════════
//  顶层视图切换（今日/计划/实验/研究/我的）
// ═══════════════════════════════════════════════════════
const VIEWS = ["today", "plan", "longterm", "lab", "research", "quant", "mine"];
function switchView(name, btn) {
  document.querySelectorAll(".view-nav .view-btn").forEach(b => {
    const on = b === btn;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  VIEWS.forEach(v => {
    const sec = document.getElementById("view-" + v);
    if (sec) sec.style.display = (v === name) ? "" : "none";
  });
  localStorage.setItem("alpha_view", name);
  // Plotly 在 display:none 里算不出宽度，切换后重算本视图全部图表
  requestAnimationFrame(() => resizeChartsIn(document.getElementById("view-" + name)));
}

// ═══════════════════════════════════════════════════════
//  IPO 周期视角（SPCX 面板子块）：超级IPO上市后12个月大盘最大回撤
//  数值为历史约值（指数日线口径），用作情绪温度计而非精确统计
// ═══════════════════════════════════════════════════════
const MEGA_IPOS = [
  { name:"NTT 1987-02",        mkt:"日经",   dd:-21, top:true  },
  { name:"Blackstone 2007-06", mkt:"标普",   dd:-18, top:true  },
  { name:"中石油A 2007-11",    mkt:"上证",   dd:-70, top:true  },
  { name:"Visa 2008-03",       mkt:"标普",   dd:-48, top:false },
  { name:"Glencore 2011-05",   mkt:"富时",   dd:-17, top:true  },
  { name:"Facebook 2012-05",   mkt:"标普",   dd:-10, top:false },
  { name:"Alibaba 2014-09",    mkt:"标普",   dd:-10, top:false },
  { name:"Coinbase 2021-04",   mkt:"BTC",    dd:-55, top:true  },
  { name:"Rivian 2021-11",     mkt:"纳指",   dd:-33, top:true  },
  { name:"Google 2004-08",     mkt:"标普",   dd:-7,  top:false },
];
// ── 因子样本外尸检（P2-5，研究面板）──
function renderFactorAudit() {
  const el = document.getElementById("factor-audit");
  if (!el) return;
  const fa = SIGNALS?.factor_audit;
  if (!fa) { el.innerHTML = `<span style="color:var(--muted)">运行一次完整流水线后显示</span>`; return; }
  const VC = { INFORMATIVE: ["#2ecc71", "稳健"], FRAGILE: ["#f39c12", "regime依赖"],
               MISLEADING: ["#e74c3c", "反向误导"], NOISE: ["#8b949e", "噪声"] };
  const esc2 = s => esc(s);
  const rows = (fa.factors || []).map(f => {
    const [c, txt] = VC[f.verdict] || ["#8b949e", f.verdict];
    const hd = f.holdout_diff_pp == null ? "—" : (f.holdout_diff_pp > 0 ? "+" : "") + f.holdout_diff_pp;
    const sgn = f.n_folds_signed ? `${Math.round((f.sign_agree_frac||0)*f.n_folds_signed)}/${f.n_folds_signed}` : "—";
    return `<tr style="border-top:1px solid var(--border)33;">
      <td style="padding:.25rem .5rem;">${esc2(f.name)}</td>
      <td style="padding:.25rem .5rem;text-align:center;color:var(--muted);">${f.assumed_dir>0?"看涨":"看跌"}</td>
      <td style="padding:.25rem .5rem;text-align:right;">${f.dev_diff_pp>0?"+":""}${Number(f.dev_diff_pp)}pp</td>
      <td style="padding:.25rem .5rem;text-align:right;color:var(--muted);">${Number(f.dev_p_boot)}</td>
      <td style="padding:.25rem .5rem;text-align:center;color:var(--muted);" title="逐折符号一致折数">${sgn}</td>
      <td style="padding:.25rem .5rem;text-align:right;">${hd}pp</td>
      <td style="padding:.25rem .5rem;text-align:center;"><span style="color:${c};font-weight:600;">${txt}</span></td>
    </tr>`;
  }).join("");
  const s = fa.summary || {};
  const probe = fa.target_probe || {};
  const dirAuc = probe.direction_auc_pooled_2012_2024, volAuc = probe.vol_auc_holdout;
  const baseHold = fa.base_rate_holdout != null ? Math.round(fa.base_rate_holdout*100) : null;
  const df = fa.deflation;   // 多重检验校正（反过拟合）；缺失则优雅不显示
  const deflHtml = df ? `<div class="insight" style="margin-top:.7rem;border-left:3px solid #8b949e;">
      <strong>🎲 多重检验校正（反过拟合 / 数据挖掘校正）：</strong>测了 ${df.n_factors} 个因子，方向一致且原始 p&lt;${df.q_level} 有 ${df.n_raw_dir_sig_p10} 个；
      依赖稳健校正后 <b style="color:#2ecc71">BY(保守)留 ${df.n_by_sig_q10}</b> / BH(乐观)留 ${df.n_bh_sig_q10}，最佳因子 Bonferroni(FWER) p=${df.best_factor_bonferroni_p}。
      ${df.note ? `<br><span style="color:var(--muted);font-size:0.76rem">${esc2(df.note)}</span>` : ""}
      ${df.caveat ? `<br><span style="color:var(--muted);font-size:0.72rem">⚠ ${esc2(df.caveat)}</span>` : ""}
    </div>` : "";
  el.innerHTML = `
    <div style="color:var(--muted);font-size:0.78rem;line-height:1.6;margin-bottom:.7rem;">
      方法：测试折拼接为样本外序列算「触发胜率−基率」（块自助 CI）；purged+embargo 扩窗用于跨折<b>符号稳定性</b>检验；
      再用<b>从未参与训练的 2024-2026</b>做终审。「符号」列=逐折方向一致的折数（全一致才算稳健）。
      看跌因子压低胜率是<b>对</b>，不是有害。
    </div>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr style="color:var(--muted);font-size:0.72rem;">
        <th style="padding:.25rem .5rem;text-align:left;">因子</th><th style="padding:.25rem .5rem;">假设</th>
        <th style="padding:.25rem .5rem;text-align:right;">开发集差</th><th style="padding:.25rem .5rem;text-align:right;">块自助p</th>
        <th style="padding:.25rem .5rem;">符号</th>
        <th style="padding:.25rem .5rem;text-align:right;">holdout</th><th style="padding:.25rem .5rem;">裁决</th>
      </tr></thead><tbody>${rows}</tbody>
    </table>
    <div class="insight" style="margin-top:.85rem;">
      <strong>结论：${s.informative ?? 0} 个因子样本外稳健，${s.fragile ?? 0} 个 regime 依赖，${s.noise ?? "?"} 个噪声，${s.misleading ?? 0} 个反向。</strong><br>
      <b>没有一个因子在所有 regime 上符号稳定</b>。最强的 <b style="color:#f39c12">BTC 20日动量</b>（涨/跌两向）拼接后高度显著
      （p≤0.08）、且在 2024-2026 确认，但逐折符号会翻——信号高度集中在 2017-2021 加密牛市，属 <b>regime 依赖，不可外推</b>。
      均线、RSI、波动率、隔夜动量等技术因子<b>全是噪声</b>。模型 AUC&lt;0.5 不是市场纯随机，
      而是没有跨 regime 稳定的因子 + 重复计数的日历效应。<br>
      <span style="color:var(--muted)">主观事件因子（${(fa.subjective_event_lrs||[]).join("、")}）无任何历史样本支撑，应标注或移出。
      ${baseHold!=null?`注：holdout(2024-2026)是 ${baseHold}% 上涨的强牛市单一 regime，对看涨因子的"方向不翻"确认力有限。`:""}</span><br><br>
      <strong>换靶子探针：</strong>方向 AUC 跨 regime 摆动（2012-2024 拼接 <b>${dirAuc ?? "?"}</b>，单一 2024-2026 ${probe.direction_auc_holdout ?? "?"}）——
      这种不稳定本身就是非平稳性；波动率 AUC <b style="color:#2ecc71">${volAuc ?? "?"}</b> 更高（单点 holdout，仍需多 regime 复核）。
      <b>数据倾向：把 ML/深度学习力气投向"预测波动率/市场状态"，而非"预测涨跌方向"。</b>
    </div>${deflHtml}`;
}

// ── 波动率状态预测原型（P2-6，研究面板）──
function renderVolModel() {
  const el = document.getElementById("vol-model");
  if (!el) return;
  const v = SIGNALS?.vol_model;
  if (!v) { el.innerHTML = `<span style="color:var(--muted)">运行一次完整流水线后显示</span>`; return; }
  const ho = v.holdout_auc, vix = v.holdout_vix_only_auc, dir = v.direction_auc_reference, gain = v.holdout_model_gain_over_vix;
  const vd = v.vol_direction;
  const bar = (auc, label, color) => {
    const pct = auc == null ? 0 : Math.max(0, Math.min(100, ((auc - 0.5) / 0.5) * 100));
    return `<div style="margin:.35rem 0;">
      <div style="display:flex;justify-content:space-between;font-size:0.78rem;">
        <span>${label}</span><span style="font-weight:700;color:${color}">${auc != null ? Number(auc).toFixed(3) : "—"}</span></div>
      <div style="height:8px;background:var(--border);border-radius:4px;overflow:hidden;">
        <div style="height:100%;width:${pct}%;background:${color};border-radius:4px;"></div></div>
    </div>`;
  };
  const imps = (v.importances || []).slice(0, 6).map(i =>
    `<tr style="border-top:1px solid var(--border)33;"><td style="padding:.2rem .5rem;">${esc(i.feature)}</td>
     <td style="padding:.2rem .5rem;text-align:right;color:${i.importance>0?"#2ecc71":"var(--muted)"}">${i.importance>0?"+":""}${Number(i.importance)}</td></tr>`).join("");
  el.innerHTML = `
    <div style="color:var(--muted);font-size:0.78rem;line-height:1.6;margin-bottom:.6rem;">
      靶子：${esc(v.target||"")}。模型：${esc(v.model||"")}。<br>${esc(v.method||"")}
    </div>
    ${vd ? `
    <div style="font-size:0.82rem;font-weight:700;margin:.2rem 0 .3rem;">① 波动率会"升还是降"？（一个被审查纠正的诚实教训）</div>
    ${bar(vd.mechanical_null_auc, "机械假象地板（打乱未来后基线仍有的 AUC）", "#e67e22")}
    ${bar(vd.pooled_auc_naive_meanrev, "自指基线(-当前波动)：大半是上面的假象", "#9b59b6")}
    ${bar(vd.pooled_auc_model, "模型(波动动态特征)：坐在同一假象台座上", "#8b949e")}
    <div class="insight" style="margin:.5rem 0 1rem;">
      <strong>⚠ 这里差点上当：rv20 同时在标签两侧（fwd&gt;rv20）又当特征，制造<b style="color:#e67e22">机械自指假象</b>——把未来打乱、毁掉一切真信号后，基线 AUC 仍≈${Number(vd.mechanical_null_auc).toFixed(2)}。</strong>
      所以 ${Number(vd.pooled_auc_model).toFixed(2)}/${Number(vd.pooled_auc_naive_meanrev).toFixed(2)} 这种"高 AUC"<b>大半是假象、不可交易</b>。
      唯一可解释的是模型 vs 同样自指基线之差 ${vd.model_vs_naive ? `= <b>${vd.model_vs_naive.diff>0?"+":""}${vd.model_vs_naive.diff}</b>（CI ${JSON.stringify(vd.model_vs_naive.ci95)}，p=${vd.model_vs_naive.p_boot}，<b>不显著</b>）` : ""}。
      <b>诚实结论：连波动率升降，用机械公平的对比也没找到稳健可利用信号。</b>
      <span style="color:var(--muted)">${esc(vd.note||"")}</span>
    </div>` : ""}

    <div style="font-size:0.82rem;font-weight:700;margin:.2rem 0 .3rem;">② 对照：预测波动率"绝对水平"（VIX 必然赢=同义反复）</div>
    ${bar(ho, "波动率水平·模型(12特征) · 终审", "#8b949e")}
    ${bar(vix, "波动率水平·只看VIX · 终审", "#9b59b6")}
    ${bar(dir, "对照：涨跌方向（不可测）", "#e74c3c")}
    <div style="font-size:0.74rem;color:var(--muted);margin:.3rem 0 .6rem;">条形=AUC相对0.5(随机)的优势。
      水平靶子上模型只比裸看 VIX 高 ${gain ?? "?"}——VIX 就是波动率水平的市场报价，赢是同义反复，信息量低。</div>
    <div style="font-size:0.75rem;color:var(--muted);margin-bottom:.2rem;">holdout 排列重要性（水平靶子）</div>
    <table style="width:100%;border-collapse:collapse;font-size:0.78rem;"><tbody>${imps}</tbody></table>
    <div class="insight" style="margin-top:.7rem;">
      <strong>总结：波动率比涨跌方向可测得多；但要问对问题。</strong><br>
      预测<b>波动"水平"</b>→ VIX 必然赢（同义反复）；预测<b>波动"升降"</b>→ VIX 失效，真信号在<b>均值回归</b>里，
      模型只能再多挤出一丝且不 robust。启示：<b>选对靶子 + 市场已把容易的部分定价</b>，复杂模型很难再加价值。
      <span style="color:var(--muted)">${esc(v.note||"")}</span>
    </div>`;
}

// ── 事件影响一览（整合宏观日历 + 历史事件研究 + 诚实框架）──
function renderEventImpact() {
  const el = document.getElementById("event-impact");
  if (!el || !SIGNALS) return;
  const cal = SIGNALS.macro_calendar || [];
  const es = SIGNALS.event_study || {};
  const today = localDateStr();

  // ① 即将到来的调度型事件（宏观日历）——放大波动、方向无稳定偏向
  const upcoming = cal.filter(e => e.date >= today).slice(0, 8).map(e => {
    const d = new Date(e.date + "T00:00:00");
    const days = Math.round((d - new Date(today + "T00:00:00")) / 86400000);
    return `<div style="display:flex;justify-content:space-between;gap:.5rem;padding:.25rem .5rem;border-top:1px solid var(--border)33;">
      <span>${esc(e.date)} <span style="color:var(--muted);font-size:0.72rem;">${days<=0?"今天":"约"+days+"天后"}</span></span>
      <span style="color:var(--text);font-size:0.78rem;">${esc(e.label)}</span></div>`;
  }).join("") || `<div style="color:var(--muted);font-size:0.78rem;padding:.3rem .5rem;">近期无已排程宏观事件</div>`;

  // ② 历史事件类型反应——诚实呈现：小样本、样本内，去掉绿红方向色与裸 p 值
  // （绿红色=暗示可预测方向，裸 p 值=被读成"显著信号"，都违反铁律；胜率带基准对照）
  const rows = Object.entries(es).map(([k, v]) => {
    const ar = v.avg_return, smallN = (v.n || 0) < 15;
    return `<tr style="border-top:1px solid var(--border)33;">
      <td style="padding:.25rem .5rem;">${esc(v.label || k)}</td>
      <td style="padding:.25rem .5rem;text-align:center;color:${smallN?"#e67e22":"var(--muted)"};" title="样本量">n=${esc(v.n)}${smallN?" ⚠":""}</td>
      <td style="padding:.25rem .5rem;text-align:right;color:var(--text);">${ar>0?"+":""}${esc(ar)}%</td>
      <td style="padding:.25rem .5rem;text-align:right;color:var(--muted);">${esc(v.win_rate)}% <span style="font-size:0.66rem;">(基准${esc(v.base_win_rate)}%)</span></td>
    </tr>`;
  }).join("");

  el.innerHTML = `
    <div style="color:var(--muted);font-size:0.78rem;line-height:1.6;margin-bottom:.6rem;">
      "如何把指数级事件纳入考虑"的诚实答案：<b>调度型事件（FOMC/CPI/非农）当天放大波动、方向无稳定偏向；
      历史冲击事件后市场反应样本太小、且是样本内统计，不能当预测。</b>事件影响的是<b>波动/不确定性</b>，不是可交易的方向。
    </div>

    <div style="font-size:0.8rem;font-weight:600;margin-bottom:.2rem;">① 即将到来的调度型事件（波动放大日）</div>
    <div style="margin-bottom:.8rem;">${upcoming}
      <div style="font-size:0.7rem;color:var(--muted);margin-top:.3rem;">→ 纳入方式：这些天<b>避免重仓新开/加杠杆</b>，等尘埃落定，而不是猜方向。</div>
    </div>

    <div style="font-size:0.8rem;font-weight:600;margin-bottom:.2rem;">② 历史冲击事件后 30 日反应（样本内统计）</div>
    <table style="width:100%;border-collapse:collapse;font-size:0.76rem;">
      <thead><tr style="color:var(--muted);font-size:0.7rem;">
        <th style="text-align:left;padding:.25rem .5rem;">事件类型</th><th style="padding:.25rem .5rem;">样本</th>
        <th style="text-align:right;padding:.25rem .5rem;">30日均涨跌</th><th style="text-align:right;padding:.25rem .5rem;">胜率 vs 基准</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>

    <div class="insight" style="margin-top:.85rem;">
      <strong>诚实警告：</strong>上表多数事件 <b>n 极小</b>（如首次加息 n=5、疫情 n=2），且是<b>样本内</b>统计、重叠窗口 p 值偏乐观——
      <b>这是"历史上发生过什么"，不是"下次会怎样"。</b>地缘冲击/疫情这类一次性事件尤其不可外推；胜率几乎都贴着基准（无边际）。
      事件提高的是波动/不确定性。<b>注：本站"叠加事件"开关会按这些历史 LR 微调概率，但幅度小、未经样本外验证——当 what-if 玩具看，别当强信号。</b>
      <span style="color:var(--muted)">纳入事件的正确方式 = 在高波动事件日控制仓位/风险，而非预测涨跌。</span>
    </div>`;
}

// ── 量化方法论页面（把项目映射到专业量化文献 + 诚实负结果）──
function renderQuantMethodology() {
  const el = document.getElementById("quant-methodology");
  if (!el) return;
  // 织入几个真实数字，让"方法论"不是空话
  const bm = SIGNALS?.benchmark?.summary || {};
  const vd = SIGNALS?.vol_model?.vol_direction;
  const fa = SIGNALS?.factor_audit?.summary || {};
  const dirAuc = SIGNALS?.factor_audit?.target_probe?.direction_auc_pooled_2012_2024;

  const method = (name, lit, how) => `
    <tr style="border-top:1px solid var(--border)33;">
      <td style="padding:.3rem .5rem;font-weight:600;">${name}</td>
      <td style="padding:.3rem .5rem;color:var(--muted);font-size:0.74rem;">${lit}</td>
      <td style="padding:.3rem .5rem;font-size:0.78rem;">${how}</td>
    </tr>`;

  el.innerHTML = `
    <div style="color:var(--muted);font-size:0.8rem;line-height:1.65;margin-bottom:.8rem;">
      这个项目最初从生态学/农学的"什么都试试"出发，诚实做下去，<b style="color:var(--text)">独立收敛到了 López de Prado 的现代量化反过拟合框架</b>——
      机构与对冲基金用的就是这套。卖点不是"信号准"，而是<b style="color:var(--text)">诚实分清真规律 vs 幻觉</b>。
    </div>

    <div style="font-size:0.85rem;font-weight:700;margin:.3rem 0 .3rem;">① 我们用的方法 ↔ 专业量化文献</div>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr style="color:var(--muted);font-size:0.7rem;">
        <th style="text-align:left;padding:.3rem .5rem;">方法</th><th style="text-align:left;padding:.3rem .5rem;">文献出处</th><th style="text-align:left;padding:.3rem .5rem;">我们怎么用</th></tr></thead>
      <tbody>
        ${method("Walk-forward 验证", "Pardo（交易策略验证黄金标准）", "六折滚动，训练→测试，跨多个 regime")}
        ${method("Purged + Embargo CV", "López de Prado 2017（防时序泄漏）", "因子尸检/波动率：切掉跨界泄漏的训练尾部")}
        ${method("块自助（Block Bootstrap）", "重叠窗口的正确显著性", "20日重叠→t检验p值偏乐观一个数量级，改用整块重采样")}
        ${method("干净保留集（Holdout）", "嵌套验证", "2024-2026 从未进训练；且只用来证伪不证实")}
        ${method("硬基线对比", "不比稻草人", "方向比基率(非0.5)、波动比VIX、策略比买入持有")}
        ${method("回测过拟合警惕", "Bailey & López de Prado 2014", "试几个配置就能凑高回测→我们把试过的都登记、做多重比较校正")}
        ${method("机械假象检测", "置换检验(permutation null)", "波动率升降：打乱未来证明高AUC是自指假象，不是信号")}
      </tbody>
    </table>

    <div style="font-size:0.85rem;font-weight:700;margin:1rem 0 .3rem;">② 我们用这套方法证伪了什么（诚实负结果）</div>
    <div class="insight" style="margin-top:0;">
      <div style="line-height:1.8;">
        ❌ <b>短期方向不可样本外预测</b>：综合信号拼接 AUC ≈ <b>${dirAuc!=null?Number(dirAuc).toFixed(2):"0.45"}</b>（&lt;0.5）；逻辑回归更差。<br>
        ❌ <b>因子大多是噪声</b>：尸检 ${fa.noise ?? 13} 个噪声 / ${fa.fragile ?? 2} 个 regime 依赖 / <b>${fa.informative ?? 0} 个稳健</b>。<br>
        ❌ <b>波动率"水平"可测但已被 VIX 定价</b>；连"升/降"用机械公平对比也<b>无稳健信号</b>${vd?.model_vs_naive?`（模型−基线 ${vd.model_vs_naive.diff>0?"+":""}${vd.model_vs_naive.diff}，p=${vd.model_vs_naive.p_boot}，不显著）`:""}。<br>
        ✅ <b>真实可用的</b>：股权溢价(买入持有)、波动率聚集、隔夜异象、相关性体制——用于<b>管理风险</b>，不是预测涨跌。
      </div>
      <div style="margin-top:.6rem;color:var(--muted);">
        Benchmark 记分卡当前：打败 ${bm.beats ?? 0} · 持平 ${bm.ties ?? 0} · 未达 ${bm.loses ?? 0} · 数据不足 ${bm.insufficient ?? 0}。
        "迄今 0 个模型稳健打败诚实基线"——这是诚实现状，不是失败。
      </div>
    </div>

    <div style="font-size:0.85rem;font-weight:700;margin:1rem 0 .3rem;">③ 和"散户量化"的区别 + 升级路线</div>
    <div style="font-size:0.8rem;line-height:1.7;color:var(--muted);">
      <b style="color:var(--text)">区别</b>：99% 的散户量化用样本内回测自吹"我的信号很准"；我们用块自助 + 干净保留集 + benchmark，
      敢公开说"打不赢基率"。<b style="color:var(--text)">这才是机构量化的标准。</b><br>
      <b style="color:var(--text)">升级路线</b>：要更严谨，升<b>验证方法</b>不升模型——Combinatorial Purged CV (CPCV) + Deflated Sharpe
      （文献证明比单一 walk-forward 更能防过拟合）。加 XGBoost 之类只会让回测更好看、样本外更差。
    </div>
    <div style="font-size:0.72rem;color:var(--muted);margin-top:.7rem;">
      文献：López de Prado《Advances in Financial Machine Learning》；Bailey & López de Prado 2014（回测过拟合）；Pardo（walk-forward）。仅供学习研究，不构成投资建议。
    </div>`;
}

// ── 市场结构解释（PCA + 相关性体制 + 因果回路）──
function renderMarketStructure() {
  const el = document.getElementById("market-structure");
  if (!el) return;
  const ms = SIGNALS?.market_structure;
  if (!ms) { el.innerHTML = `<span style="color:var(--muted)">运行一次完整流水线后显示</span>`; return; }

  // 近零载荷归零，避免 "-0" 显示
  const ld = x => Math.abs(x) < 0.005 ? 0 : Number(x);
  // PCA：主成分解释力 + 载荷（前5）
  const pcs = (ms.pca?.components || []).map(c => {
    const load = c.loadings.slice(0, 5).map(l => {
      const val = ld(l.loading);
      const col = val > 0 ? "#2ecc71" : val < 0 ? "#e74c3c" : "var(--muted)";
      return `<span style="color:${col};margin-right:.5rem;">${esc(l.label)} ${val>0?"+":""}${val}</span>`;
    }).join("");
    return `<div style="margin:.3rem 0;">
      <div style="font-size:0.78rem;"><b>PC${c.pc}</b> 解释 <b>${Number(c.explained_pct)}%</b> 共同变动</div>
      <div style="font-size:0.74rem;line-height:1.6;">${load}</div></div>`;
  }).join("");

  // 相关性体制：按 |shift| 排序。高亮门槛 0.4（>3×SE，超出噪声带才标记）
  const se = ms.corr_se ?? 0.13;
  const cr = [...(ms.correlation_regime || [])].sort((a,b)=>Math.abs(b.shift)-Math.abs(a.shift));
  const crRows = cr.map(r => {
    const big = Math.abs(r.shift) >= 0.4;
    const sc = r.shift > 0 ? "#2ecc71" : "#e74c3c";
    return `<tr style="border-top:1px solid var(--border)33;${big?"background:rgba(241,196,15,.06);":""}">
      <td style="padding:.22rem .5rem;">${esc(r.pair)}</td>
      <td style="padding:.22rem .5rem;text-align:right;">${r.recent_60d>0?"+":""}${Number(r.recent_60d)}</td>
      <td style="padding:.22rem .5rem;text-align:right;color:var(--muted);">${r.full_history>0?"+":""}${Number(r.full_history)}<span style="font-size:0.62rem;">·${r.full_years}y</span></td>
      <td style="padding:.22rem .5rem;text-align:right;color:${sc};font-weight:${big?700:400};">${r.shift>0?"+":""}${Number(r.shift)}${big?" ⚠":""}</td>
    </tr>`;
  }).join("");

  // 因果回路（定性系统动力学）：两个核心反馈环
  const loop = (title, color, nodes, kind) => `
    <div style="border:1px solid ${color}44;border-radius:8px;padding:.6rem .8rem;background:${color}0d;">
      <div style="font-size:0.78rem;font-weight:700;color:${color};margin-bottom:.3rem;">${title}</div>
      <div style="font-size:0.76rem;line-height:1.7;">${nodes.join(' <span style="color:'+color+'">→</span> ')}
        <span style="color:${color}">↻</span></div>
      <div style="font-size:0.68rem;color:var(--muted);margin-top:.25rem;">${kind}</div>
    </div>`;

  el.innerHTML = `
    <div style="color:var(--muted);font-size:0.78rem;line-height:1.6;margin-bottom:.6rem;">${esc(ms.window||"")}</div>
    <div style="font-size:0.8rem;font-weight:600;margin-bottom:.3rem;">① 主成分分析（PCA）：市场的共同因子</div>
    ${pcs}
    <div style="font-size:0.72rem;color:var(--muted);margin:.3rem 0 .8rem;">${esc(ms.pca?.pc1_note||"")}</div>

    <div style="font-size:0.8rem;font-weight:600;margin-bottom:.3rem;">② 相关性体制：近60日 vs 各对完整历史
      <span style="font-size:0.66rem;color:var(--muted);font-weight:400;">⚠ 60日为小样本，标准误≈±${se}，单格变化≥0.4(高亮)才超出噪声带</span></div>
    <table style="width:100%;border-collapse:collapse;font-size:0.76rem;">
      <thead><tr style="color:var(--muted);font-size:0.7rem;">
        <th style="text-align:left;padding:.22rem .5rem;">资产对</th><th style="text-align:right;padding:.22rem .5rem;">近60日</th>
        <th style="text-align:right;padding:.22rem .5rem;">完整历史</th><th style="text-align:right;padding:.22rem .5rem;">变化</th></tr></thead>
      <tbody>${crRows}</tbody>
    </table>

    <div style="font-size:0.8rem;font-weight:600;margin:.85rem 0 .4rem;">③ 因果回路：波动生态的反馈结构（定性·系统动力学）</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.5rem;">
      ${loop("波动聚集 · 平衡环", "#3498db",
             ["波动↑","风险厌恶↑","抛售/对冲","波动更高","随后均值回归","波动↓"], "balancing：波动有记忆但会回落，是可预测性来源")}
      ${loop("强平螺旋 · 增强环", "#e74c3c",
             ["价格↓","保证金不足","被迫卖出","价格更↓"], "reinforcing：危机时正反馈，相关性趋同、分散失效")}
    </div>

    <div class="insight" style="margin-top:.8rem;">
      <strong>当前结构读数：</strong>PC1（risk-on/off）解释约 ${ms.pca?.components?.[0]?.explained_pct ?? "?"}% 的跨资产共动——
      一个"风险偏好"开关解释了最大一块共同变动。高亮行（|变化|≥0.4，超出 60 日噪声带）<b>值得留意但仍需更长窗口确认</b>：
      例如纳指–黄金转正、纳指–利率/美元转负，<i>可能</i>暗示市场转向"利率/流动性主导"（降息预期来时股和黄金齐涨）——
      但 60 日样本噪声大，这是假设不是定论。
      <span style="color:var(--muted)">${esc(ms.note||"")}</span>
    </div>`;
}

function renderIPOCycle() {
  const el = document.getElementById("chart-ipo-cycle");
  if (!el) return;
  const rows = [...MEGA_IPOS].sort((a, b) => a.dd - b.dd);
  Plotly.newPlot("chart-ipo-cycle", [{
    type: "bar", orientation: "h",
    y: rows.map(r => r.name), x: rows.map(r => r.dd),
    marker: { color: rows.map(r => r.dd <= -15 ? "#e74c3c" : "#2ecc71") },
    text: rows.map(r => `${r.dd}%（${r.mkt}）`), textposition: "auto",
    hovertemplate: "%{y}<br>上市后12个月所在市场最大回撤 ≈ %{x}%<extra></extra>",
  }], {...DARK, margin:{...DARK.margin, l:150},
    xaxis:{...DARK.xaxis, title:"上市后12个月大盘最大回撤 %"}}, {responsive:true});
  const ins = document.getElementById("ipo-cycle-insight");
  if (ins) {
    const bad = MEGA_IPOS.filter(r => r.dd <= -15).length;
    ins.innerHTML = `<strong>IPO 周期视角：</strong>史上${MEGA_IPOS.length}个"超级/全民"IPO中，
      ${bad} 个之后12个月内所在市场出现 ≥15% 回撤（NTT 1987、中石油 2007、Rivian 2021 几乎贴顶）。
      机制真实——发行人挑估值最贵、散户最热情的时候卖股票（IPO 热度是 Baker-Wurgler 情绪指数成分）；
      但领先期 0–18 个月不等，也有谷歌/阿里/脸书这样的平静反例。
      <span style="color:var(--muted)">数值为历史约值。当温度计用，别当择时按钮——本站的答案永远是上面的校准概率。</span>`;
  }
}
