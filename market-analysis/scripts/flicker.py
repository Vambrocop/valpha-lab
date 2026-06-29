"""flicker.py — Anti-flicker / stability descriptive reader for the Valpha Lab self-growing loop.

HONESTY NOTE: This module is purely DESCRIPTIVE. It reads verdicts already written by the
autodiscovery pipeline; it computes NO new statistics and NO new p-values.

Key framing: the daily log is the SAME cumulative dataset re-snapshotted each day.
"Stable for N snapshots" ≈ ONE test re-read N times (autocorrelated), NOT N independent
confirmations. The only honest proxy for how long the log has been running is `span_days`.
True independent out-of-sample evidence lives in the door-4 OOS gate (oos_gate / 知识库).
"""

import csv
import datetime
from pathlib import Path

# LOG path derived from this file's location, not cwd.
LOG = Path(__file__).parent.parent / "data" / "autodiscovery_log.csv"


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def read_log(path=LOG):
    """Return all rows as a list of dicts (csv.DictReader). Empty file → []."""
    p = Path(path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Per-candidate computation
# ---------------------------------------------------------------------------

def _build_candidate(cid, dated_rows):
    """Build per-candidate stats dict from rows that share the same candidate_id.

    dated_rows: list of (date_str, row_dict), already sorted ascending by date.
    """
    # Collapse to ONE verdict per distinct date (in case of duplicates in raw data).
    seen = {}
    for date_str, row in dated_rows:
        if date_str not in seen:
            seen[date_str] = row["verdict"]
    ordered_dates = sorted(seen.keys())
    verdicts = [seen[d] for d in ordered_dates]

    snapshots = len(verdicts)
    latest_verdict = verdicts[-1] if verdicts else None

    # stable_days: consecutive trailing run of latest_verdict
    stable_days = 0
    for v in reversed(verdicts):
        if v == latest_verdict:
            stable_days += 1
        else:
            break

    # flips: count verdict changes across ordered history
    flips = sum(1 for i in range(1, len(verdicts)) if verdicts[i] != verdicts[i - 1])

    boundary_flicker = flips >= 2

    # Grab key/family from most recent row
    most_recent_row = next(
        r for _, r in sorted(dated_rows, key=lambda x: x[0], reverse=True)
        if True
    )

    return {
        "candidate_id": cid,
        "key": most_recent_row.get("key", ""),
        "family": most_recent_row.get("family", ""),
        "latest_verdict": latest_verdict,
        "snapshots": snapshots,
        "stable_days": stable_days,
        "flips": flips,
        "boundary_flicker": boundary_flicker,
    }


def compute_candidates(rows):
    """Group rows by candidate_id and build per-candidate dicts."""
    by_id = {}
    for row in rows:
        cid = row["candidate_id"]
        date_str = row["date"]
        by_id.setdefault(cid, []).append((date_str, row))

    return [_build_candidate(cid, dated_rows) for cid, dated_rows in by_id.items()]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def summarize(cands):
    """Return summary dict + sorted candidate list (flips desc, snapshots desc).

    n_stable: candidates with flips==0 AND snapshots>=2 (consistently same verdict
    across multiple reads — but note: still autocorrelated, not independent).
    """
    n_boundary_flicker = sum(1 for c in cands if c["boundary_flicker"])
    n_stable = sum(1 for c in cands if c["flips"] == 0 and c["snapshots"] >= 2)
    sorted_cands = sorted(cands, key=lambda c: (-c["flips"], -c["snapshots"]))
    return {
        "n_candidates": len(cands),
        "n_boundary_flicker": n_boundary_flicker,
        "n_stable": n_stable,
        "candidates": sorted_cands,
    }


# ---------------------------------------------------------------------------
# Caveat text (honesty-critical; do NOT weaken)
# ---------------------------------------------------------------------------

def _build_caveat(n_snapshots):
    base = (
        "诚实提醒：裁决稳定 N 天 != N 次独立确认——"
        "这是同一份累积数据反复重读（自相关）。"
        "真正独立的样本外证据看门4 OOS（oos_gate / 知识库），不是这里的稳定度。"
        "本页只用来抓【在 FDR 边界来回横跳的脆弱候选】。"
        "非荐股、探索性。"
    )
    if n_snapshots <= 1:
        base += (
            " 【注意：前向历史刚刚开始积累（当前仅 <=1 个快照），"
            "稳定度尚无意义，请等待更多每日快照后再看此页。】"
        )
    return base


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(write=True, path=LOG):
    """Assemble the flicker output dict; optionally write flicker.json.

    write=False is used in tests to avoid touching web/ / docs/.
    path allows tests to inject a temp CSV.
    """
    rows = read_log(path)

    # Distinct log dates (for span_days and n_snapshots)
    all_dates = sorted({r["date"] for r in rows} if rows else set())
    n_snapshots = len(all_dates)

    if n_snapshots >= 2:
        d0 = datetime.date.fromisoformat(all_dates[0])
        d1 = datetime.date.fromisoformat(all_dates[-1])
        span_days = (d1 - d0).days
    else:
        span_days = 0

    cands = compute_candidates(rows)
    summ = summarize(cands)

    caveat = _build_caveat(n_snapshots)

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    out = {
        "generated": generated,
        "n_snapshots": n_snapshots,
        "span_days": span_days,
        "summary": {
            "n_candidates": summ["n_candidates"],
            "n_boundary_flicker": summ["n_boundary_flicker"],
            "n_stable": summ["n_stable"],
        },
        "candidates": summ["candidates"],
        "caveat": caveat,
    }

    if write:
        from util_io import write_json
        write_json("flicker.json", out, allow_nan=False)

    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = run()
    n_c = result["summary"]["n_candidates"]
    n_bf = result["summary"]["n_boundary_flicker"]
    n_s = result["summary"]["n_stable"]
    ns = result["n_snapshots"]
    sd = result["span_days"]
    print(
        f"flicker.py: {n_c} candidates across {ns} snapshots ({sd} calendar days) | "
        f"boundary_flicker={n_bf} | stable(flips==0,snap>=2)={n_s}"
    )
