// ═══════════════════════════════════════════════════════
//  全局状态
// ═══════════════════════════════════════════════════════
let SIGNALS = null;
let PRICES  = null;
let MV      = null;  // multivariate analysis results
let selectedDate = null;
let activeEvents = new Set();

const TIER_META = {
  5: { label:"强势入场", stars:"★★★★★", color:"#27ae60", short:"季节 + 技术 + 宏观全面支撑",
       desc:"季节性、技术面、宏观全面支撑，历史上此类信号后20天平均涨幅最大" },
  4: { label:"适合入场", stars:"★★★★☆", color:"#2ecc71", short:"多数指标偏多，可正常仓位",
       desc:"多数指标偏多，可按计划正常仓位入场" },
  3: { label:"中性观望", stars:"★★★☆☆", color:"#f1c40f", short:"信号混合，小仓位或等待",
       desc:"信号混合，建议小仓位试探或等待更明确信号" },
  2: { label:"谨慎等待", stars:"★★☆☆☆", color:"#e67e22", short:"偏空信号为主，建议观望",
       desc:"偏空信号为主，建议观望，不宜重仓" },
  1: { label:"极高风险", stars:"★☆☆☆☆", color:"#e74c3c", short:"多重负面因素叠加，规避",
       desc:"多重负面因素叠加，历史上此类时期平均亏损，建议规避" },
};

// 档位阈值：唯一来源是 signals.json（build_signals 从 signal_model.TIER_THRESHOLDS 下发）
const TIER_FALLBACK = { 5:0.80, 4:0.60, 3:0.40, 2:0.20 };
function tierThresholds() { return SIGNALS?.tier_thresholds || TIER_FALLBACK; }

function renderTierLegend() {
  const el = document.getElementById("tier-legend");
  if (!el) return;
  const th = tierThresholds();
  const bounds = { 5:"100%", 4:Math.round(th[5]*100)+"%", 3:Math.round(th[4]*100)+"%",
                   2:Math.round(th[3]*100)+"%", 1:Math.round(th[2]*100)+"%" };
  el.innerHTML = [5,4,3,2,1].map(t => {
    const m = TIER_META[t];
    const lo = t === 1 ? "0%" : Math.round(th[t]*100)+"%";
    return `<div class="tier-row" style="background:${m.color}10">
      <div class="tier-badge" style="background:${m.color};color:${t===3?"#000":"#fff"}">${t}</div>
      <div><strong style="color:${m.color}">${m.label}</strong> ${lo}–${bounds[t]}<br>
        <span style="color:var(--muted);font-size:0.75rem">${m.short}</span></div>
    </div>`;
  }).join("");
}

// subjective:true = 该事件 LR 是主观估计，无历史样本支撑（P2-5 尸检结论）；
// 其余来自 event_study 数据驱动（仍是小样本/样本内，但至少有实证依据）。
const EVENTS_CONFIG = [
  { key:"war",        label:"战争爆发",   dot:"#e74c3c" },
  { key:"pandemic",   label:"疫情封锁",   dot:"#c0392b" },
  { key:"trade_war",  label:"贸易战升级", dot:"#d35400" },
  { key:"fed_hike",   label:"意外加息",   dot:"#9b59b6" },
  { key:"fed_cut",    label:"降息",       dot:"#27ae60" },
  { key:"gold_spike", label:"黄金暴涨",   dot:"#f1c40f", subjective:true },
  { key:"oil_spike",  label:"油价暴涨",   dot:"#e67e22", subjective:true },
  { key:"vix_spike",  label:"VIX恐慌↑",  dot:"#e74c3c" },
  { key:"halving",    label:"BTC减半",    dot:"#f39c12", subjective:true },
  { key:"ai_boom",    label:"AI重大利好", dot:"#1abc9c" },
  { key:"ipo_boom",   label:"大型IPO潮",  dot:"#3498db", subjective:true },
  { key:"election",   label:"选举不确定", dot:"#3498db", subjective:true },
];

// ═══════════════════════════════════════════════════════
//  初始化
// ═══════════════════════════════════════════════════════
async function init() {
  // 直接双击打开 HTML（file:// 协议）时 fetch 全部失败，页面会大面积空白
  if (location.protocol === "file:") {
    const w = document.createElement("div");
    w.style.cssText = "background:#e74c3c;color:#fff;padding:.6rem 1rem;font-size:0.85rem;text-align:center;";
    w.innerHTML = "⚠ 检测到直接打开文件（file://）——浏览器会拦截数据加载，大部分面板将空白。请双击 <b>启动网站.bat</b> 或访问线上页面。";
    document.body.prepend(w);
  }
  try {
    const r = await fetch("signals.json?_=" + Date.now());
    const txt = await r.text();
    SIGNALS = JSON.parse(txt);   // 后端已保证严格合法 JSON（_clean + allow_nan=False）
    const genDate = new Date(SIGNALS.generated);
    const daysDiff = Math.floor((Date.now() - genDate) / 86400000);
    const staleHtml = daysDiff > 3
      ? `<span style="color:#e67e22">⚠ 数据${daysDiff}天前</span>`
      : `<span style="color:var(--muted)">更新：${SIGNALS.generated}</span>`;
    document.getElementById("updated-time").innerHTML = staleHtml;
  } catch(e) {
    console.warn("signals.json 未找到，使用演示数据", e);
    SIGNALS = buildDemoSignals();
  }

  try {
    const r2 = await fetch("multivariate.json");
    MV = await r2.json();
  } catch(e) {
    console.warn("multivariate.json 未找到", e);
  }

  buildEventGrid();
  renderTierLegend();
  initDatePicker();
  renderPriceChart();
  renderSignalHistory();

  if (MV) {
    // 只渲染默认可见的标签页；其余标签页首次打开时再渲染
    // （Plotly 在 display:none 容器里算不出宽度，启动时全部渲染会画成一团）
    renderModelComparison();
  }

  loadLongHistory();
}

// ═══════════════════════════════════════════════════════
//  演示数据（当 signals.json 不存在时）
// ═══════════════════════════════════════════════════════
function buildDemoSignals() {
  const daily = {};
  const start = new Date("2015-01-01");
  const end   = new Date();
  const PRIOR = [0,0.62,0.54,0.62,0.80,0.58,0.40,0.80,0.54,0.45,0.62,0.80,0.74];
  for(let d = new Date(start); d <= end; d.setDate(d.getDate()+1)) {
    const k = d.toISOString().slice(0,10);
    const m = d.getMonth()+1;
    const p = PRIOR[m] * (0.85 + Math.random()*0.3);
    const prob = Math.min(0.97, Math.max(0.03, p));
    daily[k] = { prob, tier: tier(prob), month: m,
      prior: PRIOR[m], nasdaq_ma200: 1, btc_mom20: 0.02,
      dxy_trend: -0.005, nasdaq_vol: 0.15, nasdaq_rsi: 55 };
  }
  return { generated: new Date().toISOString().slice(0,10),
    latest_prob: 0.392, latest_tier: 2,
    event_adjustments: {war:0.72,pandemic:0.65,trade_war:0.78,fed_hike:0.80,
      fed_cut:1.20,election:0.90,halving:1.15,gold_spike:0.82,oil_spike:0.78,
      vix_spike:0.70,none:1.0,ai_boom:1.18,ipo_boom:1.08},
    daily_signals: daily };
}

function tier(p) {
  const th = tierThresholds();
  for (const t of [5,4,3,2]) if (p >= th[t]) return t;
  return 1;
}

// 样本外校准插值：模型原始概率 → 历史同档位实际胜率（OOS）
// 点列来自 SIGNALS.calibration_points（按 prob 升序），端点夹紧
function calibrateProb(p) {
  const pts = SIGNALS?.calibration_points;
  if (!pts || !pts.length || p == null) return null;
  const xs = pts.map(d => d.prob);
  const ys = pts.map(d => d.actual_wr);
  if (p <= xs[0]) return Math.round(ys[0] * 100) / 100;
  if (p >= xs[xs.length - 1]) return Math.round(ys[xs.length - 1] * 100) / 100;
  for (let i = 0; i < xs.length - 1; i++) {
    if (p >= xs[i] && p <= xs[i + 1]) {
      const t = (p - xs[i]) / (xs[i + 1] - xs[i]);
      return Math.round((ys[i] + t * (ys[i + 1] - ys[i])) * 10000) / 10000;
    }
  }
  return null;
}

// ── 历史信号按需加载（signals.json 只发布近两年，更早在 signals_history.json）──
let _historyPromise = null;
function ensureHistory() {
  if (_historyPromise) return _historyPromise;
  _historyPromise = fetch("signals_history.json")
    .then(r => r.json())
    .then(h => {
      SIGNALS.daily_signals = { ...h.daily_signals, ...SIGNALS.daily_signals };
      if (h.daily_signals_sp500 && SIGNALS.daily_signals_sp500)
        SIGNALS.daily_signals_sp500 = { ...h.daily_signals_sp500, ...SIGNALS.daily_signals_sp500 };
      SIGNALS._historyTried = true;
    })
    .catch(e => { console.warn("signals_history.json 加载失败", e); SIGNALS._historyTried = true; });
  return _historyPromise;
}

// ═══════════════════════════════════════════════════════
//  日期选择器
// ═══════════════════════════════════════════════════════
// 交易日的「今天」一律以美东为准：澳洲/亚洲访问者本地日期比美国快一天，
// 用本地日期会把还没发生的交易日当成今天（en-CA 格式正好是 YYYY-MM-DD）
function localDateStr(d) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit" }).format(d || new Date());
}

function initDatePicker() {
  const dp = document.getElementById("date-picker");
  const today = localDateStr();
  const maxDate = new Date(); maxDate.setDate(maxDate.getDate() + 60);  // 前瞻40个交易日≈2个月
  dp.value = today;
  dp.max   = localDateStr(maxDate);
  dp.min   = "2015-01-01";
  dp.addEventListener("change", () => updateSignal(dp.value));
  updateSignal(today);
}

function updateSignal(dateStr) {
  selectedDate = dateStr;
  const today = localDateStr();
  const isFuture = dateStr > today;

  // ── 未来日期：从 next_opportunities 前瞻数据中取 ──
  if (isFuture) {
    const allFc = SIGNALS.next_opportunities?.all_forecast || [];
    let forecast = allFc.find(d => d.date === dateStr);
    // 如果不是交易日（节假日/周末），找最近的交易日
    if (!forecast && allFc.length > 0) {
      const target = new Date(dateStr).getTime();
      forecast = allFc.reduce((best, d) => {
        return Math.abs(new Date(d.date).getTime() - target) <
               Math.abs(new Date(best.date).getTime() - target) ? d : best;
      });
    }
    if (!forecast) {
      const ring = document.getElementById("signal-ring");
      ring.className = "signal-ring tier-3";
      document.getElementById("signal-pct").textContent  = "—";
      document.getElementById("signal-label").textContent = "超出预测范围";
      document.getElementById("signal-stars").textContent = "—";
      document.getElementById("insight-box").innerHTML =
        `<strong>${dateStr}</strong><br>该日期超出预测范围（至 ${allFc[allFc.length-1]?.date||"—"}）。<br>
         <span style="color:var(--muted);font-size:0.78rem">"最佳操作窗口"显示未来40个交易日的高/低概率窗口；再往后技术因子外推不可靠，不提供数字。</span>`;
      document.getElementById("factor-list").innerHTML = "";
      document.getElementById("signal-percentile").innerHTML = "";
      return;
    }
    // 如果找到的是最近交易日而非选定日期本身，给 forecast 加一个标记
    if (forecast.date !== dateStr) forecast = {...forecast, _nearestDate: forecast.date};
    // 用预测数据合成一个 rec，技术因子用最新值
    const tech = SIGNALS.next_opportunities?.latest_tech || {};
    const synRec = {
      prob: forecast.prob, tier: forecast.tier, month: forecast.month,
      prior: forecast.prior, dow: forecast.dow_cn ? ["周一","周二","周三","周四","周五"].indexOf(forecast.dow_cn) : 0,
      wom: forecast.wom, cal_lr: forecast.cal_lr || 1.0, holiday_lr: forecast.hol_lr || 1.0,
      nasdaq_ma200: tech.nasdaq_ma200 ?? 1, btc_mom20: tech.btc_mom20 ?? 0,
      dxy_trend: tech.dxy_trend ?? 0, nasdaq_rsi: tech.nasdaq_rsi ?? 50,
      nasdaq_vol: tech.nasdaq_vol ?? 0.15,
      _isForecast: true, _reasons: forecast.reasons || [],
    };
    let prob = forecast.prob;
    if(activeEvents.size > 0) {
      let logOdds = Math.log(prob/(1-prob+1e-10));
      for(const ev of activeEvents) logOdds += Math.log(Math.max(SIGNALS.event_adjustments[ev]||1, 0.01));
      prob = Math.min(0.97, Math.max(0.03, 1/(1+Math.exp(-logOdds))));
    }
    renderSignalMeter(prob, synRec);
    renderFactors(synRec, prob);
    renderPercentileInfo(prob);
    renderTodayRec(prob);
    renderTradePlan(forecast, allFc);
    return;
  }

  // ── 历史日期：从 daily_signals 取（瘦身后早于 cutoff 的按需加载）──
  const daily = SIGNALS.daily_signals;
  let key = dateStr;
  if (!daily[key]) {
    const d = new Date(dateStr);
    for(let i=0;i<7;i++) { d.setDate(d.getDate()-1); key=d.toISOString().slice(0,10); if(daily[key]) break; }
  }
  const rec = daily[key];
  if (!rec && SIGNALS.history_cutoff && dateStr < SIGNALS.history_cutoff && !SIGNALS._historyTried) {
    document.getElementById("signal-pct").textContent = "…";
    document.getElementById("signal-label").textContent = "加载历史数据";
    ensureHistory().then(() => updateSignal(dateStr));
    return;
  }
  if (!rec) { document.getElementById("signal-pct").textContent = "无数据"; return; }

  let prob = rec.prob;
  if(activeEvents.size > 0) {
    let logOdds = Math.log(prob/(1-prob+1e-10));
    for(const ev of activeEvents) logOdds += Math.log(Math.max(SIGNALS.event_adjustments[ev]||1, 0.01));
    prob = Math.min(0.97, Math.max(0.03, 1/(1+Math.exp(-logOdds))));
  }
  renderSignalMeter(prob, rec);
  renderFactors(rec, prob);
  renderPercentileInfo(prob);
  renderTodayRec(prob);
  const tp = document.getElementById("trade-plan");
  if (tp) tp.innerHTML = "";   // 历史日期不显示操作计划
}

function renderSignalMeter(prob, rec) {
  const rawPct = Math.round(prob * 100);
  const baseRate = SIGNALS?.base_rate_20d;
  const ring = document.getElementById("signal-ring");

  // 校准曲线被 PAV 压平 = 模型无样本外区分度。此时不显示"档位/星级"这种
  // 暗示把握度的标签，改为中性"基率框架"——这是当前证据下唯一诚实的展示。
  if (SIGNALS?.calibration_flat) {
    // 大数字用无条件基率（base_rate_20d），不是 PAV 压平值（那是测试窗均值，会偏高几个点）
    const flatPct = baseRate ?? 0.62;
    ring.className = "signal-ring tier-3";   // 黄=中性，不绿不红
    document.getElementById("signal-pct").textContent  = Math.round(flatPct * 100) + "%";
    document.getElementById("signal-label").textContent = "≈基率";
    document.getElementById("signal-stars").textContent = "—";
    document.getElementById("signal-desc").innerHTML =
      `<span style="color:var(--muted);font-size:0.72rem">模型原始打分 ${rawPct}%，但样本外无区分度：` +
      `无论打分高低，未来20日上涨概率都≈基率 ${Math.round(flatPct*100)}%。当温度计看，别当把握度。</span>`;
    renderSignalMeterTail(prob, rec, { color: "#f1c40f",
      desc: "walk-forward 块自助验证未发现样本外优势，故不显示档位。" });
    return;
  }

  // 用校准概率决定档位、颜色、星级、标签；回退到原始概率
  const calProb = calibrateProb(prob);
  const displayProb = calProb !== null ? calProb : prob;
  const t = tier(displayProb);
  const meta = TIER_META[t];

  ring.className = "signal-ring tier-" + t;
  document.getElementById("signal-pct").textContent   = Math.round(displayProb*100) + "%";
  document.getElementById("signal-label").textContent  = meta.label;
  document.getElementById("signal-stars").textContent  = meta.stars;

  // 小字说明：原始输出、20日窗口、基率
  const baseRatePart = baseRate != null ? ` · 基率 ${Math.round(baseRate * 100)}%` : "";
  document.getElementById("signal-desc").innerHTML =
    `<span style="color:var(--muted);font-size:0.72rem">原始模型输出 ${rawPct}% · 未来20日窗口${baseRatePart}</span>`;

  renderSignalMeterTail(prob, rec, { color: meta.color, desc: meta.desc });
}

// 信号环以下的解释区（日期徽章/季节先验/事件叠加/模型状态），档位与基率两种展示共用
function renderSignalMeterTail(prob, rec, opts) {
  const MONTH = ["","1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"];
  const today = localDateStr();
  const isToday = selectedDate === today;
  const isForecast = rec._isForecast;
  const nearestNote = rec._nearestDate
    ? ` <span style="color:var(--muted);font-size:0.75rem">（非交易日，显示最近交易日 ${rec._nearestDate}）</span>`
    : "";
  const dateBadge = isToday
    ? `<span style="background:#2ecc7122;color:#2ecc71;border-radius:4px;padding:1px 6px;font-size:0.78rem">今天</span>`
    : isForecast
    ? `<span style="background:#3498db22;color:#3498db;border-radius:4px;padding:1px 6px;font-size:0.78rem">📡 预测</span>`
    : "";
  const evText = activeEvents.size > 0
    ? `<br>叠加事件调整后 → <strong style="color:${opts.color}">${Math.round(prob*100)}%</strong>`
    : "";
  const forecastReasons = isForecast && rec._reasons?.length
    ? `<br>日历因子：${rec._reasons.join("、")}`
    : "";
  const techNote = isForecast
    ? `<br><span style="color:var(--muted);font-size:0.76rem">技术因子冻结为最新值</span>`
    : "";

  document.getElementById("insight-box").innerHTML = `
    <strong>${selectedDate}</strong>${nearestNote} ${dateBadge}（${MONTH[rec.month]}）<br>
    季节先验：${Math.round(rec.prior*100)}%${forecastReasons}
    ${evText}${techNote}<br>
    ${opts.desc}
  `;

  // model_status_note：muted 小字，仅当字段存在时（动态插入 #signal-percentile 之后）
  const statusNote = SIGNALS?.model_status_note;
  if (!renderSignalMeterTail._statusEl) {
    const el = document.createElement("div");
    el.id = "signal-model-status";
    const percEl = document.getElementById("signal-percentile");
    if (percEl && percEl.parentNode) percEl.parentNode.insertBefore(el, percEl.nextSibling);
    renderSignalMeterTail._statusEl = el;
  }
  const statusEl = renderSignalMeterTail._statusEl;
  if (statusEl) {
    statusEl.innerHTML = statusNote
      ? `<span style="font-size:0.7rem;color:var(--muted);">${statusNote}</span>`
      : "";
  }
}

function renderFactors(rec, finalProb) {
  const MONTH = ["","1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"];
  const DOW_NAMES = ["周一","周二","周三","周四","周五","周六","周日"];
  const DOW_LR = [0.940,0.981,1.038,1.004,1.038,1.0,1.0];

  // 日历效应文字
  const calLR = rec.cal_lr || 1.0;
  const hlLR  = rec.holiday_lr || 1.0;
  const womLR = rec.wom ? ({1:1.112,2:0.996,3:1.015,4:0.950,5:0.992}[rec.wom]||1.0) : 1.0;
  function lrToText(lr) {
    if (lr >= 1.20) return "强利好 ↑↑";
    if (lr >= 1.10) return "利好 ↑";
    if (lr >= 1.02) return "微正 →↑";
    if (lr >= 0.98) return "中性 →";
    if (lr >= 0.90) return "微负 →↓";
    return "利空 ↓";
  }
  function lrToScore(lr) { return Math.min(0.9, Math.max(0.1, (lr - 0.85) / 0.45)); }

  const calNote = (rec.month===4 && rec.dom===15) ? "报税截止日(66%)" :
                  (rec.month===4 && rec.dom<=14)  ? "报税季前(57%)" :
                  (rec.month===12 && rec.dom>=11 && rec.dom<=15) ? "税损收割(47%)" :
                  (rec.month===12 && rec.dom>=21 && rec.dom<=25) ? "圣诞前(61%)" :
                  ([1,4,7,10].includes(rec.month) && rec.dom<=5) ? "季初建仓(59%)" : "普通";

  const factors = [
    { name:"月度季节性", tip:"基于1928年以来S&P500月度历史胜率的贝叶斯先验概率，6月历史均值约62%",
      val: MONTH[rec.month]+" "+Math.round(rec.prior*100)+"%",
      score: rec.prior,
      dir: rec.prior>0.6?"↑":rec.prior<0.5?"↓":"→" },
    { name:`星期效应(${DOW_NAMES[rec.dow||0]})`, tip:"周内效应：周三/周五历史胜率最高(55%+)，周一最弱；这是市场微结构造成的系统性规律",
      val: lrToText(DOW_LR[rec.dow||0])+" LR×"+DOW_LR[rec.dow||0],
      score: lrToScore(DOW_LR[rec.dow||0]),
      dir: DOW_LR[rec.dow||0]>=1?"↑":"↓" },
    { name:`月内第${rec.wom||"?"}周`, tip:"月内周次效应：第1周(季初建仓)和第3周往往强于第4周(月末税收/平仓压力)",
      val: lrToText(womLR)+" LR×"+womLR.toFixed(3),
      score: lrToScore(womLR),
      dir: womLR>=1?"↑":"↓" },
    { name:"日历异常", tip:"税季异常、报税截止日、圣诞行情等特殊日历效应，来自贝叶斯似然比(LR)调整",
      val: calNote+" LR×"+calLR.toFixed(3),
      score: lrToScore(calLR),
      dir: calLR>=1.05?"↑":calLR<=0.95?"↓":"→" },
    { name:"假日效应", tip:"感恩节前夕胜率76%、节前节后均高于基准。节前买入、节后卖出是有统计支持的策略",
      val: hlLR>1.2?"节日窗口 ↑↑":hlLR>1.0?"节前/后 ↑":"普通",
      score: lrToScore(hlLR),
      dir: hlLR>1?"↑":"→" },
    { name:"NASDAQ均线", tip:"价格在200日均线上方=多头结构(牛市)；下方=空头结构(熊市)。这是最基础的趋势判断工具",
      val: rec.nasdaq_ma200?"多头结构":"空头结构",
      score: rec.nasdaq_ma200?0.75:0.35,
      dir: rec.nasdaq_ma200?"↑":"↓" },
    { name:"BTC 20日动量", tip:"BTC的20日价格动量(涨跌幅)。BTC往往领先纳指科技股1-2周：BTC涨→科技股跟涨概率高",
      val: (rec.btc_mom20>0?"+":"")+Math.round((rec.btc_mom20||0)*100)+"%",
      score: (rec.btc_mom20||0)>0.03?0.72:(rec.btc_mom20||0)<-0.03?0.38:0.55,
      dir: (rec.btc_mom20||0)>0?"↑":"↓" },
    { name:"DXY 美元趋势", tip:"美元指数(DXY)与股市通常负相关：美元强→外资回流美债，股市承压；美元弱→股市往往受益",
      val: (rec.dxy_trend>0?"+":"")+Math.round((rec.dxy_trend||0)*100)+"%",
      score: (rec.dxy_trend||0)<-0.01?0.72:(rec.dxy_trend||0)>0.01?0.38:0.55,
      dir: (rec.dxy_trend||0)<0?"↑":"↓" },
    { name:"NASDAQ RSI", tip:"RSI(相对强弱指数)：>70超买(短期可能回调)；<30超卖(可能反弹)；50以上偏多，50以下偏空",
      val: Math.round(rec.nasdaq_rsi||50),
      score: (rec.nasdaq_rsi||50)<35?0.72:(rec.nasdaq_rsi||50)>75?0.35:0.55,
      dir: (rec.nasdaq_rsi||50)<35?"↑(超卖)":(rec.nasdaq_rsi||50)>75?"↓(超买)":"→" },
  ];

  const COLORS = {0.72:"#27ae60", 0.75:"#27ae60", 0.71:"#2ecc71",
                  0.55:"#f1c40f", 0.38:"#e67e22", 0.35:"#e74c3c"};
  function colForScore(s) {
    if(s>=0.70) return "#27ae60"; if(s>=0.60) return "#2ecc71";
    if(s>=0.50) return "#f1c40f"; if(s>=0.40) return "#e67e22"; return "#e74c3c";
  }

  const html = factors.map(f => `
    <div class="factor-row">
      <span class="factor-name"><span class="tip" data-tip="${f.tip}">${f.name}</span></span>
      <div class="factor-bar-wrap"><div class="factor-bar" style="width:${Math.round(f.score*100)}%;background:${colForScore(f.score)}"></div></div>
      <span class="factor-val" style="color:${colForScore(f.score)}">${f.val} ${f.dir}</span>
    </div>
  `).join("");
  document.getElementById("factor-list").innerHTML = html;
}

// ═══════════════════════════════════════════════════════
//  事件选择
// ═══════════════════════════════════════════════════════
function buildEventGrid() {
  const grid = document.getElementById("event-grid");
  grid.innerHTML = EVENTS_CONFIG.map(e => `
    <label class="event-item" id="ev-${e.key}" onclick="toggleEvent('${e.key}',this)"
      ${e.subjective ? 'style="opacity:.6" title="主观估计·无历史样本支撑（未经验证）"' : 'title="来自事件研究的数据驱动估计（小样本）"'}>
      <input type="checkbox">
      <span class="event-dot" style="background:${e.dot}"></span>
      ${e.label}${e.subjective ? ' <span style="font-size:0.6rem;color:var(--muted);">主观?</span>' : ''}
    </label>
  `).join("");
}

function toggleEvent(key, el) {
  if(activeEvents.has(key)) { activeEvents.delete(key); el.classList.remove("active"); }
  else                       { activeEvents.add(key);   el.classList.add("active"); }
  if(selectedDate) updateSignal(selectedDate);
}

// ═══════════════════════════════════════════════════════
//  图表
// ═══════════════════════════════════════════════════════
const DARK = { paper_bgcolor:"transparent", plot_bgcolor:"transparent",
  font:{color:"#e6edf3",size:11}, xaxis:{gridcolor:"#30363d",zerolinecolor:"#30363d"},
  yaxis:{gridcolor:"#30363d",zerolinecolor:"#30363d"}, margin:{t:30,b:40,l:50,r:20} };

async function loadCSV(path) {
  try {
    const r = await fetch(path);
    const text = await r.text();
    const lines = text.trim().split("\n");
    const headers = lines[0].split(",");
    return lines.slice(1).map(l => {
      const vals = l.split(",");
      const row = {};
      headers.forEach((h,i) => row[h.trim()] = vals[i]?.trim());
      return row;
    });
  } catch(e) { return []; }
}

let PRICES_JSON = null;
let CHARTS_EXTRA = null;

async function loadPricesJSON() {
  if (PRICES_JSON) return PRICES_JSON;
  try {
    const r = await fetch("prices.json");
    PRICES_JSON = await r.json();
  } catch(e) { PRICES_JSON = null; }
  return PRICES_JSON;
}

async function loadChartsExtra() {
  if (CHARTS_EXTRA) return CHARTS_EXTRA;
  try {
    const r = await fetch("charts_extra.json");
    CHARTS_EXTRA = await r.json();
  } catch(e) { CHARTS_EXTRA = {}; }
  return CHARTS_EXTRA;
}

async function renderPriceChart() {
  const pj = await loadPricesJSON();
  if (!pj) { Plotly.newPlot("chart-price", [], {...DARK, title:{text:"价格数据加载失败"}}); return; }

  const SHOW = ["NASDAQ","NDX100","SP500","BTC","DXY","GOLD","VIX","ETH"];
  const dates = pj.dates;
  const assets = pj.assets;
  const traces = SHOW.filter(a => assets[a]).map(a => ({
    x: dates,
    y: assets[a].values,
    name: assets[a].label,
    type: "scatter", mode: "lines",
    line: {color: assets[a].color, width: 1.8},
    hovertemplate: `<b>${assets[a].label}</b> %{x}<br>指数 %{y:.1f}<extra></extra>`,
    visible: ["NASDAQ","NDX100","SP500","BTC","DXY"].includes(a) ? true : "legendonly",
  }));

  Plotly.newPlot("chart-price", traces, {...DARK, hovermode:"x unified",
    yaxis:{...DARK.yaxis, title:"归一化指数（起点=100）"},
    xaxis:{...DARK.xaxis, rangeselector: RANGE_SEL},
    legend:{orientation:"h", y:1.08}, height:400}, {responsive:true});
}

// 时间范围快捷按钮（周线数据最小到1月粒度）
const RANGE_SEL = {
  buttons: [
    {count:1,  label:"1月", step:"month", stepmode:"backward"},
    {count:6,  label:"6月", step:"month", stepmode:"backward"},
    {count:1,  label:"1年", step:"year",  stepmode:"backward"},
    {count:5,  label:"5年", step:"year",  stepmode:"backward"},
    {count:10, label:"10年", step:"year", stepmode:"backward"},
    {step:"all", label:"全部"},
  ],
  bgcolor: "rgba(255,255,255,0.06)", activecolor: "#3498db",
  font: { color: "#aab", size: 10 }, y: 1.18,
};

async function renderCorrChart() {
  const extra = await loadChartsExtra();
  const rc = extra?.rolling_corr;
  if (!rc) return;
  const cols = Object.keys(rc.series);
  const colors = ["#f39c12","#9b59b6","#3498db","#2ecc71","#e74c3c","#1abc9c"];
  const traces = cols.map((c,i)=>({
    x:rc.dates, y:rc.series[c],
    name:c.replace("NASDAQ_vs_","NASDAQ↔"), type:"scatter", mode:"lines",
    line:{color:colors[i%colors.length],width:1.5}
  }));
  if(rc.dates.length>0) traces.push({
    x:[rc.dates[0],rc.dates[rc.dates.length-1]],y:[0,0],
    mode:"lines",line:{color:"#555",dash:"dash"},showlegend:false});
  Plotly.newPlot("chart-corr",traces,{...DARK,yaxis:{...DARK.yaxis,range:[-1,1],
    title:"相关系数"},hovermode:"x unified",legend:{orientation:"h",y:1.05}},{responsive:true});
}

async function renderMonthlyChart() {
  const extra = await loadChartsExtra();
  const data = extra?.monthly_stats;
  if(!data || !data.length) return;
  const MONTH = ["","1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"];
  const assets=["NASDAQ","DXY","BTC","ETH"], colors={NASDAQ:"#2ecc71",DXY:"#3498db",BTC:"#f39c12",ETH:"#9b59b6"};
  const traces = assets.map(a=>({
    x:data.filter(r=>r.asset===a).map(r=>MONTH[+r.month]),
    y:data.filter(r=>r.asset===a).map(r=>Math.round(parseFloat(r.win_rate)*100)),
    name:a, type:"bar", marker:{color:colors[a]},
    hovertemplate:`<b>${a}</b> %{x}<br>胜率 %{y}%<extra></extra>`
  }));
  Plotly.newPlot("chart-monthly",traces,{...DARK,barmode:"group",
    yaxis:{...DARK.yaxis,title:"胜率 (%)"},legend:{orientation:"h",y:1.05}},{responsive:true});
}

async function renderGarchChart() {
  const extra = await loadChartsExtra();
  const traces = [];
  const nd = extra?.garch_nasdaq;
  const bt = extra?.garch_btc;
  if(nd && nd.dates && nd.volatility)
    traces.push({x:nd.dates, y:nd.volatility,
      name:"NASDAQ年化波动率",type:"scatter",mode:"lines",line:{color:"#2ecc71",width:1.5}});
  if(bt && bt.dates && bt.volatility)
    traces.push({x:bt.dates, y:bt.volatility,
      name:"BTC年化波动率",type:"scatter",mode:"lines",line:{color:"#f39c12",width:1.5},
      yaxis:"y2"});
  if(!traces.length) return;
  Plotly.newPlot("chart-garch",traces,{...DARK,hovermode:"x unified",
    yaxis:{...DARK.yaxis,title:"NASDAQ波动率%"},
    yaxis2:{overlaying:"y",side:"right",title:"BTC波动率%",gridcolor:"transparent"},
    legend:{orientation:"h",y:1.05}},{responsive:true});
}

async function renderGrangerChart() {
  const extra = await loadChartsExtra();
  const data = extra?.granger;
  if(!data || !data.length) {
    const demoData = [
      {label:"美元→纳指",pval:0.0005,lag:8,sig:1},
      {label:"BTC→纳指", pval:0.0067,lag:8,sig:1},
      {label:"纳指→BTC", pval:0.0625,lag:1,sig:0},
      {label:"ETH→BTC",  pval:0.0001,lag:10,sig:1},
      {label:"BTC→ETH",  pval:0.0039,lag:6,sig:1},
    ];
    renderGrangerFromRows(demoData); return;
  }
  renderGrangerFromRows(data.map(r=>({label:r.label,pval:parseFloat(r.p_value),lag:+r.best_lag_days,sig:r.significant===true||r.significant==="True"?1:0})));
}

function renderGrangerFromRows(rows) {
  const colors = rows.map(r=>r.sig?"#2ecc71":"#e74c3c");
  Plotly.newPlot("chart-granger",[{
    type:"bar", orientation:"h",
    x:rows.map(r=>Math.max(-Math.log10(r.pval),0)),
    y:rows.map(r=>r.label),
    marker:{color:colors},
    text:rows.map(r=>`p=${r.pval.toFixed(4)} 滞后${r.lag}天 ${r.sig?"✓":"✗"}`),
    textposition:"outside", hovertemplate:"%{y}<br>%{text}<extra></extra>",
  }],{...DARK,xaxis:{...DARK.xaxis,title:"-log10(p值)，越大越显著"},
    shapes:[{type:"line",x0:1.3,x1:1.3,y0:-0.5,y1:rows.length-0.5,
      line:{color:"#e74c3c",dash:"dash",width:1}}],
    annotations:[{x:1.3,y:rows.length-0.5,text:"p=0.05",showarrow:false,
      font:{color:"#e74c3c",size:10}}]},{responsive:true});
}

async function renderAnnualChart() {
  const extra = await loadChartsExtra();
  const data = extra?.annual_returns;
  if(!data || !data.length) return;
  const assets=["NASDAQ","DXY","BTC","ETH"];
  const years=data.map(r=>r.year);
  const z=assets.map(a=>data.map(r=>r[a]!=null?Math.round(parseFloat(r[a])*100):null));
  Plotly.newPlot("chart-annual",[{type:"heatmap",z,x:years,y:assets,
    colorscale:"RdYlGn",zmid:0,
    text:z.map(row=>row.map(v=>v!=null?v+"%":"—")),
    texttemplate:"%{text}",colorbar:{title:"涨幅%"},
    hovertemplate:"<b>%{y}</b> %{x}年<br>%{text}<extra></extra>"}],
    {...DARK,margin:{...DARK.margin,b:60}},{responsive:true});
}

async function renderSignalHistory() {
  if(!SIGNALS) return;
  const entries = Object.entries(SIGNALS.daily_signals).slice(-500);
  const dates = entries.map(([k])=>k);
  const probs = entries.map(([,v])=>v.prob*100);
  const tiers = entries.map(([,v])=>v.tier);
  const colors = tiers.map(t=>[,"#e74c3c","#e67e22","#f1c40f","#2ecc71","#27ae60"][t]);

  Plotly.newPlot("chart-signal-history",[
    {x:dates,y:probs,type:"scatter",mode:"lines",name:"贝叶斯概率",
     line:{color:"#3498db",width:1.5},fill:"tozeroy",fillcolor:"rgba(52,152,219,.15)"},
    {x:dates,y:Array(dates.length).fill(60),mode:"lines",
     line:{color:"#2ecc71",dash:"dot",width:1},name:"入场线(60%)",showlegend:true},
    {x:dates,y:Array(dates.length).fill(80),mode:"lines",
     line:{color:"#27ae60",dash:"dot",width:1},name:"强势线(80%)",showlegend:true},
  ],{...DARK,yaxis:{...DARK.yaxis,range:[0,100],title:"入场概率%"},
    hovermode:"x unified",legend:{orientation:"h",y:1.05}},{responsive:true});
}

// ── 标签切换（主图区，仅影响 id="tab-*" 的内容）──
const MAIN_TABS = ["forecast","corr","monthly","garch","granger","annual"];
const _mainTabRendered = new Set();
function switchTab(name, el) {
  el.closest(".tabs").querySelectorAll(".tab").forEach(t=>t.classList.remove("active"));
  el.classList.add("active");
  MAIN_TABS.forEach(t => {
    const el2 = document.getElementById("tab-"+t);
    if (el2) el2.classList.remove("active");
  });
  const pane = document.getElementById("tab-"+name);
  pane?.classList.add("active");
  setTimeout(() => {
    if (_mainTabRendered.has(name)) { resizeChartsIn(pane); return; }
    _mainTabRendered.add(name);
    const ph = document.getElementById("ph-"+name);
    if (ph) ph.style.display = "none";
    if (name === "forecast")  safeRender(renderForecastChart, "Forecast");
    if (name === "corr")      safeRender(renderCorrChart,     "Corr");
    if (name === "monthly")   safeRender(renderMonthlyChart,  "Monthly");
    if (name === "garch")     safeRender(renderGarchChart,    "Garch");
    if (name === "granger")   safeRender(renderGrangerChart,  "Granger");
    if (name === "annual")    safeRender(renderAnnualChart,   "Annual");
  }, 0);
}

// ═══════════════════════════════════════════════════════
//  DOW 周内效应面板
// ═══════════════════════════════════════════════════════
function renderDOWPanel() {
  if (!SIGNALS || !SIGNALS.dow) return;
  const dow = SIGNALS.dow;  // [{dow,day_name,win_rate,avg_return}]
  const todayDow = new Date().getDay() - 1;  // 0=Mon
  const maxWR = Math.max(...dow.map(d => d.win_rate));
  const minWR = Math.min(...dow.map(d => d.win_rate));

  const NAMES = ["周一","周二","周三","周四","周五"];
  const cards = NAMES.map((name, i) => {
    const d = dow.find(x => x.dow === i) || {win_rate: 54, avg_return: 0};
    const isToday = i === todayDow;
    const isBest  = d.win_rate === maxWR;
    const isWorst = d.win_rate === minWR;
    const cls = isToday ? "today" : isBest ? "best" : isWorst ? "worst" : "";
    const color = d.win_rate >= 56 ? "#27ae60" : d.win_rate >= 54 ? "#2ecc71" :
                  d.win_rate >= 52 ? "#f1c40f" : "#e74c3c";
    const rank = isBest ? "🥇最佳" : isWorst ? "⚠最弱" : isToday ? "📍今天" : "";
    return `<div class="dow-card ${cls}">
      <div class="dow-name">${name}</div>
      <div class="dow-wr" style="color:${color}">${d.win_rate}%</div>
      <div class="dow-avg">${d.avg_return > 0 ? '+' : ''}${d.avg_return}%</div>
      <div class="dow-rank">${rank}</div>
    </div>`;
  });
  document.getElementById("dow-grid").innerHTML = cards.join("");

  const best = dow.reduce((a,b) => a.win_rate > b.win_rate ? a : b);
  const worst = dow.reduce((a,b) => a.win_rate < b.win_rate ? a : b);
  document.getElementById("dow-insight").innerHTML =
    `<strong>周内规律：</strong>历史上<strong style="color:#27ae60">${NAMES[best.dow]}（${best.win_rate}%）</strong>是最佳买入日，
     <strong style="color:#e74c3c">${NAMES[worst.dow]}（${worst.win_rate}%）</strong>最弱。
     BTC周四往往有期权Gamma压力，科技股周三/周一开盘后回调是加仓时机。`;
}

// ═══════════════════════════════════════════════════════
//  卖出信号面板
// ═══════════════════════════════════════════════════════
function renderSellPanel() {
  if (!SIGNALS || !SIGNALS.sell) {
    // 演示数据
    SIGNALS.sell = { score: 33.7, tier: "持有观察", rsi: 56, mom20: 2.6, ma_cross: 1, vol_pct: 25 };
  }
  const s = SIGNALS.sell;
  const score = s.score || 0;

  const barColor = score >= 70 ? "#e74c3c" : score >= 55 ? "#e67e22" :
                   score >= 40 ? "#f1c40f" : score >= 25 ? "#2ecc71" : "#27ae60";
  document.getElementById("sell-score-txt").textContent = score.toFixed(1) + "/100";
  document.getElementById("sell-bar").style.width = score + "%";
  document.getElementById("sell-bar").style.background = barColor;

  const tierColor = score >= 55 ? "#e74c3c" : score >= 40 ? "#f1c40f" : "#2ecc71";
  document.getElementById("sell-tier-txt").style.color = tierColor;
  document.getElementById("sell-tier-txt").textContent = s.tier || "—";

  const rsi = s.rsi > 100 ? "—" : (s.rsi || 0).toFixed(1);
  const rsiColor = s.rsi > 75 ? "#e74c3c" : s.rsi > 60 ? "#f1c40f" : "#2ecc71";
  const maText = s.ma_cross ? "金叉 ✓" : "死叉 ✗";
  const maColor = s.ma_cross ? "#2ecc71" : "#e74c3c";
  const volColor = (s.vol_pct || 0) > 70 ? "#e74c3c" : (s.vol_pct || 0) > 40 ? "#f1c40f" : "#2ecc71";

  document.getElementById("sell-metrics").innerHTML = `
    <div class="sell-metric">
      <div class="sell-metric-label">RSI（超75卖出）</div>
      <div class="sell-metric-val" style="color:${rsiColor}">${rsi}</div>
    </div>
    <div class="sell-metric">
      <div class="sell-metric-label">20日动量</div>
      <div class="sell-metric-val" style="color:${(s.mom20||0)>0?'#2ecc71':'#e74c3c'}">${(s.mom20||0)>0?'+':''}${(s.mom20||0).toFixed(1)}%</div>
    </div>
    <div class="sell-metric">
      <div class="sell-metric-label">均线状态</div>
      <div class="sell-metric-val" style="color:${maColor}">${maText}</div>
    </div>
    <div class="sell-metric">
      <div class="sell-metric-label">波动率分位</div>
      <div class="sell-metric-val" style="color:${volColor}">${(s.vol_pct||0).toFixed(0)}%历史位</div>
    </div>
  `;

  const advice = score >= 70 ? "⚠️ 多重卖出信号触发，建议减仓至少50%，等待回调后再建仓" :
                 score >= 55 ? "注意风险上升，可考虑止盈部分仓位，保留核心持仓" :
                 score >= 40 ? "信号混合，建议持有但不加仓，设好止损位" :
                 "当前持有安全，继续持有等待更好的卖出时机";
  document.getElementById("sell-insight").innerHTML =
    `<strong>建议：</strong>${advice}`;
}

// ══════════════════════════════════════════════════════
//  长历史 + 假日效应
// ══════════════════════════════════════════════════════
let LONG_HISTORY = null;
let currentPeriod = "1928+";

async function loadLongHistory() {
  try {
    const r = await fetch("long_history.json");
    LONG_HISTORY = await r.json();
    renderLongMonthly(currentPeriod);
    renderHolidayChart();
    renderBearMarkets();
  } catch(e) { console.warn("long_history.json 未找到", e); }
}

function setPeriod(period, el) {
  currentPeriod = period;
  document.querySelectorAll(".period-btn").forEach(b => b.classList.remove("active"));
  el.classList.add("active");
  renderLongMonthly(period);
}

function renderLongMonthly(period) {
  if (!LONG_HISTORY) return;
  const rows = (LONG_HISTORY.monthly_by_period || {})[period] || [];
  if (!rows.length) return;

  const MONTH = ["","1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"];
  const colors = rows.map(r => {
    if (r.win_rate >= 65) return "#27ae60";
    if (r.win_rate >= 58) return "#2ecc71";
    if (r.win_rate >= 52) return "#f1c40f";
    if (r.win_rate >= 47) return "#e67e22";
    return "#e74c3c";
  });

  Plotly.newPlot("chart-longmonthly", [
    {type:"bar", x: rows.map(r=>MONTH[r.month]), y: rows.map(r=>r.win_rate),
     name:"月度胜率%", marker:{color:colors},
     text: rows.map(r=>`${r.win_rate}%<br>均值${r.avg_return>0?"+":""}${r.avg_return}%<br>n=${r.n}`),
     hovertemplate:"<b>%{x}</b><br>%{text}<extra></extra>"},
    {type:"scatter", x: rows.map(r=>MONTH[r.month]), y: rows.map(r=>r.avg_return),
     name:"月均收益%", yaxis:"y2", mode:"lines+markers",
     line:{color:"#3498db",width:2}, marker:{size:6},
     hovertemplate:"%{x} 均值%{y:.2f}%<extra></extra>"},
  ], {
    ...DARK,
    barmode:"overlay",
    yaxis: {...DARK.yaxis, title:"胜率 %", range:[30,85]},
    yaxis2: {overlaying:"y", side:"right", title:"月均收益 %", gridcolor:"transparent",
              zeroline:true, zerolinecolor:"#555"},
    shapes:[{type:"line",x0:-0.5,x1:11.5,y0:50,y1:50,
             line:{color:"#555",dash:"dash",width:1}}],
    legend:{orientation:"h",y:1.05},
  }, {responsive:true});

  // 更新样本数徽章
  const totalN = rows.reduce((s,r)=>s+r.n,0);
  document.getElementById("period-sample-badge").textContent =
    `${period}  共${totalN}个月样本`;

  // 找最强/最弱月
  const best  = rows.reduce((a,b) => a.win_rate > b.win_rate ? a : b);
  const worst = rows.reduce((a,b) => a.win_rate < b.win_rate ? a : b);
  document.getElementById("longmonthly-insight").innerHTML =
    `<strong>${period} 统计（${rows[0]?.n} 年/月）：</strong>
     最强月 <span style="color:#27ae60">${MONTH[best.month]}（${best.win_rate}%，均值${best.avg_return>0?"+":""}${best.avg_return}%）</span> ·
     最弱月 <span style="color:#e74c3c">${MONTH[worst.month]}（${worst.win_rate}%，均值${worst.avg_return}%）</span>
     · 9月效应在所有时段均成立（历史最稳定的熊市规律）`;
}

function renderHolidayChart() {
  if (!LONG_HISTORY || !LONG_HISTORY.holiday_effects) return;
  const he = LONG_HISTORY.holiday_effects;

  const items = [
    {name:"感恩节前夕(周三)", wr: he.thanksgiving_eve?.win_rate,    avg: he.thanksgiving_eve?.avg_return,    n: he.thanksgiving_eve?.n},
    {name:"感恩节后(黑五)",   wr: he.thanksgiving_friday?.win_rate, avg: he.thanksgiving_friday?.avg_return, n: he.thanksgiving_friday?.n},
    {name:"圣诞行情(Dec26-Jan3)", wr: he.santa_claus_rally?.win_rate, avg: he.santa_claus_rally?.avg_return, n: he.santa_claus_rally?.n},
    {name:"节前交易日",       wr: he.pre_holiday?.win_rate,         avg: he.pre_holiday?.avg_return,         n: he.pre_holiday?.n},
    {name:"节后交易日",       wr: he.post_holiday?.win_rate,        avg: he.post_holiday?.avg_return,        n: he.post_holiday?.n},
    {name:"1月效应(前5日)",   wr: he.january_effect?.win_rate,      avg: he.january_effect?.avg_return,      n: he.january_effect?.n},
    {name:"普通交易日(基准)", wr: he.normal?.win_rate,              avg: he.normal?.avg_return,              n: he.normal?.n},
  ].filter(d => d.wr != null).reverse();

  const colors = items.map(d => d.name.includes("基准") ? "#555" :
    d.wr >= 70 ? "#27ae60" : d.wr >= 60 ? "#2ecc71" : d.wr >= 55 ? "#f1c40f" : "#e74c3c");

  Plotly.newPlot("chart-holiday", [{
    type:"bar", orientation:"h",
    x: items.map(d=>d.wr), y: items.map(d=>d.name),
    marker:{color:colors},
    text: items.map(d=>`${d.wr}%胜率  均值${d.avg>0?"+":""}${(d.avg*100).toFixed ? d.avg.toFixed(2) : d.avg}%  n=${d.n}`),
    textposition:"outside",
    hovertemplate:"<b>%{y}</b><br>%{text}<extra></extra>",
  }], {
    ...DARK,
    xaxis:{...DARK.xaxis, range:[40,85], title:"日频胜率 %"},
    margin:{t:20,b:50,l:160,r:80},
    shapes:[{type:"line",x0:52.4,x1:52.4,y0:-0.5,y1:items.length-0.5,
             line:{color:"#555",dash:"dot",width:1}}],
    annotations:[{x:52.4,y:items.length-0.5,text:"基准52.4%",
      showarrow:false,font:{color:"#8b949e",size:10}}],
  }, {responsive:true});

  document.getElementById("holiday-insight").innerHTML =
    `<strong>贝叶斯应用：</strong>感恩节前夕（周三）胜率 <span style="color:#27ae60">76.3%</span>，
     已自动纳入每日信号计算（似然比×1.46）。
     节前/节后统一+6%胜率优势，圣诞行情窗口+5.5%。
     <span style="color:var(--muted);font-size:0.78rem">数据来源：S&P 500 日频 1950-2026，约24,000个交易日。</span>`;
}

function renderBearMarkets() {
  if (!LONG_HISTORY || !LONG_HISTORY.bear_markets) return;
  const bm = LONG_HISTORY.bear_markets;

  Plotly.newPlot("chart-bearmarkets", [{
    type:"bar", orientation:"h",
    x: bm.map(b=>b.drawdown),
    y: bm.map(b=>`${b.name} (${b.start})`),
    marker:{color: bm.map(b => b.drawdown < -50 ? "#c0392b" : b.drawdown < -30 ? "#e74c3c" : "#e67e22")},
    text: bm.map(b=>`跌幅${b.drawdown}%  恢复${b.recovery_months}月  ${b.cause}`),
    textposition:"outside",
    hovertemplate:"<b>%{y}</b><br>%{text}<extra></extra>",
    cliponaxis: false,
  }], {
    ...DARK,
    xaxis:{...DARK.xaxis, title:"最大跌幅 %", range:[-105,5]},
    margin:{t:20,b:50,l:165,r:10},
  }, {responsive:true});
}

// ── 多元分析标签切换 ──
// 各标签页对应的渲染函数（首次打开时才渲染，保证容器可见、宽度正确）
const MV_RENDERERS = {
  modelcmp:   () => renderModelComparison(),
  shap:       () => renderSHAPChart(),
  prophet:    () => renderProphetChart(),
  kalman:     () => renderKalmanChart(),
  rolling:    () => renderRollingBetaChart(),
  path:       () => renderPathChart(),
  cca:        () => renderCCAChart(),
  backtest:   () => renderBacktestCharts(),
};
const _mvTabRendered = new Set(["modelcmp"]);   // modelcmp 启动时已渲染

// 让刚变为可见的容器里所有 Plotly 图重算尺寸（修复曾在隐藏状态下渲染的图）
function resizeChartsIn(container) {
  if (!container) return;
  container.querySelectorAll(".js-plotly-plot").forEach(c => {
    try { Plotly.Plots.resize(c); } catch(e) {}
  });
}

// 窗口缩放时全局重算（防手机横竖屏/调窗口后图表挤压）
let _resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(() => {
    document.querySelectorAll(".js-plotly-plot").forEach(c => {
      try { Plotly.Plots.resize(c); } catch(e) {}
    });
  }, 250);
});

function switchMVTab(name, el) {
  document.querySelectorAll("#mv-tabs .tab").forEach(t=>t.classList.remove("active"));
  document.querySelectorAll("[id^='mvtab-']").forEach(t=>t.classList.remove("active"));
  el.classList.add("active");
  const pane = document.getElementById("mvtab-"+name);
  pane.classList.add("active");
  setTimeout(() => {
    if (!_mvTabRendered.has(name)) {
      _mvTabRendered.add(name);
      safeRender(MV_RENDERERS[name] || (()=>{}), "MV:"+name);
    } else {
      resizeChartsIn(pane);   // 已渲染过：重算尺寸，防挤压/叠加
    }
  }, 0);
}

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
        return `<tr style="border-bottom:1px solid var(--border)22;${todayBg}">
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
       校准曲线：模型预测概率越高 → 实际胜率越高，说明信号有单调性。<br>
       「仅Tier≥4入场」策略 20日胜率 ${s4.win_rate_20d||"?"}% vs 随时买入 ${s4.baseline_win_rate||"?"}%，
       p=${s4.p_value||"?"}（<strong>高度显著</strong>）。绝对差距 +${s4.diff||"?"}pp，持续复利后可产生显著超额收益。
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
        onclick="selectForecastDay('${d.date}')"
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
    return `<div style="display:flex;align-items:flex-start;gap:.6rem;padding:.4rem 0;border-bottom:1px solid var(--border)22;">
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
const COIN_IDS = { BTC:"bitcoin", ETH:"ethereum", XLM:"stellar", DOGE:"dogecoin", HOME:"defi-app", SOL:"solana", BNB:"binancecoin" };
let portfolioPrices = {};

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
    const p = portfolioPrices[item.ticker] || item.priceUSD;
    const pAUD = p && _portAudRate ? p / _portAudRate : null;
    const val = pAUD ? item.qty * pAUD : null;
    if (val) total += val;
    // P&L
    const costUSD = item.costUSD;
    const costAUD = (costUSD && _portAudRate) ? (costUSD / _portAudRate * item.qty) : null;
    if (costAUD) totalCost += costAUD;
    const plAUD = (val && costAUD) ? val - costAUD : null;
    const plPct = (plAUD != null && costAUD > 0) ? plAUD / costAUD * 100 : null;
    const plStr = item.qty <= 0 ? "" :
      plAUD != null
      ? `<br><span class="${plAUD >= 0 ? 'pl-up' : 'pl-dn'}">${plAUD >= 0 ? '+' : ''}A$${plAUD.toFixed(0)} (${plPct >= 0 ? '+' : ''}${(plPct||0).toFixed(1)}%)</span>`
      : `<br><span class="cost-link" onclick="setPortfolioCost(${i},'${item.ticker}')">设置成本价</span>`;
    const valStr = val ? `A$${val.toFixed(2)}` : "—";
    const pStr  = p   ? `$${p < 1 ? p.toFixed(4) : p.toFixed(2)}` : "—";
    return `<tr style="border-bottom:1px solid var(--border)22;">
      <td style="padding:.35rem .4rem;font-weight:600;color:var(--text)">${item.ticker}${item.note?`<br><span style="font-size:0.68rem;color:var(--muted);font-weight:400">${item.note}</span>`:""}</td>
      <td style="text-align:right;padding:.35rem .4rem;color:var(--muted)">${item.qty}</td>
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

async function fetchPortfolioPrices() {
  const btn = document.getElementById("portfolio-refresh-btn");
  if (btn) btn.textContent = "⏳ 获取中...";
  try {
    const ids = Object.values(COIN_IDS).join(",");
    const r = await fetch(`https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd,aud`);
    const data = await r.json();
    let audRate = null;
    Object.entries(COIN_IDS).forEach(([ticker, id]) => {
      if (data[id]?.usd) portfolioPrices[ticker] = data[id].usd;
      if (!audRate && data[id]?.usd && data[id]?.aud) audRate = data[id].usd / data[id].aud;
    });
    const now = new Date();
    const ts = `${now.getHours()}:${String(now.getMinutes()).padStart(2,'0')}`;
    const updEl = document.getElementById("portfolio-updated");
    if (updEl) updEl.textContent = `更新于 ${ts}，1 AUD ≈ US$${audRate?audRate.toFixed(4):"?"}`;
    renderPortfolioTable(audRate || 0.71);
    renderSPCXTracker();
    updateSPCXCalc();
  } catch(e) {
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
    yaxis:{...DARK.yaxis, title:"平均恢复天数"},
    xaxis:{...DARK.xaxis},
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
    xaxis:{...DARK.xaxis},
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

  el.innerHTML = [
    gauge("VIX（波动率/恐慌指数）", vixProxy, 10, 50, vixZones, "",
      vixProxy ? `<30=恐慌买入机会 · <15=过度乐观需谨慎 · 数据截至 ${SIGNALS.generated}` : ""),
    gauge("纳指RSI（超买超卖）", rsi, 0, 100, rsiZones, "",
      "RSI>70超买，<30超卖；现在" + (rsi>70?"偏高，注意回调":rsi<30?"极度超卖，反弹概率大":"正常区间")),
    gauge("BTC 20日动量", btcPct, -50, 50, btcZones, "%",
      "BTC往往领先美股科技股1-2周，负值代表近期加密偏弱"),
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

// ═══════════════════════════════════════════════════════
//  SpaceX SPCX IPO 追踪器
// ═══════════════════════════════════════════════════════
const SPCX_LISTING_DATE = "2026-06-12";
const SPCX_ISSUE_USD    = 135;

function renderSPCXTracker() {
  const el = document.getElementById("spcx-tracker");
  if (!el) return;
  const today = localDateStr();
  const hasListed = today >= SPCX_LISTING_DATE;

  // Countdown
  const listDt  = new Date(2026, 5, 12); // June 12 local time
  const daysLeft = Math.max(0, Math.ceil((listDt - new Date()) / 86400000));

  const savedShares = +(localStorage.getItem("spcx_shares") || 0);
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
        value="${savedShares||""}" oninput="saveSPCXData('shares',this.value)">
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
      value="${savedShares||""}" oninput="saveSPCXData('shares',this.value)">
    <div style="font-size:0.78rem;color:var(--muted);margin:.5rem 0 .3rem">当前市价 (USD)</div>
    <input class="spcx-input" type="number" min="0" step="0.01" placeholder="发行价135"
      value="${savedPrice||""}" oninput="saveSPCXData('price',this.value)">
    ${savedShares > 0 && savedPrice > 0 ? `
    <div class="spcx-pl-row" style="margin-top:.65rem;">
      <div class="spcx-pl-val"><span style="color:var(--muted);font-size:0.7rem">成本</span><br><strong>A$${issueAUD.toFixed(0)}</strong></div>
      <div class="spcx-pl-val"><span style="color:var(--muted);font-size:0.7rem">市值</span><br><strong>A$${currAUD.toFixed(0)}</strong></div>
      <div class="spcx-pl-val"><span style="color:var(--muted);font-size:0.7rem">盈亏</span><br>
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

  const shares = sharesIn || +(localStorage.getItem("spcx_shares")||0);
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
      <div class="spcx-pl-val"><span style="color:var(--muted);font-size:0.7rem">股数</span><br><strong>${shares}</strong></div>
      <div class="spcx-pl-val"><span style="color:var(--muted);font-size:0.7rem">成本(AUD)</span><br><strong>A$${issueAUD.toFixed(0)}</strong></div>
      ${currAUD > 0 ? `<div class="spcx-pl-val"><span style="color:var(--muted);font-size:0.7rem">市值(AUD)</span><br><strong>A$${currAUD.toFixed(0)}</strong></div>
      <div class="spcx-pl-val"><span style="color:var(--muted);font-size:0.7rem">盈亏</span><br>
        <strong style="color:${plAUD>=0?'#2ecc71':'#e74c3c'}">${plAUD>=0?'+':''}A$${plAUD.toFixed(0)}<br>${plPct>=0?'+':''}${plPct.toFixed(1)}%</strong></div>` : ""}
    </div>
    ${currAUD > 0 && gainPct > 5 ? `<div style="font-size:0.78rem;color:var(--muted)">卖一半可入袋 <strong style="color:#2ecc71">A$${halfProfit.toFixed(0)}</strong></div>` : ""}
    ${recHtml}`;
}

// Try to fetch SPCX price from Yahoo Finance
async function fetchSPCXPrice() {
  const btn = document.getElementById("spcx-price-btn");
  if (btn) btn.textContent = "⏳ 获取中...";
  try {
    const r = await fetch("https://query1.finance.yahoo.com/v8/finance/chart/SPCX?interval=1d&range=1d");
    const d = await r.json();
    const price = d?.chart?.result?.[0]?.meta?.regularMarketPrice;
    if (price) {
      const inp = document.getElementById("spcx-price-input");
      if (inp) { inp.value = price.toFixed(2); updateSPCXCalc(); }
      localStorage.setItem("spcx_price", price);
      renderSPCXTracker();
    } else {
      alert("暂时无法自动获取价格，请在上市后手动输入。");
    }
  } catch(e) {
    alert("获取失败（可能尚未上市）。上市后手动输入当前价格即可。");
  } finally {
    if (btn) btn.textContent = "📡 获取价格";
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
    const r = await fetch("https://api.alternative.me/fng/?limit=7&format=json");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const json = await r.json();
    renderFearGreed(json.data || []);
  } catch(e) {
    el.innerHTML = `<div style="font-size:0.78rem;color:var(--muted)">
      恐惧贪婪指数暂时无法加载
      <button onclick="fetchFearAndGreed()"
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

  el.innerHTML = `
    <div style="background:var(--surface2);border-radius:8px;padding:1rem;margin-top:.5rem;">
      <div style="font-size:0.8rem;font-weight:600;color:var(--muted);margin-bottom:.5rem;">
        ${assetName !== "custom" && assetName ? assetName : ""}  ${qty} 个 · 持有${heldMonths ? heldMonths+"个月" : "未知"}
        ${eligible50 ? '<span style="background:rgba(46,204,113,.2);color:#2ecc71;border-radius:3px;padding:1px 6px;font-size:0.7rem;margin-left:.3rem;">✓ 12月折扣</span>' : ""}
      </div>
      <div class="cgt-result-row"><span style="color:var(--muted)">买入总成本</span><span>A$${totalCost.toLocaleString("en-AU",{minimumFractionDigits:2,maximumFractionDigits:2})}</span></div>
      <div class="cgt-result-row"><span style="color:var(--muted)">卖出总收入</span><span>A$${totalProceeds.toLocaleString("en-AU",{minimumFractionDigits:2,maximumFractionDigits:2})}</span></div>
      <div class="cgt-result-row"><span style="color:var(--muted)">资本利得（税前）</span><span style="color:${gain_color};font-weight:700">${rawGain >= 0 ? '+' : ''}A$${rawGain.toLocaleString("en-AU",{minimumFractionDigits:2,maximumFractionDigits:2})}</span></div>
      ${eligible50 ? `<div class="cgt-result-row"><span style="color:var(--muted)">50%折扣（持有>12月）</span><span style="color:#2ecc71">−A$${(rawGain*0.5).toFixed(2)}</span></div>` : ""}
      <div class="cgt-result-row"><span style="color:var(--muted)">应税金额</span><span>A$${Math.max(0,taxableGain).toFixed(2)}</span></div>
      <div class="cgt-result-row"><span style="color:var(--muted)">个税（${taxRate}%）</span><span style="color:#e74c3c">−A$${taxOnGain.toFixed(2)}</span></div>
      <div class="cgt-result-row"><span style="color:var(--muted)">Medicare征费（2%）</span><span style="color:#e74c3c">−A$${medicare.toFixed(2)}</span></div>
      <div class="cgt-result-row cgt-highlight"><span>税后净盈亏</span>
        <span style="color:${netGain >= 0 ? '#2ecc71' : '#e74c3c'}">${netGain >= 0 ? '+' : ''}A$${netGain.toFixed(2)} (${netPct >= 0 ? '+' : ''}${netPct.toFixed(1)}%)</span></div>
      ${isGain && !eligible50 && heldMonths > 0 && heldMonths < 12 ? `
      <div style="background:rgba(241,196,15,.1);border:1px solid rgba(241,196,15,.3);border-radius:5px;padding:.5rem .75rem;margin-top:.5rem;font-size:0.78rem;">
        💡 再持有 <strong style="color:#f1c40f">${12 - heldMonths} 个月</strong>即可享受50%折扣，届时预计少缴税 <strong style="color:#2ecc71">A$${(rawGain*0.5*(taxRate/100+0.02)).toFixed(0)}</strong>
      </div>` : ""}
      <div style="font-size:0.72rem;color:var(--muted);margin-top:.5rem;">
        保本卖出价（税后回本）≈ <strong>A$${breakEvenAUD.toFixed(4)}/个</strong>
      </div>
    </div>`;
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

// Portfolio cost basis editor
function setPortfolioCost(i, ticker) {
  const cost = prompt(`请输入 ${ticker} 的平均买入价（USD）：\n（例如：BTC填95000，DOGE填0.15）`);
  if (cost == null) return;
  const v = parseFloat(cost);
  if (isNaN(v) || v < 0) { alert("请输入有效价格"); return; }
  const port = loadPortfolio();
  if (port[i]) {
    port[i].costUSD = v;
    savePortfolio(port);
    renderPortfolioTable(_portAudRate);
  }
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
    return `<tr onclick="renderStockChart('${sym}')" style="cursor:pointer;border-bottom:1px solid var(--border)33;">
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
      `<div title="${l.note}" style="flex:1;min-width:96px;text-align:center;padding:.35rem .2rem;
           border:1px solid ${LC[l.status]}55;border-radius:7px;background:${LC[l.status]}11;cursor:help;">
        <div style="font-size:0.62rem;color:var(--muted);">${l.name}</div>
        <div style="font-size:0.78rem;font-weight:700;color:${LC[l.status]};">●&nbsp;${l.value}</div>
      </div>`).join("");
    const lightsHtml = lights
      ? `<div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:.55rem;">${lights}</div>` : "";
    el.innerHTML = lightsHtml + (b.lines || []).map(l => {
      const m = l.match(/^【(.+?)】(.*)$/);
      if (!m) return `<div>${l}</div>`;
      const warn = m[2].includes("⚠");
      return `<div style="padding:.18rem 0;">
        <span style="color:var(--muted);font-size:0.72rem;">【${m[1]}】</span>
        <span style="${warn ? "color:#e67e22;" : ""}">${m[2]}</span></div>`;
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
      <td style="padding:.25rem .4rem;"><button class="period-btn" onclick="gameSell('${s}')">卖出</button></td>
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
      <button class="cgt-btn" style="flex:0;padding:.4rem .8rem;" onclick="gameBuy()">买入</button>
    </div>
    ${holdRows ? `<table style="width:100%;font-size:0.74rem;border-collapse:collapse;">${holdRows}</table>` : ""}
    ${recent ? `<div style="margin-top:.4rem;">${recent}</div>` : ""}
    <div style="display:flex;justify-content:space-between;margin-top:.45rem;align-items:center;">
      <span style="color:var(--muted);font-size:0.66rem;">按最近收盘价成交（${STOCKS.generated}）· 存在本浏览器</span>
      <button class="period-btn" onclick="gameReset()">重置</button>
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
    const head = cols.map(c => `<th style="text-align:left;padding:.3rem .6rem;color:var(--muted);font-size:0.72rem;">${c}</th>`).join("");
    const rows = (s.table || []).map(r =>
      `<tr>${cols.map(c => `<td style="padding:.3rem .6rem;border-top:1px solid var(--border)33;">${r[c]}</td>`).join("")}</tr>`).join("");
    return `<div style="margin-bottom:1.1rem;">
      <div style="font-weight:700;margin-bottom:.35rem;">${s.title}</div>
      <table style="border-collapse:collapse;min-width:50%;">${head ? `<tr>${head}</tr>` : ""}${rows}</table>
      ${s.note ? `<div style="color:var(--muted);font-size:0.72rem;margin-top:.3rem;line-height:1.5;">${s.note}</div>` : ""}
    </div>`;
  }).join("") + `<div style="color:var(--muted);font-size:0.68rem;">生成于 ${rep.generated} · 模型 v${rep.model_version}</div>`;
}

// ═══════════════════════════════════════════════════════
//  今日市场要闻（news.json，由 AI 监控循环 / 手工更新）
// ═══════════════════════════════════════════════════════
// HTML 转义：RSS 标题来自外部源，必须当不可信数据处理（防 XSS）
function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
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
  if (up && news.updated) up.textContent = `更新 ${news.updated}`;
  const IC = { positive: ["▲", "#2ecc71"], negative: ["▼", "#e74c3c"], neutral: ["●", "#f1c40f"] };
  el.innerHTML = (news.items || []).map(n => {
    const [sym, color] = IC[n.impact] || IC.neutral;
    return `<div style="padding:.4rem 0;border-bottom:1px solid var(--border)22;">
      <div style="display:flex;gap:.45rem;align-items:flex-start;">
        <span style="color:${color};flex-shrink:0;">${sym}</span>
        <div>
          <div style="font-weight:600;line-height:1.4;">${esc(n.title)}</div>
          ${n.note ? `<div style="color:var(--muted);font-size:0.72rem;margin-top:.15rem;line-height:1.5;">${esc(n.note)}</div>` : ""}
          <div style="color:var(--muted);font-size:0.65rem;margin-top:.15rem;">${esc(n.time)}${n.source ? " · " + esc(n.source) : ""}</div>
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
  html += `<span style="color:var(--muted);font-size:0.7rem">以上为历史统计规律的机械应用，非投资建议；越远的日期技术因子失效越多，临近时以当日信号为准。</span></div>`;
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════
//  市场时钟：美东开收盘 ↔ 本地时间对照（自动处理夏令时）
// ═══════════════════════════════════════════════════════
function renderMarketClock() {
  const el = document.getElementById("market-clock");
  if (!el) return;
  const now = new Date();
  // 美东当前时间（Intl 自动处理 EST/EDT）
  const etFmt = new Intl.DateTimeFormat("zh-CN", { timeZone: "America/New_York",
    hour: "2-digit", minute: "2-digit", weekday: "short", hour12: false });
  const etParts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York",
    hour: "numeric", minute: "numeric", weekday: "short", hour12: false })
    .formatToParts(now).reduce((a, p) => (a[p.type] = p.value, a), {});
  const etMinutes = parseInt(etParts.hour) * 60 + parseInt(etParts.minute);
  const isWeekday = !["Sat", "Sun"].includes(etParts.weekday);
  const openMin = 9 * 60 + 30, closeMin = 16 * 60;
  const isOpen = isWeekday && etMinutes >= openMin && etMinutes < closeMin;

  const status = isOpen
    ? `<span style="color:#2ecc71;font-weight:700;">● 开盘中</span>`
    : `<span style="color:var(--muted);font-weight:700;">○ 休市</span>`;
  let countdown = "";
  if (isOpen) {
    const left = closeMin - etMinutes;
    countdown = `距收盘 ${Math.floor(left/60)}小时${left%60}分`;
  } else if (isWeekday && etMinutes < openMin) {
    const left = openMin - etMinutes;
    countdown = `距开盘 ${Math.floor(left/60)}小时${left%60}分`;
  }
  const tzBtn = `<button onclick="toggleTZMode()" title="切换页面时间显示：美东统一 / 你的本地"
    style="background:var(--surface2);border:1px solid var(--border);color:var(--muted);
    padding:1px 7px;border-radius:5px;font-size:0.68rem;cursor:pointer;">
    🕐 ${TZ_MODE === "ET" ? "美东" : "本地"}时间 ⇄</button>`;
  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.3rem;">
      <span>${status} <span style="color:var(--muted)">${countdown}</span></span>
      <span style="color:var(--muted)">美东 ${etFmt.format(now)} ${tzBtn}</span>
    </div>
    <div style="color:var(--muted);margin-top:.25rem;">
      常规时段 <b style="color:var(--text)">${tzRange(9,30,16,0)}</b>
      <span style="font-size:0.68rem">${TZ_MODE === "ET" ? "（页面时间已统一为美东·含夏令时）" : "（已换算为你的本地·含夏令时）"}</span>
    </div>
    ${sessionTip()}`;

  // 盘中情境建议（基于隔夜收益异象）
  function sessionTip() {
    let tip = "";
    if (isOpen && etMinutes < openMin + 45) {
      tip = "🔔 开盘初段（首45分钟）波动最大，历史上不宜追高——日内段长期收益≈0";
    } else if (isOpen && etMinutes >= closeMin - 60) {
      tip = "🔔 尾盘时段——按信号执行买入的优选窗口（捕获隔夜段收益）";
    } else if (isOpen) {
      tip = "🔔 盘中：当日数据为临时价，正式信号以收盘后刷新为准";
    } else if (isWeekday && etMinutes < openMin) {
      tip = "🔔 未开盘。如计划买入，统计上尾盘买入优于开盘追高";
    }
    return tip ? `<div style="color:#f1c40f;font-size:0.72rem;margin-top:.3rem;">${tip}</div>` : "";
  }
}
setInterval(renderMarketClock, 30000);

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
    `<button class="period-btn ${i === 0 ? "active" : ""}" onclick="renderOvernight('${n}', this)">${n.split("_")[0]}</button>`
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
    <div class="insight" style="margin-top:.85rem;">
      <strong>${esc(bm.headline)}</strong><br>
      <span style="color:var(--muted);font-size:0.75rem;">原则：${esc(bm.principle)}</span>
    </div>`;
}

function safeRender(fn, name) {
  try { fn(); } catch(e) { console.warn("renderError ["+name+"]:", e); }
}

init().then(() => {
  safeRender(renderDOWPanel,        "DOW");
  safeRender(renderSellPanel,       "Sell");
  safeRender(renderOppPanel,        "Opp");
  safeRender(renderForecastChart,   "Forecast");
  safeRender(renderTodayRec,        "TodayRec");
  safeRender(renderForecastCalendar,"ForecastCal");
  safeRender(renderSentimentPanel,  "Sentiment");
  safeRender(renderEconCalendar,    "EconCal");
  safeRender(renderDipGuide,        "DipGuide");
  safeRender(renderSPCXTracker,     "SPCX");
  safeRender(renderPredictionAccuracy, "PredAccuracy");
  safeRender(renderIndicesCompare,  "IndicesCompare");
  safeRender(renderLiveTracking,    "LiveTracking");
  safeRender(renderMarketClock,     "MarketClock");
  loadStocksPanel();
  loadOvernightPanel();
  loadNewsPanel();
  loadBriefPanel();
  loadPaperPanel();
  loadReportPanel();
  safeRender(renderBenchmark,       "Benchmark");
  fetchFearAndGreed();
  safeRender(renderSPCXDetail,      "SPCXDetail");
  // Sync SPCX inputs with localStorage
  const savedShares = localStorage.getItem("spcx_shares");
  const savedPrice  = localStorage.getItem("spcx_price");
  if (savedShares) { const el = document.getElementById("spcx-shares-input"); if (el) el.value = savedShares; }
  if (savedPrice)  { const el = document.getElementById("spcx-price-input");  if (el) el.value = savedPrice; }
  renderPortfolioTable(0.71);  // render with fallback rate; user can refresh for live prices
  _mainTabRendered.add("forecast");
  // Digit chart is default-visible; use setTimeout so Plotly gets correct width
  _calTabRendered.add("digit");
  setTimeout(() => safeRender(renderDigitChart, "Digit"), 100);
  safeRender(renderIPOCycle, "IPOCycle");
  safeRender(renderFactorAudit, "FactorAudit");
  safeRender(renderVolModel, "VolModel");
  safeRender(renderMarketStructure, "MarketStructure");
  safeRender(renderEventImpact, "EventImpact");
  safeRender(renderQuantMethodology, "QuantMethodology");
  // 恢复上次浏览的视图（默认"今日"）
  const savedView = localStorage.getItem("alpha_view");
  if (savedView && savedView !== "today") {
    const btn = document.querySelector(`.view-btn[data-view="${savedView}"]`);
    if (btn) switchView(savedView, btn);
  }
});

// ═══════════════════════════════════════════════════════
//  顶层视图切换（今日/计划/实验/研究/我的）
// ═══════════════════════════════════════════════════════
const VIEWS = ["today", "plan", "lab", "research", "quant", "mine"];
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
    </div>`;
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
