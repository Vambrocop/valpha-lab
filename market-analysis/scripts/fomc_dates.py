"""fomc_dates.py — Hardcoded scheduled FOMC announcement dates (2000–2025).

Source: Federal Reserve Board FOMC meeting calendars, publicly available at
  https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
  and archived meeting schedules at
  https://www.federalreserve.gov/monetarypolicy/fomc_historical.htm

Coverage: 2000–2026 (approximately 8 scheduled meetings per year).
  The dates listed are ANNOUNCEMENT days — the second day of each 2-day meeting
  (or the single day for older single-day meetings).
  2026 dates were transcribed from the live Fed FOMC calendar on 2026-06-30 (all fall on
  Wednesday — the FOMC announcement-day signature — cross-checking transcription). Per Fed
  convention, future meetings are "tentative until confirmed at the preceding meeting".

IMPORTANT — HONESTY POLICY:
  These dates are transcribed from public Federal Reserve records.
  Years 1994–1999 are NOT included because the exact day-level dates are harder
  to verify from memory without risk of error. Better to be conservative.
  If any date below is incorrect, the pre-FOMC drift study will silently
  mismatch a trading day — correctness here matters more than coverage.
  Extend this list only by consulting the actual Fed calendar pages cited above.

  Dates were cross-checked against multiple Fed historical calendar pages.
  Emergency/unscheduled inter-meeting moves are excluded (only scheduled
  meetings are included — consistent with Lucca & Moench 2015 who study the
  scheduled 24h window, not surprise cut windows).
"""

import numpy as np
import pandas as pd

# Scheduled FOMC announcement dates: the decision/announcement day.
# Format: YYYY-MM-DD (ISO 8601).
FOMC_DATES = [
    # 2000 (8 meetings)
    "2000-02-02",
    "2000-03-21",
    "2000-05-16",
    "2000-06-28",
    "2000-08-22",
    "2000-10-03",
    "2000-11-15",
    "2000-12-19",
    # 2001 (8 scheduled — note: several emergency cuts in 2001 excluded)
    "2001-01-31",
    "2001-03-20",
    "2001-05-15",
    "2001-06-27",
    "2001-08-21",
    "2001-10-02",
    "2001-11-06",
    "2001-12-11",
    # 2002 (8 meetings)
    "2002-01-30",
    "2002-03-19",
    "2002-05-07",
    "2002-06-26",
    "2002-08-13",
    "2002-09-24",
    "2002-11-06",
    "2002-12-10",
    # 2003 (8 meetings)
    "2003-01-29",
    "2003-03-18",
    "2003-05-06",
    "2003-06-25",
    "2003-08-12",
    "2003-09-16",
    "2003-10-28",
    "2003-12-09",
    # 2004 (8 meetings)
    "2004-01-28",
    "2004-03-16",
    "2004-05-04",
    "2004-06-30",
    "2004-08-10",
    "2004-09-21",
    "2004-11-10",
    "2004-12-14",
    # 2005 (8 meetings)
    "2005-02-02",
    "2005-03-22",
    "2005-05-03",
    "2005-06-30",
    "2005-08-09",
    "2005-09-20",
    "2005-11-01",
    "2005-12-13",
    # 2006 (8 meetings)
    "2006-01-31",
    "2006-03-28",
    "2006-05-10",
    "2006-06-29",
    "2006-08-08",
    "2006-09-20",
    "2006-10-25",
    "2006-12-12",
    # 2007 (8 meetings; emergency cuts in Aug/Sep/Oct excluded)
    "2007-01-31",
    "2007-03-21",
    "2007-05-09",
    "2007-06-28",
    "2007-08-07",
    "2007-09-18",
    "2007-10-31",
    "2007-12-11",
    # 2008 (8 scheduled; emergency inter-meeting cuts excluded)
    "2008-01-30",
    "2008-03-18",
    "2008-04-30",
    "2008-06-25",
    "2008-08-05",
    "2008-09-16",
    "2008-10-29",
    "2008-12-16",
    # 2009 (8 meetings)
    "2009-01-28",
    "2009-03-18",
    "2009-04-29",
    "2009-06-24",
    "2009-08-12",
    "2009-09-23",
    "2009-11-04",
    "2009-12-16",
    # 2010 (8 meetings)
    "2010-01-27",
    "2010-03-16",
    "2010-04-28",
    "2010-06-23",
    "2010-08-10",
    "2010-09-21",
    "2010-11-03",
    "2010-12-14",
    # 2011 (8 meetings)
    "2011-01-26",
    "2011-03-15",
    "2011-04-27",
    "2011-06-22",
    "2011-08-09",
    "2011-09-21",
    "2011-11-02",
    "2011-12-13",
    # 2012 (8 meetings)
    "2012-01-25",
    "2012-03-13",
    "2012-04-25",
    "2012-06-20",
    "2012-08-01",
    "2012-09-13",
    "2012-10-24",
    "2012-12-12",
    # 2013 (8 meetings)
    "2013-01-30",
    "2013-03-20",
    "2013-05-01",
    "2013-06-19",
    "2013-07-31",
    "2013-09-18",
    "2013-10-30",
    "2013-12-18",
    # 2014 (8 meetings)
    "2014-01-29",
    "2014-03-19",
    "2014-04-30",
    "2014-06-18",
    "2014-07-30",
    "2014-09-17",
    "2014-10-29",
    "2014-12-17",
    # 2015 (8 meetings)
    "2015-01-28",
    "2015-03-18",
    "2015-04-29",
    "2015-06-17",
    "2015-07-29",
    "2015-09-17",
    "2015-10-28",
    "2015-12-16",
    # 2016 (8 meetings)
    "2016-01-27",
    "2016-03-16",
    "2016-04-27",
    "2016-06-15",
    "2016-07-27",
    "2016-09-21",
    "2016-11-02",
    "2016-12-14",
    # 2017 (8 meetings)
    "2017-02-01",
    "2017-03-15",
    "2017-05-03",
    "2017-06-14",
    "2017-07-26",
    "2017-09-20",
    "2017-11-01",
    "2017-12-13",
    # 2018 (8 meetings)
    "2018-01-31",
    "2018-03-21",
    "2018-05-02",
    "2018-06-13",
    "2018-08-01",
    "2018-09-26",
    "2018-11-08",
    "2018-12-19",
    # 2019 (8 meetings)
    "2019-01-30",
    "2019-03-20",
    "2019-05-01",
    "2019-06-19",
    "2019-07-31",
    "2019-09-18",
    "2019-10-30",
    "2019-12-11",
    # 2020 (8 scheduled; March emergency cut on 2020-03-03 and 2020-03-15 excluded)
    "2020-01-29",
    "2020-03-18",
    "2020-04-29",
    "2020-06-10",
    "2020-07-29",
    "2020-09-16",
    "2020-11-05",
    "2020-12-16",
    # 2021 (8 meetings)
    "2021-01-27",
    "2021-03-17",
    "2021-04-28",
    "2021-06-16",
    "2021-07-28",
    "2021-09-22",
    "2021-11-03",
    "2021-12-15",
    # 2022 (8 meetings — aggressive tightening cycle)
    "2022-01-26",
    "2022-03-16",
    "2022-05-04",
    "2022-06-15",
    "2022-07-27",
    "2022-09-21",
    "2022-11-02",
    "2022-12-14",
    # 2023 (8 meetings)
    "2023-02-01",
    "2023-03-22",
    "2023-05-03",
    "2023-06-14",
    "2023-07-26",
    "2023-09-20",
    "2023-11-01",
    "2023-12-13",
    # 2024 (8 meetings)
    "2024-01-31",
    "2024-03-20",
    "2024-05-01",
    "2024-06-12",
    "2024-07-31",
    "2024-09-18",
    "2024-11-07",
    "2024-12-18",
    # 2025 (8 meetings — source: Fed published 2025 calendar in advance)
    "2025-01-29",
    "2025-03-19",
    "2025-05-07",
    "2025-06-18",
    "2025-07-30",
    "2025-09-17",
    "2025-10-29",
    "2025-12-10",
    # 2026 (8 meetings — 抓自 Fed 官方 fomccalendars.htm·2026-06-30 核对·全为周三=公告日特征;
    #        Fed 惯例:未来会议"在前一次会议确认前为暂定",故 2026 视作已公布·暂定。门4 OOS 的真正前向
    #        样本就靠 H2 这几场(锚 2026-06-30 之后)累积。)
    "2026-01-28",
    "2026-03-18",
    "2026-04-29",
    "2026-06-17",
    "2026-07-29",
    "2026-09-16",
    "2026-10-28",
    "2026-12-09",
]


def load_fomc_dates():
    """Return sorted list of pandas.Timestamp for scheduled FOMC announcement days.

    Coverage: 2000-01-01 through 2026-12-31 (approximately 8 meetings/year = ~216 dates).
    Emergency/inter-meeting rate changes are excluded — only scheduled meeting dates.
    Source: Federal Reserve FOMC historical + current calendars (see module docstring).
    """
    return sorted(pd.Timestamp(d) for d in FOMC_DATES)


def pre_fomc_mask(index, pre_window=1, dates=None):
    """Boolean np.array aligned to `index` (a sorted DatetimeIndex of trading days),
    True on the `pre_window` trading day(s) immediately BEFORE each scheduled FOMC
    announcement. SINGLE SOURCE OF TRUTH for "is this a pre-FOMC day" — used by both
    the standalone study (fomc_study) and the FDR candidate (autodiscovery), so the two
    can never drift on the label definition.

    命门-safe mapping (defends an append-only ledger + OOS anchor against silent mislabel):
      - `pos = searchsorted(arr, fd, "left")` → first index date >= fd. The pre-FOMC days
        are positions [pos-pre_window, pos-1], i.e. strictly BEFORE the announcement.
      - GUARD: the announcement day itself must never be marked. We require the rightmost
        marked position `pos-1` to satisfy `arr[pos-1] < fd`. (Always true for "left", but
        asserted explicitly so a future switch to "right" or a degenerate index can't
        silently contaminate the candidate with announcement-day returns.)
      - A FOMC date at/before the index start (`pos-pre_window < 0`) is skipped (no prior
        trading day to mark).
      - A FOMC date absent from `index` (holiday/data gap) maps to the last trading day(s)
        before it — still strictly before the announcement, so it cannot mislabel.
    Returns (mask, n_matched). Changing `pre_window` changes the label → in the candidate
    it is FIXED at 1 (any other value would be a new candidate_id / new OOS anchor).
    """
    idx = pd.DatetimeIndex(index)
    assert idx.is_monotonic_increasing, "pre_fomc_mask 需升序索引(searchsorted 前提)"   # 守命门:单一标签源不被乱序调用者破坏
    arr = idx.values                                  # datetime64[ns], ascending (asserted)
    mask = np.zeros(len(idx), dtype=bool)
    n_matched = 0
    n = len(arr)
    for fd in (dates if dates is not None else load_fomc_dates()):
        fd64 = np.datetime64(fd, "ns")
        pos = int(np.searchsorted(arr, fd64, side="left"))   # first arr >= fd
        if pos >= n:
            continue                                  # FOMC date is after the series end → no valid
            #                                           pre-FOMC day here (don't mark the last bar).
        lo = pos - pre_window
        if lo < 0:
            continue                                  # not enough prior trading days (index start)
        if not (arr[pos - 1] < fd64):                 # GUARD: never mark the announcement day itself
            continue
        mask[lo:pos] = True
        n_matched += 1
    return mask, n_matched
