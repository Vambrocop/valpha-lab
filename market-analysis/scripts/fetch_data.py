"""
fetch_data.py
下载全量宏观 + 资产数据
  资产：NASDAQ / S&P500 / VIX / DXY / BTC / ETH / 原油 / 黄金 / 10Y美债
  宏观：M2货币供应（FRED）/ 美联储基准利率（FRED）
"""

import yfinance as yf
import pandas as pd
import warnings
warnings.filterwarnings("ignore")
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ── Yahoo Finance 可直接下载的 ────────────────────────────────────
TICKERS = {
    "NASDAQ":  "^IXIC",       # 纳斯达克综合
    "SP500":   "^GSPC",       # 标普500
    "VIX":     "^VIX",        # 恐慌指数
    "DXY":     "DX-Y.NYB",    # 美元指数
    "BTC":     "BTC-USD",     # 比特币
    "ETH":     "ETH-USD",     # 以太坊
    "OIL":     "CL=F",        # WTI原油期货
    "GOLD":    "GC=F",        # 黄金期货
    "TNX":     "^TNX",        # 10年期美债收益率
    # 新增
    "VNQ":     "VNQ",         # 美国REIT（房地产信托），信贷压力代理
    "NVDA":    "NVDA",        # 英伟达（AI景气最佳代理指标）
}

START = "2000-01-01"   # 含2000年互联网泡沫 + 2008年金融危机
END   = "2026-06-05"

def _get_close(ticker, name):
    df = yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)
    if df.empty:
        print(f"  ⚠ {name} 无数据，跳过")
        return None
    col = df["Close"]
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]
    col = col.rename(name)
    col.index = pd.to_datetime(col.index)
    return col

def fetch_yahoo():
    frames = {}
    for name, ticker in TICKERS.items():
        print(f"  下载 {name} ({ticker})...")
        s = _get_close(ticker, name)
        if s is not None:
            frames[name] = s
            s.to_csv(RAW_DIR / f"{name}.csv")
            print(f"    → {len(s)} 行")
    return frames

# ── FRED 宏观数据（直接下载CSV，无需API Key） ─────────────────────
def fetch_fred():
    import requests, io
    frames = {}
    FRED_SERIES = {
        "M2":       "M2SL",      # M2货币供应（十亿美元，月频）
        "FED_RATE": "FEDFUNDS",  # 美联储基准利率（月频）
        "CPI":      "CPIAUCSL",  # CPI通胀（月频）
        "UNRATE":   "UNRATE",    # 失业率（月频）
        "YIELD_10Y":"GS10",      # 10年期国债收益率（月频，FRED官方）
        "YIELD_2Y": "GS2",       # 2年期国债收益率（用于算倒挂）
    }
    for name, series in FRED_SERIES.items():
        try:
            print(f"  下载 {name} (FRED:{series})...")
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            df.columns = ["Date", name]
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date")[name]
            df = df[df.index >= START].replace(".", pd.NA).dropna()
            df = df.astype(float)
            frames[name] = df
            df.to_csv(RAW_DIR / f"{name}.csv")
            print(f"    → {len(df)} 行（月频）")
        except Exception as e:
            print(f"    ⚠ {name} 失败: {e}")
    return frames

# ── 合并所有数据（日频，月频向前填充） ────────────────────────────
def merge_all(yahoo_frames, fred_frames):
    # 日频资产
    daily = pd.concat(list(yahoo_frames.values()), axis=1) if yahoo_frames else pd.DataFrame()
    daily.index.name = "Date"
    daily = daily.sort_index()

    # 月频宏观（前向填充到日频）
    if fred_frames:
        monthly = pd.concat(list(fred_frames.values()), axis=1)
        monthly.index.name = "Date"
        monthly = monthly.sort_index()
        # 重采样到日频
        monthly_daily = monthly.resample("D").ffill().reindex(daily.index, method="ffill")
        combined = pd.concat([daily, monthly_daily], axis=1)
    else:
        combined = daily

    combined.to_csv(RAW_DIR / "combined_prices.csv")
    print(f"\n合并完成 → {RAW_DIR / 'combined_prices.csv'}  ({combined.shape})")
    return combined

def fetch_all():
    print("=== Yahoo Finance ===")
    yahoo = fetch_yahoo()
    print("\n=== FRED 宏观数据 ===")
    fred  = fetch_fred()
    return merge_all(yahoo, fred)

if __name__ == "__main__":
    fetch_all()
