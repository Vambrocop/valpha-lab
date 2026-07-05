"""test_fetch_cot.py — CFTC COT 取数：zip/CSV 解析 / usable_from(+4交易日) / 幂等 upsert / 坏行跳过
（全部合成数据·不联网：手搭小 zip 注入，不读真实 CFTC 响应；不落盘真实 data/cot.csv）。"""
import datetime
import io
import zipfile

import pytest

import fetch_cot as fc


# ── 合成 zip 工厂 ────────────────────────────────────────────────────────
def _zip_of(csv_text, inner_name="annual.txt"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(inner_name, csv_text)
    return buf.getvalue()


LEGACY_HEADER = (
    "Market and Exchange Names,CFTC Contract Market Code,"
    "As of Date in Form YYYY-MM-DD,Open Interest (All),"
    "Noncommercial Positions-Long (All),Noncommercial Positions-Short (All)"
)

TFF_HEADER = (
    "Market_and_Exchange_Names,CFTC_Contract_Market_Code,"
    "Report_Date_as_YYYY-MM-DD,Open_Interest_All,"
    "Lev_Money_Positions_Long_All,Lev_Money_Positions_Short_All"
)


# ── legacy 解析：目标合约留下、非目标合约过滤、坏行跳过 ───────────────────
def test_parse_legacy_zip_filters_and_computes_net():
    rows_csv = "\n".join([
        LEGACY_HEADER,
        # sp500 E-mini（目标 code）：净持仓 = 300-100=200，pct=200/1000*100=20
        "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE,13874A,2026-06-23,1000,300,100",
        # nasdaq100 E-mini（目标 code）
        "NASDAQ MINI - CHICAGO MERCANTILE EXCHANGE,209742,2026-06-23,500,50,150",
        # 非目标 code（全尺寸 S&P 500，已停牌）——应被过滤，不出现在结果里
        "S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE,138741,2026-06-23,999,1,1",
        # 同名多合约陷阱：Consolidated 口径（不同 code 13874+）——应被过滤
        "S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE,13874+,2026-06-23,2000,1,1",
    ])
    rows = fc.parse_legacy_zip(_zip_of(rows_csv))
    assert len(rows) == 2
    by_market = {r["market"]: r for r in rows}
    assert by_market["sp500"]["noncomm_net"] == 200
    assert by_market["sp500"]["noncomm_net_pct_oi"] == pytest.approx(20.0)
    assert by_market["sp500"]["lev_funds_net"] is None
    assert by_market["sp500"]["source"] == "legacy"
    assert by_market["nasdaq100"]["noncomm_net"] == -100
    assert by_market["nasdaq100"]["open_interest"] == 500


def test_parse_legacy_zip_skips_bad_rows():
    rows_csv = "\n".join([
        LEGACY_HEADER,
        # 非数值 OI → 跳过
        "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE,13874A,2026-06-23,N/A,300,100",
        # 非法日期 → 跳过
        "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE,13874A,not-a-date,1000,300,100",
        # 正常一行，应保留
        "NASDAQ MINI - CHICAGO MERCANTILE EXCHANGE,209742,2026-06-16,500,50,150",
    ])
    rows = fc.parse_legacy_zip(_zip_of(rows_csv))
    assert len(rows) == 1
    assert rows[0]["market"] == "nasdaq100"


def test_parse_legacy_zip_missing_column_raises():
    bad_csv = "Some Other Column\nx"
    with pytest.raises(ValueError):
        fc.parse_legacy_zip(_zip_of(bad_csv))


# ── TFF 解析：leveraged funds net、两种日期格式都要认 ──────────────────────
def test_parse_tff_zip_computes_lev_net_iso_date():
    rows_csv = "\n".join([
        TFF_HEADER,
        "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE,13874A,2026-06-23,2000000,300000,350000",
    ])
    rows = fc.parse_tff_zip(_zip_of(rows_csv))
    assert len(rows) == 1
    r = rows[0]
    assert r["market"] == "sp500"
    assert r["source"] == "tff"
    assert r["lev_funds_net"] == -50000
    assert r["noncomm_net"] is None
    assert r["report_date"] == datetime.date(2026, 6, 23)


def test_parse_tff_zip_handles_backfill_datetime_format():
    # 回填包(fin_fut_txt_2006_2016)日期形如 "1/10/2012 12:00:00 AM"（美式 M/D/YYYY + 时间戳）
    rows_csv = "\n".join([
        TFF_HEADER,
        "NASDAQ MINI - CHICAGO MERCANTILE EXCHANGE,209742,1/10/2012 12:00:00 AM,300000,80000,70000",
    ])
    rows = fc.parse_tff_zip(_zip_of(rows_csv))
    assert len(rows) == 1
    assert rows[0]["report_date"] == datetime.date(2012, 1, 10)
    assert rows[0]["lev_funds_net"] == 10000


def test_parse_tff_zip_skips_non_target_code():
    rows_csv = "\n".join([
        TFF_HEADER,
        "MICRO E-MINI S&P 500 INDEX,13874U,2026-06-23,100000,1000,900",
    ])
    assert fc.parse_tff_zip(_zip_of(rows_csv)) == []


# ── usable_from = report_date + 4 交易日(合成交易日历) ─────────────────────
def test_add_trading_days_tue_to_next_monday_no_holiday():
    # 2026-06-23 是周二；calendar 覆盖到很晚 → 精确排周末，无节假日
    calendar = {
        datetime.date(2026, 6, 23), datetime.date(2026, 6, 24), datetime.date(2026, 6, 25),
        datetime.date(2026, 6, 26), datetime.date(2026, 6, 29), datetime.date(2026, 6, 30),
    }
    d = fc.add_trading_days(datetime.date(2026, 6, 23), 4, calendar)
    assert d == datetime.date(2026, 6, 29)          # Tue → 次周一


def test_add_trading_days_skips_holiday_within_known_calendar():
    # 周二 2026-07-07；周五(07-10)恰是节假日、calendar 里没有这一天(排除掉) →
    # 真实交易日序列是 Wed07-08, Thu07-09, Mon07-13, Tue07-14 → 数到第4个是 07-14
    calendar = {
        datetime.date(2026, 7, 7), datetime.date(2026, 7, 8), datetime.date(2026, 7, 9),
        # 07-10 节假日，故意不放进 calendar
        datetime.date(2026, 7, 13), datetime.date(2026, 7, 14),
    }
    d = fc.add_trading_days(datetime.date(2026, 7, 7), 4, calendar)
    assert d == datetime.date(2026, 7, 14)


def test_add_trading_days_falls_back_to_weekday_beyond_known_calendar():
    # calendar 只知道到 2026-06-24（模拟 pipeline 还没抓到最新收盘价）；
    # 之后的步数退化为纯周一到周五计数，不排节假日
    calendar = {datetime.date(2026, 6, 23), datetime.date(2026, 6, 24)}
    d = fc.add_trading_days(datetime.date(2026, 6, 23), 4, calendar)
    # Wed06-24(已知,计1) Thu06-25(退化,周中计2) Fri06-26(退化,计3) Sat/Sun跳过 Mon06-29(退化,计4)
    assert d == datetime.date(2026, 6, 29)


def test_add_trading_days_empty_calendar_pure_weekday():
    d = fc.add_trading_days(datetime.date(2026, 6, 23), 4, set())
    assert d == datetime.date(2026, 6, 29)


# ── 幂等 upsert：同 key 重跑不重复、new 覆盖 old(允许 CFTC 修订历史值) ───────
def test_upsert_rows_dedup_by_key():
    existing = [
        {"report_date": datetime.date(2026, 6, 23), "market": "sp500", "source": "legacy",
         "noncomm_net": 100, "noncomm_net_pct_oi": 1.0, "lev_funds_net": None, "open_interest": 1000},
    ]
    new = [
        # 同 key，重跑一次一模一样的数据 → 合并后仍只有 1 行
        dict(existing[0]),
    ]
    merged = fc.upsert_rows(existing, new)
    assert len(merged) == 1


def test_upsert_rows_new_overwrites_old_value():
    existing = [
        {"report_date": datetime.date(2026, 6, 23), "market": "sp500", "source": "legacy",
         "noncomm_net": 100, "noncomm_net_pct_oi": 1.0, "lev_funds_net": None, "open_interest": 1000},
    ]
    revised = [
        {"report_date": datetime.date(2026, 6, 23), "market": "sp500", "source": "legacy",
         "noncomm_net": 999, "noncomm_net_pct_oi": 9.9, "lev_funds_net": None, "open_interest": 1000},
    ]
    merged = fc.upsert_rows(existing, revised)
    assert len(merged) == 1
    assert merged[0]["noncomm_net"] == 999


def test_upsert_rows_distinguishes_by_source_and_market():
    existing = [
        {"report_date": datetime.date(2026, 6, 23), "market": "sp500", "source": "legacy",
         "noncomm_net": 100, "noncomm_net_pct_oi": 1.0, "lev_funds_net": None, "open_interest": 1000},
    ]
    new = [
        # 同日期同市场，但 source 不同(tff) → 不应覆盖，应新增一行
        {"report_date": datetime.date(2026, 6, 23), "market": "sp500", "source": "tff",
         "noncomm_net": None, "noncomm_net_pct_oi": None, "lev_funds_net": 50, "open_interest": 1000},
        # 同日期同 source，但市场不同(nasdaq100) → 也应新增
        {"report_date": datetime.date(2026, 6, 23), "market": "nasdaq100", "source": "legacy",
         "noncomm_net": 5, "noncomm_net_pct_oi": 0.5, "lev_funds_net": None, "open_interest": 500},
    ]
    merged = fc.upsert_rows(existing, new)
    assert len(merged) == 3


# ── run() 端到端(monkeypatch 网络 + 落盘路径，不碰真实 data/) ────────────────
def test_run_backfill_writes_csv(tmp_path, monkeypatch):
    legacy_csv = "\n".join([
        LEGACY_HEADER,
        "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE,13874A,2026-06-23,1000,300,100",
    ])
    tff_csv = "\n".join([
        TFF_HEADER,
        "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE,13874A,2026-06-23,1000,300,350",
    ])
    legacy_zip = _zip_of(legacy_csv)
    tff_zip = _zip_of(tff_csv)

    def fake_get_bytes(url):
        if "fin_fut_txt" in url or "fut_fin_txt" in url:
            return tff_zip
        return legacy_zip

    monkeypatch.setattr(fc, "_get_bytes", fake_get_bytes)
    monkeypatch.setattr(fc, "OUT_CSV", tmp_path / "cot.csv")
    monkeypatch.setattr(fc, "load_trading_days", lambda: {datetime.date(2026, 6, 23), datetime.date(2026, 6, 24)})
    # 限制年份范围，避免测试真去拼一堆 URL(反正都走同一个 fake，多拼没意义、只拖时间)
    monkeypatch.setattr(fc, "LEGACY_YEAR_START", 2026)
    monkeypatch.setattr(fc, "TFF_YEAR_START", 2026)

    n = fc.run(force_backfill=True)
    assert n is not None
    out = fc.OUT_CSV.read_text(encoding="utf-8")
    lines = out.strip().splitlines()
    assert lines[0] == ",".join(fc.COLUMNS)
    # legacy + tff 各一行(同 report_date/market 但 source 不同，不会互相覆盖)
    assert len(lines) == 3


def test_run_network_error_non_fatal(monkeypatch, tmp_path):
    def boom(url):
        raise OSError("CFTC 网络错误")
    monkeypatch.setattr(fc, "_get_bytes", boom)
    monkeypatch.setattr(fc, "OUT_CSV", tmp_path / "cot.csv")
    assert fc.run(force_backfill=True) is None
    assert not (tmp_path / "cot.csv").exists()


def test_run_incremental_mode_when_file_exists(tmp_path, monkeypatch):
    out_csv = tmp_path / "cot.csv"
    out_csv.write_text(
        "report_date,market,source,noncomm_net,noncomm_net_pct_oi,lev_funds_net,open_interest,usable_from\n"
        "2026-06-16,sp500,legacy,100,10.0,,1000,2026-06-22\n",
        encoding="utf-8",
    )
    legacy_csv = "\n".join([
        LEGACY_HEADER,
        "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE,13874A,2026-06-23,1000,300,100",
    ])
    tff_csv = "\n".join([
        TFF_HEADER,
        "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE,13874A,2026-06-23,1000,300,350",
    ])

    def fake_get_bytes(url):
        if "fin_fut_txt" in url or "fut_fin_txt" in url:
            return _zip_of(tff_csv)
        return _zip_of(legacy_csv)

    monkeypatch.setattr(fc, "_get_bytes", fake_get_bytes)
    monkeypatch.setattr(fc, "OUT_CSV", out_csv)
    monkeypatch.setattr(fc, "load_trading_days", lambda: {datetime.date(2026, 6, 23), datetime.date(2026, 6, 24)})

    n = fc.run(force_backfill=False)               # 不传 --backfill，文件已存在 → 应走增量(当年 zip)
    assert n == 3                                    # 旧的 1 行(legacy 06-16) + 新 legacy(06-23) + 新 tff(06-23)
    out = out_csv.read_text(encoding="utf-8")
    assert "2026-06-16,sp500,legacy" in out          # 旧行保留(幂等，没被覆盖没被删)
