"""
fetch_news.py — 免费 RSS 源抓取市场要闻（无需 API key，可在 GitHub Actions 跑）

更新 web/news.json 的 auto 条目；kind="curated"（AI 监控循环写的分析条目）保留不动。
"""
import json
import re
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

WEB_DIR = Path(__file__).parent.parent / "web"
NEWS_PATH = WEB_DIR / "news.json"

FEEDS = {
    "CNBC Markets":  "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "CNBC Top News": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "MarketWatch":   "https://feeds.content.dowjones.io/public/rss/mw_topstories",
}

MAX_AUTO = 5        # 自动条目上限
MAX_TOTAL = 8       # 面板总条目上限
MAX_AGE_H = 24      # 只保留24小时内的新闻

# 粗略的影响标签：标题关键词启发式
NEG = re.compile(r"\b(fall|drop|plunge|sink|tumble|slump|crash|fear|selloff|sell-off|"
                 r"recession|losses|cuts|warning|risk|down)\b", re.I)
POS = re.compile(r"\b(rise|jump|surge|rally|gain|soar|record high|beat|boost|up)\b", re.I)

# 市场相关性过滤：标题必须命中至少一个（否则是泛新闻杂音）
RELEVANT = re.compile(
    r"\b(stock|stocks|market|markets|nasdaq|s&p|dow|fed|fomc|inflation|cpi|ppi|"
    r"rate|rates|yield|treasury|bond|earnings|ipo|tariff|recession|economy|gdp|"
    r"jobs report|payrolls|unemployment|bitcoin|crypto|oil prices|gold|dollar|"
    r"apple|microsoft|nvidia|google|alphabet|amazon|meta|tesla|broadcom|tsmc|"
    r"openai|anthropic|ai spending|chip|semiconductor|wall street|futures|"
    r"bull|bear|correction|rally|sell-?off)\b", re.I)


def _impact(title):
    if NEG.search(title) and not POS.search(title):
        return "negative"
    if POS.search(title) and not NEG.search(title):
        return "positive"
    return "neutral"


def fetch_feed(name, url):
    items = []
    try:
        r = requests.get(url, timeout=20,
                         headers={"User-Agent": "Mozilla/5.0 (alpha-lab personal dashboard)"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        now = datetime.now(timezone.utc)
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            pub   = item.findtext("pubDate")
            if not title or not pub:
                continue
            try:
                dt = parsedate_to_datetime(pub)
            except Exception:
                continue
            if now - dt > timedelta(hours=MAX_AGE_H):
                continue
            if not RELEVANT.search(title):
                continue   # 过滤与市场无关的泛新闻
            items.append({
                "time":   dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "_dt":    dt.isoformat(),
                "title":  title,
                "impact": _impact(title),
                "note":   "",
                "source": name,
                "kind":   "auto",
            })
    except Exception as e:
        print(f"  ⚠ {name} 抓取失败: {e}")
    return items


def main():
    print("=== 抓取市场要闻 RSS ===")
    auto = []
    for name, url in FEEDS.items():
        got = fetch_feed(name, url)
        print(f"  {name}: {len(got)} 条（24h内）")
        auto.extend(got)
    # 按时间倒序、去重（标题前40字符）
    auto.sort(key=lambda x: x["_dt"], reverse=True)
    seen, dedup = set(), []
    for it in auto:
        key = it["title"][:40].lower()
        if key not in seen:
            seen.add(key)
            it.pop("_dt", None)
            dedup.append(it)
    auto = dedup[:MAX_AUTO]

    # 保留人工/AI 分析条目（kind 缺省视为 curated）
    curated = []
    try:
        with open(NEWS_PATH, encoding="utf-8") as f:
            old = json.load(f)
        curated = [it for it in old.get("items", [])
                   if it.get("kind", "curated") == "curated"]
    except Exception:
        pass

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "items": (curated + auto)[:MAX_TOTAL],
    }
    with open(NEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"[OK] news.json：{len(curated)} 条分析 + {len(auto)} 条自动要闻")


if __name__ == "__main__":
    main()
