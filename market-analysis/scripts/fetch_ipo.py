"""fetch_ipo.py — SEC EDGAR 近期 IPO 相关申报（免费·CI 可达）→ ipo_filings.json。

给 IPO 雷达页补一个【自动更新】的事实层：直接读 SEC EDGAR 全文搜索
（efts.sec.gov/LATEST/search-index），拉最近 N 天的四类申报：
  · S-1 / S-1/A       = 已递交招股书（"已申报"档的原始事实；递交≠一定上市）
  · F-1 / F-1/A       = 外国发行人招股书（如海力士这类境外公司来美上市；同属"已递交"，行内 foreign=True）
  · 424B4 / 424B1     = 已定价/生效招股书（≈"即将/刚上市"；比 S-1/F-1 更接近真上市）
  · 8-A12B            = 已在交易所注册挂牌（IPO/直挂都必经，最干净的"确定要上"信号）
  · F-6               = ADR 存托设施（常由存托行代递，多为程序性，独立隔离于 adr 档，不解析标的公司）
只做取数 + 解析 + 形状守门，写 ipo_filings.json。**非荐股、非预测——就是一张 SEC 申报快照。**

═══ 数据源可行性（2026-07-02 实地核实·澳洲/CI 可达） ═══
  · 端点：https://efts.sec.gov/LATEST/search-index?forms=S-1,424B4&dateRange=custom&startdt=..&enddt=..
    实测 HTTP 200、返回干净 JSON（hits[]._source 含 display_names / file_date / file_type / ciks）。
  · 免费、无需 API key；沿用 fetch_insider.py 的 SEC UA 铁律（SEC_UA_CONTACT 环境变量，含真实邮箱）。
  · display_names 形如 "OneMedNet Corp  (ONMD, ONMDW)  (CIK 0001849380)"——公司名 + 括号 ticker（有时缺）+ CIK。

═══ ⚠ 诚实边界（务必读·别过度声称） ═══
  EDGAR 给的是【全体】S-1/424B4 申报，**绝大多数是小盘/微盘/SPAC/空壳**（如 VARSAL TECH、Asia AI Group），
  **不等于**页面手工策展的那批明星 IPO（SpaceX/Cerebras/Discord/OpenAI）。EDGAR **无法**提供：
    · "传闻/预期"档（未申报的市场传闻——那来自媒体/人工判断，SEC 无记录）
    · 估值（~$15B / ~$1T 这类）、承销商、目标季度等叙事字段
  所以本 json 是【机构级原始事实流】，用来**补充**（不是替换）手工策展快照。前端应清楚标注
  "以下为 SEC 自动抓取的近期申报（含大量小盘/空壳，非策展）"，与上方明星快照区分开。

失败/未配置 UA → SEC 可能 403；本脚本**静默退 0 不阻断**（同 fetch_insider/fetch_earnings 模式），
保留旧 ipo_filings.json（若有），绝不写坏数据。

单独跑：$env:PYTHONUTF8='1'; $env:SEC_UA_CONTACT='你的应用名 your@email'; py market-analysis/scripts/fetch_ipo.py
"""
import datetime
import gzip
import json
import os
import re
import sys
import urllib.parse
import urllib.request

# SEC 要求 UA 含真实可联系邮箱（否则可能被限/403）。从环境读，避免把私人邮箱硬编码进公开仓库。
UA = os.environ.get(
    "SEC_UA_CONTACT",
    "valpha-lab honest-stats dashboard (set SEC_UA_CONTACT env to your contact email)",
)
HEADERS = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}

LOOKBACK_DAYS = 30          # 只看最近 30 天的申报（IPO 雷达关心近况）
HTTP_TIMEOUT = 25
MAX_BYTES = 8_000_000       # 单响应大小上限（防异常巨响应耗尽 CI）
MAX_ROWS = 60               # 每档最多留多少行（防噪声刷屏；按日期新→旧取前 N）
FTS_URL = "https://efts.sec.gov/LATEST/search-index"

# display_names 里抽 ticker：公司名  (TICK[, TICK2])  (CIK 0001234567)
_NAME_RE = re.compile(r"^(.*?)\s*(?:\(([A-Z][A-Z0-9., ]*)\)\s*)?\(CIK\s*(\d+)\)\s*$")


def _get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        raw = r.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError(f"响应过大(>{MAX_BYTES // 1_000_000}MB)，跳过 {url}")
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8", "replace"))


def _parse_name(display):
    """把 'OneMedNet Corp  (ONMD, ONMDW)  (CIK 0001849380)' → (company, ticker, cik)。

    ticker 缺失时返回 None；多 ticker 只取第一个（普通股），并拒非法/占位符。
    """
    m = _NAME_RE.match((display or "").strip())
    if not m:
        return (display or "").strip() or None, None, None
    company = (m.group(1) or "").strip().rstrip(",") or None
    ticker = None
    if m.group(2):
        first = m.group(2).split(",")[0].strip().upper()
        # 干净 ticker：1–6 位字母数字（允许点），排空/占位
        if re.fullmatch(r"[A-Z][A-Z0-9.]{0,5}", first):
            ticker = first
    cik = m.group(3)
    return company, ticker, cik


def _fetch_forms(forms, start, end):
    """拉某组 forms 在 [start, end] 的申报，返回按 file_date 降序去重的行列表。"""
    q = urllib.parse.urlencode({
        "forms": ",".join(forms),
        "dateRange": "custom",
        "startdt": start.isoformat(),
        "enddt": end.isoformat(),
    })
    data = _get(f"{FTS_URL}?{q}")
    hits = (data.get("hits", {}) or {}).get("hits", []) or []
    rows, seen = [], set()
    for h in hits:
        s = h.get("_source", {}) or {}
        names = s.get("display_names") or []
        display = names[0] if names else None
        company, ticker, cik = _parse_name(display)
        if not company or not cik:
            continue
        form = s.get("file_type") or (s.get("root_forms") or [None])[0]
        date_ = s.get("file_date")
        # 去重：同一公司(cik)同一 root form 只留最新一条（S-1 与 S-1/A 常密集重复）
        root = (s.get("root_forms") or [form])[0]
        dedup_key = (cik, root)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        # accession（供 ipo_enrich 富化定位费用来源）：efts 命中 _id 形如
        # "0001234567-26-000123:file.htm"；_source.adsh 有时直接给。两路都试 + 格式验证兜底。
        adsh = s.get("adsh") or (h.get("_id", "") or "").split(":")[0]
        adsh = adsh if re.fullmatch(r"\d{10}-\d{2}-\d{6}", adsh or "") else None
        rows.append({
            "company": company,
            "ticker": ticker,        # 可能为 None（申报里没带交易代码）
            "cik": cik,
            "form": form,
            "filed": date_,
            "foreign": bool(form and str(form).upper().startswith("F-1")),  # F-1/F-1/A = 外国发行人招股书
            "adsh": adsh,
        })
    rows.sort(key=lambda r: (r.get("filed") or ""), reverse=True)
    return rows[:MAX_ROWS]


def run():
    today = datetime.date.today()
    start = today - datetime.timedelta(days=LOOKBACK_DAYS)
    filed, priced, listing, adr = [], [], [], []
    try:
        # 已递交招股书（S-1 家族 + F-1 外国发行人家族）——"已申报"事实档
        filed = _fetch_forms(["S-1", "F-1"], start, today)
        # 已定价/生效招股书（424B）——更接近"真上市"
        priced = _fetch_forms(["424B4", "424B1"], start, today)
        # 已在交易所注册挂牌（8-A12B）——IPO/直挂都必经，最干净的"确定要上"信号
        listing = _fetch_forms(["8-A12B"], start, today)
        # ADR 存托设施（F-6）——常由存托行代递，多为程序性，独立隔离、不污染其他档
        adr = _fetch_forms(["F-6"], start, today)
    except Exception as e:
        print(f"[IPO] SEC EDGAR 拉取失败（非致命，不阻断）: {e}")
        return None

    if not filed and not priced and not listing and not adr:
        print("[IPO] 一条申报都没抓到——保留旧 ipo_filings.json（若有），不写坏数据")
        return None

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "SEC EDGAR full-text search (efts.sec.gov)",
        "lookback_days": LOOKBACK_DAYS,
        "disclaimer": (
            "SEC EDGAR 近期申报快照，含大量小盘/微盘/SPAC/空壳，非策展、非荐股、非预测。"
            "S-1=已递交招股书(递交≠一定上市)；424B=已定价/生效招股书(更接近真上市)；"
            "F-1=外国发行人招股书(如海力士这类境外公司来美上市；递交≠一定上市)；"
            "8-A12B=已在交易所注册挂牌(IPO/直挂都必经，更接近确定上市)；"
            "F-6=ADR存托设施(常由存托行代递，多为程序性，与标的公司本身上市与否无必然关系)。"
            "不含未申报的市场传闻与估值/承销商等叙事字段（SEC 无记录）。"
        ),
        "n_filed": len(filed),
        "n_priced": len(priced),
        "n_listing": len(listing),
        "n_adr": len(adr),
        "filed": filed,      # S-1 + F-1 家族（各行带 foreign 标记）
        "priced": priced,    # 424B 家族
        "listing": listing,  # 8-A12B（交易所注册挂牌）
        "adr": adr,          # F-6（ADR 存托设施，多为程序性）
    }

    from util_io import write_json
    written = write_json("ipo_filings.json", out, indent=1, allow_nan=False)
    print(f"[OK] ipo_filings.json — S-1/F-1 {len(filed)} 条 / 424B {len(priced)} 条 "
          f"/ 8-A12B {len(listing)} 条 / F-6 {len(adr)} 条 "
          f"（近 {LOOKBACK_DAYS} 天）→ {len(written)} 处")
    return out


if __name__ == "__main__":
    run()
    sys.exit(0)
