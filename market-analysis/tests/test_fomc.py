"""test_fomc.py — Tests for pre-FOMC drift event study.

Tests cover:
  1. fomc_dates: structural validity (sorted, unique, ISO, count, anchor dates).
  2. fomc_study.run(): shape/keys, planted positive drift, thin-data inconclusive path.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fomc_dates as fd
import fomc_study as fs


# ─────────────────────────────────────────────────────────────────────────────
# 1. fomc_dates tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFomcDates:
    def setup_method(self):
        self.dates = fd.load_fomc_dates()

    def test_returns_list_of_timestamps(self):
        assert isinstance(self.dates, list)
        assert len(self.dates) > 0
        assert all(isinstance(d, pd.Timestamp) for d in self.dates)

    def test_sorted(self):
        assert self.dates == sorted(self.dates), "Dates must be in ascending order"

    def test_unique(self):
        assert len(self.dates) == len(set(self.dates)), "Dates must be unique"

    def test_valid_iso_strings_in_raw_list(self):
        """All raw strings in FOMC_DATES must be parseable ISO dates."""
        for s in fd.FOMC_DATES:
            parsed = pd.Timestamp(s)
            assert parsed.year >= 2000, f"Expected coverage from 2000+, got {s}"
            assert parsed.year <= 2026, f"Unexpected future date: {s}"

    def test_count_plausible(self):
        """~8 meetings/year; allow ±25% band (6–10/year)."""
        dates = self.dates
        if not dates:
            pytest.skip("No dates to check")
        start_year = dates[0].year
        end_year = dates[-1].year
        n_years = end_year - start_year + 1
        expected_nominal = 8 * n_years
        # ±25% tolerance
        lo = int(expected_nominal * 0.75)
        hi = int(expected_nominal * 1.25)
        n = len(dates)
        assert lo <= n <= hi, (
            f"Expected {lo}–{hi} dates for {n_years} years (8/yr ±25%), got {n}"
        )

    def test_well_known_anchor_dates_present(self):
        """A few high-confidence anchor dates from public Fed calendars."""
        date_set = set(self.dates)
        # December 2015 liftoff — first rate hike since 2006, extremely well-documented
        assert pd.Timestamp("2015-12-16") in date_set, (
            "2015-12-16 (December 2015 liftoff) should be in FOMC dates"
        )
        # December 2008 — zero lower bound announcement, one of the most cited meetings
        assert pd.Timestamp("2008-12-16") in date_set, (
            "2008-12-16 (ZLB announcement) should be in FOMC dates"
        )
        # December 2022 — part of the aggressive 2022 tightening cycle
        assert pd.Timestamp("2022-12-14") in date_set, (
            "2022-12-14 (2022 tightening cycle meeting) should be in FOMC dates"
        )

    def test_coverage_range(self):
        """Dates should span at least 2000–2025."""
        years = {d.year for d in self.dates}
        assert 2000 in years, "Coverage should include year 2000"
        assert 2025 in years, "Coverage should include year 2025"

    def test_all_weekdays(self):
        """FOMC announcements always happen on business days (Mon–Fri)."""
        non_weekdays = [d for d in self.dates if d.weekday() >= 5]
        assert len(non_weekdays) == 0, (
            f"Found FOMC dates on weekends: {non_weekdays}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. fomc_study tests
# ─────────────────────────────────────────────────────────────────────────────

def _make_sp_series(n_days=500, seed=99):
    """Synthetic daily return series: pure white noise, no drift."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2010-01-04", periods=n_days, freq="B")
    returns = rng.normal(0.0005, 0.01, size=n_days)
    return pd.Series(returns, index=dates, name="SP500")


def _make_sp_series_with_fomc_drift(fomc_dates_list, n_days=500, drift=0.02, seed=42):
    """Synthetic returns with PLANTED positive drift on pre-FOMC days.

    For each FOMC date in fomc_dates_list, the trading day before it gets
    return = base_noise + drift to plant a detectable positive signal.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2010-01-04", periods=n_days, freq="B")
    returns = rng.normal(0.0005, 0.01, size=n_days)
    s = pd.Series(returns.copy(), index=dates, name="SP500")

    # Plant drift on pre-FOMC days
    date_arr = np.array(dates)
    for fd_ts in fomc_dates_list:
        fd_np = np.datetime64(fd_ts, "ns")
        pos = int(np.searchsorted(date_arr, fd_np, side="left"))
        if pos >= 1:
            s.iloc[pos - 1] = drift  # strong planted positive return

    return s


class TestFomcStudyShape:
    """Test that run(write=False) returns a dict with expected keys."""

    def test_output_keys(self, monkeypatch):
        sp = _make_sp_series(n_days=300)
        # Use 3 fake FOMC dates within range
        fake_fomc = [
            pd.Timestamp("2010-06-10"),
            pd.Timestamp("2010-09-15"),
            pd.Timestamp("2011-01-05"),
        ]
        result = fs.run(
            write=False,
            _load_returns=lambda: sp,
            _load_fomc=lambda: fake_fomc,
        )
        assert isinstance(result, dict), "run() must return a dict"
        for key in ("generated", "n_fomc_days", "pre_window", "overall", "decades",
                    "verdict", "caveat"):
            assert key in result, f"Missing key: {key}"

    def test_overall_keys(self, monkeypatch):
        sp = _make_sp_series(n_days=300)
        fake_fomc = [pd.Timestamp("2010-06-10"), pd.Timestamp("2011-01-05")]
        result = fs.run(write=False, _load_returns=lambda: sp, _load_fomc=lambda: fake_fomc)
        ov = result["overall"]
        for k in ("up_pct", "base_pct", "diff_pp", "p", "n"):
            assert k in ov, f"overall missing key: {k}"

    def test_pre_window_recorded(self):
        sp = _make_sp_series(n_days=200)
        fake_fomc = [pd.Timestamp("2010-06-10")]
        result = fs.run(write=False, _load_returns=lambda: sp, _load_fomc=lambda: fake_fomc)
        assert result["pre_window"] == 1

    def test_caveat_present_and_nonempty(self):
        sp = _make_sp_series(n_days=300)
        fake_fomc = [pd.Timestamp("2010-06-10"), pd.Timestamp("2011-01-05")]
        result = fs.run(write=False, _load_returns=lambda: sp, _load_fomc=lambda: fake_fomc)
        assert isinstance(result["caveat"], str) and len(result["caveat"]) > 10


class TestFomcStudyDrift:
    """Plant a strong pre-FOMC signal and verify the study detects positive diff_pp."""

    def test_planted_positive_drift_detected(self):
        """With a strongly planted pre-FOMC drift, diff_pp should be > 0."""
        # Use many FOMC dates to get n > 10 (needed for bootstrap)
        fake_fomc = [
            pd.Timestamp(f"201{y}-{m:02d}-15")
            for y in range(0, 5)   # 2010–2014
            for m in [2, 4, 6, 8, 10, 12]
        ]
        sp = _make_sp_series_with_fomc_drift(fake_fomc, n_days=1500, drift=0.05, seed=7)
        result = fs.run(write=False, _load_returns=lambda: sp, _load_fomc=lambda: fake_fomc)

        n = result["n_fomc_days"]
        assert n > 0, "Should match at least some pre-FOMC days"

        diff_pp = result["overall"]["diff_pp"]
        assert diff_pp is not None, "diff_pp should not be None with planted drift"
        assert diff_pp > 0, (
            f"Expected positive diff_pp with planted pre-FOMC drift, got {diff_pp}"
        )

    def test_planted_drift_up_pct_above_base(self):
        """Pre-FOMC up% should exceed base up% when drift is planted."""
        fake_fomc = [
            pd.Timestamp(f"201{y}-{m:02d}-15")
            for y in range(0, 5)
            for m in [2, 5, 8, 11]
        ]
        sp = _make_sp_series_with_fomc_drift(fake_fomc, n_days=1500, drift=0.06, seed=11)
        result = fs.run(write=False, _load_returns=lambda: sp, _load_fomc=lambda: fake_fomc)

        ov = result["overall"]
        if ov["up_pct"] is not None and ov["base_pct"] is not None:
            assert ov["up_pct"] > ov["base_pct"], (
                f"Pre-FOMC up% {ov['up_pct']} should exceed base {ov['base_pct']} "
                "when drift is planted"
            )


class TestFomcStudyThinData:
    """Thin data (few pre-FOMC days) should yield inconclusive verdict, not forced conclusion."""

    def test_zero_fomc_dates(self):
        """No FOMC dates → n=0, verdict must not claim significance."""
        sp = _make_sp_series(n_days=100)
        result = fs.run(write=False, _load_returns=lambda: sp, _load_fomc=lambda: [])
        assert result["n_fomc_days"] == 0
        # Verdict must not contain language asserting significance
        v = result["verdict"].lower()
        assert "显著" not in v or "不足" in v or "inconclusive" in v.lower(), (
            "With zero FOMC days, verdict should not claim significance"
        )

    def test_thin_fomc_sample_inconclusive(self):
        """Fewer than MIN_N=10 pre-FOMC days → verdict mentions 无定论 or 样本不足."""
        sp = _make_sp_series(n_days=200, seed=5)
        # Only 3 FOMC dates → at most 3 pre-FOMC days → thin
        thin_fomc = [
            pd.Timestamp("2010-03-10"),
            pd.Timestamp("2010-07-14"),
            pd.Timestamp("2010-11-03"),
        ]
        result = fs.run(write=False, _load_returns=lambda: sp, _load_fomc=lambda: thin_fomc)
        n = result["n_fomc_days"]
        assert n < 10, f"Expected thin sample, got n={n}"
        v = result["verdict"]
        # Must not assert significance on thin sample
        assert ("无定论" in v or "不足" in v or "inconclusive" in v.lower()), (
            f"Thin sample verdict should be inconclusive, got: {v}"
        )

    def test_fomc_dates_outside_sp_range_silently_skipped(self):
        """FOMC dates before SP series starts should be skipped gracefully."""
        sp = _make_sp_series(n_days=50)  # starts 2010-01-04
        old_fomc = [pd.Timestamp("1998-01-28"), pd.Timestamp("1998-03-31")]
        result = fs.run(write=False, _load_returns=lambda: sp, _load_fomc=lambda: old_fomc)
        assert result["n_fomc_days"] == 0
        assert result["overall"]["n"] == 0
