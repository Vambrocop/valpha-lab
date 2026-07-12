"""ipo_enrich.py — IPO「重大性分层」富化引擎（A2）。

从 fetch_ipo.py 写的原始 SEC 申报流（ipo_filings.json）机械分层出
  🔴 major（重大） / 🟡 notable（值得注意） / rest（其余·含未匹配/占位/空壳）。
**未知一律不升档、绝不自由文本刮取美元数**——这是防「又一个吹票机」的结构性保证。
事实/日历层，非荐股非预测。规格：docs_internal/SPEC_IPO_ENRICH.md（军师 Fable 建造级详规）。

═══ 五阶段（详规 §1）═══════════════════════════════════════════════════
  Stage A  零请求预筛：名称归一 + SPAC 名称启发 + 策展/别名整词匹配（data/curated/ipo_watch.json）
  Stage B  submissions API：SIC(6770=SPAC 权威) + 回溯最新 S-1/F-1 accession（费用来源）+ 交易所
  Stage C  EX-FILING FEES(Exhibit 107)：index.json 定位 → 原生 XBRL 实例 → 拟募资总额（FFD 分类）
  Stage D  母市场市值：别名命中者 → yfinance 母代码 → 换 USD（KRW→USD 是隐藏坑）
  Stage E  分层决策表（机械·有先后·公司级 CIK 去重）→ 写回 ipo_filings.json

═══ 第 0 步实弹验证（2026-07-12·建造者实抓 4 家 2026 真申报核对）═══════════
  实测：EX-FILING FEES 现代格式 = 独立【原生 XBRL 实例 .xml】(*exfiling_fees_htm.xml)，
  含 <ffd:MaxAggtOfferingPric …>整数美元</…>（decimals 属性，非 scale；值已是全额）。
  同名 .htm 是纯 HTML 渲染、零 <ix:nonFraction> 标签。故【XML 分支为已验证主路径】：
  ElementTree 取精确 localname 元素文本求和，不乘 scale。iXBRL/scale 分支仅作保守兜底
  （越界即拒→unknown，绝不降级为正文刮取）。样本：SK hynix F-1/A 费表两行求和 $30.19B；
  Apnimed/Holtec/Syntiant 均恰 $100M（经典占位额→placeholder_suspect，不升档）。

═══ 诚实铁则（详规 §5）═══
  1. 绝不自由文本美元刮取——结构化解析失败 = 金额 unknown，走其他信号。
  2. 金额语义不对称：Proposed Max Aggregate 是含绿鞋/余量的【上限】，小额常为占位
     → 高额=可靠大交易信号，低额≠小交易信号。故【金额只有升档力、没有降档力】。
  3. fail-soft：富化炸掉 → 原始 ipo_filings.json 完好，前端把无 tier 的行显示「未分层」。
  4. SEC 403/限流 → 退避收工，绝不代理/轮换 IP（件3 定案）。

单独跑：$env:PYTHONUTF8='1'; $env:SEC_UA_CONTACT='你的应用名 your@email'; py market-analysis/scripts/ipo_enrich.py
"""
import datetime
import gzip
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────────────────────
SCRIPTS = Path(__file__).parent
WEB = SCRIPTS.parent / "web"
CURATED = SCRIPTS.parent / "data" / "curated" / "ipo_watch.json"
CACHE_PATH = SCRIPTS.parent / "data" / "raw" / "ipo_enrich_cache.json"   # data/raw gitignore（本地 top-up）

# ── SEC 请求（照 fetch_ipo/fetch_insider 的 UA 铁律；限速 + 硬顶）─────────
UA = os.environ.get(
    "SEC_UA_CONTACT",
    "valpha-lab honest-stats dashboard (set SEC_UA_CONTACT env to your contact email)",
)
HEADERS = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}
REQ_PAUSE = 0.12                                              # ≈8 req/s，留 SEC 10 req/s 余量
HTTP_TIMEOUT = 25
MAX_BYTES = 12_000_000
# 每 run SEC 请求硬顶；冷启动最坏 >顶 → 超顶行标 deferred 下轮续跑（~4 轮跑平；稳态每日 5-15）。
# 可用环境变量 IPO_ENRICH_MAX_REQ 覆盖（本地富化/一次性回填时调高；默认常量 150）。
MAX_ENRICH_REQ = int(os.environ.get("IPO_ENRICH_MAX_REQ", "150"))

# ── 阈值（详规 §8·lean 常量·拍板后一行改）──────────────────────────────
MAJOR_USD_M = 500      # 🔴：兜住无策展的本土独角兽（Reddit 型实募~$750M；proposed max 含水分~15-25%）
NOTABLE_USD_M = 150    # 🟡 下沿（避开 $100M 经典占位额）
HOME_MKTCAP_USD_B = 10  # 别名命中母公司市值 ≥ 此 → 🔴

# ── 名称归一与 SPAC 名称启发（详规 §3）────────────────────────────────
# 尾部法律后缀（迭代剥）：不剥 HOLDINGS/GROUP（剥了会把 "XX Holdings" 与 "XX" 混同，误匹配）。
_LEGAL_SUFFIX = {"INC", "CORP", "CORPORATION", "LTD", "LIMITED", "CO", "COMPANY",
                 "PLC", "NV", "SA", "AG", "LLC", "LP", "SPA", "AB", "OYJ", "GMBH"}
# SPAC 名称启发（仅此一条·宽了必误伤）：ACQUISITION 紧邻 CORP/CO/COMPANY/HOLDINGS。
# 对【未剥后缀】的全归一名跑（剥了会把 "X Acquisition Corp" 的 CORP 剥掉、启发失效）。
# 反例守门实测：'DATA ACQUISITION SYSTEMS INC' → ACQUISITION 后是 SYSTEMS，不命中。
_SPAC_NAME_RE = re.compile(r"\bACQUISITION\s+(CORP(ORATION)?|CO(MPANY)?|HOLDINGS)\b")


def _norm_full(name):
    """大写 → 去标点(留空格) → 压空格。用于 SPAC 名称启发（保留全部词，含 CORP）。"""
    s = (name or "").upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm_key(name):
    """在 _norm_full 基础上迭代剥尾部法律后缀。用于策展/别名整词匹配。"""
    words = _norm_full(name).split()
    while words and words[-1] in _LEGAL_SUFFIX:
        words.pop()
    return " ".join(words)


def _is_word_subseq(needle_words, hay_words):
    """needle_words 作为【连续整词】子序列出现在 hay_words 中？（整词匹配，非字符子串）。"""
    n, h = len(needle_words), len(hay_words)
    if n == 0 or n > h:
        return False
    for i in range(h - n + 1):
        if hay_words[i:i + n] == needle_words:
            return True
    return False


# ── 数字工具 ──────────────────────────────────────────────────────────
def _to_float(s):
    if s is None:
        return None
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _localname(tag):
    return tag.rsplit("}", 1)[-1]


# ── HTTP（gzip 自解 + 限速 + 大小上限）────────────────────────────────
class SecBlocked(Exception):
    """SEC 403/限流：退避收工，绝不代理绕行（件3 红线）。"""


def _get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            raw = r.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError(f"响应过大(>{MAX_BYTES // 1_000_000}MB)，跳过 {url}")
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise SecBlocked(f"HTTP {e.code} @ {url}")
        raise
    finally:
        time.sleep(REQ_PAUSE)
    return raw.decode("utf-8", "replace")


# ══════════════════════════════════════════════════════════════════════
# Stage A — 零请求预筛：策展/别名匹配 + SPAC 名称启发
# ══════════════════════════════════════════════════════════════════════
def load_watch():
    """读 ipo_watch.json → (watchlist_normkey_words[], aliases[{words, home, note}], exclusions_set, asof)。
    每 watchlist/alias 名预归一为整词列表。缺文件 → 空表（富化仍跑、只是无策展升档）。
    exclusions（F2）：与 watchlist 词形碰撞、但确系无关公司的法定全名（如 Kraken Robotics ≠ Kraken/Payward）；
    normkey 整名全等命中即从 watchlist 匹配里排除（见 match_watchlist）。"""
    try:
        raw = json.loads(CURATED.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠ ipo_watch.json 读取失败({e})；策展/别名降级为空")
        return [], [], set(), None
    wl = []
    for nm in raw.get("watchlist", []):
        words = _norm_key(nm).split()
        if words:
            wl.append((nm, words))
    aliases = []
    for a in raw.get("aliases", []):
        home = a.get("home")
        entry_words = []
        for nm in a.get("names", []):
            key = _norm_key(nm)
            # 别名防误匹配闸①：条目名须 ≥5 字符独特串
            if home and len(key) >= 5:
                entry_words.append(key.split())
        if home and entry_words:
            aliases.append({"names": entry_words, "home": home, "note": a.get("note")})
    exclusions = {_norm_key(nm) for nm in raw.get("exclusions", []) if _norm_key(nm)}
    return wl, aliases, exclusions, raw.get("asof")


def match_watchlist(normkey, watchlist, exclusions=None):
    """整词匹配 watchlist。命中 ≥2 个不同条目 → 弃权(歧义宁漏勿错)。
    命中后（F2）若整名(normkey)与 exclusions 中任一条目全等 → 视为未命中（同名他司排除，
    如 "Kraken Robotics" 整名撞 exclusions → 不因子串含 "Kraken" 而误升 major）。
    每次真实命中（含单命中）打印一行供本地人眼核对。返回 (hit_bool, matched_name|None)。"""
    hay = normkey.split()
    hits = [nm for nm, words in watchlist if _is_word_subseq(words, hay)]
    if len(hits) >= 2:
        print(f"  ⚠ watchlist 歧义弃权：'{normkey}' 命中 {hits}")
        return False, None
    if not hits:
        return False, None
    if exclusions and normkey in exclusions:
        return False, None
    print(f"  watchlist 命中: '{normkey}' ← 条目 '{hits[0]}'")
    return True, hits[0]


def match_alias(normkey, aliases):
    """整词匹配 aliases（三闸：≥5字符/整词/歧义弃权）。返回 home_ticker|None。"""
    hay = normkey.split()
    hits = []
    for a in aliases:
        if any(_is_word_subseq(w, hay) for w in a["names"]):
            hits.append(a["home"])
    hits = list(dict.fromkeys(hits))
    if len(hits) >= 2:
        print(f"  ⚠ alias 歧义弃权：'{normkey}' 命中 {hits}")
        return None
    return hits[0] if hits else None


def name_spac(normfull):
    return bool(_SPAC_NAME_RE.search(normfull))


# ══════════════════════════════════════════════════════════════════════
# Stage B — submissions API（1 请求/CIK，缓存后近零）
# ══════════════════════════════════════════════════════════════════════
_S1_FORMS = ("S-1", "S-1/A", "F-1", "F-1/A")


def fetch_submissions(cik):
    """GET submissions/CIK{10}.json 一次取三样。返回 {sic, s1_adsh, exchange}。"""
    data = json.loads(_get(f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"))
    sic = (data.get("sic") or "").strip() or None
    rec = data.get("filings", {}).get("recent", {}) or {}
    forms = rec.get("form", []) or []
    accs = rec.get("accessionNumber", []) or []
    s1_adsh = None
    for i, f in enumerate(forms):
        if f in _S1_FORMS and i < len(accs):
            s1_adsh = accs[i]        # filings.recent 已按新→旧，取最新的 S-1/F-1
            break
    exchs = data.get("exchanges") or []
    exchange = exchs[0] if exchs else None
    return {"sic": sic, "s1_adsh": s1_adsh, "exchange": exchange}


# ══════════════════════════════════════════════════════════════════════
# Stage C — EX-FILING FEES 定位与解析（核心硬件）
# ══════════════════════════════════════════════════════════════════════
_FEE_FILE_RE = re.compile(r"(?i)(ex[-_.]?107|filing[-_]?fees?)")


def locate_fee_doc(cik, s1_adsh):
    """index.json → 费用文档 URL（.xml 优先于 .htm）。无候选 → None。（实测 index.json 已列全部文件，
    足以定位，无需 index.htm 二次刮取。）"""
    adsh_nodash = s1_adsh.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh_nodash}"
    idx = json.loads(_get(f"{base}/index.json"))
    names = [it.get("name", "") for it in idx.get("directory", {}).get("item", [])]
    cand = [n for n in names if _FEE_FILE_RE.search(n)]
    if not cand:
        return None
    cand.sort(key=lambda n: (not n.lower().endswith(".xml"), n))   # .xml 优先
    return f"{base}/{cand[0]}", cand[0].lower().endswith(".xml")


def parse_fee_doc(text, is_xml):
    """解析费用文档 → (amount_usd|None, status)。
    status ∈ {"parsed","placeholder_suspect","unknown"}。
    XML 分支（已验证主路径）：原生 XBRL 实例，精确 localname 求和，全额值不乘 scale；
       优先取 TtlOfferingAmt（申报级注册总额），否则求和 MaxAggtOfferingPric（避免 carry-forward 变体重复计）。
    iXBRL 分支（保守兜底·实测现代申报走不到）：<ix:nonFraction name=…MaxAggtOffer… scale=…> 吃 scale。
    绝不正文刮取；越界即拒（1e5..1e13）→ unknown。"""
    total = None
    if is_xml:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return None, "unknown"
        ttl, maxes = [], []
        for el in root.iter():
            ln = _localname(el.tag)
            v = _to_float(el.text)
            if v is None:
                continue
            if ln == "TtlOfferingAmt":
                ttl.append(v)
            elif ln == "MaxAggtOfferingPric":
                maxes.append(v)
        if ttl:
            total = max(ttl)                 # 申报级总额（单值·避免多 context 相加）
        elif maxes:
            total = sum(maxes)               # 多证券类别求和 = 注册总额
    else:
        # iXBRL 兜底：吃 scale 属性（<ix:nonFraction … scale="0">1,234</ix:nonFraction>）
        vals = []
        for m in re.finditer(
                r'<ix:nonFraction[^>]*name="[^"]*MaxAggtOffer[^"]*"[^>]*>([^<]*)</', text, re.I):
            tag = m.group(0)
            sc = re.search(r'scale="(-?\d+)"', tag)
            scale = int(sc.group(1)) if sc else 0
            v = _to_float(m.group(1))
            if v is not None:
                vals.append(v * (10 ** scale))
        if vals:
            total = sum(vals)

    if total is None or not (1e5 <= total <= 1e13):     # 界外即拒（含 None）
        return None, "unknown"
    if 95e6 <= total <= 105e6:                          # $100M 经典占位额：仅标注，不改分层
        return total, "placeholder_suspect"
    return total, "parsed"


# ══════════════════════════════════════════════════════════════════════
# Stage D — 母市场市值（仅别名命中者调用·极少数）
# ══════════════════════════════════════════════════════════════════════
def _fi_get(fi, *keys):
    """从 yfinance fast_info（类 dict/对象）取值，容错多种取法。"""
    for k in keys:
        try:
            v = fi[k]
        except (KeyError, TypeError, IndexError):
            v = None
        if v is None:
            v = getattr(fi, k, None)
        if v is not None:
            return v
    return None


def _fetch_fast_info(symbol):
    """独立包一层便于测试 monkeypatch（真实调用走 yfinance）。"""
    import yfinance as yf
    return yf.Ticker(symbol).fast_info


def home_mktcap_usd(home_ticker):
    """母市值换 USD（KRW→USD 是隐藏坑：韩元市值直接比 $10B 会全过）。任一步失败 → None → 不升档。"""
    try:
        fi = _fetch_fast_info(home_ticker)
        cap = _fi_get(fi, "market_cap", "marketCap")
        cur = _fi_get(fi, "currency")
        if cap is None:
            return None
        cap = float(cap)
        if cur and cur != "USD":
            fx = _fetch_fast_info(f"{cur}USD=X")
            rate = _fi_get(fx, "last_price", "lastPrice", "previous_close")
            if not rate:
                return None
            cap *= float(rate)
        return cap
    except Exception as e:
        print(f"  ⚠ 母市值取用失败 {home_ticker}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════
# Stage E — 分层决策表（机械·有先后·公司级）
# ══════════════════════════════════════════════════════════════════════
def decide_tier(*, curated_hit, home_mktcap_b, spac, amount_m, amount_status, foreign):
    """返回 (tier, tier_reasons[])。金额只有升档力（仅 status=='parsed' 才作数）。"""
    if curated_hit:
        return "major", ["watchlist"]
    if home_mktcap_b is not None and home_mktcap_b >= HOME_MKTCAP_USD_B:
        return "major", ["home_mktcap"]
    if spac:
        return "rest", ["spac"]                      # 到此为止，金额不再看
    eff_amt = amount_m if amount_status == "parsed" else None   # 占位/未知 → 不作数
    if eff_amt is not None:
        if eff_amt >= MAJOR_USD_M:
            return "major", ["amount"]
        if eff_amt >= NOTABLE_USD_M:
            return "notable", ["amount"]
    if foreign and not spac and eff_amt is None:
        return "notable", ["foreign_unknown"]
    return "rest", []


# ══════════════════════════════════════════════════════════════════════
# 缓存（SIC/费用是申报级不变事实、永久有效；母市值不缓存，每 run 现取）
# ══════════════════════════════════════════════════════════════════════
def load_cache():
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(cache):
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"  ⚠ 缓存写入失败(非致命): {e}")


# ══════════════════════════════════════════════════════════════════════
# 编排：读 ipo_filings.json → 按 CIK 富化 → 写回
# ══════════════════════════════════════════════════════════════════════
_BUCKETS = ("filed", "priced", "listing", "adr")
_BUCKET_RANK = {"listing": 0, "priced": 1, "filed": 2, "adr": 3}   # 显示优先级（越确定越靠前）


def _company_index(data):
    """按 CIK 聚合：cik → {buckets:set, rows:[(bucket,row)], company, foreign, latest}。"""
    idx = {}
    for b in _BUCKETS:
        for row in data.get(b, []) or []:
            cik = row.get("cik")
            if not cik:
                continue
            c = idx.setdefault(cik, {"buckets": set(), "rows": [], "company": row.get("company"),
                                     "foreign": False, "latest": ""})
            c["buckets"].add(b)
            c["rows"].append((b, row))
            form = str(row.get("form") or "")
            if row.get("foreign") or form.upper().startswith(("F-1", "F-6")):
                c["foreign"] = True
            c["latest"] = max(c["latest"], row.get("filed") or "")
            if not c["company"]:
                c["company"] = row.get("company")
    return idx


class Budget:
    def __init__(self, cap):
        self.cap, self.used, self.blocked = cap, 0, False

    def can(self):
        return (not self.blocked) and self.used < self.cap

    def spend(self):
        self.used += 1


def _process_cik(cik, comp, *, watchlist, aliases, cache, budget, exclusions=None):
    """跑一家公司的富化，返回 enrichment dict（含 tier|None、各字段、enrich 状态）。"""
    normfull = _norm_full(comp["company"])
    normkey = _norm_key(comp["company"])
    curated_hit, wl_name = match_watchlist(normkey, watchlist, exclusions)
    home_ticker = match_alias(normkey, aliases)
    nm_spac = name_spac(normfull)
    foreign = comp["foreign"]
    adr_only = comp["buckets"] == {"adr"}

    enr = {
        "curated_hit": curated_hit, "curated_name": wl_name,
        "home_ticker": home_ticker, "home_mktcap_usd_b": None,
        "spac": nm_spac, "spac_source": "name" if nm_spac else None,
        "amount_usd_m": None, "amount_status": "unknown",
        "tier": None, "tier_reasons": [], "enrich": "done",
    }

    # 母市值（别名命中者才取；yfinance，不计 SEC 预算）
    home_b = None
    if home_ticker:
        cap = home_mktcap_usd(home_ticker)
        if cap:
            home_b = round(cap / 1e9, 2)
            enr["home_mktcap_usd_b"] = home_b

    sic = None
    # 决定是否需要 SEC（B/C）：
    #  · adr-only（纯 F-6）→ 跳过 B/C（详规 §6：程序性代递，SIC/费用无意义）
    #  · 名称启发已判 SPAC → rest 已定，无需 SEC（省预算，SPAC 是噪音主体）
    #  · curated_hit / home_mktcap≥阈值 已不再短路（R1 拍板）：tier 早定，但仍照样取 SEC 费表金额
    #    可核佐证（如 SK hynix：母市值已判 major，仍应能亮出 $30B 级 SEC 申报金额）。
    need_sec = (not adr_only) and (not nm_spac)

    if need_sec:
        cached = cache.get(cik)
        comp_latest_filed = comp.get("latest") or ""
        # F1 缓存失效：该公司若出现了不早于缓存 fetched_date 的新申报行（可能是占位额升级为真额的
        # 新 S-1/A）→ 缓存判过期、重走 B/C 拿最新 accession；否则信任缓存（SIC/费用是申报级不变事实）。
        fresh = bool(cached) and "sic" in cached and comp_latest_filed < cached.get("fetched_date", "")
        if fresh:
            sic = cached.get("sic")
            enr["amount_usd_m"] = cached.get("amount_usd_m")
            enr["amount_status"] = cached.get("amount_status", "unknown")
        else:
            if not budget.can():
                enr["enrich"] = "deferred"
                enr["amount_status"] = "deferred"
                # 名称非 SPAC、金额待定：先不落 tier（下轮续跑）；但 foreign 仍可给出保守 notable？
                # 详规 §7：未知不升档。deferred 行不落 tier（前端「未分层·延迟」）。
                return enr
            try:
                budget.spend()
                subs = fetch_submissions(cik)
                sic = subs["sic"]
                s1_adsh = subs["s1_adsh"]
                amount_m, status = None, "unknown"
                if sic != "6770" and s1_adsh:      # SPAC 短路：不解析费用
                    budget.spend()
                    loc = locate_fee_doc(cik, s1_adsh)
                    if loc:
                        budget.spend()
                        doc_url, is_xml = loc
                        amt, status = parse_fee_doc(_get(doc_url), is_xml)
                        amount_m = round(amt / 1e6, 2) if amt is not None else None
                enr["amount_usd_m"] = amount_m
                enr["amount_status"] = status
                cache[cik] = {"sic": sic, "amount_usd_m": amount_m,
                              "amount_status": status,
                              "fetched_date": datetime.date.today().isoformat()}
            except SecBlocked as e:
                print(f"  ⚠ SEC 限流/封禁，退避收工：{e}")
                budget.blocked = True
                enr["enrich"] = "deferred"
                enr["amount_status"] = "deferred"
                return enr
            except Exception as e:
                print(f"  ⚠ {cik} ({comp['company']}) 富化失败(跳过·保守 unknown): {type(e).__name__}: {e}")
                enr["amount_status"] = "unknown"

    # 汇总 SPAC（名称启发 ∪ SIC 6770）
    if sic == "6770":
        enr["spac"] = True
        enr["spac_source"] = "sic"

    # adr-only 且未命中别名 → 保持未分层（噪音隔离·不落 tier）
    if adr_only and not home_ticker:
        enr["tier"] = None
        enr["enrich"] = "adr_unlayered"
        return enr

    tier, reasons = decide_tier(
        curated_hit=enr["curated_hit"], home_mktcap_b=home_b, spac=enr["spac"],
        amount_m=enr["amount_usd_m"], amount_status=enr["amount_status"], foreign=foreign)
    enr["tier"], enr["tier_reasons"] = tier, reasons
    return enr


# 公示文案（前端 <details>「本分层怎么算的」直接读）
_TIER_RULES = {
    "zh": ("机械分层、无人工评级、非荐股非预测。按先后：①在策展关注名单→🔴；"
           "②境外母公司市值≥$10B→🔴；③SPAC(SIC 6770 或「X Acquisition Corp」名称)→其余；"
           "④拟募资≥$500M→🔴；⑤拟募资≥$150M→🟡；⑥外国发行人且金额未知→🟡；⑦其余→折叠。"
           "拟募资读 SEC EX-FILING FEES(Exhibit 107)结构化数据，绝不正文刮数；"
           "【金额只有升档力】——申报「拟募资上限」含绿鞋/余量，小额（如 $100M 占位额）不作降档信号；"
           "【未知一律不升档】。SEC 限制自动化 CI 抓取，随本地流水线运行分批富化，无 tier 的行=未分层/延迟。"),
    "en": ("Mechanical tiering — no human rating, not advice, not a forecast. In order: (1) on the "
           "curated watchlist → 🔴; (2) foreign parent's market-cap ≥ $10B → 🔴; (3) SPAC (SIC 6770 or "
           "an \"X Acquisition Corp\" name) → rest; (4) proposed raise ≥ $500M → 🔴; (5) ≥ $150M → 🟡; "
           "(6) foreign issuer with unknown amount → 🟡; (7) everything else → collapsed. The proposed "
           "raise is read from SEC EX-FILING FEES (Exhibit 107) structured data — never scraped from prose; "
           "amount can only PROMOTE (the filed max aggregate is a ceiling incl. green-shoe/headroom; a small "
           "or $100M-placeholder figure is never a downgrade signal); unknown never promotes. SEC blocks "
           "automated CI fetches, so enrichment runs in local batches — rows without a tier are unlayered/deferred."),
}


def enrich(data, *, watchlist, aliases, cache, budget, exclusions=None):
    """就地富化 data（各 bucket 行加字段）+ 加顶级字段。返回 (n_major, n_notable)。"""
    idx = _company_index(data)

    # 优先级：策展/别名 → listing → priced → filed → adr（新→旧）
    def prio(cik):
        c = idx[cik]
        nk = _norm_key(c["company"])
        star = 0 if (match_watchlist(nk, watchlist, exclusions)[0] or match_alias(nk, aliases)) else 1
        rank = min(_BUCKET_RANK[b] for b in c["buckets"])
        return (star, rank, _neg_date(c["latest"]))

    order = sorted(idx.keys(), key=prio)
    enr_by_cik = {}
    for cik in order:
        enr_by_cik[cik] = _process_cik(cik, idx[cik], watchlist=watchlist,
                                       aliases=aliases, cache=cache, budget=budget,
                                       exclusions=exclusions)

    # 写回每行（公司级同一 enrichment 贴到该 CIK 的所有行）
    _ENR_FIELDS = ("tier", "tier_reasons", "spac", "spac_source", "amount_usd_m",
                   "amount_status", "home_ticker", "home_mktcap_usd_b", "curated_hit", "enrich")
    n_major = n_notable = 0
    for cik, enr in enr_by_cik.items():
        if enr["tier"] == "major":
            n_major += 1
        elif enr["tier"] == "notable":
            n_notable += 1
    for b in _BUCKETS:
        for row in data.get(b, []) or []:
            enr = enr_by_cik.get(row.get("cik"))
            if not enr:
                continue
            for f in _ENR_FIELDS:
                if enr.get(f) is not None or f in ("tier", "amount_usd_m", "home_mktcap_usd_b"):
                    row[f] = enr.get(f)
    return n_major, n_notable


def _neg_date(d):
    """让新日期排前（升序 sort 里取负）。d 形如 'YYYY-MM-DD' 或 ''。"""
    return tuple(-int(x) for x in d.split("-")) if d else (0,)


def run():
    src = WEB / "ipo_filings.json"
    if not src.exists():
        print("[IPO-ENRICH] 无 ipo_filings.json，跳过（fetch_ipo 未产出）")
        return None
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[IPO-ENRICH] ipo_filings.json 读取失败，跳过(原文件完好): {e}")
        return None

    watchlist, aliases, exclusions, asof = load_watch()
    cache = load_cache()
    budget = Budget(MAX_ENRICH_REQ)

    try:
        n_major, n_notable = enrich(data, watchlist=watchlist, aliases=aliases,
                                    cache=cache, budget=budget, exclusions=exclusions)
    except Exception as e:
        # fail-soft：富化整体炸掉 → 原始 ipo_filings.json 完好、不写坏数据
        print(f"[IPO-ENRICH] 富化异常，保留原始 ipo_filings.json(不写): {type(e).__name__}: {e}")
        return None

    save_cache(cache)

    data["tier_rules"] = _TIER_RULES
    data["tier_thresholds"] = {"major_usd_m": MAJOR_USD_M, "notable_usd_m": NOTABLE_USD_M,
                               "home_mktcap_usd_b": HOME_MKTCAP_USD_B}
    data["curated_asof"] = asof
    data["enrich_generated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["n_major"] = n_major
    data["n_notable"] = n_notable
    data["enrich_budget"] = {"max_req": budget.cap, "used": budget.used,
                             "sec_blocked": budget.blocked}

    from util_io import write_json
    written = write_json("ipo_filings.json", data, indent=1, allow_nan=False)
    print(f"[OK] ipo_filings.json 富化 — 🔴major {n_major} · 🟡notable {n_notable} · "
          f"SEC 请求 {budget.used}/{budget.cap}"
          f"{'（SEC 退避·部分 deferred）' if budget.blocked else ''} → {len(written)} 处")
    return data


if __name__ == "__main__":
    run()
    sys.exit(0)
