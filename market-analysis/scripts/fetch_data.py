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
from datetime import date, timedelta

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ── Yahoo Finance 可直接下载的 ────────────────────────────────────
TICKERS = {
    "NASDAQ":  "^IXIC",       # 纳斯达克综合（1971+）
    "NDX100":  "^NDX",        # 纳斯达克100（科技龙头，1985+）
    "SP500":   "^GSPC",       # 标普500
    "VIX":     "^VIX",        # 恐慌指数
    "VIX3M":   "^VIX3M",      # 3个月VIX（与VIX的差=期限结构，倒挂=恐慌，2009+）
    "DXY":     "DX-Y.NYB",    # 美元指数
    "BTC":     "BTC-USD",     # 比特币
    "ETH":     "ETH-USD",     # 以太坊
    "OIL":     "CL=F",        # WTI原油期货
    "GOLD":    "GC=F",        # 黄金期货
    "TNX":     "^TNX",        # 10年期美债收益率
    "VNQ":     "VNQ",         # 美国REIT（房地产信托），信贷压力代理
    "AUD":     "AUDUSD=X",    # 澳元/美元（用户在澳洲，持仓计算器以AUD计价）
    "CNY":     "CNY=X",       # 美元/人民币
    "NVDA":    "NVDA",        # 英伟达（AI景气个股代理）
    "SOX":     "^SOX",        # 费城半导体指数（AI/芯片景气标准指标，1994+）
}

START = "2000-01-01"   # 含2000年互联网泡沫 + 2008年金融危机
END   = (date.today() + timedelta(days=1)).isoformat()  # 永远取到最新一天

# ── 个股观察池：七姐妹 + 优质龙头（可自行增删）──────────────────
STOCK_TICKERS = {
    "AAPL":  "AAPL",   # 苹果
    "MSFT":  "MSFT",   # 微软
    "GOOGL": "GOOGL",  # 谷歌
    "AMZN":  "AMZN",   # 亚马逊
    "NVDA":  "NVDA",   # 英伟达
    "META":  "META",   # Meta
    "TSLA":  "TSLA",   # 特斯拉
    "AVGO":  "AVGO",   # 博通
    "TSM":   "TSM",    # 台积电
    "COST":  "COST",   # 好市多
    "LLY":   "LLY",    # 礼来
    "BRK-B": "BRK-B",  # 伯克希尔
    "SPCX":  "SPCX",   # SpaceX（2026-06-12 上市；历史不足260天，由 export_stocks 专属块处理）
}

def _cache_fallback(name):
    """Yahoo 失败/限流时回退上次缓存的 CSV（与 FRED 同款），避免列静默消失。"""
    cache = RAW_DIR / f"{name}.csv"
    if cache.exists():
        try:
            s = pd.read_csv(cache, index_col=0, parse_dates=True).squeeze("columns")
            s = s.dropna()
            if len(s):
                print(f"  ⚠ {name} Yahoo 无数据，使用缓存（截至 {s.index[-1].date()}）")
                return s.rename(name)
        except Exception:
            pass
    print(f"  ⚠ {name} 无数据且无缓存，跳过")
    return None


def _get_close(ticker, name):
    try:
        df = yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)
    except Exception as e:
        print(f"  ⚠ {name} 下载异常：{e}")
        return _cache_fallback(name)
    if df.empty:
        # 新上市股票 yf.download(start=2000年) 常返回空，但 Ticker().history 拿得到
        try:
            hist = yf.Ticker(ticker).history(period="3mo", auto_adjust=True)
            if not hist.empty:
                s = hist["Close"].dropna().rename(name)
                s.index = pd.to_datetime(s.index.tz_localize(None).date)
                print(f"    （Ticker.history 回退，{len(s)} 行）")
                s.to_csv(RAW_DIR / f"{name}.csv")     # 写缓存，与主路径同款兜底
                return s
        except Exception:
            pass
        return _cache_fallback(name)   # 限流/ticker变更/宕机 → 回退缓存而非掉列
    col = df["Close"]
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]
    col = col.rename(name)
    col.index = pd.to_datetime(col.index)
    col = col.dropna()

    # Yahoo 日线常滞后1天：用小时线最新价补一个临时收盘（下次运行被官方值覆盖）
    try:
        intra = yf.download(ticker, period="5d", interval="60m",
                            auto_adjust=True, progress=False)
        if not intra.empty:
            ic = intra["Close"]
            if isinstance(ic, pd.DataFrame):
                ic = ic.iloc[:, 0]
            ic = ic.dropna()
            last_day = pd.Timestamp(ic.index[-1].tz_localize(None).date())
            if len(col) and last_day > col.index[-1]:
                col.loc[last_day] = float(ic.iloc[-1])
                print(f"    + 盘中临时价补到 {last_day.date()}")
    except Exception:
        pass
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
        "T10Y2Y":   "T10Y2Y",    # 10Y-2Y利差（日频）：<0 倒挂=衰退预警
        "HY_SPREAD":"BAMLH0A0HYM2",  # 高收益债利差（日频）：信用压力，>5%危险
    }
    for name, series in FRED_SERIES.items():
        try:
            print(f"  下载 {name} (FRED:{series})...")
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
            r = requests.get(url, timeout=30)
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
            # 下载失败时回退到上次缓存的 CSV，保证 combined_prices 列不缺失
            cache = RAW_DIR / f"{name}.csv"
            if cache.exists():
                df = pd.read_csv(cache, index_col="Date", parse_dates=True).squeeze()
                frames[name] = df.astype(float)
                print(f"    ⚠ {name} 下载失败，使用缓存（截至 {df.index[-1].date()}）: {e}")
            else:
                print(f"    ⚠ {name} 失败且无缓存: {e}")
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

def fetch_stocks():
    """个股观察池单独存 stocks_prices.csv，不混入 combined_prices（宏观/指数数据集）"""
    print("\n=== 个股观察池 ===")
    frames = {}
    for name, ticker in STOCK_TICKERS.items():
        print(f"  下载 {name} ({ticker})...")
        s = _get_close(ticker, name)
        if s is not None:
            frames[name] = s
            print(f"    → {len(s)} 行")
    if frames:
        df = pd.concat(list(frames.values()), axis=1).sort_index()
        df.index.name = "Date"
        df.to_csv(RAW_DIR / "stocks_prices.csv")
        print(f"  → stocks_prices.csv  ({df.shape})")
    return frames

def fetch_all():
    print("=== Yahoo Finance ===")
    yahoo = fetch_yahoo()
    print("\n=== FRED 宏观数据 ===")
    fred  = fetch_fred()
    fetch_stocks()
    return merge_all(yahoo, fred)

if __name__ == "__main__":
    fetch_all()
