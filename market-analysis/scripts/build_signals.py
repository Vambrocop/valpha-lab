"""
build_signals.py
预计算每一天的入场信号，输出 JSON 供前端使用。
信号 = 综合贝叶斯概率（季节性 + 技术 + 宏观 + 事件调整）
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"

# ── 月度先验概率（贝叶斯先验，来自历史统计） ─────────────────────
MONTHLY_PRIOR = {
    1: 0.62, 2: 0.54, 3: 0.62, 4: 0.80,
    5: 0.58, 6: 0.40, 7: 0.80, 8: 0.54,
    9: 0.45, 10: 0.62, 11: 0.80, 12: 0.74,
}

# 事件调整因子（乘法，贝叶斯似然比）
EVENT_ADJUSTMENTS = {
    "war":        0.72,   # 战争爆发，概率乘0.72
    "pandemic":   0.65,   # 疫情/封锁
    "trade_war":  0.78,   # 贸易战升级
    "fed_hike":   0.80,   # 意外加息
    "fed_cut":    1.20,   # 降息
    "election":   0.90,   # 选举不确定
    "halving":    1.15,   # BTC减半（正面情绪溢出）
    "gold_spike": 0.82,   # 黄金暴涨（避险情绪）
    "oil_spike":  0.78,   # 油价暴涨（滞胀担忧）
    "vix_spike":  0.70,   # VIX恐慌指数飙升
    "none":       1.00,   # 无特殊事件
    "ai_boom":    1.18,   # AI重大利好
    "ipo_boom":   1.08,   # 大型科技IPO
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

    for date in idx:
        if date not in tech.index:
            continue
        row = tech.loc[date]
        if row.isnull().all():
            continue

        month = date.month
        prior = MONTHLY_PRIOR[month]

        # 技术似然比
        likelihoods = []

        # NASDAQ在200日均线上方 → 牛市结构
        if not pd.isna(row.get("NASDAQ_above_ma200")):
            likelihoods.append(1.15 if row["NASDAQ_above_ma200"] else 0.85)

        # BTC动量（领先8天效应）
        if not pd.isna(row.get("BTC_mom20")):
            m = row["BTC_mom20"]
            likelihoods.append(1.12 if m > 0.05 else (0.90 if m < -0.05 else 1.0))

        # 美元趋势（负相关）
        if not pd.isna(row.get("dxy_trend")):
            d = row["dxy_trend"]
            likelihoods.append(0.88 if d > 0.01 else (1.12 if d < -0.01 else 1.0))

        # NASDAQ波动率（低波动 = 好信号）
        if not pd.isna(row.get("NASDAQ_vol20")):
            v = row["NASDAQ_vol20"]
            likelihoods.append(0.85 if v > 0.25 else (1.10 if v < 0.15 else 1.0))

        # NASDAQ RSI（超买/超卖）
        if not pd.isna(row.get("NASDAQ_rsi")):
            rsi = row["NASDAQ_rsi"]
            likelihoods.append(0.85 if rsi > 75 else (1.10 if rsi < 35 else 1.0))

        prob = bayesian_update(prior, likelihoods)

        records[date.strftime("%Y-%m-%d")] = {
            "prob":        round(prob, 4),
            "tier":        _tier(prob),
            "month":       month,
            "prior":       round(prior, 4),
            "nasdaq_ma200": int(row.get("NASDAQ_above_ma200", 0)),
            "btc_mom20":   round(float(row.get("BTC_mom20", 0) or 0), 4),
            "dxy_trend":   round(float(row.get("dxy_trend", 0) or 0), 4),
            "nasdaq_vol":  round(float(row.get("NASDAQ_vol20", 0) or 0), 4),
            "nasdaq_rsi":  round(float(row.get("NASDAQ_rsi", 0) or 0), 1),
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

    print(f"✓ 信号已写入 {out}  ({len(signals)} 天)")
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


if __name__ == "__main__":
    result = build()

    # 合并时机摘要
    timing = build_timing_summary()
    result.update(timing)

    out = WEB_DIR / "signals.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("✓ signals.json 已更新（含买卖时机）")
