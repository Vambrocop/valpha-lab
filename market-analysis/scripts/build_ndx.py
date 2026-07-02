"""build_ndx.py — 纳指100 成分变动追踪（季度调仓自动抓 adds/drops + 对照 valpha150 覆盖缺口）。

抓维基百科 Nasdaq-100 成分表（需 User-Agent，否则 403）→ 对比上次快照
data/ndx_constituents.csv → 算 adds/drops；再对照 valpha150 标“在 NDX 但不在我们 150”的缺口。
写 ndx.json（web+docs）+ 更新快照。盘后/手动单独跑（同 valpha150/wildpool，不入 run_all）；失败不致命。
"""
import re
import json
import urllib.request
from io import StringIO
from datetime import date
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.parent
SNAP = BASE / "data" / "ndx_constituents.csv"      # 上次成分快照（被 CI 提交持久化，用于下次 diff）
WIKI = "https://en.wikipedia.org/wiki/Nasdaq-100"


def _fetch_constituents():
    """抓当前 NDX-100 成分（~100 公司+GOOG/GOOGL≈101 行）。失败返回 None。"""
    req = urllib.request.Request(WIKI, headers={"User-Agent": "Mozilla/5.0 (valpha-lab ndx tracker)"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    for t in pd.read_html(StringIO(html)):
        tcol = next((c for c in t.columns if "Ticker" in str(c) or "Symbol" in str(c)), None)
        if tcol is not None and 90 <= len(t) <= 110:     # 成分表 ~101 行；排除 220 行的变更史表
            out, seen = [], set()
            for x in t[tcol].astype(str):
                s = re.sub(r"[^A-Za-z.]", "", x).upper()
                if s and s != "NAN" and s not in seen:
                    seen.add(s)
                    out.append(s)
            if len(out) >= 90:
                return out
    return None


def build_all():
    cur = _fetch_constituents()
    if not cur:
        print("[NDX] 未解析到成分表，跳过（不致命）")
        return
    prev = pd.read_csv(SNAP)["ticker"].astype(str).tolist() if SNAP.exists() else []
    added = sorted(set(cur) - set(prev)) if prev else []     # 首跑无快照 → 仅建基线
    removed = sorted(set(prev) - set(cur)) if prev else []
    v150 = set(pd.read_csv(BASE / "data" / "valpha150.csv")["ticker"].astype(str))
    not_in = sorted(set(cur) - v150)                         # 在 NDX 但我们 150 没有 = 缺口
    out = {"generated": date.today().isoformat(), "n": len(cur),
           "added": added, "removed": removed,
           "not_in_valpha150": not_in, "in_valpha150": len(set(cur) & v150)}
    from util_io import write_json
    write_json("ndx.json", out, allow_nan=False)
    pd.DataFrame({"ticker": cur}).to_csv(SNAP, index=False)
    print(f"[OK] ndx.json — 成分 {len(cur)} · 新进 {added or '—'} · 调出 {removed or '—'} · 150未覆盖 {len(not_in)}")


if __name__ == "__main__":
    build_all()
