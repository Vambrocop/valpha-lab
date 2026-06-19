"""build_valpha150.py — Valpha150 大盘数据。

读 data/valpha150.csv → 批量抓价 → 算 6月/1年涨幅 + 近20日年化波动 + 距52周高 → valpha150.json。
universe 大(~140)、慢，**独立于主流水线**，手动/定时单独跑：
    py market-analysis/scripts/build_valpha150.py
诚实标注：涨幅是历史、非预测；幸存者偏差（只含当前在册的）。
"""
import json
from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd
import yfinance as yf

BASE = Path(__file__).parent.parent
uni = pd.read_csv(BASE / "data" / "valpha150.csv")
print("板块分布：")
print(uni.sector.value_counts().to_string())
print(f"共 {len(uni)} 只，开始抓价…")

tickers = uni.ticker.tolist()
px = yf.download(tickers, period="2y", interval="1d", auto_adjust=True, progress=False)["Close"]

rows, miss = [], []
for _, r in uni.iterrows():
    s = r.ticker
    if s not in px.columns or px[s].dropna().empty:
        miss.append(s); continue
    p = px[s].dropna()
    if len(p) < 130:
        miss.append(s + "(史短)"); continue
    ret = p.pct_change()
    last = float(p.iloc[-1])
    c6 = round((last / p.iloc[-126] - 1) * 100, 1) if len(p) > 126 else None
    c1 = round((last / p.iloc[-252] - 1) * 100, 1) if len(p) > 252 else None
    vol = round(float(ret.tail(20).std() * np.sqrt(252) * 100), 1)
    fh = round((last / p.tail(252).max() - 1) * 100, 1)
    rows.append({"t": s, "n": r.name_cn, "sec": r.sector, "p": round(last, 2),
                 "c6": c6, "c1": c1, "v": vol, "fh": fh})

out = {"generated": date.today().isoformat(), "n": len(rows), "stocks": rows}
for d in [BASE / "web", BASE.parent / "docs"]:
    (d / "valpha150.json").write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"[OK] {len(rows)}/{len(uni)} 只 → valpha150.json" + (f"；缺: {miss}" if miss else ""))
