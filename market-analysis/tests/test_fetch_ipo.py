"""test_fetch_ipo.py — SEC EDGAR IPO 申报取数：display_names 解析 / 去重 / 排序 / 形状
（全部合成数据·不联网：monkeypatch _get 注入假 EDGAR 响应；不落盘 web/docs）。"""
import pytest

import fetch_ipo as fi


# ── display_names 解析：公司名 + 括号 ticker(可缺/多个) + CIK ─────────────
def test_parse_name_with_ticker():
    company, ticker, cik = fi._parse_name("OneMedNet Corp  (ONMD, ONMDW)  (CIK 0001849380)")
    assert company == "OneMedNet Corp"
    assert ticker == "ONMD"                 # 多 ticker 只取第一个
    assert cik == "0001849380"


def test_parse_name_no_ticker():
    company, ticker, cik = fi._parse_name("Asia AI Group Inc  (CIK 0002141084)")
    assert company == "Asia AI Group Inc"
    assert ticker is None                   # 申报未带交易代码 → None
    assert cik == "0002141084"


def test_parse_name_rejects_junk_ticker():
    # 括号里不是干净 ticker（如带空格/占位）时 ticker 应为 None，公司名仍解析
    company, ticker, cik = fi._parse_name("Weird Co  (N O G)  (CIK 0000000123)")
    assert company == "Weird Co"
    assert ticker is None
    assert cik == "0000000123"


def test_parse_name_garbage_returns_none_cik():
    company, ticker, cik = fi._parse_name("no cik here at all")
    assert cik is None                       # 无 CIK → run() 会跳过该行


# ── 合成 EDGAR 响应工厂 ───────────────────────────────────────────────
def _hit(display, form, date_, cik, root=None):
    return {"_source": {
        "display_names": [display],
        "file_type": form,
        "root_forms": [root or form],
        "file_date": date_,
        "ciks": [cik],
    }}


def _resp(hits):
    return {"hits": {"total": {"value": len(hits)}, "hits": hits}}


def test_fetch_forms_dedup_and_sort(monkeypatch):
    # 同一公司(cik)的 S-1 与 S-1/A 只留最新一条；跨公司按日期倒序
    hits = [
        _hit("Beta Inc  (BETA)  (CIK 0000000002)", "S-1/A", "2026-06-20", "0000000002", root="S-1"),
        _hit("Beta Inc  (BETA)  (CIK 0000000002)", "S-1",   "2026-06-10", "0000000002", root="S-1"),
        _hit("Alpha Inc  (ALPH)  (CIK 0000000001)", "S-1",  "2026-06-25", "0000000001", root="S-1"),
    ]
    monkeypatch.setattr(fi, "_get", lambda url: _resp(hits))
    import datetime
    rows = fi._fetch_forms(["S-1"], datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))
    # 去重：Beta 两条塌成一条（保留先出现=最新那条 S-1/A）
    ciks = [r["cik"] for r in rows]
    assert len(ciks) == len(set(ciks)) == 2
    # 倒序：Alpha(06-25) 在 Beta(06-20) 之前
    assert [r["company"] for r in rows] == ["Alpha Inc", "Beta Inc"]
    assert rows[0]["filed"] == "2026-06-25"


def test_fetch_forms_skips_rows_without_cik(monkeypatch):
    hits = [
        _hit("Good Co  (GOOD)  (CIK 0000000009)", "S-1", "2026-06-15", "0000000009"),
        {"_source": {"display_names": ["garbage no cik"], "file_type": "S-1",
                     "root_forms": ["S-1"], "file_date": "2026-06-14"}},
    ]
    monkeypatch.setattr(fi, "_get", lambda url: _resp(hits))
    import datetime
    rows = fi._fetch_forms(["S-1"], datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))
    assert [r["company"] for r in rows] == ["Good Co"]


def test_fetch_forms_caps_rows(monkeypatch):
    hits = [_hit(f"Co{i}  (T{i})  (CIK {i:010d})", "S-1", f"2026-06-{(i % 28) + 1:02d}", f"{i:010d}")
            for i in range(1, 200)]
    monkeypatch.setattr(fi, "_get", lambda url: _resp(hits))
    import datetime
    rows = fi._fetch_forms(["S-1"], datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))
    assert len(rows) <= fi.MAX_ROWS


# ── run(): 组装形状 + 计数一致 + 不落盘（monkeypatch write_json）───────────
def test_run_shape(monkeypatch):
    filed_hits = [_hit("Filer Inc  (FILE)  (CIK 0000000010)", "S-1", "2026-06-20", "0000000010")]
    priced_hits = [_hit("Priced Inc  (PRIC)  (CIK 0000000011)", "424B4", "2026-06-22", "0000000011")]

    def fake_get(url):
        return _resp(priced_hits if ("424B" in url) else filed_hits)

    monkeypatch.setattr(fi, "_get", fake_get)
    import util_io
    captured = {}
    monkeypatch.setattr(util_io, "write_json",
                        lambda name, payload, **k: captured.update({"name": name, "payload": payload}) or ["web"])

    out = fi.run()
    assert out is not None
    assert out["n_filed"] == len(out["filed"]) == 1
    assert out["n_priced"] == len(out["priced"]) == 1
    assert out["filed"][0]["company"] == "Filer Inc"
    assert out["priced"][0]["form"] == "424B4"
    assert captured["name"] == "ipo_filings.json"
    # 诚实纪律：disclaimer 必须点明"含小盘/空壳·非荐股"
    assert "非荐股" in out["disclaimer"]


def test_run_empty_keeps_old(monkeypatch):
    # 两档都空 → 返回 None（保留旧 json，不写坏数据）
    monkeypatch.setattr(fi, "_get", lambda url: _resp([]))
    import util_io
    monkeypatch.setattr(util_io, "write_json",
                        lambda *a, **k: pytest.fail("空结果不应落盘"))
    assert fi.run() is None


def test_run_network_error_non_fatal(monkeypatch):
    def boom(url):
        raise OSError("SEC 403")
    monkeypatch.setattr(fi, "_get", boom)
    # 不抛异常、返回 None（静默退 0 不阻断流水线）
    assert fi.run() is None
