"""fomc_study.py — Pre-FOMC drift event study.

Prior: Lucca & Moench (2015, JF) document that U.S. equity returns are elevated
in the ~24h window BEFORE scheduled FOMC announcements. This script tests whether
that pattern appears in the SP500 daily return series in this repo.

Method
------
- Unit of analysis: daily SP500 returns (pct-change, from placebo_test.load_sp500_daily).
- Selection (pre_window=1): for each scheduled FOMC announcement date, find the
  *prior* available trading day in the SP500 index. That is the "pre-FOMC day."
- y: up-indicator (return > 0) cast to float — consistent with autodiscovery framework.
- Overall comparison: up-rate on pre-FOMC days vs all other days, with
  block_bootstrap_diff (block=20, B=2000) for a two-sided p-value.
- Per-decade breakdown: mirrors autodiscovery._decade_rows style.
- Verdict: significant only if p < 0.05 AND n_fomc_days >= 10.

Honesty policy
--------------
This is an exploratory study. Pre-FOMC drift was documented through ~2013 in the
original paper; whether it persists OOS is an empirical question. Results are
reported as-is. Whether to promote this into candidate_space.py FDR pool is
the main brain's decision — NOT made here.

Emergency/inter-meeting Fed actions are excluded (only scheduled meetings).
"""

import sys
import datetime
import pandas as pd
import numpy as np
from pathlib import Path

# Make scripts importable when run directly
_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from placebo_test import load_sp500_daily
from walk_forward import block_bootstrap_diff
from fomc_dates import load_fomc_dates, pre_fomc_mask   # pre_fomc_mask = single source of truth for the label
from util_io import write_json


def _decade_rows_fomc(idx, sel, up):
    """Per-decade: pre-FOMC up-rate vs that decade's base. Mirrors autodiscovery._decade_rows."""
    idx = pd.DatetimeIndex(idx)
    dec = (idx.year // 10) * 10
    sel = np.asarray(sel, dtype=bool)
    up = np.asarray(up, dtype=float)
    out = []
    for d in sorted(set(int(x) for x in dec)):
        m = dec == d
        tm = m & sel
        n_fomc = int(tm.sum())
        n_decade = int(m.sum())
        if n_decade < 30 or n_fomc < 5:
            # Too sparse — skip rather than report noise
            continue
        ut = float(up[tm].mean())
        ub = float(up[m].mean())
        out.append({
            "decade": f"{d}s",
            "pre_fomc_up_pct": round(ut * 100, 1),
            "base_up_pct": round(ub * 100, 1),
            "diff_pp": round((ut - ub) * 100, 1),
            "n": n_fomc,
        })
    return out


def run(write=True, _load_returns=None, _load_fomc=None):
    """Run the pre-FOMC drift study.

    Parameters
    ----------
    write : bool
        If True, write fomc_study.json via util_io.write_json.
    _load_returns : callable or None
        Injected for testing. Defaults to placebo_test.load_sp500_daily.
    _load_fomc : callable or None
        Injected for testing. Defaults to fomc_dates.load_fomc_dates.

    Returns
    -------
    dict  The output payload (same as what is written to JSON).
    """
    load_returns = _load_returns if _load_returns is not None else load_sp500_daily
    load_fomc = _load_fomc if _load_fomc is not None else load_fomc_dates

    sp = load_returns()  # Series indexed by Timestamp, values = daily pct-change
    fomc_ts = load_fomc()  # sorted list of Timestamps

    PRE_WINDOW = 1

    # --- Map FOMC dates to prior trading days (shared label, no drift vs the FDR candidate) ---
    sel, n_matched = pre_fomc_mask(sp.index, pre_window=PRE_WINDOW, dates=fomc_ts)
    y = (sp.values > 0).astype(float)  # up-indicator (this standalone study reports UP-RATE;
    #   note: the FDR candidate in autodiscovery tests the one-sided MEAN-RETURN prior — same
    #   label via pre_fomc_mask, different statistic by design. See discoveries.html note.

    n_fomc_days = int(sel.sum())
    n_total = len(sp)

    # --- Overall stats ---
    pre_up = float(y[sel].mean()) if n_fomc_days > 0 else float("nan")
    base_up = float(y.mean())

    bb = block_bootstrap_diff(sel, y, block=20, B=2000, seed=42)

    if bb is not None:
        diff_pp = bb["diff"]
        p_val = bb["p_boot"]
        ci95 = bb["ci95"]
    else:
        diff_pp = round((pre_up - base_up) * 100, 2) if n_fomc_days > 0 else None
        p_val = None
        ci95 = None

    # --- Per-decade breakdown ---
    decades = _decade_rows_fomc(sp.index, sel, y)

    # --- Honest verdict ---
    MIN_N = 10
    if n_fomc_days < MIN_N:
        verdict = f"样本不足（n={n_fomc_days} < {MIN_N}）— 无定论，先保留结论"
    elif p_val is None:
        verdict = "无法计算p值 — 无定论"
    elif p_val < 0.05:
        verdict = (
            f"探索性显著: 前FOMC日上涨率 {pre_up*100:.1f}% vs 基率 {base_up*100:.1f}% "
            f"(+{diff_pp:.1f}pp, p={p_val:.3f}, n={n_fomc_days}). "
            "注：探索性结果，未经FDR多重比较校正，勿直接交易。"
        )
    else:
        verdict = (
            f"效应未显现: 前FOMC日上涨率 {pre_up*100:.1f}% vs 基率 {base_up*100:.1f}% "
            f"({diff_pp:+.1f}pp, p={p_val:.3f}, n={n_fomc_days}) — "
            "样本充足但 p≥0.05，暂列无定论/inconclusive。"
        )

    caveat = (
        "探索性研究·非荐股·非投资建议。"
        f"样本 n={n_fomc_days} 个预FOMC交易日，仅含计划会议（排除紧急会议）。"
        "过去规律≠未来表现。"
        "未经FDR多重比较校正：若此为多候选检验之一，需纳入FDR池再下结论。"
        "如样本较少先保留结论，待主脑决定是否纳入 candidate_space。"
    )

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Lucca & Moench 2015 (JF) prior; Federal Reserve FOMC scheduled dates",
        "n_fomc_dates_in_list": len(fomc_ts),
        "n_fomc_days": n_fomc_days,
        "n_fomc_matched": n_matched,
        "pre_window": PRE_WINDOW,
        "overall": {
            "up_pct": round(pre_up * 100, 2) if not (pre_up != pre_up) else None,
            "base_pct": round(base_up * 100, 2),
            "diff_pp": diff_pp,
            "ci95": ci95,
            "p": p_val,
            "n": n_fomc_days,
        },
        "decades": decades,
        "verdict": verdict,
        "caveat": caveat,
    }

    if write:
        written = write_json("fomc_study.json", out, allow_nan=False)
        for d in written:
            print(f"  Written: {d}/fomc_study.json")

    return out


if __name__ == "__main__":
    result = run(write=True)
    ov = result["overall"]
    print(f"\n=== Pre-FOMC Drift Study ===")
    print(f"  FOMC dates in list  : {result['n_fomc_dates_in_list']}")
    print(f"  Matched trading days: {result['n_fomc_days']}")
    print(f"  Pre-FOMC up%        : {ov['up_pct']}")
    print(f"  Base up%            : {ov['base_pct']}")
    print(f"  Diff (pp)           : {ov['diff_pp']}")
    print(f"  95% CI              : {ov['ci95']}")
    print(f"  p (boot)            : {ov['p']}")
    print()
    print(f"Verdict: {result['verdict']}")
    print()
    if result["decades"]:
        print("Per-decade breakdown:")
        print(f"  {'Decade':<8} {'PreFOMC%':>9} {'Base%':>7} {'Diff(pp)':>9} {'n':>5}")
        for row in result["decades"]:
            print(f"  {row['decade']:<8} {row['pre_fomc_up_pct']:>9.1f} "
                  f"{row['base_up_pct']:>7.1f} {row['diff_pp']:>+9.1f} {row['n']:>5}")
    else:
        print("(No decade rows — insufficient data per decade)")
    print()
    print(f"Caveat: {result['caveat']}")
