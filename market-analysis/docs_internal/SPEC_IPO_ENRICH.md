# SPEC_IPO_ENRICH — IPO「重大性分层」富化引擎(A2)

> Fable 军师建造级详规(2026-07-12)。目的:从每档 60 条原始申报流机械分层出
> `major`(🔴重大)/`notable`(🟡值得注意)/`rest`(其余)。**未知一律不升档、绝不猜数**——
> 这是防吹票机的结构性保证。事实/日历层,非荐股非预测。

## 0. 定位与红线
- **新建 `ipo_enrich.py`**,run_all 里挂在 `fetch_ipo.py` 之后(同 fail-soft、不入 `--light`)。
  不并入 fetch_ipo——富化失败时原始快照仍新鲜,前端把无 `tier` 字段的行显示为「未分层」。
- CI 现实:SEC 封 Actions IP → 富化与抓取一样走**本地 top-up**;前端已有「非固定周期」标注天然覆盖,无新增诚实债。
- **第 0 步实弹验证(建造者必做)**:从当前 ipo_filings.json filed 档随机取 3 个 adsh,实抓 fee exhibit,
  dump 实际文件名与标签名核对本规格正则;**若对不上 → 停下报告实际结构,禁止即兴改成自由文本美元刮取**。

## 1. 数据流五阶段
```
fetch_ipo.py(改一处:行加 adsh) → ipo_filings.json(原始)
  → ipo_enrich.py:
     Stage A 零请求预筛(名称启发+策展/别名匹配)
     Stage B submissions API(SIC + S-1 accession 回溯 + 交易所)
     Stage C EX-FILING FEES(定位+解析拟募资额)
     Stage D 母市场市值(别名表→yfinance→USD 换算)
     Stage E 分层决策表 → 写回 ipo_filings.json(富化)
  → ipo.html 分档展示+规则公示
```

## 2. fetch_ipo.py 唯一改动:捕获 accession
`_fetch_forms` 每行加:
```python
adsh = s.get("adsh") or (h.get("_id", "").split(":")[0])
row["adsh"] = adsh if re.fullmatch(r"\d{10}-\d{2}-\d{6}", adsh or "") else None
```
(efts 命中 `_id` 形如 `0001234567-26-000123:file.htm`;`_source.adsh` 有时直接给。两路都试、格式验证兜底。)

## 3. Stage A — 零请求预筛
**normalize(name)**:大写→去标点→压空格→迭代剥尾部法律后缀
`(INC|CORP|CORPORATION|LTD|LIMITED|CO|COMPANY|PLC|NV|SA|AG)`。**不剥 HOLDINGS/GROUP**
(剥了会把 "XX Holdings" 和 "XX" 混同,误匹配)。

**SPAC 名称启发**(仅此一条正则,宽了必误伤,对 normalize 后名字):
`\bACQUISITION\s+(CORP(ORATION)?|CO(MPANY)?|HOLDINGS)\b`
反例守门:"Data Acquisition Systems Inc" 不得命中。名称启发命中标 `spac_source:"name"`(前端「疑似空壳」),
SIC 命中标 `spac_source:"sic"`(确定)。

**策展/别名表** `market-analysis/data/curated/ipo_watch.json`(新建·人工维护·文件头写 as-of + 维护规约):
```json
{
  "asof": "2026-07",
  "watchlist": ["SPACEX", "OPENAI", "ANTHROPIC", "CEREBRAS", "..."],
  "aliases": [{"names": ["SK HYNIX"], "home": "000660.KS", "note": "韩交所母上市"}]
}
```
- `watchlist` 种子 = ipo.html 策展快照的已申报/传闻档名单(L143-177);**建造者只搬现有名单、绝不自己加名**
  (加名=编辑判断,只走主公/用户/Fable)。
- 匹配:normalize 后**整词子串匹配**;命中 ≥2 个不同别名条目 → **弃权不匹配 + 打 warning**(歧义即弃权,宁漏勿错)。
  watchlist 命中 = `curated_hit:true`。
- `aliases` 防误匹配三闸:①条目名 ≥5 字符独特串 ②整词匹配 ③歧义弃权。

## 4. Stage B — submissions API(1 请求/CIK,缓存后近零)
`GET https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json`(同 SEC_UA_CONTACT UA)一次取三样:
1. `sic == "6770"` → blank check(SPAC 权威判定,与名称启发取并集);
2. `filings.recent`:在 `form[]` 找最新 `S-1|S-1/A|F-1|F-1/A` → 其 `accessionNumber[i]` = 费用解析目标
   (**解决 424B/8-A12B 行的费用来源**——它们的注册费在早前 S-1 里,可能已出 30 天窗;零额外请求);
3. `tickers[]/exchanges[]`:辅助显示,不参与分层。

**adr(F-6)档特殊规则**:只跑 Stage A + D,跳过 B/C(F-6 常为存托行程序性代递,SIC/费用无意义)。
但**别名命中的 adr 行走完整 D 阶梯**——海力士 F-6 07-01 是全案最早信号,这条规则保住那份 lead time;
未命中别名的 F-6 保持未分层(噪音继续隔离)。

## 5. Stage C — EX-FILING FEES 定位与解析(核心硬件)
背景:2022-01-31 起费用移入独立 **Exhibit 107**(EDGAR 类型 `EX-FILING FEES`),iXBRL 结构化分阶段强制
(大型加速 2024-07-31、其余 2025-07-31)→ 2026 新申报**应当**都有结构化费用;更早旧格式诚实降级。

**定位(2 请求/公司)**:
```
① GET https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh去横杠}/index.json → directory.item[].name
   候选 = 文件名匹配 r"(?i)(ex[-_.]?107|filing[-_]?fees?)";.xml 优先于 .htm
② 若无候选 → GET .../{adsh}-index.htm,找含 "EX-FILING FEES" 的表格行、取同一 <tr> 块内 href
③ 仍无 → amount_status="unknown",停(旧格式/缺失,不猜)
④ GET 候选文档
```
**解析伪码**(FFD taxonomy 目标 = `MaxAggtOfferingPric` 族):
```python
def parse_fee_doc(text, is_xml):
    vals = []
    if is_xml:
        vals = [el.text for el in iter_elements(text) if "MaxAggtOffer" in localname(el)]
    else:  # iXBRL: <ix:nonFraction name="ffd:MaxAggtOfferingPric..." scale="0">1,234,567,890</...>
        for m in re.finditer(r'<ix:nonFraction[^>]*name="[^"]*MaxAggtOffer[^"]*"[^>]*>([^<]*)</', text, re.I):
            scale = int(re.search(r'scale="(-?\d+)"', m.group(0)).group(1)) if 'scale="' in m.group(0) else 0
            vals.append(clean_number(m.group(1)) * 10 ** scale)   # 必须吃 scale 属性
    vals = [v for v in map(to_float, vals) if v is not None and 1e5 <= v <= 1e13]  # 界外即拒
    if not vals:
        return None, "unknown"
    total = sum(vals)                     # 费用表多行(多证券类别)求和=注册总额
    status = "parsed"
    if 95e6 <= total <= 105e6:
        status = "placeholder_suspect"    # $100M 经典占位额,仅标注,不改分层
    return total, status
```
**三条诚实铁则**:
1. **绝不自由文本美元刮取**(正文 regex "$xxx" 找数——误抓错数比未知更糟)。结构化解析失败=金额未知,走其他信号。
2. **金额语义不对称**:Proposed Maximum Aggregate 是含绿鞋+余量的**上限**,小额常为占位 →
   **高额是可靠大交易信号,低额不是小交易信号**。故**金额只有升档力、没有降档力**。
3. **建造者第 0 步实弹验证**(见 §0)。

## 6. Stage D — 母市场市值
```python
def home_mktcap_usd(home_ticker):          # 仅对 aliases 命中的公司调用(极少数)
    fi = yf.Ticker(home_ticker).fast_info
    cap, cur = fi["market_cap"], fi["currency"]      # 000660.KS 给的是 KRW!
    if cur != "USD":
        cap *= yf.Ticker(f"{cur}USD=X").fast_info["last_price"]   # 失败→None
    return cap    # 任何一步失败 → None → unknown → 不升档
```
币种换算是隐藏坑(韩元市值直接比 $10B 会全过)——测试必须含 KRW 用例。

## 7. Stage E — 分层决策表(机械·有先后·公司级)
按 **CIK 去重到公司级**(同一公司跨档取最高档,各档行都显示同一 tier 徽章):
```
1. curated_hit                    → 🔴 major   理由码 "watchlist"(传闻转已申报=最高价值)
2. home_mktcap_usd ≥ $10B         → 🔴 major   理由码 "home_mktcap"
3. spac(SIC 6770 或名称启发)      → rest       理由码 "spac"(到此为止,金额不再看)
4. amount_usd ≥ 🔴阈值            → 🔴 major   理由码 "amount"
5. amount_usd ≥ $150M             → 🟡 notable 理由码 "amount"
6. foreign 且非spac 且金额unknown → 🟡 notable 理由码 "foreign_unknown"
7. 其余(含 unknown/占位/未匹配F-6)→ rest
```
每行落 `tier_reasons:[]`(机器码,前端译理由芯片:「拟募资 $1.2B」「母市值 $118B (000660.KS)」「SIC 6770 空壳」)。

## 8. 阈值(拍板项·Fable lean)
- **🔴 阈值 lean $500M**(不推 $1B):金额规则的独特职责=兜住无策展的本土独角兽(Reddit 型实募~$750M);
  $1B 会把 Reddit 级漏成🟡不推送=用户最恨的「对新闻级事件沉默」。proposed max 含水分~15-25% →
  $500M 申报≈$400M 实募,仍是任一年前 30 大 IPO。🔴 事件估~每月 2-4 条,未到疲劳线。
  权衡:选 $1B 严格档=「重大」标签更稀缺(每月~1条)但漏 Reddit 级。**建造不阻塞:先按 $500M 建成常量,拍板后一行改。**
- **🟡 下沿 $150M**(避开 $100M 占位额:≤$105M 全占位嫌疑)。

## 9. 请求预算与缓存(10 req/s 内)
- 全局 `time.sleep(0.12)`(≈8/s)+ `MAX_ENRICH_REQ=150`/run 硬顶。
- 冷启动最坏~180 CIK×(1 subs+2 fee)=540 请求>顶 → **超顶行标 `enrich:"deferred"` 下轮续跑**(~4 轮跑平;稳态每日增量 5-15 请求)。
- 花费优先级:策展/别名 → listing → priced → filed(新→旧)。
- 缓存 `data/raw/ipo_enrich_cache.json` 按 CIK 存 `{sic, fee:{adsh,amount,status}, fetched_date}`;
  SIC/费用是申报级不变事实、永久有效;母市值不缓存(每 run 现取)。data/raw 已 gitignore(本地 top-up)。
- **403/频繁失败 → 退避收工,绝不代理/轮换 IP**(件3 定案:规避 SEC 公平访问=气味问题)。

## 10. 输出 schema 增量(ipo_filings.json)
行级:`adsh, tier("major"|"notable"|"rest"|缺失=未分层), tier_reasons[], spac, spac_source,
amount_usd_m, amount_status("parsed"|"placeholder_suspect"|"unknown"|"deferred"), home_ticker,
home_mktcap_usd_b, curated_hit`。
顶级:`tier_rules`(公示文案:机械规则+阈值+「未知不升档」声明), `tier_thresholds:{major_usd_m,notable_usd_m,home_mktcap_usd_b}`,
`curated_asof, enrich_generated, n_major, n_notable`。

## 11. 前端(ipo.html·A2 可见半边)
- SEC 自动区顶部先列 🔴 组、再 🟡 组(带理由芯片),rest 折叠为现状原始流;tier 缺失显示「未分层(富化未跑/延迟)」。
- `<details>`「本分层怎么算的」= 公示 `tier_rules` 全文 + 阈值 + 未知不升档声明 + 占位额说明。
- zh/en 走既有 L10N;镜像 docs/;跑 `tools/audit_frontend.py` + `interaction_audit.py`。

## 12. 测试(pytest·canned fixtures 不碰网络)
1. iXBRL 解析(含 scale 属性、千分逗号);2. XML 变体;3. 占位额 $100M→placeholder_suspect 且不改档;
4. 界外值拒收;5. KRW 市值换算;6. 别名歧义弃权;7. SPAC 名称启发反例 "Data Acquisition Systems";
8. 决策表全分支(spac 短路金额、unknown 不升档、adr 别名例外);9. 富化器炸掉→原始 JSON 完好(fail-soft)。

## 停机点
- 任何人要「给 IPO 打分/评级」→ 停(荐股滑坡)。
- 第 0 步实弹验证对不上 → 停报实际结构,**禁止降级为自由文本刮取**。
- 策展/别名表加名=编辑判断,建造者只搬现有名单;新增名只走主公/用户/Fable。
- SEC 403/限流 → 退避收工,绝不代理绕行。

## 附录:实现偏差与已知限制(2026-07-12)
- **第 0 步实弹**:现代 EX-FILING FEES = 独立原生 XBRL `.xml` 实例文件(`*exfiling_fees_htm.xml`),
  含 `<ffd:…>` 全额值(decimals 属性,非 scale;值已是全额,不乘 10^scale)。同名 `.htm` 是纯 HTML 渲染、
  零 `<ix:nonFraction>` 标签。故 **XML 分支为已验证主路径**:ElementTree 取精确 localname 元素文本求和,
  不乘 scale;`TtlOfferingAmt` 主、`sum(MaxAggtOfferingPric)` 兜底(封 S-1/A 重复计洞)。iXBRL/scale 分支
  仅作保守兜底(实测现代申报走不到)。略过 §5②「index.htm 二次刮取」——实测 `index.json` 已列全部文件,
  足以定位;失败方向保守(直接 `unknown`,不再退化去刮 index.htm)。
- **已知限制①** `foreign_unknown`(理由码)噪音偏高:微型外国发行人(F-1/F-6 程序性代递居多)金额常年
  拿不到结构化费表 → 大量落 🟡 notable,人工看会觉得「太多黄标」。诚实说明:这是「未知不升档」铁则下的
  保守副作用,不是误判——只标了「外国 + 金额未知」,没有编造金额升档。
- **已知限制②** aliased 纯 F-6(adr-only)且母市值取数失败(yfinance 抓不到/API 波动)→ 不落 tier,
  停在 `foreign_unknown` 或未分层 🟡/空白,须等下轮富化重取(母市值不缓存、每 run 现取)。
- **F1/F2/R1 补丁(2026-07-12·军师亲审裁决落地)**:
  - F1 缓存失效:原实现里 SIC/费用缓存命中即永久短路、无失效条件,导致占位额(如 $100M)一旦缓存,
    后续 S-1/A 填真额永远看不见。改为缓存存 `fetched_date`;若该公司在当前 feed 里最新申报行的
    `filed` 日期不早于缓存 `fetched_date` → 视为可能有新申报出现,判缓存过期、重走 Stage B/C 拿最新
    accession,否则信任缓存。
  - F2 watchlist 收紧:`ipo_watch.json` 加 `exclusions`(法定全名整名相等即排除同名他司,如
    Kraken Robotics/Energy ≠ 加密交易所 Kraken);军师依规约授权加名 `Payward`(Kraken 法定名)、
    `Space Exploration Technologies`(SpaceX 法定名,补齐口径)。
  - 决定1:母市值理由芯片(`home_mktcap`)改为只标档位文案(「过 $10B 档」+ home_ticker),不再在
    前端亮精确市值数字(JSON 里 `home_mktcap_usd_b` 原始值仍完整保留、可审计)。
  - R1:`already_major`(策展/母市值命中即短路省 SEC)短路移除——curated_hit/home_mktcap 已判 major
    的公司现在仍会走 Stage B/C 取 SEC 费表金额作佐证(如 SK hynix 现带 $30.19B)。**已知副作用**:这些
    公司的 tier 此前不依赖 SEC 可用性(名称/市值匹配零 SEC 依赖、瞬时可判);现在若同一 run 内 SEC
    403/限流或预算耗尽发生在它们被处理**之前**,会连带落「未分层·延迟」而非瞬时 major,需等下轮
    续跑才恢复(fail-soft、自愈,但不再是此前的「零 SEC 依赖」保证)——因 watchlist/别名命中在优先级
    排序里排最前(`prio()` 的 star=0),实践中触发窗口很窄,但理论上存在;留意本条,非本次任务范围。
