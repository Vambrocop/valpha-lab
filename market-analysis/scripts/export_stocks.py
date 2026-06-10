"""
export_stocks.py — 个股观察池数据导出（七姐妹 + 优质龙头）

读取 stocks_prices.csv + combined_prices.csv（指数基准），
为每只股票计算关键指标和近3年归一化周线走势，输出 web/stocks.json。
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
WEB_DIR = Path(__file__).parent.parent / "web"

LABELS = {
    "AAPL": "苹果", "MSFT": "微软", "GOOGL": "谷歌", "AMZN": "亚马逊",
    "NVDA": "英伟达", "META": "Meta", "TSLA": "特斯拉",
    "AVGO": "博通", "TSM": "台积电", "COST": "好市多",
    "LLY": "礼来", "BRK-B": "伯克希尔",
}
MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

YEARS_OF_SERIES = 3   # 走势图年数（周线）


def _rsi(returns, period=14):
    gain = returns.clip(lower=0).rolling(period).mean()
    loss = (-returns.clip(upper=0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / (loss + 1e-10))


def _stats(s, bench_ret):
    """单只股票的关键指标（s: 日线收盘价序列）"""
    s = s.dropna()
    if len(s) < 260:
        return None
    ret = s.pct_change()
    last = s.index[-1]
    ytd_start = s[s.index.year < last.year]
    out = {
        "last":       round(float(s.iloc[-1]), 2),
        "date":       last.strftime("%Y-%m-%d"),
        "chg_1d":     round(float(ret.iloc[-1] * 100), 2),
        "chg_20d":    round(float((s.iloc[-1] / s.iloc[-21] - 1) * 100), 2),
        "ytd":        round(float((s.iloc[-1] / ytd_start.iloc[-1] - 1) * 100), 2)
                      if len(ytd_start) else None,
        "chg_1y":     round(float((s.iloc[-1] / s.iloc[-253] - 1) * 100), 2)
                      if len(s) > 253 else None,
        "from_high_52w": round(float((s.iloc[-1] / s.tail(252).max() - 1) * 100), 2),
        "above_ma50":  bool(s.iloc[-1] > s.rolling(50).mean().iloc[-1]),
        "above_ma200": bool(s.iloc[-1] > s.rolling(200).mean().iloc[-1]),
        "rsi14":       round(float(_rsi(ret).iloc[-1]), 1),
        "vol20_ann":   round(float(ret.rolling(20).std().iloc[-1] * np.sqrt(252) * 100), 1),
    }
    # 与纳指的1年期 beta / 相关性（按共同交易日对齐）
    pair = pd.concat([ret, bench_ret], axis=1, join="inner").dropna().tail(252)
    if len(pair) > 60:
        cov = pair.cov()
        out["beta_nasdaq_1y"] = round(float(cov.iloc[0, 1] / cov.iloc[1, 1]), 2)
        out["corr_nasdaq_1y"] = round(float(pair.corr().iloc[0, 1]), 2)
    return out


def _weekly_norm(s, start):
    """周线 + 归一化到100"""
    w = s.dropna()[start:].resample("W").last().dropna()
    if len(w) < 10:
        return None
    base = w.iloc[0]
    return {
        "dates":  [d.strftime("%Y-%m-%d") for d in w.index],
        "values": [round(float(v / base * 100), 2) for v in w],
    }


def main():
    stocks = pd.read_csv(RAW_DIR / "stocks_prices.csv",
                         index_col="Date", parse_dates=True)
    combined = pd.read_csv(RAW_DIR / "combined_prices.csv",
                           index_col="Date", parse_dates=True)
    bench_ret = combined["NASDAQ"].dropna().pct_change()

    start = (stocks.index[-1] - pd.DateOffset(years=YEARS_OF_SERIES))

    out = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "mag7": MAG7,
        "indices": {},
        "stocks": {},
    }
    # 指数基准走势（同窗口归一化）
    for idx in ["NASDAQ", "SP500"]:
        series = _weekly_norm(combined[idx], start)
        if series:
            out["indices"][idx] = series

    for sym in stocks.columns:
        s = stocks[sym]
        stats = _stats(s, bench_ret)
        series = _weekly_norm(s, start)
        if not stats or not series:
            print(f"  ⚠ {sym} 数据不足，跳过")
            continue
        out["stocks"][sym] = {
            "label":  LABELS.get(sym, sym),
            "is_mag7": sym in MAG7,
            "stats":  stats,
            "series": series,
        }
        print(f"  {sym:<6} {LABELS.get(sym, sym):<5} 最新={stats['last']:>10}  "
              f"YTD={stats['ytd']:>7}%  RSI={stats['rsi14']}")

    path = WEB_DIR / "stocks.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[OK] {len(out['stocks'])} 只个股 → {path}  ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
