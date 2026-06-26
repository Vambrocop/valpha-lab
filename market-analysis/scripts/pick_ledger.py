"""pick_ledger.py — 把 outlook 的「看好/看淡」直接进 append-only 公开计分账本（敢荐就敢认账）。

差异化命门 = 诚实计分,不是又一个吹票机:每条荐股记入场→满 HOLD_TD 个交易日 vs QQQ 自动结算→
公开胜率,边跑边攒。范式同 insider_signal / overreaction_alert。

口径(都进 caveat):
- 来源 = outlook.json 的 bullish(看好)/bearish(看淡),现为「6个月动量领先/垫底」的透明规则
  (规则以后可换,账本与规则无关——脊梁是公开认账)。
- 入场 = 出榜日次日(act after the call,不抢跑);持有 HOLD_TD 个交易日;相对 QQQ 超额。
- 命中口径:看好命中=跑赢 QQQ;看淡命中=跑输 QQQ(看淡是「预期落后」)。call_excess=站在「这条判断对不对」角度的得分。
- 诚实预期:追 6 月动量多半跑不赢 QQQ(尤其已涨上天的)——但那正是公开认账的价值,不是失败。
- 幸存者偏差(退市/无价丢弃)、重叠窗口只看描述、相关≠因果、非投资建议、不可交易(成本/滑点/税)、
  会错、过去≠未来。append-only,绝不改历史行。
"""
import csv
import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).parent
BASE = SCRIPTS.parent
PROC = BASE / "data" / "processed"
WEB = BASE / "web"
LOG = BASE / "data" / "pick_ledger.csv"

HOLD_TD = 20            # 持有的交易日数(≈1 个月,对齐计分卡 horizon_days=20)
BENCH = "QQQ"           # 基准:纳指 ETF(贴合我们的科技股观察池)
RAW = BASE / "data" / "raw"
UNIVERSE = RAW / "stocks_prices.csv"   # 观察池价格面板(date×ticker),同 outlook 源
MOM_WIN, VOL_WIN, N_PICKS = 126, 63, 3
# 当前挑票规则(透明·可换;换规则只改这里 + _select_picks,账本/结算/前端都不动)
PICK_RULE = "动量+低波动 等权排名（126日动量 + 63日低波动，观察池取头/尾各3）"
_TRUE = ("true", "1", "yes")

HEADER = ["pick_date", "symbol", "view", "mom_pct", "entry_date", "entry_px",
          "exit_date", "exit_px", "ret_pct", "bench_pct", "excess_pct",
          "call_excess_pct", "hit", "settled", "dropped"]


def _is_true(v):
    return str(v).strip().lower() in _TRUE


# ── 挑票规则:动量 + 低波动 等权排名(透明·可换)──────────────────────
def _select_picks(prices):
    """价格面板 → 按(126日动量百分位 + 63日低波动百分位)等权打分,取头 N 看好/尾 N 看淡。
    返回 [{symbol, view, mom_pct}]（mom_pct=动量分量,供展示;score 仅用于选,不入账)。
    低波动异象 + 动量都是文献支持的因子——比裸动量更稳健,但仍未经我们回测,由前向公开计分裁决。"""
    px = prices.apply(pd.to_numeric, errors="coerce")
    if len(px) < MOM_WIN + 1:
        return []
    mom = px.iloc[-1] / px.iloc[-1 - MOM_WIN] - 1                 # 6 个月动量
    vol = px.pct_change().iloc[-VOL_WIN:].std()                   # 近 63 日波动
    df = pd.DataFrame({"mom": mom, "vol": vol}).dropna()
    n = N_PICKS if len(df) >= 2 * N_PICKS else max(1, len(df) // 2)
    if n < 1 or df.empty:
        return []
    df["score"] = 0.5 * df["mom"].rank(pct=True) + 0.5 * (-df["vol"]).rank(pct=True)
    df = df.sort_values("score", ascending=False)
    out = []
    for sym, r in df.head(n).iterrows():
        out.append({"symbol": str(sym), "view": "看好", "mom_pct": round(float(r["mom"]) * 100, 1)})
    for sym, r in df.tail(n).iloc[::-1].iterrows():
        out.append({"symbol": str(sym), "view": "看淡", "mom_pct": round(float(r["mom"]) * 100, 1)})
    return out


def _load_picks():
    """读观察池价格面板 → _select_picks → 标今日为出榜日。读不到价格则空(不阻断)。"""
    try:
        prices = pd.read_csv(UNIVERSE, index_col=0, parse_dates=True)
    except Exception:
        return []
    today = datetime.date.today().isoformat()
    return [{**p, "pick_date": today} for p in _select_picks(prices)]


# ── append-only 账本(结算只填空,不改身份)──────────────────────────
def _read_log():
    if not LOG.exists():
        return []
    with open(LOG, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_log(rows):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HEADER})


def _key(r):
    return (r.get("symbol"), str(r.get("pick_date")), r.get("view"))


# ── yfinance 批量取价(可注入便于测试)────────────────────────────────
def _fetch_prices(symbols, start):
    import yfinance as yf
    cols = {}
    uniq = sorted({s for s in symbols if s} | {BENCH})
    for i in range(0, len(uniq), 120):
        chunk = uniq[i:i + 120]
        try:
            px = yf.download(chunk, start=start, auto_adjust=True, progress=False)["Close"]
        except Exception:
            continue
        if isinstance(px, pd.Series):
            px = px.to_frame(chunk[0])
        for c in px.columns:
            s = pd.to_numeric(px[c], errors="coerce").dropna()
            if len(s) > 5:
                cols[c] = s
    return cols


# ── 单条前向:出榜次日首个交易日买、持有 HOLD_TD 个交易日 ──────────────
def _fwd(series, followable, hold_td):
    """返回 (ret, entry_date, exit_date, entry_px, exit_px)；窗未走完→"pending"；无价→None。"""
    if series is None or series.empty:
        return None
    f = pd.Timestamp(followable)
    after = series.index[series.index >= f]
    if len(after) == 0:
        return "pending" if f > series.index[-1] else None
    ed = after[0]
    pos = series.index.get_indexer([ed])[0]
    if pos < 0 or pos + hold_td >= len(series):
        return "pending"
    xd = series.index[pos + hold_td]
    epx, xpx = float(series.iloc[pos]), float(series.iloc[pos + hold_td])
    if epx <= 0:
        return None
    return (xpx / epx - 1.0, ed, xd, epx, xpx)


def _settle(rows, px):
    bench = px.get(BENCH)
    n = 0
    for r in rows:
        if _is_true(r.get("settled")) or _is_true(r.get("dropped")):
            continue
        followable = pd.Timestamp(r["pick_date"]) + pd.Timedelta(days=1)   # 出榜次日
        b = _fwd(bench, followable, HOLD_TD)
        if b == "pending" or b is None:
            continue
        s = _fwd(px.get(r["symbol"]), followable, HOLD_TD)
        if s == "pending":
            continue
        if s is None:                                      # 退市/无价 → 透明丢弃
            r["dropped"] = True
            n += 1
            continue
        sret, ed, xd, epx, xpx = s
        bret = b[0]
        excess = sret - bret
        bullish = r.get("view") == "看好"
        # 看好命中=跑赢QQQ;看淡命中=跑输QQQ。call_excess=站在"这条判断"角度的得分(都越大越对)
        hit = excess > 0 if bullish else excess < 0
        call_excess = excess if bullish else -excess
        r["entry_date"], r["exit_date"] = ed.date().isoformat(), xd.date().isoformat()
        r["entry_px"], r["exit_px"] = round(epx, 4), round(xpx, 4)
        r["ret_pct"], r["bench_pct"] = round(sret * 100, 3), round(bret * 100, 3)
        r["excess_pct"] = round(excess * 100, 3)
        r["call_excess_pct"] = round(call_excess * 100, 3)
        r["hit"] = bool(hit)
        r["settled"] = True
        n += 1
    return n


def _side_stats(rows, view):
    s = [r for r in rows if _is_true(r.get("settled")) and r.get("view") == view]
    if not s:
        return {"n": 0, "hit_pct": None, "mean_call_excess_pct": None}
    hit = sum(1 for r in s if _is_true(r.get("hit")))
    ce = np.array([float(r["call_excess_pct"]) for r in s], float)
    return {"n": len(s), "hit_pct": round(hit / len(s) * 100, 1),
            "mean_call_excess_pct": round(float(ce.mean()), 3)}


def _scorecard(rows):
    settled = [r for r in rows if _is_true(r.get("settled"))]
    n = len(settled)
    n_hit = sum(1 for r in settled if _is_true(r.get("hit")))
    n_pending = sum(1 for r in rows
                    if not _is_true(r.get("settled")) and not _is_true(r.get("dropped")))
    n_dropped = sum(1 for r in rows if _is_true(r.get("dropped")))
    return {
        "n_settled": n, "n_hit": n_hit,
        "call_hit_pct": round(n_hit / n * 100, 1) if n else None,
        "bullish": _side_stats(rows, "看好"),
        "bearish": _side_stats(rows, "看淡"),
        "n_pending": n_pending, "n_dropped": n_dropped,
        "dropped_pct": round(n_dropped / max(1, n + n_dropped) * 100, 1),
    }


def _verdict(sc):
    n = sc["n_settled"]
    if n == 0:
        return "刚上线·0 结算——约 1 个月后才有第一批荐股战绩，攒数据中。"
    ch = sc["call_hit_pct"]
    head = f"已结算 {n} 条荐股：判断对(看好跑赢/看淡跑输 QQQ)的比例 {ch}%"
    if n < 30:
        return head + f"（n={n} 太小，纯描述、不是结论）。"
    if 45 <= ch <= 55:
        return head + "——≈掷硬币，追动量没看出对 QQQ 的 edge（诚实）。"
    return head + "。重叠窗口/幸存者偏差未除，别当 edge。"


def run(write=True, prices=None):
    rows = _read_log()
    seen = {_key(r) for r in rows}

    n_new = 0
    for p in _load_picks():
        if _key(p) in seen:
            continue
        seen.add(_key(p))
        rows.append({**p, "entry_date": "", "entry_px": "", "exit_date": "", "exit_px": "",
                     "ret_pct": "", "bench_pct": "", "excess_pct": "", "call_excess_pct": "",
                     "hit": "", "settled": False, "dropped": False})
        n_new += 1

    settled_now = 0
    unsettled = [r for r in rows if not _is_true(r.get("settled")) and not _is_true(r.get("dropped"))]
    if unsettled:
        try:                                   # 结算靠 yfinance 网络——出错不许拖垮流水线
            if prices is None:
                start = (datetime.date.today() - datetime.timedelta(days=HOLD_TD * 2 + 200)).isoformat()
                prices = _fetch_prices([r["symbol"] for r in unsettled], start)
            settled_now = _settle(rows, prices)
        except Exception as e:
            print(f"[荐股计分] 结算阶段出错(非致命,跳过本次结算): {e}")

    sc = _scorecard(rows)
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "动量+低波动 选股 → 前向公开计分",
        "pick_rule": PICK_RULE,
        "hold_td": HOLD_TD, "benchmark": BENCH,
        "track_record": sc,
        "recent": sorted(
            [{"symbol": r["symbol"], "view": r.get("view"), "pick_date": r.get("pick_date"),
              "mom_pct": _num(r.get("mom_pct")), "settled": _is_true(r.get("settled")),
              "dropped": _is_true(r.get("dropped")), "excess_pct": _num(r.get("excess_pct")),
              "call_excess_pct": _num(r.get("call_excess_pct")), "hit": _is_true(r.get("hit"))}
             for r in rows],
            key=lambda x: (x["pick_date"] or ""), reverse=True)[:40],
        "verdict": _verdict(sc),
        "caveat": ("出格区·荐股前向公开计分。挑票规则=%s(透明·可换;2026-06-26 起,此前为裸6月动量),"
                   "进 append-only 账本:出榜次日入场、持有 %d 交易日、相对 %s 结算。"
                   "看好命中=跑赢QQQ、看淡命中=跑输QQQ。**前向计分**:刚上线样本极小(约1月后首批),别当结论。"
                   "规则更稳健(低波动异象+动量有文献支持)但未经我们回测,由公开计分裁决。"
                   "幸存者偏差%s%%因退市/无价被丢;重叠窗口只看描述;"
                   "相关≠因果;非投资建议、不可交易(成本/滑点/税)、会错、过去≠未来。每跑 append 认账。"
                   % (PICK_RULE, HOLD_TD, BENCH, sc["dropped_pct"])),
    }

    if write:
        from util_io import write_json
        write_json("picks.json", out)
        _write_log(rows)
        print(f"[OK] picks.json — {out['verdict']}")
        print(f"  新增 {n_new} 条 · 本次新结算 {settled_now} · 已结算 {sc['n_settled']} "
              f"(判断对 {sc['call_hit_pct']}%) · 挂账 {sc['n_pending']} · 丢弃 {sc['n_dropped']}")
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    run()
