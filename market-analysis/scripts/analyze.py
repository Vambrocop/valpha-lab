"""
analyze.py
统计分析：相关性 / 滚动相关 / 月度规律 / 政治周期 / 波动率
输出：processed/ 目录下的CSV文件
"""

import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
PROC_DIR.mkdir(exist_ok=True)

ASSETS = ["NASDAQ", "DXY", "BTC", "ETH"]

def load():
    df = pd.read_csv(RAW_DIR / "combined_prices.csv", index_col="Date", parse_dates=True)
    return df[ASSETS].dropna(how="all")

def pct_returns(df):
    return df.pct_change().dropna()

# ── 1. 全期相关性矩阵 ─────────────────────────────────────────────
def full_correlation(ret):
    corr = ret.corr(method="pearson")
    corr.to_csv(PROC_DIR / "correlation_full.csv")
    print("✓ 全期相关性矩阵")
    return corr

# ── 2. 滚动90天相关性（NASDAQ vs 其他） ──────────────────────────
def rolling_correlation(ret, window=90):
    result = pd.DataFrame(index=ret.index)
    base = "NASDAQ"
    for col in [c for c in ASSETS if c != base]:
        result[f"NASDAQ_vs_{col}"] = ret[base].rolling(window).corr(ret[col])
    result.to_csv(PROC_DIR / "rolling_correlation_90d.csv")
    print("✓ 滚动90天相关性")
    return result

# ── 3. 月度收益统计 ───────────────────────────────────────────────
def monthly_stats(ret):
    monthly = (1 + ret).resample("ME").prod() - 1
    rows = []
    for asset in ASSETS:
        s = monthly[asset].dropna()
        for m in range(1, 13):
            vals = s[s.index.month == m]
            rows.append({
                "asset":      asset,
                "month":      m,
                "avg_return": vals.mean(),
                "win_rate":   (vals > 0).mean(),
                "median":     vals.median(),
                "std":        vals.std(),
                "count":      len(vals),
            })
    df = pd.DataFrame(rows)
    df.to_csv(PROC_DIR / "monthly_stats.csv", index=False)
    print("✓ 月度统计")
    return df

# ── 4. 年度收益（按资产） ─────────────────────────────────────────
def annual_returns(prices):
    annual = prices.resample("YE").last().pct_change().dropna()
    annual.index = annual.index.year
    annual.index.name = "year"
    annual.to_csv(PROC_DIR / "annual_returns.csv")
    print("✓ 年度收益")
    return annual

# ── 5. 政治周期分析（总统任期年） ────────────────────────────────
def presidential_cycle(annual):
    # 2017=Year1, 2018=Y2, 2019=Y3, 2020=Y4, 2021=Y1...
    def cycle_year(y):
        return ((y - 2017) % 4) + 1

    result = annual.copy()
    result["cycle_year"] = result.index.map(cycle_year)
    avg = result.groupby("cycle_year")[ASSETS].mean()
    avg.to_csv(PROC_DIR / "presidential_cycle.csv")
    print("✓ 总统任期周期")
    return avg

# ── 6. 波动率制度分析（低/中/高波动） ────────────────────────────
def volatility_regimes(ret):
    vol = ret["NASDAQ"].rolling(30).std() * np.sqrt(252)
    q33, q67 = vol.quantile(0.33), vol.quantile(0.67)
    def regime(v):
        if pd.isna(v): return None
        if v < q33: return "低波动"
        if v < q67: return "中波动"
        return "高波动"
    labels = vol.map(regime)
    merged = ret.copy()
    merged["regime"] = labels
    avg_by_regime = merged.groupby("regime")[ASSETS].mean() * 252
    avg_by_regime.to_csv(PROC_DIR / "volatility_regimes.csv")
    print("✓ 波动率制度")
    return avg_by_regime

# ── 7. BTC减半前后分析 ────────────────────────────────────────────
def halving_analysis(prices):
    halvings = ["2016-07-09", "2020-05-11", "2024-04-20"]
    rows = []
    for h in halvings:
        h_date = pd.Timestamp(h)
        for days in [30, 90, 180, 365]:
            pre  = prices.loc[h_date - pd.Timedelta(days=days):h_date]
            post = prices.loc[h_date:h_date + pd.Timedelta(days=days)]
            for asset in ASSETS:
                if len(pre) < 2 or len(post) < 2: continue
                rows.append({
                    "halving": h,
                    "asset":   asset,
                    "period":  f"{days}d",
                    "pre_return":  (pre[asset].iloc[-1] / pre[asset].iloc[0]) - 1,
                    "post_return": (post[asset].iloc[-1] / post[asset].iloc[0]) - 1,
                })
    df = pd.DataFrame(rows)
    df.to_csv(PROC_DIR / "halving_analysis.csv", index=False)
    print("✓ BTC减半分析")
    return df

# ── 8. 黑天鹅冲击分析 ────────────────────────────────────────────
def black_swan_analysis(prices):
    from events import EVENTS
    swans = [e for e in EVENTS if e["type"] == "black_swan"]
    rows = []
    for e in swans:
        d = pd.Timestamp(e["date"])
        for asset in ASSETS:
            s = prices[asset].dropna()
            if d not in s.index:
                d_adj = s.index[s.index.searchsorted(d)]
            else:
                d_adj = d
            idx = s.index.get_loc(d_adj)
            for fwd in [5, 20, 60]:
                if idx + fwd < len(s) and idx >= 1:
                    ret = (s.iloc[idx + fwd] / s.iloc[idx]) - 1
                    rows.append({
                        "event":  e["label"],
                        "date":   str(d.date()),
                        "asset":  asset,
                        "days":   fwd,
                        "return": ret,
                    })
    df = pd.DataFrame(rows)
    df.to_csv(PROC_DIR / "black_swan_impact.csv", index=False)
    print("✓ 黑天鹅冲击")
    return df

def run_all():
    print("加载数据...")
    prices = load()
    ret = pct_returns(prices)

    full_correlation(ret)
    rolling_correlation(ret)
    monthly_stats(ret)
    annual_returns(prices)
    presidential_cycle(annual_returns(prices))
    volatility_regimes(ret)
    halving_analysis(prices)
    black_swan_analysis(prices)

    print("\n所有分析完成，结果在 data/processed/")

if __name__ == "__main__":
    run_all()
