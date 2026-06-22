"""fetch_senate.py — 参议院交易数据（免费·senate-stock-watcher）→ senate_trades.csv。

「政治钱」诚实检验族的数据底座：测议员买入【披露之后再跟】是否仍有 OOS edge。
源：timothycarambat/senate-stock-watcher-data（GitHub raw，STOCK Act 披露，约 2012 起）。
只留股票类 + 有效代码 + 买/卖；解析日期；加 45 天披露滞后 = followable_date（可跟单日，保守防前瞻）。
非荐股、描述性研究。盘后/手动单独跑（同 valpha150/wildpool，不入 run_all）；失败不致命。
"""
import json
import csv
import re
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent.parent
OUT = BASE / "data" / "senate_trades.csv"          # 被 CI 提交持久化（可复现 + 给分析层读）
SRC = "https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data/master/aggregate/all_transactions.json"
LAG_DAYS = 45                                       # STOCK Act 报告期限 → 披露滞后保守上界


def _date(s):
    try:
        return datetime.strptime((s or "").strip(), "%m/%d/%Y").date()
    except Exception:
        return None


def fetch():
    req = urllib.request.Request(SRC, headers={"User-Agent": "Mozilla/5.0 (valpha senate)"})
    data = json.loads(urllib.request.urlopen(req, timeout=60).read())
    rows = []
    for r in data:
        if (r.get("asset_type") or "").strip() != "Stock":
            continue
        tk = re.sub(r"[^A-Za-z.]", "", (r.get("ticker") or "")).upper()
        if not tk or tk == "NAN" or len(tk) > 6:
            continue
        d = _date(r.get("transaction_date"))
        if not d:
            continue
        ttype = (r.get("type") or "").strip()
        side = "buy" if ttype.startswith("Purchase") else ("sell" if ttype.startswith("Sale") else None)
        if side is None:                            # 跳过 Exchange 等
            continue
        rows.append({
            "txn_date": d.isoformat(),
            "followable_date": (d + timedelta(days=LAG_DAYS)).isoformat(),
            "ticker": tk, "side": side, "amount": (r.get("amount") or "").strip(),
            "senator": (r.get("senator") or "").strip().rstrip(","), "owner": (r.get("owner") or "").strip(),
        })
    rows.sort(key=lambda x: x["txn_date"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["txn_date", "followable_date", "ticker", "side", "amount", "senator", "owner"])
        w.writeheader()
        w.writerows(rows)
    buys = [r for r in rows if r["side"] == "buy"]
    tickers = {r["ticker"] for r in rows}
    print(f"[OK] senate_trades.csv — {len(rows)} 笔(买 {len(buys)}/卖 {len(rows) - len(buys)}) · "
          f"{len(tickers)} 个代码 · {rows[0]['txn_date']}→{rows[-1]['txn_date']}")
    print("  最活跃议员:", Counter(r['senator'] for r in rows).most_common(5))
    print("  最常交易代码:", Counter(r['ticker'] for r in rows).most_common(10))
    return rows


if __name__ == "__main__":
    fetch()
