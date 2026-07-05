"""test_fetch_putcall.py — CBOE Put/Call 取数：CSV/JSON 解析、衔接不重叠、断点续传、幂等
（全部合成数据·不联网：monkeypatch _get_text/_get_daily_raw 注入假响应；不落盘真实 data/）。"""
import datetime

import pytest

import fetch_putcall as fp


TOTAL_CSV = """Disclaimer text goes here, ignore this line entirely.
, PRODUCT: TOTAL,,EXCHANGE: Cboe,
DATE,CALLS,PUTS,TOTAL,P/C Ratio
11/1/2006,1000,900,1900,0.90
11/2/2006,2000,400,2400,0.20
"""

EQUITY_CSV = """Disclaimer text goes here, ignore this line entirely.
, PRODUCT: EQUITY,,EXCHANGE: Cboe,
DATE,CALL,PUT,TOTAL,P/C Ratio
11/1/2006,500,300,800,0.60
"""


# ── CSV 解析：按列位置(不依赖列名单复数)，日期两种格式都认，除零/坏行跳过 ──────
def test_parse_pc_csv_basic():
    out = fp.parse_pc_csv(TOTAL_CSV)
    assert out[datetime.date(2006, 11, 1)] == pytest.approx(900 / 1000)
    assert out[datetime.date(2006, 11, 2)] == pytest.approx(400 / 2000)


def test_parse_pc_csv_handles_zero_padded_and_unpadded_dates():
    csv_text = "DATE,CALLS,PUTS,TOTAL,P/C Ratio\n10/04/2019, 100, 50, 150, 0.50\n9/5/2019, 200, 100, 300, 0.50\n"
    out = fp.parse_pc_csv(csv_text)
    assert datetime.date(2019, 10, 4) in out
    assert datetime.date(2019, 9, 5) in out


def test_parse_pc_csv_skips_zero_calls_and_bad_date():
    csv_text = "\n".join([
        "DATE,CALLS,PUTS,TOTAL,P/C Ratio",
        "11/1/2006,0,900,900,0",           # calls=0 → 除零风险，跳过
        "not-a-date,1000,500,1500,0.5",     # 坏日期 → 跳过
        "11/3/2006,1000,500,1500,0.5",      # 正常
    ])
    out = fp.parse_pc_csv(csv_text)
    assert list(out.keys()) == [datetime.date(2006, 11, 3)]


def test_parse_pc_csv_missing_header_raises():
    with pytest.raises(ValueError):
        fp.parse_pc_csv("not,a,valid,header\n1,2,3,4")


def test_build_csv_backfill_rows_outer_join_by_date():
    rows = fp.build_csv_backfill_rows(TOTAL_CSV, EQUITY_CSV)
    by_date = {r["date"]: r for r in rows}
    d1, d2 = datetime.date(2006, 11, 1), datetime.date(2006, 11, 2)
    assert by_date[d1]["total_pc"] is not None and by_date[d1]["equity_pc"] is not None
    assert by_date[d2]["total_pc"] is not None
    assert by_date[d2]["equity_pc"] is None      # equity CSV 没有这天 → 留空,不是伪造
    assert all(r["source"] == "csv" and r["index_pc"] is None for r in rows)


# ── JSON 解析：三个比率、部分缺失、解析失败 ──────────────────────────────
def test_parse_daily_json_extracts_three_ratios():
    payload = b'{"ratios":[{"name":"TOTAL PUT/CALL RATIO","value":"1.05"},' \
              b'{"name":"EQUITY PUT/CALL RATIO","value":"0.70"},' \
              b'{"name":"INDEX PUT/CALL RATIO","value":"1.12"}]}'
    r = fp.parse_daily_json(payload, datetime.date(2019, 10, 7))
    assert r == {"date": datetime.date(2019, 10, 7), "total_pc": 1.05, "equity_pc": 0.70,
                 "index_pc": 1.12, "source": "json"}


def test_parse_daily_json_missing_both_ratios_returns_none():
    payload = b'{"ratios":[{"name":"OEX PUT/CALL RATIO","value":"3.0"}]}'
    assert fp.parse_daily_json(payload, datetime.date(2019, 10, 7)) is None


def test_parse_daily_json_malformed_returns_none():
    assert fp.parse_daily_json(b"not json{{{", datetime.date(2019, 10, 7)) is None


# ── fetch_daily_json：403 AccessDenied=正常跳过(不重试)；429=退避重试 ─────────
def test_fetch_daily_json_access_denied_403_no_retry(monkeypatch):
    calls = {"n": 0}

    def fake_get(d):
        calls["n"] += 1
        return 403, b"<Error><Code>AccessDenied</Code></Error>"

    monkeypatch.setattr(fp, "_get_daily_raw", fake_get)
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)
    found, payload = fp.fetch_daily_json(datetime.date(2020, 1, 4))   # 周六
    assert found is False and payload is None
    assert calls["n"] == 1                      # 不重试——AccessDenied 是常规"该日无数据"


def test_fetch_daily_json_429_retries_then_succeeds(monkeypatch):
    seq = [(429, b""), (429, b""), (200, b'{"ratios":[]}')]
    calls = {"n": 0}

    def fake_get(d):
        v = seq[calls["n"]]
        calls["n"] += 1
        return v

    monkeypatch.setattr(fp, "_get_daily_raw", fake_get)
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)     # 测试不真等
    found, payload = fp.fetch_daily_json(datetime.date(2019, 10, 7))
    assert found is True
    assert calls["n"] == 3                       # 两次 429 退避 + 第三次成功


def test_fetch_daily_json_exhausts_retries_and_skips(monkeypatch):
    monkeypatch.setattr(fp, "_get_daily_raw", lambda d: (429, b""))
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)
    found, payload = fp.fetch_daily_json(datetime.date(2019, 10, 7))
    assert found is False and payload is None


# ── 衔接边界：csv 段与 json 段同日冲突 → STOP(不是别的日子——精确同一天) ───────
def test_upsert_one_boundary_conflict_raises():
    store = {datetime.date(2019, 10, 4): {"date": datetime.date(2019, 10, 4), "total_pc": 1.0,
                                            "equity_pc": None, "index_pc": None, "source": "csv"}}
    conflicting = {"date": datetime.date(2019, 10, 4), "total_pc": 5.0, "equity_pc": None,
                   "index_pc": None, "source": "json"}
    with pytest.raises(fp.BoundaryConflict):
        fp.upsert_one(store, conflicting)


def test_upsert_one_same_source_overwrites_no_conflict():
    store = {datetime.date(2019, 10, 4): {"date": datetime.date(2019, 10, 4), "total_pc": 1.0,
                                            "equity_pc": None, "index_pc": None, "source": "csv"}}
    revised = {"date": datetime.date(2019, 10, 4), "total_pc": 1.2345, "equity_pc": None,
               "index_pc": None, "source": "csv"}
    fp.upsert_one(store, revised)                # 同 source 重跑 → 直接覆盖，不算冲突
    assert store[datetime.date(2019, 10, 4)]["total_pc"] == 1.2345


def test_upsert_one_different_source_small_diff_tolerated():
    # 跨源但数值几乎一致(浮点/四舍五入误差 < 0.05) → 不算冲突，正常覆盖
    store = {datetime.date(2019, 10, 7): {"date": datetime.date(2019, 10, 7), "total_pc": 1.050,
                                            "equity_pc": None, "index_pc": None, "source": "csv"}}
    close_enough = {"date": datetime.date(2019, 10, 7), "total_pc": 1.06, "equity_pc": None,
                     "index_pc": None, "source": "json"}
    fp.upsert_one(store, close_enough)
    assert store[datetime.date(2019, 10, 7)]["source"] == "json"


# ── 交易日历判定：已知范围内精确查表；超出范围退化为周一到周五 ───────────────
def test_is_trading_day_known_calendar_excludes_holiday():
    # 07-10 是节假日(周五，工作日但不在 calendar 里)；07-13 是之后的交易日，
    # 用来把 known_max 顶到 07-10 之后，让 07-10 落在"已知范围内"才能测出精确排除
    calendar = {datetime.date(2026, 7, 8), datetime.date(2026, 7, 9), datetime.date(2026, 7, 13)}
    assert fp._is_trading_day(datetime.date(2026, 7, 8), calendar) is True
    assert fp._is_trading_day(datetime.date(2026, 7, 10), calendar) is False


def test_is_trading_day_beyond_known_calendar_falls_back_to_weekday():
    calendar = {datetime.date(2026, 6, 24)}
    assert fp._is_trading_day(datetime.date(2026, 6, 26), calendar) is True    # Fri，退化判定
    assert fp._is_trading_day(datetime.date(2026, 6, 27), calendar) is False   # Sat


# ── 断点续传 + 幂等：已有日期跳过，不重复请求/不重复写 ────────────────────────
def test_fetch_json_increment_skips_existing_dates(monkeypatch):
    requested = []

    def fake_fetch(d):
        requested.append(d)
        return True, b'{"ratios":[{"name":"TOTAL PUT/CALL RATIO","value":"1.0"}]}'

    monkeypatch.setattr(fp, "fetch_daily_json", fake_fetch)
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)
    monkeypatch.setattr(fp, "JSON_START_DATE", datetime.date(2026, 6, 22))     # Mon

    calendar = {datetime.date(2026, 6, 22), datetime.date(2026, 6, 23), datetime.date(2026, 6, 24)}
    store = {datetime.date(2026, 6, 22): {"date": datetime.date(2026, 6, 22), "total_pc": 0.5,
                                            "equity_pc": None, "index_pc": None, "source": "json"}}
    n_req = fp.fetch_json_increment(store, calendar, today=datetime.date(2026, 6, 24))
    # 06-22 已存在 → 跳过；06-23、06-24 是新交易日 → 各发 1 个请求
    assert n_req == 2
    assert requested == [datetime.date(2026, 6, 23), datetime.date(2026, 6, 24)]
    assert len(store) == 3


def test_fetch_json_increment_respects_max_requests(monkeypatch):
    requested = []

    def fake_fetch(d):
        requested.append(d)
        return False, None

    monkeypatch.setattr(fp, "fetch_daily_json", fake_fetch)
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)
    monkeypatch.setattr(fp, "JSON_START_DATE", datetime.date(2026, 6, 22))

    calendar = {datetime.date(2026, 6, 22), datetime.date(2026, 6, 23), datetime.date(2026, 6, 24),
                datetime.date(2026, 6, 25), datetime.date(2026, 6, 26)}
    store = {}
    n_req = fp.fetch_json_increment(store, calendar, max_requests=2, today=datetime.date(2026, 6, 26))
    assert n_req == 2
    assert len(requested) == 2


# ── run() 端到端(monkeypatch 网络 + 落盘路径，不碰真实 data/) ────────────────
def test_run_first_time_does_csv_backfill_then_json(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "OUT_CSV", tmp_path / "cboe_putcall.csv")
    monkeypatch.setattr(fp, "_get_text", lambda url: TOTAL_CSV if "totalpc" in url else EQUITY_CSV)
    monkeypatch.setattr(fp, "load_trading_days", lambda: {datetime.date(2006, 11, 1), datetime.date(2006, 11, 2)})
    monkeypatch.setattr(fp, "JSON_START_DATE", datetime.date(2026, 7, 1))
    monkeypatch.setattr(fp, "fetch_daily_json",
                        lambda d: (True, b'{"ratios":[{"name":"TOTAL PUT/CALL RATIO","value":"0.8"}]}'))
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)

    result = fp.run(today=datetime.date(2026, 7, 1))
    assert result["n_rows"] == 3                 # 2 csv 天 + 1 json 天(2026-07-01)
    out = fp.OUT_CSV.read_text(encoding="utf-8")
    assert "2006-11-01" in out and "csv" in out
    assert "2026-07-01" in out and "json" in out


def test_run_second_call_skips_csv_backfill(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "OUT_CSV", tmp_path / "cboe_putcall.csv")
    csv_calls = {"n": 0}

    def counting_get_text(url):
        csv_calls["n"] += 1
        return TOTAL_CSV if "totalpc" in url else EQUITY_CSV

    monkeypatch.setattr(fp, "_get_text", counting_get_text)
    monkeypatch.setattr(fp, "load_trading_days", lambda: {datetime.date(2006, 11, 1), datetime.date(2006, 11, 2)})
    monkeypatch.setattr(fp, "JSON_START_DATE", datetime.date(2026, 7, 1))
    monkeypatch.setattr(fp, "fetch_daily_json",
                        lambda d: (True, b'{"ratios":[{"name":"TOTAL PUT/CALL RATIO","value":"0.8"}]}'))
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)

    fp.run(today=datetime.date(2026, 7, 1))
    assert csv_calls["n"] == 2                    # 第一次：total+equity 各一次
    fp.run(today=datetime.date(2026, 7, 1))        # 第二次：已有 csv 来源的行 → 不该再拉 CSV
    assert csv_calls["n"] == 2                     # 计数没增加


def test_run_network_error_non_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "OUT_CSV", tmp_path / "cboe_putcall.csv")

    def boom(url):
        raise OSError("CBOE 网络错误")

    monkeypatch.setattr(fp, "_get_text", boom)
    monkeypatch.setattr(fp, "load_trading_days", lambda: set())
    monkeypatch.setattr(fp, "JSON_START_DATE", datetime.date(2026, 7, 1))
    monkeypatch.setattr(fp, "fetch_daily_json", lambda d: (False, None))
    monkeypatch.setattr(fp.time, "sleep", lambda s: None)

    result = fp.run(today=datetime.date(2026, 7, 1))   # CSV 回填失败(非致命)，JSON 段也没拿到——但不该抛异常
    assert result["n_rows"] == 0
