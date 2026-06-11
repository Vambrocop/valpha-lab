"""假日日历对照 NYSE 官方休市表（不含半日市，模型只用全日休市）"""
from datetime import date

from signal_model import us_holidays, HOLIDAY_SET

NYSE_2025 = ["2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18",
             "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01",
             "2025-11-27", "2025-12-25"]
NYSE_2026 = ["2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
             "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
             "2026-11-26", "2026-12-25"]


def test_2025_full_calendar():
    assert us_holidays(2025) == {date.fromisoformat(d) for d in NYSE_2025}


def test_2026_full_calendar():
    assert us_holidays(2026) == {date.fromisoformat(d) for d in NYSE_2026}


def test_juneteenth_only_since_2022():
    assert date(2021, 6, 18) not in us_holidays(2021)
    assert date(2021, 6, 19) not in us_holidays(2021)
    # 2022-06-19 是周日 → NYSE 周一 06-20 补休
    assert date(2022, 6, 20) in us_holidays(2022)


def test_weekend_observance():
    # 2026-07-04 周六 → 周五 07-03；2027-06-19 周六 → 周五 06-18
    assert date(2026, 7, 3) in us_holidays(2026)
    assert date(2027, 6, 18) in us_holidays(2027)


def test_prebuilt_set_covers_range():
    assert date(1995, 7, 4) in HOLIDAY_SET
    assert date(2026, 6, 19) in HOLIDAY_SET
