"""Tests for flicker.py — anti-flicker / stability descriptive reader.

All tests inject a temp CSV via path= argument; no real log is touched.
"""

import csv
import pytest
from pathlib import Path

import flicker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HEADER = ["date", "candidate_id", "key", "family", "verdict", "p", "recent_p"]


def write_csv(path, rows):
    """Write header + rows to path."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_csv(tmp_path):
    """Multi-candidate CSV covering the main test scenarios."""
    p = tmp_path / "autodiscovery_log.csv"
    rows = [
        # stable1: 3 dates, all survive → flips=0, stable_days=3
        ["2026-01-01", "stable1", "key_a", "calendar", "survive", "0.01", "0.02"],
        ["2026-01-02", "stable1", "key_a", "calendar", "survive", "0.01", "0.02"],
        ["2026-01-03", "stable1", "key_a", "calendar", "survive", "0.01", "0.02"],
        # flicker1: 4 dates dead/survive/dead/survive → flips=3, boundary_flicker=True
        ["2026-01-01", "flicker1", "key_b", "factor",   "dead",    "0.10", "0.20"],
        ["2026-01-02", "flicker1", "key_b", "factor",   "survive", "0.04", "0.05"],
        ["2026-01-03", "flicker1", "key_b", "factor",   "dead",    "0.11", "0.21"],
        ["2026-01-04", "flicker1", "key_b", "factor",   "survive", "0.03", "0.04"],
        # once1: 1 date only → snapshots=1, flips=0, stable_days=1
        ["2026-01-01", "once1",    "key_c", "rebound",  "faded",   "0.00", "0.50"],
    ]
    write_csv(p, rows)
    return p


@pytest.fixture()
def single_snapshot_csv(tmp_path):
    """CSV with only ONE distinct date (log just started)."""
    p = tmp_path / "single.csv"
    rows = [
        ["2026-06-22", "cand_x", "some_key", "calendar", "inconclusive", "0.30", "0.40"],
        ["2026-06-22", "cand_y", "other_key", "factor",  "dead",         "0.50", "0.60"],
    ]
    write_csv(p, rows)
    return p


# ---------------------------------------------------------------------------
# Per-candidate logic
# ---------------------------------------------------------------------------

def _find(cands, cid):
    return next(c for c in cands if c["candidate_id"] == cid)


def test_stable1(tmp_csv):
    rows = flicker.read_log(tmp_csv)
    cands = flicker.compute_candidates(rows)
    c = _find(cands, "stable1")
    assert c["flips"] == 0
    assert c["stable_days"] == 3
    assert c["boundary_flicker"] is False
    assert c["snapshots"] == 3
    assert c["latest_verdict"] == "survive"


def test_flicker1(tmp_csv):
    rows = flicker.read_log(tmp_csv)
    cands = flicker.compute_candidates(rows)
    c = _find(cands, "flicker1")
    assert c["flips"] == 3
    assert c["boundary_flicker"] is True
    assert c["latest_verdict"] == "survive"
    assert c["stable_days"] == 1


def test_once1(tmp_csv):
    rows = flicker.read_log(tmp_csv)
    cands = flicker.compute_candidates(rows)
    c = _find(cands, "once1")
    assert c["snapshots"] == 1
    assert c["flips"] == 0
    assert c["stable_days"] == 1


# ---------------------------------------------------------------------------
# summarize ordering and n_boundary_flicker
# ---------------------------------------------------------------------------

def test_summarize_ordering_and_counts(tmp_csv):
    rows = flicker.read_log(tmp_csv)
    cands = flicker.compute_candidates(rows)
    summ = flicker.summarize(cands)

    # flicker1 (flips=3) must appear before stable1 (flips=0)
    ids = [c["candidate_id"] for c in summ["candidates"]]
    assert ids.index("flicker1") < ids.index("stable1"), (
        "summarize must order by flips desc; flicker1 should come before stable1"
    )

    assert summ["n_boundary_flicker"] == 1, "Only flicker1 has flips>=2"
    assert summ["n_candidates"] == 3
    # stable1 has flips==0 and snapshots==3 >= 2 → counts as stable
    assert summ["n_stable"] == 1


# ---------------------------------------------------------------------------
# run() on ≤1-snapshot log doesn't crash; caveat honesty check
# ---------------------------------------------------------------------------

def test_run_single_snapshot_no_crash_and_caveat(single_snapshot_csv):
    """run(write=False) on a ≤1-snapshot log must not raise, and caveat must contain
    both the autocorrelation warning and 非荐股."""
    result = flicker.run(write=False, path=single_snapshot_csv)

    assert result["n_snapshots"] == 1
    assert result["span_days"] == 0

    caveat = result["caveat"]
    assert "自相关" in caveat or "独立确认" in caveat, (
        f"caveat must mention autocorrelation (自相关 or 独立确认); got: {caveat!r}"
    )
    assert "非荐股" in caveat, f"caveat must contain '非荐股'; got: {caveat!r}"

    # When <=1 snapshot the caveat should also flag that history just started
    assert "<=1" in caveat or "快照" in caveat or "刚刚开始" in caveat, (
        f"caveat for <=1 snapshot should mention that history just started; got: {caveat!r}"
    )


# ---------------------------------------------------------------------------
# run(write=False) on the multi-snapshot fixture — sanity check output shape
# ---------------------------------------------------------------------------

def test_run_multi_snapshot_shape(tmp_csv):
    result = flicker.run(write=False, path=tmp_csv)
    assert result["n_snapshots"] == 4      # Jan 1,2,3,4
    assert result["span_days"] == 3        # Jan 1 → Jan 4 = 3 days
    assert "generated" in result
    assert "caveat" in result
    assert len(result["candidates"]) == 3
    # caveat should NOT include the ≤1-snapshot warning for a multi-snapshot log
    assert "刚刚开始积累" not in result["caveat"]
