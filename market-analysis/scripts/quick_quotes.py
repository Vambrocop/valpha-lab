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
import urllib.parse
import urllib.request
from pathlib import Path

WEB  = Path(__file__).parent.parent / "web"
DOCS = Path(__file__).parent.parent.parent / "docs"
SYMS = {"SPCX": "SPCX", "NASDAQ": "^IXIC", "SP500": "^GSPC", "BTC": "BTC-USD"}
COIN_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "XLM": "stellar", "DOGE": "dogecoin",
            "HOME": "home", "SOL": "solana", "BNB": "binancecoin"}   # 与前端 app-3.js COIN_IDS 同步


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


def _nasdaq_bid_ask(symbol):
    """Nasdaq 官方 API 的实时 bid/ask——IPO 首日 Yahoo 最后成交价滞后数小时，
    但订单簿是活的：bid/ask 中值可作'指示价'诚实展示（明确标注非成交价）。"""
    url = f"https://api.nasdaq.com/api/quote/{symbol}/info?assetclass=stocks"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=15))
    p = d.get("data", {}).get("primaryData", {}) or {}

    def _num(s):
        try:
            return float(str(s).replace("$", "").replace(",", ""))
        except (ValueError, TypeError):
            return None
    return {"bid": _num(p.get("bidPrice")), "ask": _num(p.get("askPrice"))}


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


def _coingecko():
    """服务端抓 CoinGecko 加密报价 + AUD 汇率 → 写同源 quotes.json，
    中国访客不必直连境外 API(CORS/被墙)。失败由 main 沿用上次数据。"""
    ids = ",".join(COIN_IDS.values())
    url = (f"https://api.coingecko.com/api/v3/simple/price"
           f"?ids={ids}&vs_currencies=usd,aud")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (valpha-lab dashboard)"})
    d = json.load(urllib.request.urlopen(req, timeout=15))
    crypto, aud_rate = {}, None
    for tk, cid in COIN_IDS.items():
        row = d.get(cid) or {}
        if row.get("usd") is not None:
            crypto[tk] = round(float(row["usd"]), 6)
        if aud_rate is None and row.get("usd") and row.get("aud"):
            aud_rate = round(float(row["usd"]) / float(row["aud"]), 4)
    return crypto, aud_rate


def _fear_greed():
    """服务端抓 alternative.me 恐惧贪婪指数(7天)→ 同源 quotes.json;中国访客不必直连境外 API。"""
    url = "https://api.alternative.me/fng/?limit=7&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (valpha-lab dashboard)"})
    d = json.load(urllib.request.urlopen(req, timeout=15))
    return d.get("data", [])


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
        if q and name == "SPCX":
            # IPO 期间补充订单簿指示价（成交价滞后时前端展示 bid/ask 中值）
            try:
                ba = _nasdaq_bid_ask(tk)
                if ba.get("bid") and ba.get("ask"):
                    q["bid"], q["ask"] = ba["bid"], ba["ask"]
            except Exception as e:
                print(f"  · SPCX bid/ask 不可用: {e}")
        if q:
            out["quotes"][name] = q
            age = ""
            if q.get("ts"):
                mins = (datetime.datetime.now(datetime.timezone.utc).timestamp() - q["ts"]) / 60
                age = f"（成交 {mins:.0f} 分钟前）"
            print(f"  {name:<7} {q['price']:>12}  {q.get('chg_pct', '—')}% {age}")

    # CoinGecko 加密报价（服务端抓 → 同源 quotes.json；中国访客不必直连境外 API）
    try:
        crypto, aud_rate = _coingecko()
    except Exception as e:
        print(f"  ! CoinGecko: {e}")
        crypto, aud_rate = {}, None
    if not crypto:   # 限流/失败 → 沿用上次 quotes.json 的加密价，不丢数据
        try:
            with open(WEB / "quotes.json", encoding="utf-8") as f:
                old = json.load(f)
            crypto = old.get("crypto", {})
            aud_rate = aud_rate or old.get("aud_rate")
        except Exception:
            pass
    if crypto:
        out["crypto"] = crypto
        print(f"  crypto  {len(crypto)} 币 · 1 AUD≈US${aud_rate}")
    if aud_rate:
        out["aud_rate"] = aud_rate

    # 恐惧贪婪指数(alternative.me)同样挪服务端 → 同源 quotes.json(中国访客不必直连境外)
    try:
        fg = _fear_greed()
    except Exception as e:
        print(f"  ! fear&greed: {e}")
        fg = []
    if not fg:   # 失败 → 沿用上次 quotes.json 的 fear_greed,不丢数据
        try:
            with open(WEB / "quotes.json", encoding="utf-8") as f:
                fg = json.load(f).get("fear_greed", [])
        except Exception:
            pass
    if fg:
        out["fear_greed"] = fg
        print(f"  fear&greed  {fg[0].get('value')} ({fg[0].get('value_classification')})")

    if not out["quotes"] and "crypto" not in out and "fear_greed" not in out:
        print("无任何报价（限流/休市异常），保留旧 quotes.json")
        sys.exit(0)

    from util_io import write_json
    write_json("quotes.json", out, indent=None, separators=(",", ":"), allow_nan=False)
    print(f"[OK] quotes.json → {len(out['quotes'])} 个报价")


if __name__ == "__main__":
    main()
