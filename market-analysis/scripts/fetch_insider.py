"""
fetch_insider.py — 数据可行性 SPIKE（草稿，待主脑用带 UA 的真实请求复核）

目的：服务端、免费、稳定地拿"近期内部人**买入**(Form 4 transactionCode=P)"清单，
写 insider.json，作为 v1.5「聪明钱/内部人 诚实检验」候选族的数据底座。
**本页只解决取数；不做跟单/荐股；统计检验(placebo/FDR/样本外)在 Phase 1 另起。**

✅ 主脑实地验证（2026-06-25·设 SEC_UA_CONTACT=真实邮箱）：
   ① company_tickers.json → 8021 条 CIK→ticker ✓
   ② daily-index → 已发布交易日 200（每日 ~1000–1700 份 Form 4）；当日盘中未发布会 403，
      靠 LOOKBACK 回看前几个工作日兜住（默认 5 天，足够）✓
   ③ parse_form4 → 30/30 XML 解析成功、抽出真实开市买入 P（如 AMS 某内部人买 ≈$1.34M）✓
   清洗：无 ticker / 0 股的边缘条目已过滤（检验需可定位标的 + 真买入）。
   **取数 GO。** 下一步 = Phase 1 真检验（跟内部人买是否有样本外 edge：placebo/FDR/walk-forward，
   大概率负——但那正是诚实内容，不是失败）。设 SEC_UA_CONTACT 环境变量（真实邮箱）后跑。

═══ SEC EDGAR 取数方案（调研结论） ═══

A) 拿"近期 Form 4 申报列表"——三条路，本脚本走【路1】最稳：

  路1 · daily-index（本脚本默认，最稳、纯静态文件、无 JSON schema 漂移风险）
    https://www.sec.gov/Archives/edgar/daily-index/{YYYY}/QTR{q}/form.{YYYYMMDD}.idx
    这是一张当日**全部申报**的定宽/管道分隔索引表，列：
      Form Type | Company Name | CIK | Date Filed | File Name
    过滤 Form Type == "4" 即得当天所有 Form 4。File Name 形如
      edgar/data/320193/0000320193-26-000077.txt
    → 申报的"完整提交文本"，里面内嵌 ownership XML。
    注意：周末/节假日无 form.idx（HTTP 404 正常，跳过即可）。

  路2 · full-text search API（备选，JSON 友好但有节流/翻页坑）
    https://efts.sec.gov/LATEST/search-index?q=...&forms=4&dateRange=custom...
    （实际公开端点是 https://efts.sec.gov/LATEST/search-index 的封装
      https://www.sec.gov/cgi-bin/srqsb 已弃用；现用 EDGAR FTS：
      https://efts.sec.gov/LATEST/search-index?forms=4 返回 hits[].
     —— FTS 对"最近 N 天全部 Form 4"不如 daily-index 直接，且有 10 req/s 限。)

  路3 · data.sec.gov 结构化 submissions（用于 CIK→ticker 映射，非取列表）
    https://data.sec.gov/submissions/CIK##########.json  (CIK 补零到 10 位)
    含 tickers[] / name；本脚本用**它的伴生文件**做全市场映射：
    https://www.sec.gov/files/company_tickers.json
      {"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."}, ...}
    → 一次性下载，建 CIK→ticker 字典，解决 Form 4 里只有 issuer CIK 的问题。

B) Form 4 ownership XML 关键字段（解析 .txt 里 <XML>…</XML> 段或 *.xml）：
    <issuer>
      <issuerCik>0000320193</issuerCik>
      <issuerTradingSymbol>AAPL</issuerTradingSymbol>   ← 有时缺，靠 CIK 映射兜底
    <reportingOwner><reportingOwnerId><rptOwnerName>COOK TIMOTHY</...>
      <reportingOwnerRelationship><isDirector>1</> <isOfficer>1</>
        <officerTitle>CEO</officerTitle>
    <nonDerivativeTable><nonDerivativeTransaction>
      <transactionDate><value>2026-06-18</value>
      <transactionCoding><transactionCode>P</transactionCode>   ← P=买入 S=卖出
                         <transactionFormType>4</>
      <transactionAmounts>
        <transactionShares><value>5000</value>
        <transactionPricePerShare><value>189.50</value>
        <transactionAcquiredDisposedCode><value>A</value>   ← A=Acquired D=Disposed
    （衍生品在 <derivativeTable>；本检验只取 nonDerivative 的现金买入 P+A，
      排除期权行权/赠与/10b5-1 计划自动卖等噪声——见 _is_open_market_buy）

C) **UA 铁律**（这正是普通无 UA 抓取被 403 的原因）：
   SEC 要求每个请求带声明式 User-Agent，含**真实联系方式**，格式建议：
     "Sample Company AdminContact@example.com"
   本脚本照仓库 quick_quotes.py / fetch_news.py 的 urllib + UA 头模式，
   但把 UA 换成 SEC 要求的"应用名 + 邮箱"。**主脑务必把邮箱改成真实地址**。
   限速：SEC 公开建议 ≤10 请求/秒；本脚本每请求 sleep 0.2s（≈5 req/s）留余量。
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

WEB = Path(__file__).parent.parent / "web"
DOCS = Path(__file__).parent.parent.parent / "docs"
PROCESSED = Path(__file__).parent.parent / "data" / "processed"

# ⚠ SEC 要求 UA 含真实可联系邮箱（否则可能被限/403）。从环境读，避免把私人邮箱硬编码进公开仓库。
# 跑前：$env:SEC_UA_CONTACT='你的应用名 your@email'（本地）或设为 GitHub Actions secret。
UA = os.environ.get("SEC_UA_CONTACT", "valpha-lab honest-stats dashboard (set SEC_UA_CONTACT env to your contact email)")
HEADERS = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}

LOOKBACK_DAYS = 5        # 回看几个交易日的 daily-index
REQ_PAUSE = 0.2         # 每请求间隔(秒)，≈5 req/s，留 SEC 10 req/s 余量
HTTP_TIMEOUT = 20
MAX_BYTES = 8_000_000   # 单文件大小上限(防异常巨型提交耗尽 CI；照 fetch_news 5MB 思路放宽到 8MB)
MAX_FILINGS = 400       # 单次最多解析的 Form 4 数(防回看太长时请求爆炸；先小步验证)

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


# ── 底层 HTTP（照仓库 urllib + UA 模式；gzip 自解）────────────────────
def _get(url, binary=False):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        raw = r.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError(f"响应过大(>{MAX_BYTES//1_000_000}MB)，跳过 {url}")
        # urllib 不自动解 gzip；按 header 手解
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    time.sleep(REQ_PAUSE)
    return raw if binary else raw.decode("utf-8", "replace")


# ── CIK→ticker 映射（一次性下载 company_tickers.json）─────────────────
def load_cik_to_ticker():
    try:
        data = json.loads(_get(COMPANY_TICKERS_URL))
    except Exception as e:
        print(f"  ⚠ company_tickers.json 拉取失败({e})；ticker 映射降级为空")
        return {}
    # 形如 {"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."}}
    return {int(row["cik_str"]): row["ticker"] for row in data.values()}


# ── 拿最近 N 个工作日的 Form 4 申报路径（走 daily-index）──────────────
def recent_form4_filings(days=LOOKBACK_DAYS):
    """返回 [(cik, txt_url)]：最近 days 个日历日里 form.idx 中 Form Type==4 的行。"""
    out = []
    today = datetime.date.today()
    workdays_seen = 0
    for back in range(days + 5):           # 多看几天补周末/节假日空洞
        if workdays_seen >= days:
            break
        d = today - datetime.timedelta(days=back)
        if d.weekday() >= 5:               # 周六周日无 form.idx
            continue
        workdays_seen += 1
        q = (d.month - 1) // 3 + 1
        idx_url = (f"https://www.sec.gov/Archives/edgar/daily-index/"
                   f"{d.year}/QTR{q}/form.{d:%Y%m%d}.idx")
        try:
            text = _get(idx_url)
        except Exception as e:
            print(f"  · {d} 无 daily-index 或拉取失败({e})，跳过")
            continue
        n_day = 0
        for line in text.splitlines():
            # .idx 是定宽/空格对齐：以 Form Type 开头，行内含 edgar/data/.../*.txt
            if not line.startswith("4 ") and not line.startswith("4\t"):
                # 更稳的判定：拆分后首列恰为 "4"
                parts = re.split(r"\s{2,}", line.strip())
                if not parts or parts[0] != "4":
                    continue
            else:
                parts = re.split(r"\s{2,}", line.strip())
            # 末列是 File Name: edgar/data/{cik}/{accession}.txt
            fname = parts[-1] if parts else ""
            m = re.search(r"edgar/data/(\d+)/(\S+\.txt)", fname)
            if not m:
                continue
            cik = int(m.group(1))
            txt_url = "https://www.sec.gov/Archives/" + m.group(0)
            out.append((cik, txt_url))
            n_day += 1
            if len(out) >= MAX_FILINGS:
                print(f"  · 命中 MAX_FILINGS={MAX_FILINGS}，停止收集")
                return out
        print(f"  · {d}: {n_day} 份 Form 4")
    return out


# ── 解析单份 Form 4 提交文本里的 ownership XML，抽"开市买入"行 ────────
def _is_open_market_buy(code, ad_code):
    # P = 公开市场/私下购买；A = Acquired。只取真金白银买入，排除 S/赠与/行权等
    return code == "P" and ad_code == "A"


# 申报人常把垃圾塞进 issuerTradingSymbol（"NONE"/"N/A"/带空格如 "N O G"）→ 这类被拒，
# 改走 CIK→ticker 兜底；连兜底都没有就丢（跟单检验需可定位的真标的）。
_BAD_TICKERS = {"NONE", "N/A", "NA", "N.A.", "-", "—", "NULL"}
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def _clean_ticker(sym):
    """返回规范 ticker 或 None（拒空格/占位符/非法格式）。"""
    if not sym:
        return None
    t = sym.strip().upper()
    if t in _BAD_TICKERS or " " in t or not _TICKER_RE.match(t):
        return None
    return t


def parse_form4(txt, cik2tk, cik):
    """从完整提交文本中切出 <ownershipDocument> XML 并抽 P 买入。返回 buys[]。"""
    # 提交 .txt 内嵌一段或多段 <XML>…</XML>；取含 ownershipDocument 的那段
    buys = []
    # 优先抓 <ownershipDocument>…</ownershipDocument>
    m = re.search(r"<ownershipDocument>.*?</ownershipDocument>", txt, re.S)
    if not m:
        return buys
    try:
        root = ET.fromstring(m.group(0))
    except ET.ParseError:
        return buys

    def _txt(node, path):
        el = node.find(path)
        return el.text.strip() if el is not None and el.text else None

    issuer = root.find("issuer")
    ticker = _clean_ticker(_txt(issuer, "issuerTradingSymbol")) if issuer is not None else None
    if not ticker:
        ticker = cik2tk.get(cik)            # 兜底：CIK→ticker（company_tickers.json 干净）
    issuer_name = _txt(issuer, "issuerName") if issuer is not None else None

    owner = root.find("reportingOwner")
    insider = (_txt(owner, "reportingOwnerId/rptOwnerName")
               if owner is not None else None)
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    title = None
    if rel is not None:
        title = _txt(rel, "officerTitle")
        if not title:
            flags = [k for k, lbl in (("isDirector", "Director"),
                                      ("isOfficer", "Officer"),
                                      ("isTenPercentOwner", "10% Owner"))
                     if (_txt(rel, k) in ("1", "true"))]
            title = "/".join(flags) if flags else None

    for tx in root.iter("nonDerivativeTransaction"):
        code = _txt(tx, "transactionCoding/transactionCode")
        ad = _txt(tx, "transactionAmounts/transactionAcquiredDisposedCode/value")
        if not _is_open_market_buy(code, ad):
            continue
        date_ = _txt(tx, "transactionDate/value")
        shares = _txt(tx, "transactionAmounts/transactionShares/value")
        price = _txt(tx, "transactionAmounts/transactionPricePerShare/value")
        try:
            sh = float(shares) if shares else None
            pr = float(price) if price else None
            val = round(sh * pr, 2) if (sh and pr) else None
        except ValueError:
            sh = pr = val = None
        if not (ticker and sh and sh > 0):       # 清洗：需可定位标的 + 真实股数(>0)，否则不入检验
            continue
        buys.append({
            "ticker": ticker,
            "issuer": issuer_name,
            "insider": insider,
            "title": title,
            "date": date_,
            "shares": sh,
            "price": pr,
            "value": val,
            "code": code,           # 留痕，便于 Phase 1 审计口径
        })
    return buys


# ── 建议的 insider.json 形状 ─────────────────────────────────────────
#   {
#     "generated": "2026-06-20T03:00:00Z",
#     "source": "SEC EDGAR Form 4 (daily-index)",
#     "lookback_days": 5,
#     "disclaimer": "内部人买入≠荐股；本数据仅供 v1.5『是否有样本外edge』诚实检验，非跟单信号。",
#     "n_filings_scanned": 312,
#     "n_buys": 41,
#     "buys": [
#       {"ticker":"AAPL","issuer":"Apple Inc.","insider":"COOK TIMOTHY",
#        "title":"CEO","date":"2026-06-18","shares":5000,"price":189.5,
#        "value":947500.0,"code":"P"}
#     ]
#   }


def main():
    print("=== SPIKE：抓 SEC Form 4 近期内部人买入(P) ===")
    print(f"    UA={UA!r}  （⚠ 复核前请确认邮箱真实）")
    cik2tk = load_cik_to_ticker()
    print(f"  CIK→ticker 映射：{len(cik2tk)} 条")

    filings = recent_form4_filings(LOOKBACK_DAYS)
    print(f"  收集到 {len(filings)} 份 Form 4 待解析")

    buys, scanned, errors = [], 0, 0
    for cik, url in filings:
        try:
            txt = _get(url)
            buys.extend(parse_form4(txt, cik2tk, cik))
            scanned += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  ⚠ 解析失败 {url}: {e}")

    # 按金额降序（仅展示排序，不构成任何"重要性"判断）
    buys.sort(key=lambda b: (b.get("value") or 0), reverse=True)

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "SEC EDGAR Form 4 (daily-index)",
        "lookback_days": LOOKBACK_DAYS,
        "disclaimer": ("内部人买入≠荐股；本数据仅供 v1.5『跟内部人买是否真有样本外 edge』"
                       "诚实检验，非跟单信号。"),
        "n_filings_scanned": scanned,
        "n_buys": len(buys),
        "buys": buys,
    }

    if not buys and scanned == 0:
        print("✗ 一份都没抓到/解析到——保留旧 insider.json（若有），不写坏数据")
        sys.exit(0)

    # 写 data/processed + web/ + docs/（proc=True）；SPIKE 阶段 PROCESSED 必写到
    from util_io import write_json
    PROCESSED.mkdir(parents=True, exist_ok=True)
    write_json("insider.json", out, indent=1, allow_nan=False, proc=True)
    print(f"[OK] insider.json：扫描 {scanned} 份、买入 {len(buys)} 行、失败 {errors} 份")
    if buys:
        top = buys[0]
        print(f"     最大一笔：{top.get('insider')} ({top.get('title')}) "
              f"买 {top.get('ticker')} ≈ ${top.get('value')}")


if __name__ == "__main__":
    main()
