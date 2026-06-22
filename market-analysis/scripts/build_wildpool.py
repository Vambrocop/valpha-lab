"""build_wildpool.py — D·A 出格池数据构建。

读 data/wild_pool.csv → 批量抓价 → 复用 build_valpha150.compute_metrics
(6月/1年涨幅 + 近20日年化波动 + 距52周高) → wildpool.json。

仅含当前在册（幸存者偏差）。历史≥130交易日才入库，不足则跳过，不崩。

手动/定时单独跑：
    py market-analysis/scripts/build_wildpool.py
"""
import json
from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd
import yfinance as yf

# 复用 valpha150 的纯函数 compute_metrics，不重写逻辑
from build_valpha150 import compute_metrics  # noqa: F401

BASE = Path(__file__).parent.parent


def build_all():
    uni = pd.read_csv(BASE / "data" / "wild_pool.csv")
    print("板块分布：")
    print(uni.sector.value_counts().to_string())
    print(f"共 {len(uni)} 只，开始抓价…")

    tickers = uni.ticker.tolist()
    px = yf.download(
        tickers, period="2y", interval="1d", auto_adjust=True, progress=False
    )["Close"]

    rows, miss = [], []
    for _, r in uni.iterrows():
        s = r.ticker
        if s not in px.columns or px[s].dropna().empty:
            miss.append(s)
            continue
        m = compute_metrics(px[s])
        if m is None:
            miss.append(s + "(史短)")
            continue
        rows.append({"t": s, "n": r.name_cn, "sec": r.sector, **m})

    out = {"generated": date.today().isoformat(), "n": len(rows), "stocks": rows}
    for d in [BASE / "web", BASE.parent / "docs"]:
        (d / "wildpool.json").write_text(
            json.dumps(out, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    print(
        f"[OK] {len(rows)}/{len(uni)} 只 → wildpool.json"
        + (f"；缺: {miss}" if miss else "")
    )


if __name__ == "__main__":
    build_all()
