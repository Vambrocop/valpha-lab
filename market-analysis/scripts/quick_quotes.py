"""
quick_quotes.py — 盘中轻量报价（CI 每 10 分钟一刀，几秒跑完）

只拉 4 个关键报价写 quotes.json（web + docs），不动其他任何数据文件。
完整流水线仍由 refresh-data.yml 每 30 分钟跑 --light。
"""
import datetime
import json
import sys
from pathlib import Path

import yfinance as yf

WEB  = Path(__file__).parent.parent / "web"
DOCS = Path(__file__).parent.parent.parent / "docs"
SYMS = {"SPCX": "SPCX", "NASDAQ": "^IXIC", "SP500": "^GSPC", "BTC": "BTC-USD"}


def main():
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quotes": {},
    }
    for name, tk in SYMS.items():
        try:
            fi = yf.Ticker(tk).fast_info
            price = fi.last_price
            prev = fi.previous_close
            if price is None:
                print(f"  ! {name} 无报价")
                continue
            q = {"price": round(float(price), 2)}
            if prev:   # 新上市首日 prev_close 可能为 None
                q["prev_close"] = round(float(prev), 2)
                q["chg_pct"] = round((float(price) / float(prev) - 1) * 100, 2)
            out["quotes"][name] = q
            print(f"  {name:<7} {q['price']:>12}  {q.get('chg_pct', '—')}%")
        except Exception as e:
            print(f"  ! {name}: {e}")

    if not out["quotes"]:
        print("无任何报价（限流/休市异常），保留旧 quotes.json")
        sys.exit(0)

    for d in (WEB, DOCS):
        if d.exists():
            with open(d / "quotes.json", "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False)
    print(f"[OK] quotes.json → {len(out['quotes'])} 个报价")


if __name__ == "__main__":
    main()
