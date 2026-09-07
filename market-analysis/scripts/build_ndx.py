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


LOG = BASE / "data" / "ndx_membership_log.csv"   # append-only:成分进出账本
POOL = BASE / "data" / "valpha150.csv"


def _append_changes(day, added, removed):
    """把成分进出写进 append-only 账本(2026-09-07 补)。

    ## 为什么需要账本

    原来 `added`/`removed` 只是"跟上一份快照比"的**瞬时差分**:绝大多数日子是空的,
    一旦某天真有进出,当天没人看 ndx.json 就**永远看不见了**——快照已经被覆盖成新的。
    这正是"成分清单会悄悄老化"的机制:**变动本身没留痕**,于是没人知道该去维护 valpha150。

    账本按 (date,ticker,action) 去重幂等:同一天重复跑不会写重。绝不回改历史行。
    """
    if not added and not removed:
        return []
    rows = [{"date": day, "ticker": t, "action": "added"} for t in added]
    rows += [{"date": day, "ticker": t, "action": "removed"} for t in removed]
    old = pd.read_csv(LOG, dtype=str) if LOG.exists() else pd.DataFrame(columns=["date", "ticker", "action"])
    new = pd.concat([old, pd.DataFrame(rows)], ignore_index=True)
    new = new.drop_duplicates(subset=["date", "ticker", "action"], keep="first")
    new.to_csv(LOG, index=False)
    return rows


def _recent_changes(day, days=180):
    """近 N 天的成分进出(从账本读)。变动稀疏,窗口给宽些才看得见。"""
    if not LOG.exists():
        return []
    df = pd.read_csv(LOG, dtype=str)
    if df.empty:
        return []
    cut = (pd.Timestamp(day) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    df = df[df["date"] >= cut].sort_values("date", ascending=False)
    return df.to_dict("records")


def _pool_curation_age(day):
    """valpha150.csv 距上次**人工维护**多少天(按 git 最后修改日算)。

    池子是人工策展的(带手写中文名/板块),外部没有权威名单可抓,所以不能自动重写 ——
    自动加票会让 name_cn/sector 开天窗,还会悄悄改变已发布的统计口径。
    能做也该做的是:**把"多久没人管了"摆出来**,让老化看得见。
    """
    import subprocess
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%cs", "--", str(POOL)],
                           cwd=str(BASE.parent), capture_output=True, text=True, timeout=20)
        last = (r.stdout or "").strip()
        if not last:
            return None, None
        return last, (pd.Timestamp(day) - pd.Timestamp(last)).days
    except Exception:
        return None, None


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
    day = date.today().isoformat()
    _append_changes(day, added, removed)               # 先记账,再出产物
    recent = _recent_changes(day)
    pool_last, pool_age = _pool_curation_age(day)
    # 新进指数**且**池子没有 = 真正值得看的缺口。
    # (不报全部 43 个"在 NDX 不在池子":那多半是策展时**刻意**没收的中盘,报出来只会被当噪声忽略。)
    recent_added_missing = sorted({r["ticker"] for r in recent
                                   if r["action"] == "added" and r["ticker"] not in v150})
    out = {"generated": day, "n": len(cur),
           "added": added, "removed": removed,
           "not_in_valpha150": not_in, "in_valpha150": len(set(cur) & v150),
           "recent_changes": recent,
           "recent_added_missing": recent_added_missing,
           "pool_last_curated": pool_last, "pool_age_days": pool_age,
           "caveat": "Valpha150 是**人工策展**池(手写中文名/板块),外部无权威名单可抓,故不自动重写"
                     "——自动加票会让中文名开天窗、并悄悄改变已发布口径。这里只把老化摆出来:"
                     "成分进出记进 append-only 账本(否则瞬时差分当天没人看就永远丢了)、"
                     "并显示池子多久没人维护。是否纳入由人决定。"}
    from util_io import write_json
    write_json("ndx.json", out, allow_nan=False)
    pd.DataFrame({"ticker": cur}).to_csv(SNAP, index=False)
    age_txt = f" · 池子 {pool_age} 天没维护(最后 {pool_last})" if pool_age is not None else ""
    print(f"[OK] ndx.json — 成分 {len(cur)} · 新进 {added or '—'} · 调出 {removed or '—'} "
          f"· 150未覆盖 {len(not_in)} · 近半年变动 {len(recent)}{age_txt}")
    if recent_added_missing:
        print(f"    ⚠ 近半年新进指数但池子还没有: {recent_added_missing}")


if __name__ == "__main__":
    build_all()
