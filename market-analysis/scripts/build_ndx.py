"""build_ndx.py — 纳指100 成分变动追踪（季度调仓自动抓 adds/drops + 对照 valpha150 覆盖缺口）。

抓维基百科 Nasdaq-100 成分表（需 User-Agent，否则 403）→ 对比上次快照
data/ndx_constituents.csv → 算 adds/drops；再对照 valpha150 标“在 NDX 但不在我们 150”的缺口。
写 ndx.json（web+docs）+ 更新快照。盘后/手动单独跑（同 valpha150/wildpool，不入 run_all）；失败不致命。

2026-06-22 后维基把成分表从主条目 Nasdaq-100 挪到独立条目 List of NASDAQ-100 companies
（主条目现只剩追踪该指数的 ETF/共同基金列表 + 里程碑历史，不再含成分表）——因此依次尝试
两个 URL；每个页面内仍用"列名含 Ticker/Symbol + 行数落在成分表量级 + 排除变更史表"的
鲁棒匹配，不写死表索引，避免维基再挪位置/改版式就又炸。
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
WIKI_COMPONENTS = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"  # 现址（2026-06 起）
WIKI = "https://en.wikipedia.org/wiki/Nasdaq-100"                              # 旧址，留作 fallback


def _fetch_constituents():
    """抓当前 NDX-100 成分（~100 公司+GOOG/GOOGL 等双股权类≈101-105 行）。失败返回 None。

    依次尝试 WIKI_COMPONENTS（现址）→ WIKI（旧址，防维基未来挪回）。命中即返回，不逐一都试。
    """
    for url in (WIKI_COMPONENTS, WIKI):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (valpha-lab ndx tracker)"})
            html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
        except Exception:
            continue
        for t in pd.read_html(StringIO(html)):
            cols = [str(c).lower() for c in t.columns]
            has_ticker = any("ticker" in c or "symbol" in c for c in cols)
            is_changes_table = any("added" in c or "removed" in c for c in cols)  # 变更史表(Added/Removed 列)，即便行数落在区间也排除
            if has_ticker and not is_changes_table and 85 <= len(t) <= 130:       # 成分表现约 101-105 行；变更史表另有 ~220+ 行
                tcol = next(c for c in t.columns if "ticker" in str(c).lower() or "symbol" in str(c).lower())
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
