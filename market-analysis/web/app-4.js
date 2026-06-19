// ═══════════════════════════════════════════════════════
//  SpaceX SPCX IPO 追踪器
// ═══════════════════════════════════════════════════════
const SPCX_LISTING_DATE = "2026-06-12";
const SPCX_ISSUE_USD    = 135;
const SPCX_MY_SHARES    = 16;   // 站长实际获配股数（localStorage 未填时的默认值）

function renderSPCXTracker() {
  const el = document.getElementById("spcx-tracker");
  if (!el) return;
  const today = localDateStr();
  const hasListed = today >= SPCX_LISTING_DATE;

  // Countdown
  const listDt  = new Date(2026, 5, 12); // June 12 local time
  const daysLeft = Math.max(0, Math.ceil((listDt - new Date()) / 86400000));

  const savedShares = +(localStorage.getItem("spcx_shares") || SPCX_MY_SHARES);
  const savedPrice  = +(localStorage.getItem("spcx_price")  || 0);
  const savedCostAUD= +(localStorage.getItem("spcx_cost_aud")|| 0);

  // AUD value
  const issueAUD = savedShares * SPCX_ISSUE_USD / _portAudRate;
  const currAUD  = savedShares > 0 && savedPrice > 0 ? savedShares * savedPrice / _portAudRate : 0;
  const plAUD    = currAUD - issueAUD;
  const plPct    = issueAUD > 0 ? plAUD / issueAUD * 100 : 0;
  const gainPct  = savedPrice > 0 ? (savedPrice - SPCX_ISSUE_USD) / SPCX_ISSUE_USD * 100 : 0;

  // Pre-listing countdown
  if (!hasListed) {
    el.innerHTML = `
      <div class="spcx-countdown">
        <div class="spcx-big-num">${daysLeft}</div>
        <div class="spcx-big-label">天后上市<br><span style="font-size:0.7rem">2026年6月12日 Nasdaq</span></div>
      </div>
      <div style="font-size:0.8rem;display:flex;flex-direction:column;gap:.3rem;margin-bottom:.75rem;">
        <div class="spcx-row"><span style="color:var(--muted)">发行价</span><span style="font-weight:700">US$135</span></div>
        <div class="spcx-row"><span style="color:var(--muted)">交易所</span><span>Nasdaq</span></div>
        <div class="spcx-row"><span style="color:var(--muted)">澳洲通道</span><span>CommSec IPO</span></div>
      </div>
      <div style="font-size:0.78rem;color:var(--muted);margin-bottom:.3rem">我的申购（股数）</div>
      <input class="spcx-input" type="number" min="0" step="1" placeholder="等待分配结果后填写"
        value="${savedShares||""}" data-spcx-save="shares">
      ${savedShares > 0 ? `<div style="font-size:0.75rem;color:var(--muted);margin-top:.35rem">
        ≈ A$${issueAUD.toFixed(0)}（按发行价US$135 · AUD/USD≈${_portAudRate.toFixed(3)}）</div>` : ""}
      <div class="spcx-decision-box" style="background:rgba(155,89,182,.1);border-left:3px solid var(--purple);">
        <strong style="color:var(--purple)">🧭 站长个人观点</strong>
        <span style="font-size:0.68rem;color:var(--muted)">· 非模型信号 · 仅个人看法</span><br>
        1. 分配结果出来后填写实际获得股数<br>
        2. 高关注度 IPO 上市首日常高于发行价（历史差异极大，见详情面板的首日分布图）<br>
        3. 我个人会：<strong>卖一半锁利润，留一半长持</strong>
        <div style="font-size:0.66rem;color:var(--muted);margin-top:.3rem">⚠ 这是我的主观判断，不是数据信号；你的剧本可不同</div>
      </div>`;
    return;
  }

  // Post-listing —— 以下是站长个人剧本（第一人称），非模型信号
  let decisionHtml = "";
  if (savedPrice > 0) {
    if (gainPct > 50)      decisionHtml = `<span style="color:#f1c40f">🔥 溢价${gainPct.toFixed(0)}%：我会卖出至少一半锁利润</span>`;
    else if (gainPct > 25) decisionHtml = `<span style="color:#2ecc71">溢价${gainPct.toFixed(0)}%：我会卖 1/3–1/2，其余长持</span>`;
    else if (gainPct > 10) decisionHtml = `<span style="color:#2ecc71">溢价${gainPct.toFixed(0)}%：我会先持有，等更高位再减</span>`;
    else if (gainPct > 0)  decisionHtml = `<span style="color:#f1c40f">⏸ 小幅溢价：我会持有观察</span>`;
    else if (gainPct > -15)decisionHtml = `<span style="color:#e67e22">轻微破发：我会持有等反弹</span>`;
    else                   decisionHtml = `<span style="color:#e74c3c">大幅破发：我会重新评估，倾向长期持有</span>`;
  }

  el.innerHTML = `
    <div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.65rem;">
      <span style="background:#27ae6022;color:#27ae60;border-radius:4px;padding:2px 8px;font-size:0.75rem;font-weight:700">已上市 ✓</span>
      <span style="color:var(--muted);font-size:0.75rem">2026-06-12 Nasdaq</span>
    </div>
    <div style="font-size:0.78rem;color:var(--muted);margin-bottom:.3rem">实际获配股数</div>
    <input class="spcx-input" type="number" min="0" step="1" placeholder="股数"
      value="${savedShares||""}" data-spcx-save="shares">
    <div style="font-size:0.78rem;color:var(--muted);margin:.5rem 0 .3rem">当前市价 (USD)</div>
    <input class="spcx-input" type="number" min="0" step="0.01" placeholder="发行价135"
      value="${savedPrice||""}" data-spcx-save="price">
    ${savedShares > 0 && savedPrice > 0 ? `
    <div class="spcx-pl-row" style="margin-top:.65rem;">
      <div class="spcx-pl-val"><span class="u-cap">成本</span><br><strong>A$${issueAUD.toFixed(0)}</strong></div>
      <div class="spcx-pl-val"><span class="u-cap">市值</span><br><strong>A$${currAUD.toFixed(0)}</strong></div>
      <div class="spcx-pl-val"><span class="u-cap">盈亏</span><br>
        <strong style="color:${plAUD>=0?'#2ecc71':'#e74c3c'}">${plAUD>=0?'+':''}A$${plAUD.toFixed(0)}<br>${plPct>=0?'+':''}${plPct.toFixed(1)}%</strong></div>
    </div>
    <div class="spcx-decision-box" style="background:rgba(155,89,182,.08);border-left:3px solid var(--purple);">
      <strong style="color:var(--purple);font-size:0.72rem">🧭 站长个人剧本</strong>
      <span style="font-size:0.66rem;color:var(--muted)">· 非模型信号</span><br>${decisionHtml}
    </div>` : `<div style="font-size:0.78rem;color:var(--muted);margin-top:.5rem">填写股数和价格查看盈亏</div>`}`;
}

function saveSPCXData(field, val) {
  if (field === 'shares') localStorage.setItem("spcx_shares", val);
  if (field === 'price')  localStorage.setItem("spcx_price",  val);
  renderSPCXTracker();
  updateSPCXCalc();
}

// SPCX right-column detail panel
function renderSPCXDetail() {
  // Historical tech IPO first-day performance data
  const ipoData = [
    { name:"Airbnb\n2020",   gain:113 }, { name:"Snowflake\n2020", gain:112 },
    { name:"Twitter\n2013",  gain:73  }, { name:"Reddit\n2024",    gain:48  },
    { name:"Palantir\n2020", gain:37  }, { name:"ARM\n2023",       gain:25  },
    { name:"Rivian\n2021",   gain:29  }, { name:"Lyft\n2019",      gain:9   },
    { name:"Uber\n2019",     gain:-8  }, { name:"Robinhood\n2021", gain:-8  },
  ];
  const colors = ipoData.map(d => d.gain > 30 ? "#27ae60" : d.gain > 0 ? "#2ecc71" : "#e74c3c");
  Plotly.newPlot("chart-spcx-ipo", [{
    type:"bar", x: ipoData.map(d=>d.name), y: ipoData.map(d=>d.gain),
    marker:{ color: colors },
    text: ipoData.map(d => (d.gain >= 0 ? "+" : "") + d.gain + "%"),
    textposition:"outside", cliponaxis:false,
    hovertemplate:"<b>%{x}</b><br>首日涨幅: %{y}%<extra></extra>",
  }], {
    ...DARK, margin:{t:20,b:55,l:35,r:10},
    yaxis:{...DARK.yaxis, title:"首日涨幅 %"},
    xaxis:{...DARK.xaxis, tickfont:{size:9}},
    shapes:[{type:"line",x0:-0.5,x1:9.5,y0:0,y1:0,line:{color:"#555",dash:"dot",width:1}}],
  }, {responsive:true});

  document.getElementById("spcx-decision-detail").innerHTML =
    `<div style="font-size:0.78rem;line-height:1.6;">
       <strong>首日历史规律（客观）：</strong>高关注度科技 IPO 首日涨幅历史上差异极大（-8% 到 +113%，见左图）。
       这是历史分布，不代表 SPCX 会怎样。
     </div>

     <div style="margin-top:.75rem;background:rgba(155,89,182,.08);border-left:3px solid var(--purple);border-radius:0 6px 6px 0;padding:.6rem .8rem;">
       <strong style="color:var(--purple)">🧭 站长个人剧本</strong>
       <span style="font-size:0.68rem;color:var(--muted)">· 非模型信号 · 仅个人看法</span><br>
       <span style="font-size:0.8rem;line-height:1.6;">溢价 &gt;25% → 我会卖一半锁利润；溢价 &lt;10% → 我会先全持等中期；破发我不恐慌（我个人看好长期）。
       <span style="color:var(--muted);font-size:0.7rem;">⚠ 这是我的主观判断，不是数据信号，你的剧本可不同。</span></span>
     </div>

     <div style="margin-top:.75rem;font-size:0.78rem;line-height:1.65;">
       <strong>🧭 纳入与解禁机制（客观）：</strong><br>
       <b>纳指100 快速纳入</b>：常规在 12 月年度重构纳入（需约 3 个月 seasoning），但纳斯达克
       <b>2026-05 生效的 "Fast Entry" 规则</b>允许总市值排名进前 40（约 ≥$1000 亿）的超大型新股豁免 seasoning，
       公告后约 <b>15 个交易日</b>在年度重构外快速纳入——<b>SpaceX 体量（约 $1.75 万亿）符合，大概率走这条快速通道</b>。
       （研究普遍发现：纳入效应近年减弱、且常在公告时被提前定价，不宜当择时信号。）<br>
       <b>标普500</b>：由委员会自由裁量（无"够格即纳入"），硬门槛含 <b>最近季度 GAAP 净利为正且最近四季合计为正 + 流通股≥50% + 市值门槛</b>。
       SpaceX 流通比例低（仅售约 5.56 亿股、马斯克锁 366 天 + 高投票权），<b>短期进标普门槛很高</b>。<br>
       <b>解禁（已披露，分级释放）</b>：S-1（2026-05-20）列明非单一 180 天，而是 <b>分阶段</b>：
       Q2 财报后早期投资者可卖 20%（股价触发条件下再加 10%）；IPO 后第 <b>70/90/105/120/135 天各释放 7%</b>；
       Q3 财报后再 28%；<b>第 180 天后不受限</b>。<b>马斯克及部分核心投资者承诺持有 ≥366 天</b>。这些是真实的供给压力时点。
     </div>
     <div style="color:var(--muted);font-size:0.72rem;margin-top:.5rem;">机制为公开规则/已披露文件的客观说明（截至 2026-06）；个人剧本为站长主观看法。均非投资建议。</div>`;

  updateSPCXCalc();
}

function updateSPCXCalc() {
  const el = document.getElementById("spcx-calc");
  if (!el) return;
  const sharesIn = parseFloat(document.getElementById("spcx-shares-input")?.value || 0) || 0;
  const priceIn  = parseFloat(document.getElementById("spcx-price-input")?.value  || 0) || 0;
  // also sync with left-panel inputs and localStorage
  if (sharesIn) { localStorage.setItem("spcx_shares", sharesIn); renderSPCXTracker(); }
  if (priceIn)  { localStorage.setItem("spcx_price",  priceIn);  renderSPCXTracker(); }

  const shares = sharesIn || +(localStorage.getItem("spcx_shares")||SPCX_MY_SHARES);
  const price  = priceIn  || +(localStorage.getItem("spcx_price") ||0);
  const rate   = _portAudRate || 0.64;

  const issueAUD = shares * SPCX_ISSUE_USD / rate;
  const currAUD  = shares > 0 && price > 0 ? shares * price / rate : 0;
  const plAUD    = currAUD - issueAUD;
  const plPct    = issueAUD > 0 ? plAUD / issueAUD * 100 : 0;
  const gainPct  = price > 0 ? (price - SPCX_ISSUE_USD) / SPCX_ISSUE_USD * 100 : 0;
  const halfAUD  = currAUD / 2;
  const halfProfit = halfAUD - issueAUD / 2;

  if (!shares) { el.innerHTML = `<span style="color:var(--muted)">输入申购股数后显示</span>`; return; }

  let recHtml = "";
  if (price > 0) {
    if (gainPct > 25)      recHtml = `<div style="color:#27ae60;font-weight:600">建议：卖出一半 → 锁定 A$${halfProfit.toFixed(0)} 利润，留一半长期持有</div>`;
    else if (gainPct > 5)  recHtml = `<div style="color:#2ecc71;font-weight:600">建议：持有观察，等待更好的卖出时机</div>`;
    else if (gainPct >= 0) recHtml = `<div style="color:#f1c40f;font-weight:600">建议：持有，SpaceX长期前景强劲</div>`;
    else                   recHtml = `<div style="color:#e67e22;font-weight:600">破发：短期持有等待反弹，长期看好</div>`;
  }

  el.innerHTML = `
    <div class="spcx-pl-row">
      <div class="spcx-pl-val"><span class="u-cap">股数</span><br><strong>${shares}</strong></div>
      <div class="spcx-pl-val"><span class="u-cap">成本(AUD)</span><br><strong>A$${issueAUD.toFixed(0)}</strong></div>
      ${currAUD > 0 ? `<div class="spcx-pl-val"><span class="u-cap">市值(AUD)</span><br><strong>A$${currAUD.toFixed(0)}</strong></div>
      <div class="spcx-pl-val"><span class="u-cap">盈亏</span><br>
        <strong style="color:${plAUD>=0?'#2ecc71':'#e74c3c'}">${plAUD>=0?'+':''}A$${plAUD.toFixed(0)}<br>${plPct>=0?'+':''}${plPct.toFixed(1)}%</strong></div>` : ""}
    </div>
    ${currAUD > 0 && gainPct > 5 ? `<div style="font-size:0.78rem;color:var(--muted)">卖一半可入袋 <strong style="color:#2ecc71">A$${halfProfit.toFixed(0)}</strong></div>` : ""}
    ${recHtml}`;
}

// ── 盘中轻量报价（quotes.json，CI 每10分钟产出；页面每5分钟自动重拉）──
let QUOTES = null;
async function loadQuotes() {
  try {
    const r = await fetch("quotes.json?_=" + Date.now());
    if (r.ok) QUOTES = await r.json();
  } catch(e) { /* 文件可能尚未生成，靠 stocks.json 兜底 */ }
  renderSPCXMonitor();
}
setInterval(loadQuotes, 5 * 60 * 1000);   // IPO 首笔成交等场景：无需手动刷新自动上墙

// ── SPCX 监视卡：盘中报价(10分钟) > 流水线收盘价(30分钟) + 解禁/税务倒计时 ──
function _spcxDaysFrom(listDt, days) {
  const d = new Date(listDt.getTime() + days * 86400000);
  return d;
}
function renderSPCXMonitor() {
  const el = document.getElementById("spcx-monitor");
  if (!el) return;
  const sp = STOCKS?.spcx;
  const listDt = new Date(2026, 5, 12);
  const now = new Date();
  const daysListed = Math.max(1, Math.floor((now - listDt) / 86400000) + 1);  // 上市日=第1天

  // ① 价格卡：盘中报价(quotes.json, ~10分钟) 优先，流水线收盘(stocks.json) 兜底。同源数据，国内访客可用。
  const q = QUOTES?.quotes?.SPCX;
  let priceHtml, autoPrice = null;
  // 占位价识别：成交量为 0，或"最后成交时间"早于今天且价格还钉在发行价
  // ——大型 IPO 开盘竞价常持续 1-3 小时，期间行情源只有发行价占位，不是真成交
  const tradeMs = q?.ts ? q.ts * 1000 : null;
  const tradeStale = tradeMs != null && (Date.now() - tradeMs > 20 * 3600 * 1000);
  const awaitingFirstTrade = q && q.price === SPCX_ISSUE_USD &&
        ((q.vol === 0) || tradeStale || q.prev_close == null);
  if (q && q.price && awaitingFirstTrade && daysListed <= 1) {
    // 有活的订单簿时展示 bid/ask 中值指示价（明确标注非成交价）
    const mid = q.bid && q.ask ? (q.bid + q.ask) / 2 : null;
    const midHtml = mid ? `
        <span style="font-size:1.25rem;font-weight:800;">≈US$${mid.toFixed(2)}</span>
        <span style="font-weight:700;color:${mid>=SPCX_ISSUE_USD?'#2ecc71':'#e74c3c'}">${mid>=SPCX_ISSUE_USD?'+':''}${((mid/SPCX_ISSUE_USD-1)*100).toFixed(1)}% vs 发行价</span>
        <span style="color:var(--muted);font-size:0.72rem">订单簿指示价（bid ${q.bid} / ask ${q.ask} 中值）· 非成交价</span>` : "";
    priceHtml = `
      <div style="display:flex;gap:.65rem;flex-wrap:wrap;align-items:baseline;">
        ${midHtml}
        <span style="font-size:0.95rem;font-weight:700;color:#f1c40f;">⏳ 等待首笔成交确认</span>
        <span style="color:var(--muted);font-size:0.74rem">超大型 IPO 首笔成交常在开盘后 1–3 小时进入公开行情源；确认后此处自动切换为成交价。</span>
      </div>`;
  } else if (q && q.price) {
    const vsIssue = (q.price / SPCX_ISSUE_USD - 1) * 100;
    const up = vsIssue >= 0;
    const tradeT = tradeMs
      ? new Date(tradeMs).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
      : (QUOTES.generated ? new Date(QUOTES.generated).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : "");
    autoPrice = q.price;
    priceHtml = `
      <div style="display:flex;gap:.65rem;flex-wrap:wrap;align-items:baseline;">
        <span style="font-size:1.3rem;font-weight:800;">US$${q.price.toFixed(2)}</span>
        <span style="font-weight:700;color:${up?'#2ecc71':'#e74c3c'}">${up?'+':''}${vsIssue.toFixed(1)}% vs 发行价</span>
        ${q.chg_pct != null ? `<span style="color:${q.chg_pct>=0?'#2ecc71':'#e74c3c'};font-size:0.8rem">日内 ${q.chg_pct>=0?'+':''}${q.chg_pct}%</span>` : ""}
        <span style="color:var(--muted);font-size:0.72rem">盘中报价 · 成交 ${tradeT}</span>
      </div>`;
  } else if (sp && sp.last) {
    const up = sp.vs_issue_pct >= 0;
    autoPrice = sp.last;
    priceHtml = `
      <div style="display:flex;gap:.65rem;flex-wrap:wrap;align-items:baseline;">
        <span style="font-size:1.3rem;font-weight:800;">US$${sp.last.toFixed(2)}</span>
        <span style="font-weight:700;color:${up?'#2ecc71':'#e74c3c'}">${up?'+':''}${sp.vs_issue_pct.toFixed(1)}% vs 发行价</span>
        ${sp.chg_1d != null ? `<span style="color:${sp.chg_1d>=0?'#2ecc71':'#e74c3c'};font-size:0.8rem">日 ${sp.chg_1d>=0?'+':''}${sp.chg_1d}%</span>` : ""}
        <span style="color:var(--muted);font-size:0.72rem">收盘数据 ${sp.date} · 区间 ${sp.low}–${sp.high}</span>
      </div>`;
  } else {
    priceHtml = `<span style="color:var(--muted);font-size:0.8rem">尚无 SPCX 数据（上市首个交易时段后出现；盘中可点上方"获取价格"手动取）</span>`;
  }
  // 用户没手填过价格时，自动用最新价算盈亏
  if (autoPrice != null) {
    const inp = document.getElementById("spcx-price-input");
    if (inp && !inp.value && !+(localStorage.getItem("spcx_price") || 0)) {
      inp.value = autoPrice.toFixed(2);
      updateSPCXCalc();
    }
  }

  // ② 解禁/里程碑倒计时（S-1 披露的分级释放 + CGT 12个月折扣日）
  const milestones = [
    { d: 70,  label: "解禁 7%（第70天）" },
    { d: 90,  label: "解禁 7%（第90天）" },
    { d: 105, label: "解禁 7%（第105天）" },
    { d: 120, label: "解禁 7%（第120天）" },
    { d: 135, label: "解禁 7%（第135天）" },
    { d: 180, label: "全面解禁（第180天）" },
    { d: 366, label: "马斯克持有承诺到期" },
    { d: 367, label: "🇦🇺 CGT 50%折扣生效（持有满12个月后卖出）" },
  ].map(m => {
    const dt = _spcxDaysFrom(listDt, m.d);
    const left = Math.ceil((dt - now) / 86400000);
    return { ...m, dt, left };
  });
  const next = milestones.find(m => m.left > 0);
  const rows = milestones.map(m => {
    const passed = m.left <= 0;
    const isNext = m === next;
    const dateStr = `${m.dt.getFullYear()}-${String(m.dt.getMonth()+1).padStart(2,"0")}-${String(m.dt.getDate()).padStart(2,"0")}`;
    return `<div style="display:flex;justify-content:space-between;gap:.5rem;padding:.18rem 0;font-size:0.78rem;
                 ${passed ? "color:var(--muted);text-decoration:line-through;" : ""}
                 ${isNext ? "font-weight:700;" : ""}">
      <span>${isNext ? "→ " : ""}${m.label}</span>
      <span style="white-space:nowrap;${isNext ? "color:#f1c40f;" : "color:var(--muted);"}">${dateStr}${passed ? "" : ` · ${m.left}天`}</span>
    </div>`;
  }).join("");

  el.innerHTML = `
    <div style="background:var(--surface2);border-radius:7px;padding:.75rem .9rem;margin-bottom:1rem;">
      <div style="font-size:0.75rem;color:var(--muted);margin-bottom:.35rem;">📡 SPCX 监视 · 上市第 ${daysListed} 天 · 流水线自动更新（盘中约30分钟一次）</div>
      ${priceHtml}
      <div style="margin-top:.65rem;border-top:1px solid var(--border);padding-top:.5rem;">
        <div style="font-size:0.72rem;color:var(--muted);margin-bottom:.25rem;">⏳ 供给压力与税务时点（S-1 披露 + 澳洲 CGT）</div>
        ${rows}
      </div>
      ${sp?.supply ? `
      <div style="margin-top:.55rem;border-top:1px solid var(--border);padding-top:.5rem;font-size:0.76rem;">
        <span style="color:var(--muted)">📦 供给面：</span>
        IPO 实际新发 ≈5.56亿股（<b>占总股本仅 ~7.5%</b>，筹码稀缺的来源）
        ${sp.supply.float_pct != null ? ` · Yahoo 流通口径 ${sp.supply.float_pct}%<span style="color:var(--muted);font-size:0.68rem">（含锁定股，勿当可交易量）</span>` : ""}
        ${sp.supply.short_pct_float != null ? ` · 做空占流通 <b>${sp.supply.short_pct_float}%</b>` : ""}
        ${sp.supply.inst_held_pct != null ? ` · 机构持仓 <b>${sp.supply.inst_held_pct}%</b>` : ""}
      </div>` : ""}
      <div style="margin-top:.55rem;background:var(--surface);border-radius:6px;padding:.5rem .7rem;font-size:0.74rem;line-height:1.6;color:var(--muted);">
        <b style="color:var(--text)">解禁怎么读（解禁 ≠ 必然抛售）：</b>解禁只是"可以卖"，会不会卖看持有人结构——
        <b>早期 VC 基金</b>有结构性卖出动机（基金到期要回收资金分给 LP）；<b>员工</b>有分散化动机（财富集中单一股票）；
        <b>马斯克</b>承诺持 366 天且为保控制权基本不会卖。学术证据（Field &amp; Hanka，约2,000家IPO样本）：
        解禁日平均异常收益约 <b style="color:#e74c3c">-1.5%</b>，幅度不大但方向稳定；SpaceX 的<b>分级解禁</b>（5×7%）
        正是为了把冲击摊平。真正值得盯的信号：每波解禁前后的<b>成交量放大</b>与<b>借券费率变化</b>，而非解禁日本身。
      </div>
      <div style="color:var(--muted);font-size:0.7rem;margin-top:.45rem;">
        CGT 日期按上市日申购计，实际以你的成交日为准。非投资建议。
      </div>
    </div>`;
}

// 拉取 SPCX 最新报价并填入盈亏计算器。
// 注：旧版直连 query1.finance.yahoo.com，浏览器跨域(CORS)必被拦截 → 永远"获取失败"；
// 且属境外第三方运行时依赖（国内访客打不开、违反本项目"同源自托管"原则）。
// 改为重拉同源 quotes.json（服务端流水线每~10分钟抓好的报价），无 CORS、国内可用。
async function fetchSPCXPrice() {
  const btn = document.getElementById("spcx-price-btn");
  const old = btn ? btn.textContent : "";
  if (btn) btn.textContent = "⏳ 获取中...";
  try {
    await loadQuotes();                              // 重拉 quotes.json 并重渲染监视卡
    const q = QUOTES?.quotes?.SPCX;
    const price = (q && q.price) ? q.price
                : (STOCKS?.spcx?.last || null);      // 报价缺失时退用收盘数据
    if (price) {
      const inp = document.getElementById("spcx-price-input");
      if (inp) { inp.value = price.toFixed(2); updateSPCXCalc(); }
      localStorage.setItem("spcx_price", price);
    } else {
      alert("报价暂未刷新（流水线约每10分钟更新 quotes.json）。请稍后再试，或在下方手动输入当前价。");
    }
  } catch(e) {
    alert("刷新失败，请在下方手动输入当前价格。");
  } finally {
    if (btn) btn.textContent = old || "📡 获取价格";
  }
}

// ═══════════════════════════════════════════════════════
//  加密恐惧贪婪指数
// ═══════════════════════════════════════════════════════
function fgMeta(score) {
  if (score <= 24) return { color:"#e74c3c", cn:"极度恐惧",  advice:"📈 历史最佳逆向买入时机（别人恐惧时贪婪）" };
  if (score <= 44) return { color:"#e67e22", cn:"恐惧",      advice:"可考虑分批建仓，情绪偏负面但未极端" };
  if (score <= 55) return { color:"#f1c40f", cn:"中性",      advice:"市场情绪中性，结合其他指标综合判断" };
  if (score <= 74) return { color:"#2ecc71", cn:"贪婪",      advice:"⚠️ 注意追高风险，短期回调概率上升" };
  return                  { color:"#27ae60", cn:"极度贪婪",  advice:"🔴 历史规律：此区间后续往往回调，适量减仓" };
}

async function fetchFearAndGreed() {
  const el = document.getElementById("fear-greed-section");
  if (!el) return;
  el.innerHTML = `<span style="color:var(--muted);font-size:0.78rem">加载中...</span>`;
  try {
    // 优先用同源 quotes.json(服务端 quick_quotes 抓的恐惧贪婪)——中国访客不必直连境外 API
    if (typeof loadQuotes === "function") { try { await loadQuotes(); } catch (e) { /* 用已有 QUOTES */ } }
    let data = QUOTES?.fear_greed;
    if (!data || !data.length) {
      const r = await fetch("https://api.alternative.me/fng/?limit=7&format=json");  // 兜底:直连境外
      if (!r.ok) throw new Error("HTTP " + r.status);
      data = (await r.json()).data || [];
    }
    renderFearGreed(data);
  } catch(e) {
    el.innerHTML = `<div style="font-size:0.78rem;color:var(--muted)">
      恐惧贪婪指数暂时无法加载
      <button data-fear-greed-retry
        style="margin-left:.5rem;background:var(--surface2);border:1px solid var(--border);color:var(--muted);padding:2px 8px;border-radius:4px;font-size:0.72rem;cursor:pointer;">重试</button>
    </div>`;
  }
}

function renderFearGreed(data) {
  const el = document.getElementById("fear-greed-section");
  if (!el || !data.length) return;
  const cur = data[0];
  const score = parseInt(cur.value);
  const m = fgMeta(score);

  // 7-day sparkline (oldest first)
  const spark = data.slice(0,7).reverse();
  const maxS = Math.max(...spark.map(d=>+d.value));
  const sparkHtml = spark.map(d => {
    const s = parseInt(d.value);
    const h = Math.max(3, Math.round(s / 100 * 26));
    const c = fgMeta(s).color;
    const dt = new Date(+d.timestamp*1000).toLocaleDateString("zh-CN",{month:"numeric",day:"numeric"});
    return `<div class="fg-spark-bar" style="height:${h}px;background:${c}" title="${dt} ${s}"></div>`;
  }).join("");

  const nextUpdate = cur.time_until_update
    ? `· ${Math.round(+cur.time_until_update/3600)}h后更新`
    : "";

  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.5rem;">
      <div>
        <div style="font-size:0.72rem;color:var(--muted);margin-bottom:.15rem">
          加密恐惧&贪婪指数 <span style="opacity:.6">(alternative.me${nextUpdate})</span>
        </div>
        <div style="display:flex;align-items:baseline;gap:.45rem;">
          <span style="font-size:2rem;font-weight:800;line-height:1;color:${m.color}">${score}</span>
          <span style="font-size:0.9rem;font-weight:700;color:${m.color}">${m.cn}</span>
        </div>
      </div>
      <div style="text-align:right;min-width:70px;">
        <div style="font-size:0.68rem;color:var(--muted);margin-bottom:.3rem;">7天走势</div>
        <div class="fg-sparkline">${sparkHtml}</div>
      </div>
    </div>
    <div class="fg-gauge-track">
      <div class="fg-needle" style="left:${score}%;background:${m.color}"></div>
    </div>
    <div style="display:flex;justify-content:space-between;font-size:0.65rem;color:var(--muted);margin-bottom:.45rem;">
      <span>0 极度恐惧</span><span>50 中性</span><span>100 极度贪婪</span>
    </div>
    <div style="font-size:0.78rem;color:${m.color};line-height:1.4">${m.advice}</div>
  `;
}

// ═══════════════════════════════════════════════════════
//  澳洲 CGT 税务计算器
// ═══════════════════════════════════════════════════════
// ──「显示货币」切换（AUD / USD / CNY）─────────────────────────────
// ⚠ 税务红线：calculateCGT 永远在 AUD 里算（澳洲 CGT 法定货币）。
//   货币切换【只换显示】，绝不改税务计算本身。输入框仍按 AUD 单价填。
const CGT_CURRENCIES = {
  AUD: { symbol: "A$", label: "AUD 澳元", locale: "en-AU" },
  USD: { symbol: "US$", label: "USD 美元", locale: "en-US" },
  CNY: { symbol: "¥",  label: "CNY 人民币", locale: "zh-CN" },
};
let _cgtFX = null;                  // { aud_usd, usd_cny, asof, generated } 来自 fx_rates.json
let _cgtDisplayCur = (typeof localStorage !== "undefined" &&
                      localStorage.getItem("cgt_display_cur")) || "AUD";
if (!CGT_CURRENCIES[_cgtDisplayCur]) _cgtDisplayCur = "AUD";

// 1 AUD = ? 目标币。AUD 优先用盘中实时 aud_rate（quotes.json），fx_rates.json 兜底。
function _cgtRateFromAUD(cur) {
  if (cur === "AUD") return 1;
  // AUD→USD：优先实时 QUOTES.aud_rate（≈0.70），否则 fx_rates.json
  const audUsd = (typeof QUOTES !== "undefined" && QUOTES && QUOTES.aud_rate)
    ? QUOTES.aud_rate : (_cgtFX && _cgtFX.aud_usd);
  if (cur === "USD") return audUsd || null;
  if (cur === "CNY") {            // AUD→USD→CNY 两段相乘
    const usdCny = _cgtFX && _cgtFX.usd_cny;
    return (audUsd && usdCny) ? audUsd * usdCny : null;
  }
  return null;
}
// 把 AUD 金额格式化成所选显示币种（带正负号/小数位）。换算不可得时回退 AUD 并标注。
function _cgtFmt(audAmount, { sign = false, decimals = 2 } = {}) {
  let cur = _cgtDisplayCur;
  let rate = _cgtRateFromAUD(cur);
  if (rate == null) { cur = "AUD"; rate = 1; }   // 汇率缺失：诚实回退 AUD，不瞎换
  const v = audAmount * rate;
  const c = CGT_CURRENCIES[cur];
  const num = Math.abs(v).toLocaleString(c.locale,
    { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  const pre = sign ? (v >= 0 ? "+" : "−") : (v < 0 ? "−" : "");
  return `${pre}${c.symbol}${num}`;
}

// 拉取 fx_rates.json（同源，国内访客可用）。失败不阻塞——AUD 始终可算。
async function loadCgtFXRates() {
  try {
    const r = await fetch("fx_rates.json?_=" + Date.now());
    if (r.ok) _cgtFX = await r.json();
  } catch (e) { /* 文件可能尚未生成；切 USD/CNY 时会提示并回退 AUD */ }
  renderCgtCurrencySelector();
  // 若结果已算过，按新汇率重渲染
  if (document.getElementById("cgt-result")?.innerHTML.trim()) calculateCGT();
}

function setCgtDisplayCur(cur) {
  if (!CGT_CURRENCIES[cur]) return;
  _cgtDisplayCur = cur;
  try { localStorage.setItem("cgt_display_cur", cur); } catch (e) {}
  renderCgtCurrencySelector();
  if (document.getElementById("cgt-result")?.innerHTML.trim()) calculateCGT();
}

// 把货币选择器 + 税务红线提示注入到计算器区域（结果容器上方）。纯 JS 渲染，不动 HTML。
function renderCgtCurrencySelector() {
  const result = document.getElementById("cgt-result");
  if (!result) return;
  let host = document.getElementById("cgt-currency-switch");
  if (!host) {
    // 用字面 id="..." 注入（也便于前端审计的 id 正则识别这个动态容器）
    result.insertAdjacentHTML("beforebegin", '<div id="cgt-currency-switch"></div>');
    host = document.getElementById("cgt-currency-switch");
  }
  if (!host) return;
  const btns = Object.keys(CGT_CURRENCIES).map(cur => {
    const active = cur === _cgtDisplayCur;
    const avail = cur === "AUD" || _cgtRateFromAUD(cur) != null;
    const c = CGT_CURRENCIES[cur];
    const style = active
      ? "background:rgba(52,152,219,.18);border:1px solid #3498db;color:#3498db;font-weight:700;"
      : "background:var(--surface2);border:1px solid var(--border);color:var(--muted);";
    const dis = avail ? "" : "opacity:.45;cursor:not-allowed;";
    return `<button type="button" data-cgt-cur="${cur}" ${avail ? "" : "disabled"}
      title="${avail ? "" : "汇率暂不可用（fx_rates.json 未生成）"}"
      style="${style}${dis}padding:.28rem .7rem;border-radius:5px;font-size:0.76rem;cursor:pointer;">${esc(c.label)}</button>`;
  }).join("");
  // 当前换算口径（让人看清用了哪条汇率），AUD 不显示
  let rateNote = "";
  if (_cgtDisplayCur !== "AUD") {
    const rate = _cgtRateFromAUD(_cgtDisplayCur);
    const sym = CGT_CURRENCIES[_cgtDisplayCur].symbol;
    rateNote = rate != null
      ? `<span style="color:var(--muted);font-size:0.7rem;">当前：1 AUD ≈ ${sym}${rate.toFixed(4)}${_cgtFX && _cgtFX.asof ? "（汇率 " + esc(_cgtFX.asof) + "）" : ""}</span>`
      : `<span style="color:#e67e22;font-size:0.7rem;">该币种汇率暂不可用，已回退按 AUD 显示</span>`;
  }
  host.innerHTML = `
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:.4rem;margin:.6rem 0 .35rem;">
      <span style="font-size:0.76rem;color:var(--muted);">显示货币：</span>
      ${btns}
      ${rateNote}
    </div>
    <div style="background:rgba(231,126,34,.08);border:1px solid rgba(231,126,34,.3);border-radius:6px;
                padding:.5rem .7rem;font-size:0.72rem;line-height:1.55;color:var(--muted);margin-bottom:.5rem;">
      ⚠️ <b>税务红线</b>：澳洲 CGT 法定按 <b>AUD</b> 计税，且买入/卖出各按<b>成交日汇率</b>计税。
      本货币切换<b>仅方便查看/估算</b>，<b>不能替代</b>按成交日 AUD 记账报税；用单一当前汇率换算会让税额失真。
      输入框仍请按 <b>AUD 单价</b>填写。
    </div>`;
}

function prefillCGT() {
  const asset = document.getElementById("cgt-asset")?.value;
  if (!asset || asset === "custom") return;
  const port = loadPortfolio();
  const item = port.find(p => p.ticker === asset);
  if (!item) return;
  // Pre-fill quantity
  const qtyEl = document.getElementById("cgt-qty");
  if (qtyEl && item.qty) qtyEl.value = item.qty;
  // Pre-fill sell price from live prices (convert USD→AUD)
  const liveUSD = portfolioPrices[asset] || item.priceUSD;
  const sellEl = document.getElementById("cgt-sell-aud");
  if (sellEl && liveUSD) sellEl.value = (liveUSD / _portAudRate).toFixed(4);
  // Pre-fill buy price from cost basis
  const costEl = document.getElementById("cgt-buy-aud");
  if (costEl && item.costUSD) costEl.value = (item.costUSD / _portAudRate).toFixed(4);
}

function calculateCGT() {
  const qty     = parseFloat(document.getElementById("cgt-qty")?.value) || 0;
  const buyAUD  = parseFloat(document.getElementById("cgt-buy-aud")?.value) || 0;
  const sellAUD = parseFloat(document.getElementById("cgt-sell-aud")?.value) || 0;
  const buyDate = document.getElementById("cgt-buy-date")?.value || "";
  const taxRate = parseFloat(document.getElementById("cgt-tax-rate")?.value) || 32.5;
  const el = document.getElementById("cgt-result");
  if (!el) return;

  if (!qty || !buyAUD || !sellAUD) {
    el.innerHTML = `<div style="color:var(--muted);font-size:0.82rem;padding:.5rem 0;">请填写数量、买入价和卖出价。</div>`;
    return;
  }

  const totalCost     = qty * buyAUD;
  const totalProceeds = qty * sellAUD;
  const rawGain       = totalProceeds - totalCost;
  const isGain        = rawGain > 0;

  // 12-month CGT discount
  let heldMonths = 0, eligible50 = false;
  if (buyDate) {
    heldMonths = Math.round((new Date() - new Date(buyDate)) / (1000*60*60*24*30.44));
    eligible50 = isGain && heldMonths >= 12;
  }

  const taxableGain = eligible50 ? rawGain * 0.5 : rawGain;
  const taxOnGain   = taxableGain > 0 ? taxableGain * (taxRate / 100) : 0;
  const medicare    = taxableGain > 0 ? taxableGain * 0.02 : 0;
  const totalTax    = taxOnGain + medicare;
  const netGain     = rawGain - totalTax;
  const netPct      = totalCost > 0 ? netGain / totalCost * 100 : 0;

  // Break-even sell price (where net gain = 0)
  const effectiveTaxRate = eligible50 ? (taxRate/100 + 0.02) * 0.5 : (taxRate/100 + 0.02);
  const breakEvenAUD = totalCost / qty / (1 - effectiveTaxRate);

  const gain_color = rawGain >= 0 ? "#2ecc71" : "#e74c3c";
  const assetName = document.getElementById("cgt-asset")?.value || "资产";

  // ⚠ 以上全部在 AUD 里算（税务红线）。下面只把【显示】换算到所选货币：_cgtFmt(aud)。
  const curMeta = CGT_CURRENCIES[_cgtRateFromAUD(_cgtDisplayCur) == null ? "AUD" : _cgtDisplayCur];
  const curTag = curMeta.symbol === "A$" ? ""
    : `<span style="color:var(--muted);font-weight:400;font-size:0.7rem;margin-left:.3rem;">· 显示币种 ${esc(curMeta.label.split(" ")[0])}（仅换算显示，税仍按 AUD）</span>`;

  el.innerHTML = `
    <div style="background:var(--surface2);border-radius:8px;padding:1rem;margin-top:.5rem;">
      <div style="font-size:0.8rem;font-weight:600;color:var(--muted);margin-bottom:.5rem;">
        ${assetName !== "custom" && assetName ? assetName : ""}  ${qty} 个 · 持有${heldMonths ? heldMonths+"个月" : "未知"}
        ${eligible50 ? '<span style="background:rgba(46,204,113,.2);color:#2ecc71;border-radius:3px;padding:1px 6px;font-size:0.7rem;margin-left:.3rem;">✓ 12月折扣</span>' : ""}${curTag}
      </div>
      <div class="cgt-result-row"><span style="color:var(--muted)">买入总成本</span><span>${_cgtFmt(totalCost)}</span></div>
      <div class="cgt-result-row"><span style="color:var(--muted)">卖出总收入</span><span>${_cgtFmt(totalProceeds)}</span></div>
      <div class="cgt-result-row"><span style="color:var(--muted)">资本利得（税前）</span><span style="color:${gain_color};font-weight:700">${_cgtFmt(rawGain, {sign:true})}</span></div>
      ${eligible50 ? `<div class="cgt-result-row"><span style="color:var(--muted)">50%折扣（持有>12月）</span><span style="color:#2ecc71">−${_cgtFmt(rawGain*0.5)}</span></div>` : ""}
      <div class="cgt-result-row"><span style="color:var(--muted)">应税金额</span><span>${_cgtFmt(Math.max(0,taxableGain))}</span></div>
      <div class="cgt-result-row"><span style="color:var(--muted)">个税（${taxRate}%）</span><span style="color:#e74c3c">−${_cgtFmt(taxOnGain)}</span></div>
      <div class="cgt-result-row"><span style="color:var(--muted)">Medicare征费（2%）</span><span style="color:#e74c3c">−${_cgtFmt(medicare)}</span></div>
      <div class="cgt-result-row cgt-highlight"><span>税后净盈亏</span>
        <span style="color:${netGain >= 0 ? '#2ecc71' : '#e74c3c'}">${_cgtFmt(netGain, {sign:true})} (${netPct >= 0 ? '+' : ''}${netPct.toFixed(1)}%)</span></div>
      ${isGain && !eligible50 && heldMonths > 0 && heldMonths < 12 ? `
      <div style="background:rgba(241,196,15,.1);border:1px solid rgba(241,196,15,.3);border-radius:5px;padding:.5rem .75rem;margin-top:.5rem;font-size:0.78rem;">
        💡 再持有 <strong style="color:#f1c40f">${12 - heldMonths} 个月</strong>即可享受50%折扣，届时预计少缴税 <strong style="color:#2ecc71">${_cgtFmt(rawGain*0.5*(taxRate/100+0.02), {decimals:0})}</strong>
      </div>` : ""}
      <div style="font-size:0.72rem;color:var(--muted);margin-top:.5rem;">
        保本卖出价（税后回本）≈ <strong>${_cgtFmt(breakEvenAUD, {decimals:4})}/个</strong>
      </div>
    </div>`;
}

// ── CGT 货币切换的初始化（自给自足，不依赖 app-5.js）──────────────
// 委派点击：货币按钮由 renderCgtCurrencySelector 动态生成，用委托绑一次即可。
function _cgtInitCurrencySwitch() {
  if (_cgtInitCurrencySwitch._done) return;
  if (!document.getElementById("cgt-result")) return;   // 不在「我的」视图的页面就跳过
  _cgtInitCurrencySwitch._done = true;
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-cgt-cur]");
    if (b && !b.disabled) setCgtDisplayCur(b.dataset.cgtCur);
  });
  renderCgtCurrencySelector();   // 先用已有/缺省汇率渲染出选择器
  loadCgtFXRates();              // 再异步拉 fx_rates.json，到了重渲染
}
// app-4.js 在 <body> 末尾加载，DOM 通常已就绪；兼容偶发未就绪的情况。
if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _cgtInitCurrencySwitch);
  } else {
    _cgtInitCurrencySwitch();
  }
}

// ── 自动刷新持仓价格 ──
let _priceRefreshTimer = null;
function toggleAutoRefresh(el) {
  if (_priceRefreshTimer) {
    clearInterval(_priceRefreshTimer);
    _priceRefreshTimer = null;
    el.textContent = "⏱ 自动";
    el.style.cssText = "background:var(--surface2);border:1px solid var(--border);color:var(--muted);padding:.3rem .8rem;border-radius:5px;font-size:0.78rem;cursor:pointer;";
  } else {
    fetchPortfolioPrices();
    _priceRefreshTimer = setInterval(fetchPortfolioPrices, 30000);
    el.textContent = "⏱ 30s·开";
    el.style.cssText = "background:rgba(46,204,113,.15);border:1px solid var(--green);color:var(--green);padding:.3rem .8rem;border-radius:5px;font-size:0.78rem;cursor:pointer;font-weight:700;";
  }
}

// Portfolio cost basis editor —— 支持两种输入：单价，或买入总价(前缀"=")
function setPortfolioCost(i, ticker) {
  const port = loadPortfolio();
  const item = port[i];
  if (!item) return;
  const qty = item.qty;
  const raw = prompt(
    `输入 ${ticker} 的成本（USD）：\n` +
    `· 知道单价 → 直接填每股/每枚价格（例：BTC填95000，DOGE填0.15）\n` +
    `· 只知买入总价 → 数字前加「=」（例：=1500 表示总共花US$1500，按持有 ${qty} 份自动折算单价）`
  );
  if (raw == null) return;
  const t = String(raw).trim();
  let unit;
  if (t.startsWith("=")) {
    const totalCost = parseFloat(t.slice(1));
    if (isNaN(totalCost) || totalCost < 0) { alert("请输入有效金额"); return; }
    if (!qty || qty <= 0) { alert("该持仓数量为 0，无法用总价折算单价——请先设好数量，或直接填单价"); return; }
    unit = totalCost / qty;
  } else {
    unit = parseFloat(t);
    if (isNaN(unit) || unit < 0) { alert("请输入有效价格"); return; }
  }
  item.costUSD = unit;
  savePortfolio(port);
  renderPortfolioTable(_portAudRate);
}

// ── 启动 ──
// ═══════════════════════════════════════════════════════
//  双指数信号对比（纳指 vs 标普，含校准概率）
// ═══════════════════════════════════════════════════════
function renderIndicesCompare() {
  const el = document.getElementById("indices-compare");
  if (!el || !SIGNALS?.indices) return;
  const TC = { 5:"#27ae60", 4:"#2ecc71", 3:"#f1c40f", 2:"#e67e22", 1:"#e74c3c" };
  const NAMES = { NASDAQ:"纳斯达克", SP500:"标普500" };
  const flat = SIGNALS.calibration_flat;
  const br = Math.round((SIGNALS.base_rate_20d ?? 0.62) * 100);
  el.innerHTML = Object.entries(SIGNALS.indices).map(([idx, s]) => {
    // 无样本外区分度：中性卡片，只显示原始打分（不给档位/校准概率，避免假把握度）
    if (flat) {
      const c = "#f1c40f";
      return `<div style="flex:1;text-align:center;padding:.6rem .4rem;border:1px solid ${c}33;border-radius:8px;background:${c}0d;">
        <div style="font-size:0.78rem;color:var(--muted);">${NAMES[idx]||idx}</div>
        <div style="font-size:1.35rem;font-weight:800;color:${c};">≈${br}%</div>
        <div style="font-size:0.66rem;color:var(--muted);">基率·无区分度</div>
        <div style="font-size:0.68rem;color:var(--muted);margin-top:.1rem;">原始打分 ${(s.prob*100).toFixed(1)}%</div>
        <div style="font-size:0.65rem;color:var(--muted);margin-top:.2rem;">截至 ${s.date||""}</div>
      </div>`;
    }
    // 主显示：校准概率（prob_cal）与 tier_cal；校准值缺失时回退原始
    const calProb = s.prob_cal != null ? s.prob_cal : s.prob;
    const calTier = s.tier_cal != null ? s.tier_cal : s.tier;
    const c = TC[calTier] || "#f1c40f";
    const rawNote = s.prob_cal != null
      ? `<div style="font-size:0.68rem;color:var(--muted);margin-top:.1rem;" title="模型原始输出（未校准）">原始 ${(s.prob*100).toFixed(1)}%</div>`
      : "";
    return `<div style="flex:1;text-align:center;padding:.6rem .4rem;border:1px solid ${c}44;border-radius:8px;background:${c}11;">
      <div style="font-size:0.78rem;color:var(--muted);">${NAMES[idx]||idx}</div>
      <div style="font-size:1.35rem;font-weight:800;color:${c};">${(calProb*100).toFixed(1)}%</div>
      <div style="font-size:0.72rem;color:${c};">第${calTier}档</div>
      ${rawNote}
      <div style="font-size:0.65rem;color:var(--muted);margin-top:.2rem;">截至 ${s.date||""}</div>
    </div>`;
  }).join("");
}

// ═══════════════════════════════════════════════════════
//  模型实盘追踪（append-only 预测日志，无法事后美化）
// ═══════════════════════════════════════════════════════
function renderLiveTracking() {
  const el = document.getElementById("live-tracking");
  if (!el) return;
  const lt = SIGNALS?.live_tracking;
  if (!lt || !lt.n_logged) {
    el.innerHTML = `<div style="font-size:0.75rem;color:var(--muted);">
      🧪 实盘追踪已启动（${SIGNALS?.model_version ? "模型 v"+SIGNALS.model_version : ""}）：
      每天记录模型预测，之后用真实行情回填对账。约一周后这里会出现第一批成绩。</div>`;
    return;
  }
  const rows = Object.entries(lt.by_index || {}).map(([idx, s]) => {
    const hit5 = s.hit_rate_5d != null ? `${s.hit_rate_5d}%` : "待回填";
    const hit1 = s.hit_rate_1d != null ? `${s.hit_rate_1d}%` : "待回填";
    return `<tr><td style="padding:.25rem .5rem;">${idx}</td>
      <td style="padding:.25rem .5rem;text-align:center;">${s.n}</td>
      <td style="padding:.25rem .5rem;text-align:center;">${hit1}</td>
      <td style="padding:.25rem .5rem;text-align:center;">${hit5}</td></tr>`;
  }).join("");
  el.innerHTML = `
    <div style="font-size:0.78rem;font-weight:600;margin-bottom:.4rem;">
      🧪 模型实盘成绩单 <span style="color:var(--muted);font-weight:400;">自 ${lt.since||"—"} · 当日预测当日记录，无法事后修改</span>
    </div>
    <table style="width:100%;font-size:0.75rem;border-collapse:collapse;">
      <tr style="color:var(--muted);"><th style="text-align:left;padding:.25rem .5rem;">指数</th>
        <th>已记录</th><th>1日方向命中</th><th>5日方向命中</th></tr>
      ${rows}
    </table>`;
}

// ═══════════════════════════════════════════════════════
//  个股观察池（七姐妹 + 优质龙头）
// ═══════════════════════════════════════════════════════
let STOCKS = null;
async function loadStocksPanel() {
  try {
    const r = await fetch("stocks.json?_=" + Date.now());
    STOCKS = await r.json();
  } catch(e) { console.warn("stocks.json 未找到", e); return; }
  renderStocksTable();
  const first = Object.keys(STOCKS.stocks)[0];
  if (first) renderStockChart(first);
  renderGamePanel();   // 用户模拟盘需要最新股价
  renderSPCXMonitor(); // SPCX 监视卡依赖 STOCKS.spcx
  if (typeof renderHorizonStocks === "function") renderHorizonStocks();  // 长期页质量表
}

function renderStocksTable() {
  const el = document.getElementById("stocks-table");
  if (!el || !STOCKS) return;
  const fmt = (v, suffix="%") => v == null ? "—"
    : `<span style="color:${v >= 0 ? "#2ecc71" : "#e74c3c"}">${v > 0 ? "+" : ""}${v}${suffix}</span>`;
  const rows = Object.entries(STOCKS.stocks).map(([sym, s]) => {
    const st = s.stats;
    const ma = st.above_ma200
      ? `<span style="color:#2ecc71">✓</span>` : `<span style="color:#e74c3c">✗</span>`;
    const rsiColor = st.rsi14 > 70 ? "#e74c3c" : st.rsi14 < 30 ? "#2ecc71" : "var(--text)";
    const tag = s.is_mag7 ? `<span style="font-size:0.6rem;background:#9b59b633;color:#9b59b6;border-radius:3px;padding:0 3px;margin-left:3px;">M7</span>` : "";
    return `<tr data-stock-symbol="${sym}" style="cursor:pointer;border-bottom:1px solid var(--border-faint);">
      <td style="padding:.35rem .5rem;font-weight:600;">${sym}${tag}<br><span style="font-size:0.68rem;color:var(--muted);">${s.label}</span></td>
      <td style="padding:.35rem .5rem;text-align:right;">$${st.last}</td>
      <td style="padding:.35rem .5rem;text-align:right;">${fmt(st.chg_1d)}</td>
      <td style="padding:.35rem .5rem;text-align:right;">${fmt(st.chg_20d)}</td>
      <td style="padding:.35rem .5rem;text-align:right;">${fmt(st.ytd)}</td>
      <td style="padding:.35rem .5rem;text-align:right;">${fmt(st.from_high_52w)}</td>
      <td style="padding:.35rem .5rem;text-align:center;color:${rsiColor};">${st.rsi14}</td>
      <td style="padding:.35rem .5rem;text-align:center;">${ma}</td>
      <td style="padding:.35rem .5rem;text-align:center;">${st.beta_nasdaq_1y ?? "—"}</td>
    </tr>`;
  }).join("");
  el.innerHTML = `<table style="width:100%;font-size:0.78rem;border-collapse:collapse;min-width:640px;">
    <tr style="color:var(--muted);font-size:0.72rem;">
      <th style="text-align:left;padding:.35rem .5rem;">股票</th><th style="text-align:right;">现价</th>
      <th style="text-align:right;">1日</th><th style="text-align:right;">20日</th>
      <th style="text-align:right;">YTD</th><th style="text-align:right;">距52周高</th>
      <th>RSI14</th><th>>MA200</th><th>β(纳指)</th>
    </tr>${rows}</table>`;
}

// ── 个股分析卡（可复用模板：趋势/动量/波动/回撤/系统性，描述性非预测）──
function renderStockScorecard(sym) {
  const el = document.getElementById("stock-scorecard");
  if (!el || !STOCKS?.stocks?.[sym]) return;
  const s = STOCKS.stocks[sym], st = s.stats;
  // 每个维度：标签 + 值 + 解读带（颜色+一句话），全部基于历史统计，不预测
  const band = (cond, txt, color) => `<span style="color:${color}">${txt}</span>`;
  const trend = st.dist_ma200 == null ? ["—", "var(--muted)", "数据不足"]
    : st.dist_ma200 > 15 ? [`+${st.dist_ma200}%`, "#e67e22", "强多头但偏离均线远，回踩风险升高"]
    : st.dist_ma200 > 0 ? [`+${st.dist_ma200}%`, "#2ecc71", "站上200日线，多头趋势"]
    : [`${st.dist_ma200}%`, "#e74c3c", "跌破200日线，趋势转弱"];
  const rsiB = st.rsi14 > 70 ? ["超买", "#e74c3c"] : st.rsi14 < 30 ? ["超卖", "#2ecc71"] : ["中性", "var(--text)"];
  const volB = st.vol_pctile_1y == null ? ["—", "var(--muted)"]
    : st.vol_pctile_1y > 80 ? [`第${st.vol_pctile_1y}百分位·异常高`, "#e74c3c"]
    : st.vol_pctile_1y < 20 ? [`第${st.vol_pctile_1y}百分位·异常平静`, "#3498db"]
    : [`第${st.vol_pctile_1y}百分位·常态`, "var(--text)"];
  const r2 = st.r2_nasdaq_1y;
  const r2B = r2 == null ? ["—", "var(--muted)", ""]
    : r2 > 0.5 ? [`${Math.round(r2*100)}%`, "#3498db", "波动主要由大盘驱动（系统性，分散作用小）"]
    : [`${Math.round(r2*100)}%`, "#9b59b6", "波动多为个股特有（独立逻辑，需看公司基本面）"];
  const rv = st.ret_vol_1y;
  const cell = (label, valHtml, note) => `
    <div style="background:var(--surface2);border-radius:7px;padding:.55rem .7rem;">
      <div style="font-size:0.68rem;color:var(--muted);">${label}</div>
      <div style="font-size:0.95rem;font-weight:700;margin:.1rem 0;">${valHtml}</div>
      <div style="font-size:0.68rem;color:var(--muted);line-height:1.4;">${note}</div>
    </div>`;
  el.innerHTML = `
    <div style="font-size:0.82rem;font-weight:700;margin-bottom:.5rem;">📊 ${sym} ${s.label} · 个股分析卡
      <span style="font-size:0.66rem;color:var(--muted);font-weight:400;">截至 ${st.date}</span></div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.5rem;">
      ${cell("趋势（距200日线）", band(0, trend[0], trend[1]), trend[2])}
      ${cell("动量 RSI14 / 距52周高", `${st.rsi14} <span style="font-size:0.7rem;color:${rsiB[1]}">${rsiB[0]}</span> · ${st.from_high_52w}%`,
             st.range_pctile_52w!=null?`位于52周区间第 ${st.range_pctile_52w} 百分位`:"")}
      ${cell("波动率状态", `${st.vol20_ann}% · <span style="font-size:0.7rem;color:${volB[1]}">${volB[0]}</span>`,
             "年化20日波动 vs 自身近一年")}
      ${cell("最大回撤 / 风险调整", `${st.max_dd}% · ${rv!=null?"性价比"+rv:"—"}`,
             rv!=null?(rv>1?"近1年收益/波动>1，性价比尚可":"近1年风险调整后一般"):"")}
      ${cell("β / 系统性占比 R²", `β ${st.beta_nasdaq_1y ?? "—"} · R² ${r2B[0]}`, r2B[2])}
      ${cell("收益（YTD / 1年）", `${st.ytd!=null?st.ytd+"%":"—"} / ${st.chg_1y!=null?st.chg_1y+"%":"—"}`, "")}
    </div>
    <div style="font-size:0.68rem;color:var(--muted);margin-top:.5rem;line-height:1.5;">
      ⚠ 这是<b>描述性</b>分析卡（趋势/动量/波动/回撤/系统性现状），不预测涨跌——
      与本站结论一致：个股方向同样不可靠预测。用它快速体检一只股的<b>当前状态与风险画像</b>，不当买卖信号。
    </div>`;
}

function renderStockChart(sym) {
  if (!STOCKS?.stocks?.[sym]) return;
  renderStockScorecard(sym);
  const s = STOCKS.stocks[sym];
  const traces = [{
    x: s.series.dates, y: s.series.values, name: `${sym} ${s.label}`,
    type: "scatter", mode: "lines", line: { color: "#9b59b6", width: 2.5 },
  }];
  for (const [idx, col] of [["NASDAQ", "#3498db"], ["SP500", "#95a5a6"]]) {
    const ser = STOCKS.indices?.[idx];
    if (ser) traces.push({
      x: ser.dates, y: ser.values, name: idx,
      type: "scatter", mode: "lines", line: { color: col, width: 1.4, dash: "dot" },
    });
  }
  Plotly.newPlot("chart-stock", traces, {...DARK, hovermode: "x unified",
    xaxis: {...DARK.xaxis, rangeselector: RANGE_SEL},
    title: { text: `${sym}（${s.label}）vs 指数 · 归一化=100`, font: { size: 13 } }},
    {displayModeBar: false, responsive: true});
}

// ═══════════════════════════════════════════════════════
//  操作计划：对未来选定日期给出 买入时段/持有期/卖出提醒
// ═══════════════════════════════════════════════════════
// 把美东 h:m 换算成访问者本地时间字符串（自动适配任何时区+夏令时）
// 时间显示时区：默认 ET（美东统一），可随时切换到 LOCAL（访问者本地）。
let TZ_MODE = (typeof localStorage !== "undefined" && localStorage.getItem("tz_mode")) || "ET";
function toggleTZMode() {
  TZ_MODE = TZ_MODE === "ET" ? "LOCAL" : "ET";
  try { localStorage.setItem("tz_mode", TZ_MODE); } catch (e) {}
  renderMarketClock();
  if (selectedDate) updateSignal(selectedDate);   // 刷新操作计划里的时段
}
function _pad2(n) { return String(n).padStart(2, "0"); }
// 把美东 h:m 换算成访问者本地时间（同一瞬间两时区钟面差固定，自动含夏令时）
function etToLocalConv(h, m) {
  const now = new Date();
  const etNow = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const offsetMs = now - etNow;
  const t = new Date(etNow); t.setHours(h, m, 0, 0);
  return new Date(t.getTime() + offsetMs)
    .toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
}
// 模式感知的"美东时段"字符串：ET 模式只显示美东；LOCAL 模式附带本地换算
function tzRange(h1, m1, h2, m2) {
  const et = `美东 ${_pad2(h1)}:${_pad2(m1)}–${_pad2(h2)}:${_pad2(m2)}`;
  return TZ_MODE === "ET" ? et : `${et}（你的 ${etToLocalConv(h1, m1)}–${etToLocalConv(h2, m2)}）`;
}

// ═══════════════════════════════════════════════════════
//  每日盘后简报（brief.json，云端规则化生成）
// ═══════════════════════════════════════════════════════
async function loadBriefPanel() {
  const el = document.getElementById("brief-content");
  if (!el) return;
  try {
    const r = await fetch("brief.json?_=" + Date.now());
    const b = await r.json();
    const up = document.getElementById("brief-updated");
    if (up && b.generated) up.textContent = `生成于 ${b.generated} · 模型v${b.model_version||""}`;
    // 🚦 关键指标红绿灯（直接看的状态层）
    const LC = { green: "#2ecc71", yellow: "#f1c40f", red: "#e74c3c" };
    const lights = (b.lights || []).map(l =>
      `<div title="${esc(l.note)}" style="flex:1;min-width:96px;text-align:center;padding:.35rem .2rem;
           border:1px solid ${LC[l.status]}55;border-radius:7px;background:${LC[l.status]}11;cursor:help;">
        <div style="font-size:0.62rem;color:var(--muted);">${esc(l.name)}</div>
        <div style="font-size:0.78rem;font-weight:700;color:${LC[l.status]};">●&nbsp;${esc(l.value)}</div>
      </div>`).join("");
    const lightsHtml = lights
      ? `<div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:.55rem;">${lights}</div>` : "";
    el.innerHTML = lightsHtml + (b.lines || []).map(l => {
      const m = l.match(/^【(.+?)】(.*)$/);
      if (!m) return `<div>${esc(l)}</div>`;
      const warn = m[2].includes("⚠");
      return `<div style="padding:.18rem 0;">
        <span style="color:var(--muted);font-size:0.72rem;">【${esc(m[1])}】</span>
        <span style="${warn ? "color:#e67e22;" : ""}">${esc(m[2])}</span></div>`;
    }).join("");
  } catch(e) {
    el.innerHTML = `<div style="color:var(--muted)">简报未生成（跑一次流水线即可）</div>`;
  }
}

// ═══════════════════════════════════════════════════════
//  我的模拟盘（用户游戏，localStorage，按最近收盘价成交）
// ═══════════════════════════════════════════════════════
const GAME_KEY = "alpha_game_v1";
function gameState() {
  try { return JSON.parse(localStorage.getItem(GAME_KEY)) ||
    { cash: 10000, holdings: {}, trades: [], started: new Date().toISOString().slice(0,10) }; }
  catch { return { cash: 10000, holdings: {}, trades: [], started: "" }; }
}
function gameSave(g) { localStorage.setItem(GAME_KEY, JSON.stringify(g)); }
function gamePx() {
  const m = {};
  if (STOCKS) for (const [s, v] of Object.entries(STOCKS.stocks)) m[s] = v.stats.last;
  return m;
}

function renderGamePanel() {
  const el = document.getElementById("game-content");
  if (!el || !STOCKS) return;
  const g = gameState(), px = gamePx();
  let mv = 0;
  const holdRows = Object.entries(g.holdings).map(([s, h]) => {
    const p = px[s] || h.cost;
    mv += h.units * p;
    const pl = (p / h.cost - 1) * 100;
    const c = pl >= 0 ? "#2ecc71" : "#e74c3c";
    return `<tr>
      <td style="padding:.25rem .4rem;font-weight:600;">${s}</td>
      <td style="padding:.25rem .4rem;text-align:right;">$${(h.units*p).toFixed(0)}</td>
      <td style="padding:.25rem .4rem;text-align:right;">成本$${h.cost.toFixed(2)}</td>
      <td style="padding:.25rem .4rem;text-align:right;color:${c};">${pl>0?"+":""}${pl.toFixed(1)}%</td>
      <td style="padding:.25rem .4rem;"><button class="period-btn" data-game-sell="${s}">卖出</button></td>
    </tr>`;
  }).join("");
  const eq = g.cash + mv, ret = (eq / 10000 - 1) * 100;
  const rc = ret >= 0 ? "#2ecc71" : "#e74c3c";
  const opts = Object.keys(STOCKS.stocks).map(s =>
    `<option value="${s}">${s} ${STOCKS.stocks[s].label} $${px[s]}</option>`).join("");
  const recent = (g.trades || []).slice(-6).reverse().map(t =>
    `<div style="color:var(--muted);font-size:0.7rem;">${t.t} ${t.side} ${t.sym} $${t.amt.toFixed(0)} @${t.px}</div>`).join("");
  el.innerHTML = `
    <div style="margin-bottom:.5rem;">净值 <b style="font-size:1.1rem;">$${eq.toFixed(0)}</b>
      <b style="color:${rc};">（${ret>0?"+":""}${ret.toFixed(2)}%）</b>
      · 现金 $${g.cash.toFixed(0)} <span style="color:var(--muted);font-size:0.7rem;">自 ${g.started||"—"}</span></div>
    <div style="display:flex;gap:.4rem;margin-bottom:.5rem;flex-wrap:wrap;">
      <select id="game-sym" class="cgt-input" style="flex:2;min-width:140px;">${opts}</select>
      <input id="game-amt" class="cgt-input" type="number" placeholder="金额$" value="1000" style="flex:1;min-width:70px;">
      <button class="cgt-btn" style="flex:0;padding:.4rem .8rem;" data-game-buy>买入</button>
    </div>
    ${holdRows ? `<table style="width:100%;font-size:0.74rem;border-collapse:collapse;">${holdRows}</table>` : ""}
    ${recent ? `<div style="margin-top:.4rem;">${recent}</div>` : ""}
    <div style="display:flex;justify-content:space-between;margin-top:.45rem;align-items:center;">
      <span style="color:var(--muted);font-size:0.66rem;">按最近收盘价成交（${STOCKS.generated}）· 存在本浏览器</span>
      <button class="period-btn" data-game-reset>重置</button>
    </div>`;
}

function gameBuy() {
  const sym = document.getElementById("game-sym").value;
  const amt = parseFloat(document.getElementById("game-amt").value);
  const g = gameState(), px = gamePx()[sym];
  if (!px || !(amt > 0)) return;
  if (amt > g.cash) { alert(`现金不足（剩 $${g.cash.toFixed(0)}）`); return; }
  const units = amt / px;
  const h = g.holdings[sym] || { units: 0, cost: 0 };
  h.cost = (h.cost * h.units + px * units) / (h.units + units);   // 加权平均成本
  h.units += units;
  g.holdings[sym] = h;
  g.cash -= amt;
  g.trades.push({ t: new Date().toISOString().slice(0,16).replace("T"," "),
                  side: "买", sym, px, amt });
  gameSave(g); renderGamePanel();
}

function gameSell(sym) {
  const g = gameState(), px = gamePx()[sym];
  const h = g.holdings[sym];
  if (!h || !px) return;
  const amt = h.units * px;
  g.cash += amt;
  delete g.holdings[sym];
  g.trades.push({ t: new Date().toISOString().slice(0,16).replace("T"," "),
                  side: "卖", sym, px, amt });
  gameSave(g); renderGamePanel();
}

function gameReset() {
  if (!confirm("清空我的模拟盘，重新从 $10,000 开始？")) return;
  localStorage.removeItem(GAME_KEY);
  renderGamePanel();
}

// ═══════════════════════════════════════════════════════
//  模拟盘（paper.json）
// ═══════════════════════════════════════════════════════
async function loadPaperPanel() {
  const el = document.getElementById("paper-content");
  if (!el) return;
  let p;
  try {
    const r = await fetch("paper.json?_=" + Date.now());
    p = await r.json();
  } catch(e) {
    el.innerHTML = `<div style="color:var(--muted)">模拟盘等待首个交易日启动（自 2026-06-10 起前向实验）</div>`;
    return;
  }
  const strats = Object.values(p.strategies || {})
    .sort((a, b) => b.ret_pct - a.ret_pct);
  if (!strats.length) {
    el.innerHTML = `<div style="color:var(--muted)">模拟盘等待首个交易日</div>`;
    return;
  }
  el.innerHTML = strats.map((s, i) => {
    const rc = s.ret_pct > 0 ? "#2ecc71" : s.ret_pct < 0 ? "#e74c3c" : "var(--muted)";
    const medal = i === 0 && s.ret_pct > 0 ? "👑 " : "";
    return `<div style="display:flex;justify-content:space-between;align-items:center;gap:.5rem;
        padding:.45rem .55rem;border:1px solid var(--border);border-radius:8px;margin-bottom:.4rem;">
      <div>
        <div style="font-weight:700;">${medal}${s.label}
          <span style="color:${rc};font-weight:800;margin-left:.4rem;">${s.ret_pct>0?"+":""}${s.ret_pct}%</span>
          <span style="color:var(--muted);font-size:0.72rem;margin-left:.3rem;">$${Math.round(s.equity).toLocaleString()}</span>
        </div>
        <div style="color:var(--muted);font-size:0.68rem;margin-top:.1rem;">${s.desc}</div>
        <div style="font-size:0.7rem;margin-top:.1rem;">仓位：<b>${s.position}</b>
          <span style="color:var(--muted)">· ${s.n_trades}次交易 · ${s.last_action}</span></div>
      </div>
    </div>`;
  }).join("") + `<div style="color:var(--muted);font-size:0.68rem;margin-top:.2rem;">
    每个 $${p.start_capital.toLocaleString()} · 自 ${p.start_date} 同日起跑 · ${p.note}</div>`;

  // 净值曲线（数据来自各策略 curve，积累几个交易日后才有形状）
  const eqEl = document.getElementById("chart-equity");
  if (!eqEl) return;
  if (strats.some(s => (s.curve?.dates || []).length > 1)) {
    Plotly.newPlot("chart-equity", strats.map(s => ({
      x: s.curve.dates, y: s.curve.equity, type: "scatter", mode: "lines",
      name: s.label,
    })), {...DARK, yaxis:{...DARK.yaxis, title:"净值 $"}, hovermode:"x unified",
      legend:{orientation:"h", y:1.1}}, {responsive:true});
  } else {
    eqEl.innerHTML = `<div style="color:var(--muted);font-size:0.78rem;display:flex;align-items:center;justify-content:center;height:100%;">📈 净值曲线将在实验积累几个交易日后出现</div>`;
  }
}

// ═══════════════════════════════════════════════════════
//  模型体检报告（report.json）
// ═══════════════════════════════════════════════════════
async function loadReportPanel() {
  const el = document.getElementById("report-content");
  if (!el) return;
  let rep;
  try {
    const r = await fetch("report.json?_=" + Date.now());
    rep = await r.json();
  } catch(e) {
    el.innerHTML = `<div style="color:var(--muted)">报告未生成（跑一次流水线即可）</div>`;
    return;
  }
  el.innerHTML = (rep.sections || []).map(s => {
    const cols = s.table?.length ? Object.keys(s.table[0]) : [];
    const head = cols.map(c => `<th style="text-align:left;padding:.3rem .6rem;color:var(--muted);font-size:0.72rem;">${esc(c)}</th>`).join("");
    const rows = (s.table || []).map(r =>
      `<tr>${cols.map(c => `<td style="padding:.3rem .6rem;border-top:1px solid var(--border-faint);">${esc(r[c])}</td>`).join("")}</tr>`).join("");
    return `<div style="margin-bottom:1.1rem;">
      <div style="font-weight:700;margin-bottom:.35rem;">${esc(s.title)}</div>
      <table style="border-collapse:collapse;min-width:50%;">${head ? `<tr>${head}</tr>` : ""}${rows}</table>
      ${s.note ? `<div style="color:var(--muted);font-size:0.72rem;margin-top:.3rem;line-height:1.5;">${esc(s.note)}</div>` : ""}
    </div>`;
  }).join("") + `<div style="color:var(--muted);font-size:0.68rem;">生成于 ${esc(rep.generated)} · 模型 v${esc(rep.model_version)}</div>`;
}

// ═══════════════════════════════════════════════════════
//  今日市场要闻（news.json，由 AI 监控循环 / 手工更新）
// ═══════════════════════════════════════════════════════
// HTML 转义：RSS 标题来自外部源，必须当不可信数据处理（防 XSS）
function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// 相对时间（"3小时前"）——免去 UTC/ET/本地 多时区困惑；解析 "YYYY-MM-DD HH:MM" 当 UTC
function relTime(t) {
  const m = String(t || "").match(/(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
  if (!m) return "";
  const mins = Math.round((Date.now() - Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5])) / 60000);
  if (mins < 0) return "";
  if (mins < 60) return mins <= 1 ? "刚刚" : `${mins}分钟前`;
  const hrs = Math.round(mins / 60);
  return hrs < 24 ? `${hrs}小时前` : `${Math.round(hrs / 24)}天前`;
}

async function loadNewsPanel() {
  const el = document.getElementById("news-list");
  if (!el) return;
  let news;
  try {
    const r = await fetch("news.json?_=" + Date.now());
    news = await r.json();
  } catch(e) {
    el.innerHTML = `<div style="color:var(--muted)">暂无要闻数据</div>`;
    return;
  }
  const up = document.getElementById("news-updated");
  if (up && news.updated) up.textContent = `更新 ${relTime(news.updated) || news.updated}`;
  const IC = { positive: ["▲", "#2ecc71"], negative: ["▼", "#e74c3c"], neutral: ["●", "#f1c40f"] };
  el.innerHTML = (news.items || []).map(n => {
    const [sym, color] = IC[n.impact] || IC.neutral;
    return `<div style="padding:.4rem 0;border-bottom:1px solid var(--border-faint);">
      <div style="display:flex;gap:.45rem;align-items:flex-start;">
        <span style="color:${color};flex-shrink:0;">${sym}</span>
        <div>
          <div style="font-weight:600;line-height:1.4;">${esc(n.title)}</div>
          ${n.note ? `<div style="color:var(--muted);font-size:0.72rem;margin-top:.15rem;line-height:1.5;">${esc(n.note)}</div>` : ""}
          <div style="color:var(--muted);font-size:0.65rem;margin-top:.15rem;">${relTime(n.time) ? esc(relTime(n.time)) + " · " : ""}${esc(n.time)}${n.source ? " · " + esc(n.source) : ""}</div>
        </div>
      </div>
    </div>`;
  }).join("") || `<div style="color:var(--muted)">暂无要闻</div>`;
}

// 日历格点击 → 联动日期选择器并滚到信号表盘
function selectForecastDay(dateStr) {
  const dp = document.getElementById("date-picker");
  if (dp) dp.value = dateStr;
  updateSignal(dateStr);
  document.querySelector(".signal-meter")?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderTradePlan(fc, allFc) {
  const el = document.getElementById("trade-plan");
  if (!el || !fc) return;
  const t = fc.tier;
  const action = t >= 4 ? ["✅ 建议买入窗口", "#2ecc71"]
               : t === 3 ? ["⏸ 中性 · 小仓试探或观望", "#f1c40f"]
               : ["🚫 偏弱 · 回避新仓/考虑减仓", "#e74c3c"];

  // 持有期内（后续20个交易日）的弱势日和宏观事件提醒
  const idx = allFc.findIndex(d => d.date === fc.date);
  const horizon = idx >= 0 ? allFc.slice(idx + 1, idx + 21) : [];
  const weakDays  = horizon.filter(d => d.tier <= 2).slice(0, 3);
  const macroDays = horizon.filter(d => d.macro).slice(0, 3);

  let html = `<div style="border:1px solid var(--border);border-radius:8px;padding:.7rem .8rem;font-size:0.78rem;line-height:1.65;">
    <div style="font-weight:700;color:${action[1]};margin-bottom:.3rem;">${fc.date}（${fc.dow_cn}）${action[0]}</div>`;

  if (t >= 3) {
    html += `🕐 <b>买入时段</b>：尾盘 <b>${tzRange(15,0,16,0)}</b><br>
      <span style="color:var(--muted)">依据隔夜收益异象（QQQ隔夜段年化+11%，日内段-2%）：避免开盘追高，接近收盘买入以捕获隔夜段。</span><br>
      📦 <b>持有期</b>：信号验证窗口为20个交易日（约1个月），短于此噪音大于信号。<br>
      🕐 <b>卖出时段</b>：如需卖出，开盘后首小时（${tzRange(9,30,10,30)}）历史上更有利（隔夜涨幅已落袋）。<br>`;
  } else {
    html += `<span style="color:var(--muted)">该日日历因子偏弱。如已持仓且计划减仓，开盘时段（${tzRange(9,30,10,30)}）通常优于尾盘。</span><br>`;
  }
  if (weakDays.length) {
    html += `⚠ 持有期内偏弱日：${weakDays.map(d => `${d.date.slice(5)}(${d.dow_cn})`).join("、")} —— 临近时复查信号<br>`;
  }
  if (macroDays.length) {
    html += `📊 持有期内宏观事件：${macroDays.map(d => `${d.date.slice(5)} ${d.macro}`).join("、")} —— 当日波动放大<br>`;
  }
  html += `<span class="u-cap">以上为历史统计规律的机械应用，非投资建议；越远的日期技术因子失效越多，临近时以当日信号为准。</span></div>`;
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════
//  市场时钟：美东开收盘 ↔ 本地时间对照（自动处理夏令时）
// ═══════════════════════════════════════════════════════
// ── 时钟工具：美东秒级状态 + 任意时区 HH:MM:SS（Intl 自动处理夏令时，本地时区由浏览器自带，无需 IP）──
const _CLOCK_CN_DOW = { Mon:"周一", Tue:"周二", Wed:"周三", Thu:"周四", Fri:"周五", Sat:"周六", Sun:"周日" };
function _clockState(now) {
  const p = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York",
    hour: "numeric", minute: "numeric", second: "numeric", weekday: "short", hour12: false })
    .formatToParts(now).reduce((a, x) => (a[x.type] = x.value, a), {});
  const etSec = (parseInt(p.hour) % 24) * 3600 + parseInt(p.minute) * 60 + parseInt(p.second);
  const isWeekday = !["Sat", "Sun"].includes(p.weekday);
  const openSec = (9 * 60 + 30) * 60, closeSec = 16 * 3600;
  const isOpen = isWeekday && etSec >= openSec && etSec < closeSec;
  let countdown = "";
  const fmtLeft = s => (s >= 3600 ? Math.floor(s / 3600) + "小时" : "") +
                       Math.floor((s % 3600) / 60) + "分" + String(s % 60).padStart(2, "0") + "秒";
  if (isOpen) countdown = "距收盘 " + fmtLeft(closeSec - etSec);
  else if (isWeekday && etSec < openSec) countdown = "距开盘 " + fmtLeft(openSec - etSec);
  return { p, etSec, isWeekday, isOpen, openSec, closeSec, countdown };
}
function _fmtHMS(tz, now) {
  return new Intl.DateTimeFormat("zh-CN", { timeZone: tz,
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(now);
}
const _LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
const _LOCAL_CITY = (_LOCAL_TZ.split("/").pop() || "本地").replace(/_/g, " ");

function renderMarketClock() {
  const el = document.getElementById("market-clock");
  if (!el) return;
  const now = new Date();
  const st = _clockState(now);

  const status = st.isOpen
    ? `<span style="color:#2ecc71;font-weight:700;">● 开盘中</span>`
    : `<span style="color:var(--muted);font-weight:700;">○ 休市</span>`;
  const tzBtn = `<button data-tz-toggle title="切换页面时间显示：美东统一 / 你的本地"
    style="background:var(--surface2);border:1px solid var(--border);color:var(--muted);
    padding:1px 7px;border-radius:5px;font-size:0.68rem;cursor:pointer;">
    🕐 ${TZ_MODE === "ET" ? "美东" : "本地"}时间 ⇄</button>`;
  // 本地时区与美东一致时（美国东部访客）不重复显示第二个钟
  const localClock = _LOCAL_TZ === "America/New_York" ? "" :
    ` · ${_LOCAL_CITY} <b style="color:var(--text);font-variant-numeric:tabular-nums;" id="clock-local">${_fmtHMS(_LOCAL_TZ, now)}</b>`;
  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.3rem;">
      <span>${status} <span style="color:var(--muted);font-variant-numeric:tabular-nums;" id="clock-countdown">${st.countdown}</span></span>
      <span style="color:var(--muted)">美东 ${_CLOCK_CN_DOW[st.p.weekday] || ""} <b style="color:var(--text);font-variant-numeric:tabular-nums;" id="clock-et">${_fmtHMS("America/New_York", now)}</b>${localClock} ${tzBtn}</span>
    </div>
    <div style="color:var(--muted);margin-top:.25rem;">
      常规时段 <b style="color:var(--text)">${tzRange(9,30,16,0)}</b>
      <span style="font-size:0.68rem">${TZ_MODE === "ET" ? "（页面时间已统一为美东·含夏令时）" : "（已换算为你的本地·含夏令时）"}</span>
    </div>
    ${sessionTip()}`;

  // 盘中情境建议（基于隔夜收益异象）
  function sessionTip() {
    let tip = "";
    const etMin = Math.floor(st.etSec / 60), openMin = st.openSec / 60, closeMin = st.closeSec / 60;
    if (st.isOpen && etMin < openMin + 45) {
      tip = "🔔 开盘初段（首45分钟）波动最大，历史上不宜追高——日内段长期收益≈0";
    } else if (st.isOpen && etMin >= closeMin - 60) {
      tip = "🔔 尾盘时段——按信号执行买入的优选窗口（捕获隔夜段收益）";
    } else if (st.isOpen) {
      tip = "🔔 盘中：当日数据为临时价，正式信号以收盘后刷新为准";
    } else if (st.isWeekday && etMin < openMin) {
      tip = "🔔 未开盘。如计划买入，统计上尾盘买入优于开盘追高";
    }
    return tip ? `<div style="color:#f1c40f;font-size:0.72rem;margin-top:.3rem;">${tip}</div>` : "";
  }
}
// 每秒只更新时间/倒计时文本（不重建 DOM，按钮可正常点击）；开/收盘状态翻转由 30 秒全量重渲染兜底
function _marketClockTick() {
  const et = document.getElementById("clock-et");
  if (!et) return;
  const now = new Date();
  et.textContent = _fmtHMS("America/New_York", now);
  const lt = document.getElementById("clock-local");
  if (lt) lt.textContent = _fmtHMS(_LOCAL_TZ, now);
  const cd = document.getElementById("clock-countdown");
  if (cd) cd.textContent = _clockState(now).countdown;
}
setInterval(renderMarketClock, 30000);
setInterval(_marketClockTick, 1000);

// ═══════════════════════════════════════════════════════
//  隔夜 vs 日内收益分解
// ═══════════════════════════════════════════════════════
let OVERNIGHT = null, _ovCur = null;
async function loadOvernightPanel() {
  try {
    const r = await fetch("overnight.json?_=" + Date.now());
    OVERNIGHT = await r.json();
  } catch(e) { console.warn("overnight.json 未找到", e); return; }
  const names = Object.keys(OVERNIGHT.indices || {});
  if (!names.length) return;
  const btns = document.getElementById("overnight-btns");
  if (btns) btns.innerHTML = names.map((n, i) =>
    `<button class="period-btn ${i === 0 ? "active" : ""}" data-overnight="${n}">${n.split("_")[0]}</button>`
  ).join("");
  renderOvernight(names[names.length - 1]);
}

function renderOvernight(name, btn) {
  const d = OVERNIGHT?.indices?.[name];
  if (!d) return;
  _ovCur = name;
  if (btn) {
    document.querySelectorAll("#overnight-btns .period-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
  }
  const series = [
    ["overnight", "隔夜持有（收盘买→次日开盘卖）", "#9b59b6"],
    ["intraday",  "日内持有（开盘买→收盘卖）",     "#e67e22"],
    ["total",     "买入持有", "#3498db"],
  ];
  const traces = series.map(([k, label, color]) => ({
    x: d[k].cum.dates, y: d[k].cum.values, name: label,
    type: "scatter", mode: "lines", line: { color, width: k === "total" ? 1.4 : 2.2,
      dash: k === "total" ? "dot" : "solid" },
  }));
  Plotly.newPlot("chart-overnight", traces, {...DARK, hovermode: "x unified",
    yaxis: {...DARK.yaxis, title: "累计净值（起点=1）", type: "log"},
    legend: { orientation: "h", y: 1.08 }},
    {displayModeBar: false, responsive: true});

  const ins = document.getElementById("overnight-insight");
  if (ins) {
    const ov = d.overnight.stats, intr = d.intraday.stats, r10 = d.recent10y;
    ins.innerHTML = `<b>${name}（2000–2026）：</b>隔夜段年化 <b style="color:#9b59b6">${ov.ann_return}%</b>（胜率${ov.win_rate}%），
      日内段年化 <b style="color:#e67e22">${intr.ann_return}%</b>（胜率${intr.win_rate}%）。
      近10年：隔夜 ${r10.overnight.ann_return}% vs 日内 ${r10.intraday.ann_return}%。
      <br><span style="color:var(--muted);font-size:0.75rem">⚠ 这是著名的「隔夜收益异象」（Lou/Polk/Skouras 2019）。注意：若实际执行需每天两笔交易，
      点差+手续费+税会吞掉大部分优势，更适合用来「选择入场时间」（如尽量收盘前买入而非开盘追高），而非高频策略。</span>`;
  }
}

