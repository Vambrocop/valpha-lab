"""
overnight_analysis.py — 隔夜 vs 日内收益分解（著名市场异象）

把日收益拆成两段：
  隔夜段 = 今日开盘 / 昨日收盘 - 1   （收盘买、次日开盘卖）
  日内段 = 今日收盘 / 今日开盘 - 1   （开盘买、收盘卖）
历史上美股长期收益几乎全部来自隔夜段，日内段接近零。

输出 web/overnight.json：月度累计净值曲线 + 统计摘要。
"""
import yfinance as yf
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import date, timedelta

WEB_DIR  = Path(__file__).parent.parent / "web"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
START = "2000-01-01"
END = (date.today() + timedelta(days=1)).isoformat()

# 用 ETF 而非指数：指数开盘价是合成值（含未开盘成分股的昨收），
# ETF 开盘价才是真实可交易价格，隔夜/日内分解才有意义
TICKERS = {"SP500_ETF(SPY)": "SPY", "NASDAQ100_ETF(QQQ)": "QQQ"}


def analyze(name, ticker):
    df = yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)
    if df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    o, c = df["Open"], df["Close"]
    # 早年指数数据 Open 可能为 0 或缺失，过滤掉
    valid = (o > 0) & (c > 0)
    o, c = o[valid], c[valid]

    overnight = (o / c.shift(1) - 1).dropna()
    intraday  = (c / o - 1).dropna()
    total     = (c / c.shift(1) - 1).dropna()
    # 过滤数据错误造成的极端值（>15% 的隔夜跳空在指数上不真实）
    overnight = overnight[overnight.abs() < 0.15]
    common = overnight.index.intersection(intraday.index)
    overnight, intraday = overnight[common], intraday[common]
    total = total[total.index.isin(common)]

    def _cum_monthly(r):
        cum = (1 + r).cumprod()
        m = cum.resample("ME").last()
        return {"dates": [d.strftime("%Y-%m") for d in m.index],
                "values": [round(float(v), 4) for v in m]}

    def _stats(r):
        n = len(r)
        years = n / 252
        ann = (1 + r).prod() ** (1 / years) - 1 if years > 0 else 0
        return {"ann_return": round(float(ann) * 100, 2),
                "win_rate":   round(float((r > 0).mean()) * 100, 1),
                "avg_bp":     round(float(r.mean()) * 10000, 2),  # 日均（基点）
                "n":          int(n)}

    print(f"  {name}: 隔夜年化={_stats(overnight)['ann_return']}%  "
          f"日内年化={_stats(intraday)['ann_return']}%  "
          f"整体年化={_stats(total)['ann_return']}%")
    return {
        "_daily": overnight,   # 日频隔夜收益（写 CSV 用，不进 JSON）
        "overnight": {"cum": _cum_monthly(overnight), "stats": _stats(overnight)},
        "intraday":  {"cum": _cum_monthly(intraday),  "stats": _stats(intraday)},
        "total":     {"cum": _cum_monthly(total),     "stats": _stats(total)},
        # 近10年单独统计（异象是否仍然成立）
        "recent10y": {
            "overnight": _stats(overnight[overnight.index >= overnight.index[-1] - pd.DateOffset(years=10)]),
            "intraday":  _stats(intraday[intraday.index >= intraday.index[-1] - pd.DateOffset(years=10)]),
        },
    }


def main():
    print("=== 隔夜 vs 日内收益分解 ===")
    out = {"generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
           "start": START, "indices": {}}
    daily_series = {}
    for name, tk in TICKERS.items():
        r = analyze(name, tk)
        if r:
            out["indices"][name] = r
            daily_series[name.split("_")[0]] = r.pop("_daily")  # 不进 JSON
    path = WEB_DIR / "overnight.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[OK] → {path}  ({path.stat().st_size // 1024} KB)")

    # 日频隔夜收益序列 → processed/，供 build_signals / walk_forward 做「隔夜动量」因子
    if daily_series:
        df = pd.DataFrame(daily_series)
        df.index.name = "Date"
        df.to_csv(PROC_DIR / "overnight_daily.csv")
        print(f"[OK] 日频隔夜收益 → overnight_daily.csv ({df.shape})")


if __name__ == "__main__":
    main()
