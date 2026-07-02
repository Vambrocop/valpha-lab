"""fetch_earnings.py — Finnhub 财报日历：给追踪的票标「下次财报日」。

财报前后跳空、波动放大，是【已知的高风险窗口】——标出来 = 提示你「这票 N 天后财报，当心」。
非荐股、非预测，只是一个客观日历事实 + 风险提示。

读 FINNHUB_API_KEY（GitHub Secret / 本地 env）；未配置静默跳过（不阻断流水线）。
Finnhub 免费版 /calendar/earnings 可用（60 次/分）。只取未来 N 天、过滤到我们追踪的
universe（valpha150 + 点单），写 earnings.json（web/ 与 docs/）。盘后/手动单独跑：
    $env:FINNHUB_API_KEY='...'; py market-analysis/scripts/fetch_earnings.py
"""
import os
import json
import datetime
import urllib.request
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.parent
HORIZON_DAYS = 45                          # 只关心未来 45 天内的财报


def _universe():
    """追踪的票池：valpha150 成分 + 点单请求（都大写）。"""
    uni = set()
    try:
        uni |= set(pd.read_csv(BASE / "data" / "valpha150.csv")["ticker"].astype(str).str.upper())
    except Exception:
        pass
    try:
        for line in (BASE / "data" / "ticker_requests.txt").read_text(encoding="utf-8").splitlines():
            s = line.split("#", 1)[0].strip().upper()
            if s:
                uni.add(s)
    except Exception:
        pass
    return uni


def run():
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        print("[财报] 未配置 FINNHUB_API_KEY，跳过")
        return None
    today = datetime.date.today()
    to = today + datetime.timedelta(days=HORIZON_DAYS)
    # key 走 X-Finnhub-Token 头、不放 URL query → 万一异常被打进 CI 日志也不带 token（审计建议）
    url = (f"https://finnhub.io/api/v1/calendar/earnings"
           f"?from={today.isoformat()}&to={to.isoformat()}")
    try:
        req = urllib.request.Request(url, headers={"X-Finnhub-Token": key})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except Exception as e:
        print(f"[财报] 拉取失败（非致命，不阻断）: {e}")
        return None
    uni = _universe()
    earn = {}                              # ticker → 最近一个未来财报日（YYYY-MM-DD）
    for e in data.get("earningsCalendar", []):
        s = (e.get("symbol") or "").upper()
        d = e.get("date")
        if s in uni and d and d >= today.isoformat():
            if s not in earn or d < earn[s]:
                earn[s] = d
    out = {
        "generated": today.isoformat(), "horizon_days": HORIZON_DAYS,
        "n": len(earn), "earnings": earn,
        "note": "Finnhub 财报日历。财报前后跳空/波动放大 = 已知高风险窗口，非荐股、非预测——只提示你留意。",
    }
    payload = json.dumps(out, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    for d in (BASE / "web", BASE.parent / "docs"):
        if d.exists():
            (d / "earnings.json").write_text(payload, encoding="utf-8")
    print(f"[OK] earnings.json — {len(earn)} 只有未来 {HORIZON_DAYS} 天内财报")
    return out


if __name__ == "__main__":
    run()
