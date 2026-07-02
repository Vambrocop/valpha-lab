// ═══════════════════════════════════════════════════════
//  全局状态
// ═══════════════════════════════════════════════════════
let SIGNALS = null;
let PRICES  = null;
let MV      = null;  // multivariate analysis results
let selectedDate = null;

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

  renderEventRefToday();   // ⑦ 真事件研究参考（替代原 buildEventGrid 主观勾选玩具）
  renderTierLegend();
  initDatePicker();
  // 研究视图的图表全部懒渲染（lazyRender 定义在 app-5.js；init 由 app-5 调用，此时已就绪）
  lazyRender("chart-price", renderPriceChart, "PriceChart");
  lazyRender("chart-signal-history", renderSignalHistory, "SignalHistory");

  if (MV) {
    // 默认标签页懒渲染；其余 MV 标签页首次点击时再渲染
    lazyRender("chart-modelcmp", renderModelComparison, "ModelCmp");
  }

  // loadLongHistory 渲染 3 张图：任意一张接近视口即触发（观察器按批去重，只跑一次）
  ["chart-longmonthly", "chart-holiday", "chart-bearmarkets"]
    .forEach(id => lazyRender(id, loadLongHistory, "LongHistory"));
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
    const prob = forecast.prob;
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

  const prob = rec.prob;
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
  const evText = "";   // 事件叠加玩具已移除(原 activeEvents);保留空串兼容下方模板
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


// ⑦ 事件影响参考：今日页用真 event_study 数据(历史同类事件30日反应)替代主观 what-if 勾选玩具
function renderEventRefToday() {
  const el = document.getElementById("event-ref-today");
  if (!el || !SIGNALS) return;
  const es = SIGNALS.event_study || {};
  const rows = Object.entries(es).map(([k, v]) => {
    const smallN = (v.n || 0) < 15;
    return `<tr style="border-top:1px solid var(--border-faint)">
      <td style="padding:.25rem .4rem">${v.label || k}</td>
      <td style="padding:.25rem .4rem;text-align:center;color:${smallN ? "#e67e22" : "var(--muted)"}">n=${v.n}${smallN ? " ⚠" : ""}</td>
      <td style="padding:.25rem .4rem;text-align:right">${v.avg_return > 0 ? "+" : ""}${v.avg_return}%</td>
      <td style="padding:.25rem .4rem;text-align:right;color:var(--muted)">${v.win_rate}% <span style="font-size:0.66rem">(基准${v.base_win_rate}%)</span></td>
    </tr>`;
  }).join("") || `<tr><td colspan="4" style="padding:.4rem;color:var(--muted)">暂无事件研究数据</td></tr>`;
  el.innerHTML = `
    <div style="color:var(--muted);font-size:0.76rem;line-height:1.55;margin-bottom:.5rem">历史同类事件后 <b>30 日</b>的平均反应（样本内统计）。<b>事件影响的是波动/不确定性，不是可交易方向</b>——小样本(n⚠)更别当预测；调度型事件(FOMC/CPI/非农)当天放大波动、方向无稳定偏向。</div>
    <table style="width:100%;border-collapse:collapse;font-size:0.78rem">
      <tr class="u-cap"><td style="padding:.2rem .4rem">事件类型</td><td style="padding:.2rem .4rem;text-align:center">样本</td><td style="padding:.2rem .4rem;text-align:right">30日均涨跌</td><td style="padding:.2rem .4rem;text-align:right">胜率 vs 基准</td></tr>
      ${rows}
    </table>
    <div style="font-size:0.7rem;color:var(--muted);margin-top:.4rem">→ 纳入方式：这些情形下<b>降杠杆 / 不重仓新开</b>，等不确定性消化，而非猜方向。反事实因果(SVB→KRE)见"📋 登记簿"。</div>`;
}

// ═══════════════════════════════════════════════════════
//  图表
// ═══════════════════════════════════════════════════════
// DARK 必须每次返回全新对象：Plotly.newPlot 会把推断结果（type:"date"/range 等）
// 回写进传入的 layout——共享同一个对象会被首张日期轴图污染，后续数字轴图全坏
// （症状：x 轴显示 Jan 1970 时间戳、translate(NaN,...) 报错）。getter 让全部
// `...DARK` / `...DARK.xaxis` 调用零改动地各拿一份副本。
function _darkLayout() {
  return { paper_bgcolor:"transparent", plot_bgcolor:"transparent",
    font:{color:"#e6edf3",size:11}, xaxis:{gridcolor:"#30363d",zerolinecolor:"#30363d"},
    yaxis:{gridcolor:"#30363d",zerolinecolor:"#30363d"}, margin:{t:30,b:40,l:50,r:20},
    hoverlabel:{bgcolor:"#161b22", bordercolor:"#30363d", font:{color:"#e6edf3", size:12}} };
}
Object.defineProperty(globalThis, "DARK", { get: _darkLayout });

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
  bgcolor: "rgba(255,255,255,0.10)", activecolor: "#3498db",
  bordercolor: "rgba(255,255,255,0.18)", borderwidth: 1,
  font: { color: "#e6edf3", size: 11 }, y: 1.18,
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
  // "今天"按美东交易日算：阿德莱德等东半球访客的本地日期常比美东快一天，直接用 getDay() 会标错
  const etWd = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short" }).format(new Date());
  const todayDow = ["Mon","Tue","Wed","Thu","Fri"].indexOf(etWd);  // 0=Mon；周末=-1（不标）
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
    `<strong>周内规律：</strong>历史上<strong style="color:#27ae60">${NAMES[best.dow]}（${best.win_rate}%）</strong>历史胜率最高，
     <strong style="color:#e74c3c">${NAMES[worst.dow]}（${worst.win_rate}%）</strong>最弱。
     <br><span style="color:var(--muted);font-size:0.79rem">⚠ 周内效应在现代段（2000后）已被套利趋弱（见🪦坟场），此为历史描述、非操作建议。</span>`;
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

  const advice = score >= 70 ? "⚠️ 卖出评分处于历史高位区（多重风险信号叠加）" :
                 score >= 55 ? "风险评分偏高" :
                 score >= 40 ? "信号混合" :
                 "评分平静";
  document.getElementById("sell-insight").innerHTML =
    `<strong>当前风险状态：</strong>${advice}`;
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

