"""forward_ledger.py — 前向公开计分账本的共享机械件（DRY 掉 insider_signal/pick_ledger… 的重复脚手架）。

只放**机械、各信号一模一样**的部分：append-only CSV 账本 I/O、yfinance 批量取价、前向收益、
结算循环骨架、挂账/丢弃计数。**每个信号自己的判断**(挑什么、命中口径)留在各自脚本里——
通过注入 `followable_of(row)`(可跟单日) 和 `outcome_of(stock_ret, bench_ret, row)→dict(结算列)` 传入。
这样：① 加新计分信号 = 写「源 + 命中口径」配置，不再克隆 ~280 行；② 结算/取价 bug 一处修。

红线不变：账本 append-only(结算只填空、绝不改历史行)；结算靠网络出错由调用方兜不阻断流水线。
"""
import csv

import pandas as pd

_TRUE = ("true", "1", "yes")


def is_true(v):
    return str(v).strip().lower() in _TRUE


# ── append-only 账本 I/O（结算只填空，不改信号身份）────────────────────
def read_log(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_log(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})


# ── yfinance 批量取价（含基准；可被测试用 prices= 注入旁路，故不在热路径强依赖）──
def fetch_prices(symbols, start, bench):
    import yfinance as yf
    cols = {}
    uniq = sorted({s for s in symbols if s} | {bench})
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


# ── 单条前向收益：可跟单日起首个交易日入场、持有 hold（日历或交易日）──────
def fwd(series, followable, hold, trading_days=False):
    """返回 (ret, entry_date, exit_date, entry_px, exit_px)；窗未走完→"pending"；无价→None。
    trading_days=False：hold 为日历天数（exit=入场+hold 日历日内最后一个交易日）；
    trading_days=True ：hold 为交易日数（exit=入场后第 hold 个交易日）。"""
    if series is None or series.empty:
        return None
    f = pd.Timestamp(followable)
    after = series.index[series.index >= f]
    if len(after) == 0:
        return "pending" if f > series.index[-1] else None
    ed = after[0]
    if trading_days:
        pos = series.index.get_indexer([ed])[0]
        if pos < 0 or pos + hold >= len(series):
            return "pending"
        xd = series.index[pos + hold]
    else:
        target = ed + pd.Timedelta(days=hold)
        if target > series.index[-1]:
            return "pending"
        xd = series.index[series.index <= target][-1]
    epx, xpx = float(series.loc[ed]), float(series.loc[xd])
    if epx <= 0:
        return None
    return (xpx / epx - 1.0, ed, xd, epx, xpx)


# ── 结算循环骨架：填 entry/exit/settled/dropped；命中口径由 outcome_of 注入 ──
def settle(rows, px, *, bench, hold, trading_days, symbol_key, followable_of, outcome_of):
    """给未结算行结算：基准&标的窗口都走完→填结算列；标的无价→标 dropped。返回新结算数。
    - followable_of(row) → 该行可跟单日；outcome_of(stock_ret, bench_ret, row) → dict(信号专属结算列)。"""
    bser = px.get(bench)
    n = 0
    for r in rows:
        if is_true(r.get("settled")) or is_true(r.get("dropped")):
            continue
        f = followable_of(r)
        b = fwd(bser, f, hold, trading_days)
        if b == "pending" or b is None:                 # 基准没结算 → 整体挂账
            continue
        s = fwd(px.get(r.get(symbol_key)), f, hold, trading_days)
        if s == "pending":
            continue
        if s is None:                                    # 退市/无价 → 透明丢弃
            r["dropped"] = True
            n += 1
            continue
        sret, ed, xd, epx, xpx = s
        r["entry_date"], r["exit_date"] = ed.date().isoformat(), xd.date().isoformat()
        r["entry_px"], r["exit_px"] = round(epx, 4), round(xpx, 4)
        r.update(outcome_of(sret, b[0], r))              # 各信号自己的命中/超额列
        r["settled"] = True
        n += 1
    return n


def count_pending_dropped(rows):
    """挂账(未结算未丢弃)、丢弃、丢弃率——各信号 scorecard 共用的计数。"""
    n_pending = sum(1 for r in rows if not is_true(r.get("settled")) and not is_true(r.get("dropped")))
    n_dropped = sum(1 for r in rows if is_true(r.get("dropped")))
    return n_pending, n_dropped
