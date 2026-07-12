"""test_ipo_enrich.py — IPO 重大性富化引擎（A2）单测。
全部 canned fixtures·不碰网络（monkeypatch 掉所有 SEC/yfinance 调用）。
fixtures 结构照【第 0 步实弹】实抓的真 EX-FILING FEES 原生 XBRL 实例复刻。
覆盖详规 §12 的 9 类。"""
import json

import pytest

import ipo_enrich as ie


# ══════════════════════════════════════════════════════════════════════
# 合成费用文档（照实测真结构：原生 XBRL 实例 .xml，含 <ffd:…> 全额值）
# ══════════════════════════════════════════════════════════════════════
def _xml_fee(*max_aggts, ttl=None):
    """原生 XBRL 实例：每个 MaxAggtOfferingPric 一行（全额美元字符串），可选 TtlOfferingAmt。"""
    rows = "".join(
        f'<ffd:MaxAggtOfferingPric contextRef="offrl_{i+1}" decimals="2" unitRef="USD">{v}</ffd:MaxAggtOfferingPric>'
        for i, v in enumerate(max_aggts))
    ttl_el = (f'<ffd:TtlOfferingAmt contextRef="rc" decimals="2" unitRef="USD">{ttl}</ffd:TtlOfferingAmt>'
              if ttl is not None else "")
    return ('<?xml version="1.0" encoding="utf-8"?>'
            '<xbrl xmlns="http://www.xbrl.org/2003/instance" '
            'xmlns:ffd="http://xbrl.sec.gov/ffd/2025">'
            f'{rows}{ttl_el}</xbrl>')


# ── §12.2 XML 变体（主路径）：多行求和 = 注册总额（照 SK hynix 实测两行）─────
def test_parse_xml_multirow_sum():
    doc = _xml_fee("29192654581.28", "999999718.72", ttl="30192654300.00")
    amt, status = ie.parse_fee_doc(doc, is_xml=True)
    assert status == "parsed"
    assert amt == pytest.approx(30_192_654_300.0, rel=1e-9)   # 取 TtlOfferingAmt


def test_parse_xml_no_ttl_sums_maxaggts():
    doc = _xml_fee("400000000.00", "350000000.00")            # 无 TtlOfferingAmt → 求和
    amt, status = ie.parse_fee_doc(doc, is_xml=True)
    assert status == "parsed"
    assert amt == pytest.approx(750_000_000.0)


def test_parse_xml_handles_commas():
    doc = _xml_fee("1,234,567,890.00")
    amt, status = ie.parse_fee_doc(doc, is_xml=True)
    assert status == "parsed" and amt == pytest.approx(1_234_567_890.0)


def test_parse_xml_malformed_returns_unknown():
    amt, status = ie.parse_fee_doc("<xbrl not closed", is_xml=True)
    assert (amt, status) == (None, "unknown")


# ── §12.1 iXBRL 兜底路径：吃 scale 属性 + 千分逗号 ───────────────────────
def test_parse_ixbrl_scale_and_commas():
    doc = ('<html><body>'
           '<ix:nonFraction name="ffd:MaxAggtOfferingPric" scale="3" decimals="-3" '
           'unitRef="USD" contextRef="c1">1,234,567</ix:nonFraction>'
           '</body></html>')
    amt, status = ie.parse_fee_doc(doc, is_xml=False)
    assert status == "parsed"
    assert amt == pytest.approx(1_234_567_000.0)              # 1,234,567 × 10^3


def test_parse_ixbrl_no_scale_defaults_zero():
    doc = ('<ix:nonFraction name="ffd:MaxAggtOfferingPricValue" unitRef="USD" '
           'contextRef="c1">750000000</ix:nonFraction>')
    amt, status = ie.parse_fee_doc(doc, is_xml=False)
    assert status == "parsed" and amt == pytest.approx(750_000_000.0)


# ── §12.3 占位额 $100M → placeholder_suspect 且不改档 ─────────────────────
def test_placeholder_100m_flagged():
    doc = _xml_fee("100000000.00", ttl="100000000.00")
    amt, status = ie.parse_fee_doc(doc, is_xml=True)
    assert status == "placeholder_suspect"
    assert amt == pytest.approx(100_000_000.0)


def test_placeholder_does_not_promote_domestic():
    # 占位额（status=placeholder_suspect）对本土公司 → 视为未知 → rest，不升 🟡
    tier, reasons = ie.decide_tier(
        curated_hit=False, home_mktcap_b=None, spac=False,
        amount_m=100.0, amount_status="placeholder_suspect", foreign=False)
    assert tier == "rest"


def test_placeholder_foreign_goes_notable_via_unknown():
    # 外国 + 占位额（视为未知）→ foreign_unknown → 🟡
    tier, reasons = ie.decide_tier(
        curated_hit=False, home_mktcap_b=None, spac=False,
        amount_m=100.0, amount_status="placeholder_suspect", foreign=True)
    assert tier == "notable" and reasons == ["foreign_unknown"]


# ── §12.4 界外值拒收 ───────────────────────────────────────────────────
def test_out_of_bounds_rejected():
    assert ie.parse_fee_doc(_xml_fee("50"), is_xml=True) == (None, "unknown")          # < 1e5
    assert ie.parse_fee_doc(_xml_fee("99999999999999"), is_xml=True) == (None, "unknown")  # > 1e13


# ── §12.5 KRW 母市值换算（隐藏坑）───────────────────────────────────────
def test_home_mktcap_krw_conversion(monkeypatch):
    def fake_fi(sym):
        if sym == "000660.KS":
            return {"market_cap": 90_000_000_000_000, "currency": "KRW"}  # 90 万亿 KRW
        if sym == "KRWUSD=X":
            return {"last_price": 0.00073}
        raise AssertionError(f"unexpected {sym}")
    monkeypatch.setattr(ie, "_fetch_fast_info", fake_fi)
    cap = ie.home_mktcap_usd("000660.KS")
    assert cap == pytest.approx(90e12 * 0.00073)             # ≈ $65.7B
    assert cap / 1e9 >= ie.HOME_MKTCAP_USD_B                 # 换算后仍 ≥ $10B


def test_home_mktcap_usd_no_conversion(monkeypatch):
    monkeypatch.setattr(ie, "_fetch_fast_info",
                        lambda s: {"market_cap": 5e9, "currency": "USD"})
    assert ie.home_mktcap_usd("XYZ") == pytest.approx(5e9)


def test_home_mktcap_fx_failure_returns_none(monkeypatch):
    def fake_fi(sym):
        if sym.endswith("=X"):
            return {}                                        # fx 无价 → None
        return {"market_cap": 1e13, "currency": "KRW"}
    monkeypatch.setattr(ie, "_fetch_fast_info", fake_fi)
    assert ie.home_mktcap_usd("000660.KS") is None           # 换算失败 → 不升档


# ── §12.6 别名/关注名单歧义弃权 ─────────────────────────────────────────
def test_alias_ambiguity_abstains():
    aliases = [
        {"names": [["GLOBAL", "TECH"]], "home": "AAA.KS", "note": None},
        {"names": [["GLOBAL", "TECH"]], "home": "BBB.T", "note": None},
    ]
    assert ie.match_alias("GLOBAL TECH", aliases) is None     # 命中 2 条 → 弃权


def test_alias_single_hit_ok():
    aliases = [{"names": [["SK", "HYNIX"]], "home": "000660.KS", "note": None}]
    assert ie.match_alias("SK HYNIX", aliases) == "000660.KS"


def test_watchlist_ambiguity_abstains():
    wl = [("Alpha", ["ALPHA"]), ("Alpha", ["ALPHA"])]         # 两条都叫 ALPHA
    hit, _ = ie.match_watchlist("ALPHA BETA GROUP", wl)
    assert hit is False


def test_watchlist_wholeword_not_substring():
    # 整词匹配：watchlist 'CANVA' 不应命中 'CANVAS' 这种子串
    wl = [("Canva", ["CANVA"])]
    assert ie.match_watchlist("CANVAS MEDICAL", wl)[0] is False
    assert ie.match_watchlist("CANVA", wl)[0] is True


# ── §12.7 SPAC 名称启发反例 "Data Acquisition Systems" ─────────────────────
def test_spac_name_counterexample():
    assert ie.name_spac(ie._norm_full("Data Acquisition Systems Inc")) is False
    assert ie.name_spac(ie._norm_full("Catalyst Acquisition Corp.")) is True
    assert ie.name_spac(ie._norm_full("Samos Energy Acquisition Corp")) is True
    assert ie.name_spac(ie._norm_full("Bravalo Holdings Acquisition Company")) is True
    # "II" 夹在中间 → 名称启发不命中（靠 SIC 6770 兜底，可接受漏）
    assert ie.name_spac(ie._norm_full("Pelican Acquisition II Corp")) is False


def test_normalize_keeps_holdings_group():
    # 不剥 HOLDINGS/GROUP（剥了会把 "XX Holdings" 与 "XX" 混同）
    assert ie._norm_key("Gloo Holdings, Inc.") == "GLOO HOLDINGS"
    assert ie._norm_key("Pattern Group Inc.") == "PATTERN GROUP"
    assert ie._norm_key("SK hynix Inc.") == "SK HYNIX"


# ── §12.8 决策表全分支（spac 短路金额·unknown 不升档·adr 别名例外）────────
def test_decide_curated_wins():
    tier, r = ie.decide_tier(curated_hit=True, home_mktcap_b=None, spac=True,
                             amount_m=None, amount_status="unknown", foreign=True)
    assert tier == "major" and r == ["watchlist"]            # 策展优先于一切


def test_decide_home_mktcap_major():
    tier, r = ie.decide_tier(curated_hit=False, home_mktcap_b=118.0, spac=False,
                             amount_m=None, amount_status="unknown", foreign=True)
    assert tier == "major" and r == ["home_mktcap"]


def test_decide_spac_shortcircuits_amount():
    # SPAC 即便金额巨大也 → rest（金额不再看）
    tier, r = ie.decide_tier(curated_hit=False, home_mktcap_b=None, spac=True,
                             amount_m=9999.0, amount_status="parsed", foreign=False)
    assert tier == "rest" and r == ["spac"]


def test_decide_amount_major_and_notable():
    assert ie.decide_tier(curated_hit=False, home_mktcap_b=None, spac=False,
                          amount_m=600.0, amount_status="parsed", foreign=False)[0] == "major"
    assert ie.decide_tier(curated_hit=False, home_mktcap_b=None, spac=False,
                          amount_m=200.0, amount_status="parsed", foreign=False)[0] == "notable"


def test_decide_unknown_never_promotes():
    tier, r = ie.decide_tier(curated_hit=False, home_mktcap_b=None, spac=False,
                             amount_m=None, amount_status="unknown", foreign=False)
    assert tier == "rest" and r == []


def test_decide_low_amount_no_downgrade_signal_domestic_rest():
    # 本土 + 真实低额（$120M 已知）→ rest（<150；低额不是"小交易"升档信号，也不升 🟡）
    tier, _ = ie.decide_tier(curated_hit=False, home_mktcap_b=None, spac=False,
                             amount_m=120.0, amount_status="parsed", foreign=False)
    assert tier == "rest"


# ── §12.8 续：adr-only 别名例外 + deferred（集成，monkeypatch 掉 SEC/yf）────
def _fake_no_sec(monkeypatch):
    def boom_get(url):
        raise AssertionError("adr-only 不应发 SEC 请求")
    monkeypatch.setattr(ie, "_get", boom_get)


def test_adr_only_alias_gets_home_mktcap(monkeypatch):
    # 纯 F-6（adr-only）但别名命中 → 跳 B/C、只走 D；母市值 ≥ $10B → major
    _fake_no_sec(monkeypatch)
    monkeypatch.setattr(ie, "_fetch_fast_info",
                        lambda s: {"market_cap": 1.2e11, "currency": "USD"})
    comp = {"buckets": {"adr"}, "company": "SK hynix Inc.", "foreign": False,
            "rows": [], "latest": "2026-07-01"}
    aliases = [{"names": [["SK", "HYNIX"]], "home": "000660.KS", "note": None}]
    enr = ie._process_cik("0002120882", comp, watchlist=[], aliases=aliases,
                          cache={}, budget=ie.Budget(150))
    assert enr["tier"] == "major" and enr["tier_reasons"] == ["home_mktcap"]
    assert enr["home_ticker"] == "000660.KS"


def test_adr_only_no_alias_stays_unlayered(monkeypatch):
    _fake_no_sec(monkeypatch)
    comp = {"buckets": {"adr"}, "company": "HONDA MOTOR CO LTD /ADR", "foreign": False,
            "rows": [], "latest": "2026-06-22"}
    enr = ie._process_cik("0000944751", comp, watchlist=[], aliases=[],
                          cache={}, budget=ie.Budget(150))
    assert enr["tier"] is None and enr["enrich"] == "adr_unlayered"


def test_budget_exhausted_defers(monkeypatch):
    _fake_no_sec(monkeypatch)                                 # 预算 0 → 根本不发请求
    comp = {"buckets": {"filed"}, "company": "Holtec Nuclear Corp", "foreign": False,
            "rows": [], "latest": "2026-07-10"}
    enr = ie._process_cik("0002104277", comp, watchlist=[], aliases=[],
                          cache={}, budget=ie.Budget(0))
    assert enr["tier"] is None and enr["enrich"] == "deferred"
    assert enr["amount_status"] == "deferred"


def test_name_spac_no_sec_needed_rest(monkeypatch):
    # 名称启发已判 SPAC → rest，无需 SEC（省预算）
    _fake_no_sec(monkeypatch)
    comp = {"buckets": {"filed"}, "company": "Catalyst Acquisition Corp.", "foreign": False,
            "rows": [], "latest": "2026-07-08"}
    enr = ie._process_cik("0002104391", comp, watchlist=[], aliases=[],
                          cache={}, budget=ie.Budget(150))
    assert enr["tier"] == "rest" and enr["spac"] is True and enr["spac_source"] == "name"


def test_sic_spac_from_submissions(monkeypatch):
    # 名称非 SPAC 但 SIC 6770 → spac_source=sic → rest（费用不解析）
    monkeypatch.setattr(ie, "fetch_submissions",
                        lambda cik: {"sic": "6770", "s1_adsh": "0001-26-000001", "exchange": "NASDAQ"})
    monkeypatch.setattr(ie, "locate_fee_doc",
                        lambda c, a: (_ for _ in ()).throw(AssertionError("SPAC 不应解析费用")))
    comp = {"buckets": {"filed"}, "company": "Pelican Acquisition II Corp", "foreign": False,
            "rows": [], "latest": "2026-07-10"}
    enr = ie._process_cik("0002122392", comp, watchlist=[], aliases=[],
                          cache={}, budget=ie.Budget(150))
    assert enr["tier"] == "rest" and enr["spac_source"] == "sic"


def test_real_operating_company_amount_major(monkeypatch):
    # 名称非 SPAC + SIC 非 6770 + 费用解析出大额 → major via amount
    monkeypatch.setattr(ie, "fetch_submissions",
                        lambda cik: {"sic": "3674", "s1_adsh": "0001-26-000009", "exchange": "NASDAQ"})
    monkeypatch.setattr(ie, "locate_fee_doc", lambda c, a: ("http://x/fee.xml", True))
    monkeypatch.setattr(ie, "_get", lambda url: _xml_fee("800000000.00", ttl="800000000.00"))
    comp = {"buckets": {"filed"}, "company": "Bigco Semiconductors Inc.", "foreign": False,
            "rows": [], "latest": "2026-07-10"}
    enr = ie._process_cik("0001718728", comp, watchlist=[], aliases=[],
                          cache={}, budget=ie.Budget(150))
    assert enr["tier"] == "major" and enr["tier_reasons"] == ["amount"]
    assert enr["amount_usd_m"] == pytest.approx(800.0)


# ── F1/F2 修复补测（军师亲审裁决落地·2026-07-12）───────────────────────────
def test_cache_stale_when_new_filing_appears(monkeypatch):
    # F1：缓存 fetched_date=2026-07-01，但该公司最新申报行 filed=2026-07-10（不早于缓存日）
    # → 必须重走 B/C（不走缓存短路），拿到新金额而非缓存里的占位额（占位→真额是最常见升档路径）。
    monkeypatch.setattr(ie, "fetch_submissions",
                        lambda cik: {"sic": "3674", "s1_adsh": "0001-26-000099", "exchange": "NASDAQ"})
    monkeypatch.setattr(ie, "locate_fee_doc", lambda c, a: ("http://x/fee.xml", True))
    monkeypatch.setattr(ie, "_get", lambda url: _xml_fee("900000000.00", ttl="900000000.00"))
    comp = {"buckets": {"filed"}, "company": "Staleco Semiconductors Inc.", "foreign": False,
            "rows": [], "latest": "2026-07-10"}
    cache = {"0001999999": {"sic": "3674", "amount_usd_m": 100.0,
                            "amount_status": "placeholder_suspect",
                            "fetched_date": "2026-07-01"}}
    enr = ie._process_cik("0001999999", comp, watchlist=[], aliases=[],
                          cache=cache, budget=ie.Budget(150))
    assert enr["amount_usd_m"] == pytest.approx(900.0)         # 不是缓存里的 100.0
    assert enr["amount_status"] == "parsed"                    # 不是缓存里的 placeholder_suspect
    assert enr["tier"] == "major"


def test_cache_fresh_when_no_new_filing_uses_cache(monkeypatch):
    # 反例守门：缓存 fetched_date 晚于（或等于）公司最新申报行 → 信任缓存，不重取（不该发 SEC 请求）。
    def boom_get(url):
        raise AssertionError("新鲜缓存不应发 SEC 请求")
    monkeypatch.setattr(ie, "_get", boom_get)
    monkeypatch.setattr(ie, "fetch_submissions",
                        lambda cik: (_ for _ in ()).throw(AssertionError("新鲜缓存不应调用 fetch_submissions")))
    comp = {"buckets": {"filed"}, "company": "Freshco Semiconductors Inc.", "foreign": False,
            "rows": [], "latest": "2026-07-01"}
    cache = {"0001999998": {"sic": "3674", "amount_usd_m": 900.0,
                            "amount_status": "parsed",
                            "fetched_date": "2026-07-10"}}
    enr = ie._process_cik("0001999998", comp, watchlist=[], aliases=[],
                          cache=cache, budget=ie.Budget(150))
    assert enr["amount_usd_m"] == pytest.approx(900.0)
    assert enr["amount_status"] == "parsed"


def test_watchlist_exclusion_full_equality_no_major():
    # F2：watchlist "Kraken" 子串命中 "Kraken Robotics"，但整名（normkey）与 exclusion 全等 → 排除，不升 major。
    wl = [("Kraken", ["KRAKEN"])]
    exclusions = {"KRAKEN ROBOTICS", "KRAKEN ENERGY"}
    hit, name = ie.match_watchlist(ie._norm_key("Kraken Robotics Inc."), wl, exclusions)
    assert (hit, name) == (False, None)
    tier, reasons = ie.decide_tier(curated_hit=hit, home_mktcap_b=None, spac=False,
                                   amount_m=None, amount_status="unknown", foreign=False)
    assert tier != "major"
    # 非排除名（真 Kraken 交易所若恰巧仍叫 "Kraken Exchange"）不受影响，照常命中
    hit2, name2 = ie.match_watchlist(ie._norm_key("Kraken Exchange Inc."), wl, exclusions)
    assert hit2 is True and name2 == "Kraken"


def test_watchlist_payward_wholeword_hit_major():
    # F2：军师加名 "Payward"（Kraken 法定名）整词命中 → curated_hit=True → major。
    wl = [("Payward", ["PAYWARD"])]
    hit, name = ie.match_watchlist(ie._norm_key("Payward, Inc."), wl)
    assert (hit, name) == (True, "Payward")
    tier, reasons = ie.decide_tier(curated_hit=hit, home_mktcap_b=None, spac=False,
                                   amount_m=None, amount_status="unknown", foreign=True)
    assert tier == "major" and reasons == ["watchlist"]


# ── §12.9 富化器炸掉 → 原始 JSON 完好（fail-soft）──────────────────────────
def test_failsoft_keeps_original(monkeypatch, tmp_path):
    original = {"generated": "2026-07-12T00:00:00Z", "filed": [
        {"company": "X", "cik": "0000000001", "form": "S-1", "filed": "2026-07-10"}]}
    src = tmp_path / "ipo_filings.json"
    src.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ie, "WEB", tmp_path)

    def boom(*a, **k):
        raise RuntimeError("富化炸了")
    monkeypatch.setattr(ie, "enrich", boom)
    import util_io
    monkeypatch.setattr(util_io, "write_json",
                        lambda *a, **k: pytest.fail("fail-soft 下不应写盘"))

    assert ie.run() is None                                   # 静默、不抛
    # 原始文件逐字节未变
    assert json.loads(src.read_text(encoding="utf-8")) == original


def test_end_to_end_enrich_writeback(monkeypatch):
    # 小型端到端：两家公司（一 major-by-amount、一 SPAC-rest），验证写回字段 + 计数
    data = {"filed": [
        {"company": "Bigco Semis Inc.", "cik": "0000000010", "form": "S-1", "filed": "2026-07-10"},
        # 名称不含 "Acquisition Corp" 邻接 → 名称启发不命中 → 走 SEC 拿到 SIC 6770
        {"company": "Nimbus Blank Check Corp", "cik": "0000000011", "form": "S-1", "filed": "2026-07-09"},
    ], "priced": [], "listing": [], "adr": []}

    def fake_subs(cik):
        return {"sic": "3826" if cik == "0000000010" else "6770",
                "s1_adsh": "0001-26-000010", "exchange": "NASDAQ"}
    monkeypatch.setattr(ie, "fetch_submissions", fake_subs)
    monkeypatch.setattr(ie, "locate_fee_doc", lambda c, a: ("http://x/fee.xml", True))
    monkeypatch.setattr(ie, "_get", lambda url: _xml_fee("700000000.00", ttl="700000000.00"))

    n_major, n_notable = ie.enrich(data, watchlist=[], aliases=[], cache={}, budget=ie.Budget(150))
    assert n_major == 1 and n_notable == 0
    big = data["filed"][0]
    assert big["tier"] == "major" and big["tier_reasons"] == ["amount"]
    assert big["amount_usd_m"] == pytest.approx(700.0)
    spac = data["filed"][1]
    assert spac["tier"] == "rest" and spac["spac_source"] == "sic"
