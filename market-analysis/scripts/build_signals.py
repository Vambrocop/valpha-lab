"""
build_signals.py
预计算每一天的入场信号，输出 JSON 供前端使用。
信号 = 综合贝叶斯概率（季节性 + 星期 + 月内 + 假日 + 技术 + 事件调整）
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import date, timedelta

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"

# ── 月度先验概率（1928-2026 真实统计，后面会从 long_history.json 覆盖）
MONTHLY_PRIOR = {
    1: 0.62, 2: 0.54, 3: 0.62, 4: 0.68,
    5: 0.58, 6: 0.55, 7: 0.60, 8: 0.57,
    9: 0.45, 10: 0.60, 11: 0.65, 12: 0.64,
}

# ── 从 long_history.json 加载更精确的月度先验（1928+）─────────────
def _load_long_priors():
    try:
        with open(PROC_DIR / "long_history.json", encoding="utf-8") as f:
            lh = json.load(f)
        rows = lh.get("monthly_by_period", {}).get("1928+", [])
        return {r["month"]: round(r["win_rate"] / 100, 4) for r in rows}
    except Exception:
        return {}

_long_priors = _load_long_priors()
if _long_priors:
    MONTHLY_PRIOR.update(_long_priors)
    print(f"  使用 long_history 月度先验（1928+年历史数据）")

# ── 星期效应似然比（日频，1928-2026 真实统计）────────────────────
# 以普通日基准 52.4% 为 1.0，各星期相对调整
DOW_LR = {
    0: 0.940,  # 周一：49.3% — 最弱
    1: 0.981,  # 周二：51.4%
    2: 1.038,  # 周三：54.4% — 最强
    3: 1.004,  # 周四：52.6%
    4: 1.038,  # 周五：54.4%
}

# ── 月内第几周效应（Week-of-Month）─────────────────────────────
# 基准53.2%。第1周最强（59.1%），第4周最弱（50.5%）
def _week_of_month(ts):
    first_dow = ts.replace(day=1).weekday()
    return (ts.day + first_dow - 1) // 7 + 1

_WOM_LR = {1: 1.112, 2: 0.996, 3: 1.015, 4: 0.950, 5: 0.992}

# ── 日历异常综合似然比（税季 + 季末 + 税损）────────────────────
# 来源：S&P 500 日频 1950-2026，n≈19,000
def _calendar_anomaly_lr(ts):
    m, d = ts.month, ts.day

    # ─ 报税季（4月细分）─────────────────────────────────────────
    if m == 4:
        if d == 15:          return 1.242   # 截止日当天：66%，最强单日
        if d <= 14:          return 1.068   # 4月1-14：平均56-57%（纳税前准备期，不跌）
        # 4月16日后恢复正常
        return 1.0

    # ─ 12月税损收割 ──────────────────────────────────────────────
    if m == 12:
        if 11 <= d <= 15:    return 0.889   # 税损收割最密集：47.2%
        if 21 <= d <= 25:    return 1.147   # 圣诞前：61%
        return 1.0

    # ─ 季初建仓（1/4/7/10月前5日）─────────────────────────────
    if m in (1, 4, 7, 10) and d <= 5:
        return 1.117   # 59.4%，机构新季度建仓

    return 1.0

# ── 假日日历（美国股市） ──────────────────────────────────────────
def _easter(year):
    a = year % 19; b = year // 100; c = year % 100
    d = b // 4; e = b % 4; f = (b + 8) // 25
    g = (b - f + 1) // 3; h = (19*a + b - d - g + 15) % 30
    i = c // 4; k = c % 4; l = (32 + 2*e + 2*i - h - k) % 7
    m = (a + 11*h + 22*l) // 451
    month = (h + l - 7*m + 114) // 31
    day = ((h + l - 7*m + 114) % 31) + 1
    return date(year, month, day)

def _nth_weekday(year, month, weekday, n):
    d = date(year, month, 1); count = 0
    while True:
        if d.weekday() == weekday:
            count += 1
            if count == n: return d
        d += timedelta(days=1)

def _last_weekday(year, month, weekday):
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d

def _adjust_weekend(d):
    if d.weekday() == 5: return d - timedelta(days=1)
    if d.weekday() == 6: return d + timedelta(days=1)
    return d

def _us_holidays(year):
    easter = _easter(year)
    return {
        _adjust_weekend(date(year, 1, 1)),       # New Year
        _nth_weekday(year, 1, 0, 3),             # MLK Day
        _nth_weekday(year, 2, 0, 3),             # Presidents Day
        easter - timedelta(days=2),               # Good Friday
        _last_weekday(year, 5, 0),               # Memorial Day
        _adjust_weekend(date(year, 7, 4)),        # Independence Day
        _nth_weekday(year, 9, 0, 1),             # Labor Day
        _nth_weekday(year, 11, 3, 4),            # Thanksgiving
        _adjust_weekend(date(year, 12, 25)),      # Christmas
    }

# 预生成1990-2030年假日集合
_HOLIDAY_SET = set()
_THANKSGIVING_DATES = set()
for _yr in range(1990, 2031):
    try:
        _HOLIDAY_SET |= _us_holidays(_yr)
        _THANKSGIVING_DATES.add(_nth_weekday(_yr, 11, 3, 4))
    except Exception:
        pass

def _holiday_lr(ts):
    """返回该交易日的假日效应似然比"""
    d = ts.date()

    # 感恩节前夕（周三）：76.3%  → LR=1.457
    if d in {tg - timedelta(days=1) for tg in _THANKSGIVING_DATES}:
        return 1.457

    # 感恩节后的黑色星期五：71.1% → LR=1.357
    if d in {tg + timedelta(days=1) for tg in _THANKSGIVING_DATES}:
        return 1.357

    # 圣诞行情窗口 Dec 26 – Jan 3
    if (d.month == 12 and d.day >= 26) or (d.month == 1 and d.day <= 3):
        return 1.105   # 57.9% vs 52.4%

    # 节前（前3天内有假日）：59.0% → LR=1.126
    for offset in range(1, 4):
        if (d + timedelta(days=offset)) in _HOLIDAY_SET:
            return 1.126

    # 节后（后3天内有假日）：58.2% → LR=1.111
    for offset in range(1, 4):
        if (d - timedelta(days=offset)) in _HOLIDAY_SET:
            return 1.111

    return 1.0  # 普通日

# 事件调整因子（乘法，贝叶斯似然比）
# ── 标注[实证]的来自 event_study.py（1928-2026历史事件研究），其余为主观估计
def _load_event_lr():
    try:
        with open(PROC_DIR / "event_study_results.json", encoding="utf-8") as f:
            es = json.load(f)
        return es.get("data_driven_lr", {})
    except Exception:
        return {}

_event_lr = _load_event_lr()

EVENT_ADJUSTMENTS = {
    # ── 实证估计（Event Study 数据驱动）────────────────────────────
    "war":          _event_lr.get("war",         1.001),  # [实证] 地缘冲击30日后=LR1.001（市场30日内反弹）
    "pandemic":     _event_lr.get("pandemic",    0.985),  # [实证] 疫情封锁30日=LR0.985（轻微负面）
    "trade_war":    _event_lr.get("trade_war",   1.089),  # [实证] 贸易战升级后市场30日=LR1.089（阶段性反弹）
    "trade_relief": _event_lr.get("trade_relief",1.080),  # [实证] 贸易协议缓和=LR1.080
    "fed_hike":     _event_lr.get("fed_hike",    0.915),  # [实证] 首次加息30日=LR0.915（显著负面 p=0.021）
    "fed_cut":      _event_lr.get("fed_cut",     0.978),  # [实证] 首次降息30日=LR0.978（反直觉：靴子落地卖）
    "vix_spike":    _event_lr.get("vix_spike",   0.978),  # [实证] VIX暴涨后30日=LR0.978
    "banking":      _event_lr.get("banking",     0.889),  # [实证] 银行危机30日=LR0.889
    "ai_boom":      _event_lr.get("ai_boom",     1.001),  # [实证] AI突破30日=LR1.001（短期中性）
    # ── 主观估计（尚无足够历史样本）────────────────────────────────
    "election":     0.92,   # 大选不确定期（主观，基于历史不确定性折扣）
    "halving":      1.15,   # BTC减半（正面情绪溢出，主观）
    "gold_spike":   0.88,   # 黄金暴涨（避险情绪，主观）
    "oil_spike":    0.85,   # 油价暴涨（滞胀担忧，主观）
    "none":         1.00,   # 无特殊事件
    "ipo_boom":     1.08,   # 大型科技IPO（主观）
}

# ── 技术信号计算 ──────────────────────────────────────────────────
def compute_technical_signals(prices, ret):
    df = pd.DataFrame(index=prices.index)

    for asset in ["NASDAQ", "BTC", "DXY"]:
        r = ret[asset]
        p = prices[asset]
        df[f"{asset}_above_ma50"]  = (p > p.rolling(50).mean()).astype(float)
        df[f"{asset}_above_ma200"] = (p > p.rolling(200).mean()).astype(float)
        df[f"{asset}_rsi"]         = _rsi(r, 14)
        df[f"{asset}_mom20"]       = p.pct_change(20)
        df[f"{asset}_vol20"]       = r.rolling(20).std() * np.sqrt(252)

    df["btc_nasdaq_corr"] = ret["BTC"].rolling(60).corr(ret["NASDAQ"])
    df["dxy_trend"]       = prices["DXY"].pct_change(20)  # 美元趋势（负=利好）
    return df

def _rsi(returns, period=14):
    gain = returns.clip(lower=0).rolling(period).mean()
    loss = (-returns.clip(upper=0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / (loss + 1e-10))

# ── 贝叶斯概率融合 ────────────────────────────────────────────────
def bayesian_update(prior, likelihoods):
    """
    简化贝叶斯更新：
    posterior ∝ prior × ∏ likelihood_i
    最后 sigmoid 压缩到 (0,1)
    """
    log_odds = np.log(prior / (1 - prior + 1e-10))
    for lr in likelihoods:
        log_odds += np.log(max(lr, 0.01))
    prob = 1 / (1 + np.exp(-log_odds))
    return float(np.clip(prob, 0.02, 0.98))

# ── 计算每日信号 ──────────────────────────────────────────────────
def compute_daily_signals(prices, ret, tech):
    records = {}
    idx = prices.dropna(how="all").index

    for ts in idx:
        if ts not in tech.index:
            continue
        row = tech.loc[ts]
        if row.isnull().all():
            continue

        month = ts.month
        prior = MONTHLY_PRIOR[month]

        # ── 似然比列表（贝叶斯连乘）────────────────────────────────
        likelihoods = []

        # 1. 星期效应（日频，1928年统计）
        likelihoods.append(DOW_LR.get(ts.weekday(), 1.0))

        # 2. 月内第几周效应（Week-of-Month，1950+统计）
        likelihoods.append(_WOM_LR.get(_week_of_month(ts), 1.0))

        # 3. 日历异常（税季/税损/季初建仓）
        likelihoods.append(_calendar_anomaly_lr(ts))

        # 4. 假日效应
        likelihoods.append(_holiday_lr(ts))

        # 4. NASDAQ在200日均线上方
        if not pd.isna(row.get("NASDAQ_above_ma200")):
            likelihoods.append(1.15 if row["NASDAQ_above_ma200"] else 0.85)

        # 5. BTC动量（领先8天效应）
        if not pd.isna(row.get("BTC_mom20")):
            m = row["BTC_mom20"]
            likelihoods.append(1.12 if m > 0.05 else (0.90 if m < -0.05 else 1.0))

        # 6. 美元趋势（负相关）
        if not pd.isna(row.get("dxy_trend")):
            d = row["dxy_trend"]
            likelihoods.append(0.88 if d > 0.01 else (1.12 if d < -0.01 else 1.0))

        # 7. NASDAQ波动率
        if not pd.isna(row.get("NASDAQ_vol20")):
            v = row["NASDAQ_vol20"]
            likelihoods.append(0.85 if v > 0.25 else (1.10 if v < 0.15 else 1.0))

        # 8. NASDAQ RSI
        if not pd.isna(row.get("NASDAQ_rsi")):
            rsi = row["NASDAQ_rsi"]
            likelihoods.append(0.85 if rsi > 75 else (1.10 if rsi < 35 else 1.0))

        prob = bayesian_update(prior, likelihoods)

        records[ts.strftime("%Y-%m-%d")] = {
            "prob":         round(prob, 4),
            "tier":         _tier(prob),
            "month":        month,
            "dow":          int(ts.weekday()),
            "dom":          int(ts.day),
            "wom":          int(_week_of_month(ts)),
            "prior":        round(prior, 4),
            "holiday_lr":   round(_holiday_lr(ts), 4),
            "cal_lr":       round(_calendar_anomaly_lr(ts), 4),
            "nasdaq_ma200": int(row.get("NASDAQ_above_ma200", 0)),
            "btc_mom20":    round(float(row.get("BTC_mom20", 0) or 0), 4),
            "dxy_trend":    round(float(row.get("dxy_trend", 0) or 0), 4),
            "nasdaq_vol":   round(float(row.get("NASDAQ_vol20", 0) or 0), 4),
            "nasdaq_rsi":   round(float(row.get("NASDAQ_rsi", 0) or 0), 1),
        }

    return records

def _tier(prob):
    if prob >= 0.80: return 5
    if prob >= 0.60: return 4
    if prob >= 0.40: return 3
    if prob >= 0.20: return 2
    return 1

# ── 当前信号（带事件调整） ────────────────────────────────────────
def compute_current_signal(base_prob, event_keys):
    likelihoods = [EVENT_ADJUSTMENTS.get(k, 1.0) for k in event_keys]
    return bayesian_update(base_prob, likelihoods)

# ── 主流程 ────────────────────────────────────────────────────────
def build():
    print("加载数据...")
    prices = pd.read_csv(RAW_DIR / "combined_prices.csv",
                         index_col="Date", parse_dates=True).ffill()
    ret = np.log(prices / prices.shift(1)).dropna()
    tech = compute_technical_signals(prices, ret)

    print("计算每日信号...")
    signals = compute_daily_signals(prices, ret, tech)

    # 当前基准概率（最新一天）
    latest = list(signals.values())[-1]
    base_prob = latest["prob"]

    # 输出事件调整表
    event_table = {k: round(compute_current_signal(base_prob, [k]), 4)
                   for k in EVENT_ADJUSTMENTS}

    output = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "latest_prob": round(base_prob, 4),
        "latest_tier": _tier(base_prob),
        "event_adjustments": EVENT_ADJUSTMENTS,
        "event_probs": event_table,
        "daily_signals": signals,
    }

    out = WEB_DIR / "signals.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[OK] 信号已写入 {out}  ({len(signals)} 天)")
    print(f"  当前基准概率: {base_prob*100:.1f}%  第{_tier(base_prob)}档")
    return output

def build_timing_summary():
    """把 timing_analysis 结果汇总为前端用的 JSON 片段"""
    summary = {}

    # DOW 胜率
    try:
        dow = pd.read_csv(PROC_DIR / "dow_stats.csv")
        ndx = dow[dow["asset"] == "NASDAQ"][["dow","day_name","win_rate","avg_return"]].copy()
        ndx["win_rate"] = (ndx["win_rate"] * 100).round(1)
        ndx["avg_return"] = (ndx["avg_return"] * 100).round(3)
        summary["dow"] = ndx.to_dict(orient="records")
    except Exception: pass

    # 卖出信号（最近一行）
    try:
        sell = pd.read_csv(PROC_DIR / "sell_signals.csv")
        last = sell.dropna().iloc[-1]
        summary["sell"] = {
            "date":       last["date"],
            "score":      float(last["sell_score"]),
            "tier":       last["sell_tier"],
            "rsi":        float(last["rsi"]) if not pd.isna(last["rsi"]) else None,
            "mom20":      float(last["mom20"]),
            "ma_cross":   int(last["ma_cross"]),
            "vol_pct":    float(last["vol_pct"]) if not pd.isna(last["vol_pct"]) else None,
        }
    except Exception: pass

    # 月内效应
    try:
        dom = pd.read_csv(PROC_DIR / "dom_stats.csv")
        ndx = dom[dom["asset"] == "NASDAQ"][["dom","win_rate","avg_return"]].copy()
        ndx["win_rate"] = (ndx["win_rate"] * 100).round(1)
        summary["dom"] = ndx.to_dict(orient="records")
    except Exception: pass

    return summary


DOW_CN = {0:"周一", 1:"周二", 2:"周三", 3:"周四", 4:"周五"}

def find_next_opportunities(signals, n_days=45):
    """
    扫描未来 n_days 个自然日中的所有交易日，计算每天的贝叶斯概率。
    日历因子（星期/月/假日/税季）完全可预测；
    技术因子（MA/BTC/DXY/RSI）用最新一天值冻结（30天内通常不会突变）。

    Returns:
        dict with top_entry (top 5 buy days), top_exit (5 weakest days),
        and all_forecast (full list sorted by date).
    """
    today = date.today()

    # 从最新信号提取技术因子LR（冻结）
    latest = list(signals.values())[-1]
    tech_lrs = []

    nasdaq_ma200 = latest.get("nasdaq_ma200", 1)
    tech_lrs.append(1.15 if nasdaq_ma200 == 1 else 0.85)

    btc_mom = latest.get("btc_mom20", 0) or 0
    tech_lrs.append(1.12 if btc_mom > 0.05 else (0.90 if btc_mom < -0.05 else 1.0))

    dxy = latest.get("dxy_trend", 0) or 0
    tech_lrs.append(0.88 if dxy > 0.01 else (1.12 if dxy < -0.01 else 1.0))

    nasdaq_vol = latest.get("nasdaq_vol", 0.20) or 0.20
    tech_lrs.append(0.85 if nasdaq_vol > 0.25 else (1.10 if nasdaq_vol < 0.15 else 1.0))

    nasdaq_rsi = latest.get("nasdaq_rsi", 50) or 50
    tech_lrs.append(0.85 if nasdaq_rsi > 75 else (1.10 if nasdaq_rsi < 35 else 1.0))

    forecast = []
    d = today + timedelta(days=1)
    trading_days_found = 0

    while trading_days_found < n_days:
        # 跳过周末
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        # 跳过假日
        if d in _HOLIDAY_SET:
            d += timedelta(days=1)
            continue

        ts = pd.Timestamp(d)
        month = ts.month
        prior = MONTHLY_PRIOR[month]

        cal_lrs = [
            DOW_LR.get(ts.weekday(), 1.0),
            _WOM_LR.get(_week_of_month(ts), 1.0),
            _calendar_anomaly_lr(ts),
            _holiday_lr(ts),
        ] + tech_lrs

        prob = bayesian_update(prior, cal_lrs)

        # 主因子说明（用于前端tooltip）
        reasons = []
        dow_lr = DOW_LR.get(ts.weekday(), 1.0)
        if dow_lr > 1.02: reasons.append(f"{DOW_CN[ts.weekday()]}效应")
        wom_lr = _WOM_LR.get(_week_of_month(ts), 1.0)
        if wom_lr > 1.05: reasons.append(f"月内第{_week_of_month(ts)}周最强")
        if wom_lr < 0.97: reasons.append(f"月内第{_week_of_month(ts)}周偏弱")
        hol_lr = _holiday_lr(ts)
        if hol_lr > 1.10: reasons.append("假日效应")
        cal_lr = _calendar_anomaly_lr(ts)
        if cal_lr > 1.10: reasons.append("税季/季初建仓")
        if cal_lr < 0.95: reasons.append("税损收割期")
        month_prior = MONTHLY_PRIOR[month]
        if month_prior >= 0.62: reasons.append(f"{month}月胜率高")
        if month_prior <= 0.50: reasons.append(f"{month}月胜率低")

        forecast.append({
            "date":      d.strftime("%Y-%m-%d"),
            "dow_cn":    DOW_CN.get(ts.weekday(), ""),
            "month":     month,
            "wom":       int(_week_of_month(ts)),
            "prob":      round(prob, 4),
            "tier":      _tier(prob),
            "prior":     round(prior, 4),
            "dow_lr":    round(dow_lr, 4),
            "wom_lr":    round(wom_lr, 4),
            "hol_lr":    round(hol_lr, 4),
            "cal_lr":    round(cal_lr, 4),
            "reasons":   reasons,
        })

        d += timedelta(days=1)
        trading_days_found += 1

    # 按概率排序
    sorted_asc  = sorted(forecast, key=lambda x: x["prob"])
    sorted_desc = sorted(forecast, key=lambda x: -x["prob"])

    return {
        "top_entry": sorted_desc[:5],   # 最佳买入：概率最高的5天
        "top_exit":  sorted_asc[:5],    # 最弱/减仓：概率最低的5天
        "all_forecast": forecast,        # 按日期顺序，供日历视图
        "tech_frozen_note": "技术信号使用当前最新值（MA/BTC/DXY/RSI），日历因子基于统计规律精确预测",
        "latest_tech": {
            "nasdaq_ma200": int(nasdaq_ma200),
            "btc_mom20":    round(btc_mom, 4),
            "dxy_trend":    round(dxy, 4),
            "nasdaq_vol":   round(nasdaq_vol, 4),
            "nasdaq_rsi":   round(nasdaq_rsi, 1),
        }
    }


def load_event_study():
    """将 event_study_results.json 中的核心数据嵌入 signals.json"""
    try:
        with open(PROC_DIR / "event_study_results.json", encoding="utf-8") as f:
            es = json.load(f)
        studies = es.get("event_studies", {})
        # 只保留前端需要的字段，去掉 returns 列表（太大）
        out = {}
        labels = {
            "fed_hike_first":      "首次加息",
            "fed_cut_first":       "首次降息",
            "trade_war_escalation":"贸易战升级",
            "trade_war_relief":    "贸易战缓和",
            "geopolitical_shock":  "地缘冲击",
            "pandemic_lockdown":   "疫情封锁",
            "vix_spike_extreme":   "VIX恐慌飙升",
            "banking_crisis":      "银行危机",
            "ai_breakthrough":     "AI突破",
        }
        for k, v in studies.items():
            out[k] = {
                "label":       labels.get(k, k),
                "n":           v["n"],
                "avg_return":  v["avg_return_pct"],
                "median_return": v["median_return_pct"],
                "win_rate":    v["win_rate"],
                "base_win_rate": v["base_win_rate"],
                "lr":          v["lr"],
                "p_value":     v["p_value"],
                "significant": v["significant"],
                "base_avg":    v["base_avg_pct"],
            }
        return out
    except Exception:
        return {}


def load_year_patterns():
    """从 long_history.json 读取年份规律统计（尾数/任期年/执政党）"""
    try:
        with open(PROC_DIR / "long_history.json", encoding="utf-8") as f:
            lh = json.load(f)
        return lh.get("year_patterns", {})
    except Exception:
        return {}

def load_holiday_effects():
    """从 long_history.json 读取假日效应统计"""
    try:
        with open(PROC_DIR / "long_history.json", encoding="utf-8") as f:
            lh = json.load(f)
        he = lh.get("holiday_effects", {})
        # 精简：只保留前端需要的字段
        keep = ["pre_holiday","post_holiday","normal","santa_claus_rally",
                "january_effect","thanksgiving_eve","thanksgiving_friday","dom","dow_daily"]
        return {k: he[k] for k in keep if k in he}
    except Exception:
        return {}


if __name__ == "__main__":
    result = build()

    # 合并时机摘要
    timing = build_timing_summary()
    result.update(timing)

    # 嵌入事件研究结果
    result["event_study"] = load_event_study()

    # 未来最佳入场/离场窗口
    result["next_opportunities"] = find_next_opportunities(result["daily_signals"], n_days=45)

    # 年份规律统计
    result["year_patterns"] = load_year_patterns()

    # 假日效应详细统计
    result["holiday_detail"] = load_holiday_effects()

    out = WEB_DIR / "signals.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("[OK] signals.json 已更新（含买卖时机）")
