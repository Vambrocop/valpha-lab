"""
fetch_data.py
下载四大资产历史数据：NASDAQ / DXY / BTC / ETH
数据来源：Yahoo Finance (免费，无需注册)
"""

import yfinance as yf
import pandas as pd
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

TICKERS = {
    "NASDAQ": "^IXIC",
    "DXY":    "DX-Y.NYB",
    "BTC":    "BTC-USD",
    "ETH":    "ETH-USD",
}

START = "2015-01-01"   # BTC数据从2015年起较完整
END   = "2026-06-03"

def fetch_all():
    frames = {}
    for name, ticker in TICKERS.items():
        print(f"下载 {name} ({ticker})...")
        df = yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)
        # yfinance 1.x 返回 MultiIndex 列，取第一列
        close_raw = df["Close"]
        if isinstance(close_raw, pd.DataFrame):
            close_raw = close_raw.iloc[:, 0]
        close = close_raw.rename(name)
        close.index = pd.to_datetime(close.index)
        frames[name] = close
        out = RAW_DIR / f"{name}.csv"
        close.to_csv(out)
        print(f"  → {out}  ({len(close)} 行)")

    combined = pd.concat(frames.values(), axis=1).dropna(how="all")
    combined.index.name = "Date"
    combined.to_csv(RAW_DIR / "combined_prices.csv")
    print(f"\n合并完成：{RAW_DIR / 'combined_prices.csv'}")
    return combined

if __name__ == "__main__":
    fetch_all()
