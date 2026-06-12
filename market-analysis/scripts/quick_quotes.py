"""
quick_quotes.py — 盘中轻量报价（CI 每 10 分钟一刀，几秒跑完）

只拉 4 个关键报价写 quotes.json（web + docs），不动其他任何数据文件。
完整流水线仍由 refresh-data.yml 每 30 分钟跑 --light。

直接打 Yahoo chart API 拿 meta（带成交时间戳 ts 和成交量 vol——
前端靠它们识别"IPO 占位价 vs 真实成交"），yfinance fast_info 兜底。
"""
import datetime
import json
import sys
import urllib.request
from pathlib import Path

WEB  = Path(__file__).parent.parent / "web"
DOCS = Path(__file__).parent.parent.parent / "docs"
SYMS = {"SPCX": "SPCX", "NASDAQ": "^IXIC", "SP500": "^GSPC", "BTC": "BTC-USD"}


def _chart_meta(symbol):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?interval=1m&range=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=15))
    return d["chart"]["result"][0]["meta"]


def _quote_from_meta(meta):
    price = meta.get("regularMarketPrice")
    if price is None:
        return None
    q = {"price": round(float(price), 2)}
    prev = meta.get("previousClose") or meta.get("chartPreviousClose")
    if prev:
        q["prev_close"] = round(float(prev), 2)
        q["chg_pct"] = round((float(price) / float(prev) - 1) * 100, 2)
    if meta.get("regularMarketTime"):
        q["ts"] = int(meta["regularMarketTime"])      # 最后成交的 epoch 秒
    if meta.get("regularMarketVolume") is not None:
        q["vol"] = int(meta["regularMarketVolume"])   # 0 = 还没有成交（IPO 竞价中）
    return q


def _quote_fallback(symbol):
    import yfinance as yf
    fi = yf.Ticker(symbol).fast_info
    if fi.last_price is None:
        return None
    q = {"price": round(float(fi.last_price), 2)}
    if fi.previous_close:
        q["prev_close"] = round(float(fi.previous_close), 2)
        q["chg_pct"] = round((q["price"] / q["prev_close"] - 1) * 100, 2)
    return q


def main():
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quotes": {},
    }
    for name, tk in SYMS.items():
        q = None
        try:
            q = _quote_from_meta(_chart_meta(tk))
        except Exception as e:
            print(f"  ! {name} chart API: {e}")
        if q is None:
            try:
                q = _quote_fallback(tk)
            except Exception as e:
                print(f"  ! {name} fallback: {e}")
        if q:
            out["quotes"][name] = q
            age = ""
            if q.get("ts"):
                mins = (datetime.datetime.now(datetime.timezone.utc).timestamp() - q["ts"]) / 60
                age = f"（成交 {mins:.0f} 分钟前）"
            print(f"  {name:<7} {q['price']:>12}  {q.get('chg_pct', '—')}% {age}")

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
