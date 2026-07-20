"""ledger_sidecar.py — append-only 公开计分账本的 sidecar 哈希链（P2-9·账本文件一行不动）。

铁律：被保护的账本 CSV 本体**绝不写入**——链哈希存独立 manifest（data/ledger_hashchain.csv），
manifest 本身也 append-only（每次封存追加一行记录，绝不重写历史记录）。
链机制复用 ledger_hash 的 row_hash/GENESIS（同一 sha256 JSON 规范化链），不造新密码学。

双头设计（直面「重封祝福改动」语义坑，见 ledger_hash.py docstring / OPTIMIZATION_LOG verify-before-seal）：
- core_head：只链【建行即定、结算也不许碰】的身份字段（纯 append 账本 = 全字段）。
  封存时 verify-before-seal：上次封存的 core 前缀链必须在当前文件上复现，否则**拒绝封存**
  ——身份字段的篡改连流水线重封都「祝福」不掉，这一头比现有 in-file 链更硬。
- full_head：链全字段。forward_ledger 类账本的合法结算（只填空）会改它 → 只在
  「相对上一次封存」意义上校验（独立审计抓外改；流水线重封会祝福——同现有 in-file 链的诚实边界）。

能买到 / 买不到（诚实边界）：
- 抓得住：外改已封存历史行（身份字段=硬门；结算字段=相对上次封存）、删行/截尾（行数单调不减）。
- 抓不住：连 manifest 一起伪造的蓄意攻击（真取证靠 git 历史）；--rebless 是显式留痕的人工
  放行口（附 note 永久进 manifest），不是静默漏洞。

纳入范围（SPECS）只收「真·append-only 公开计分账本」；tipjar_log（可从价格确定性重算+已有
in-file 链）、paper_ledger/prediction_log（已有 in-file 链，且 merge=union+repair_ledgers
会合法去重排序重封，前缀不变式不适用）不在此列——见各自注释。
overreaction_signal_log 原被排除(processed/ merge=union 区)——2026-07-03 收编:调查发现它
**从未被 git 跟踪**(.gitignore 负模式对未跟踪文件失效·靠 actions/cache 假活)——已 git add -f
建跟踪(创世=当时状态·不伪造历史)+ .gitattributes 显式 merge=text 挪出 union + CI 缓存回灌防护。
"""
import csv
import datetime
import sys
from pathlib import Path

from ledger_hash import GENESIS, row_hash

DATA = Path(__file__).parent.parent / "data"
MANIFEST = DATA / "ledger_hashchain.csv"
MANIFEST_HEADER = ["sealed_at", "ledger", "n_rows", "fields", "core_fields",
                   "full_head", "core_head", "note"]

# (文件名, 身份字段;None = 全字段皆身份(纯 append 账本,历史行一个字节都不该变))
# 身份字段口径:建行即写死、结算(forward_ledger.settle 只填空)也不许碰的列。
SPECS = [
    # —— 纯 append(util_io.append_daily_log / 自写 append,绝不重写文件)——
    ("autodiscovery_log.csv", None),      # 自生长日裁决账本(CLAUDE.md 点名红线)
    ("candidate_registry.csv", None),     # OOS 锚点登记簿(declared_date 防挪靶的唯一真相)
    ("kb_ledger.csv", None),              # 知识库晋升/降级账本(尚无晋升时文件不存在→跳过)
    ("composite_log.csv", None),          # 综合倾向日计分
    ("regime_forward_log.csv", None),     # 体制前向裁决
    ("senate_signal_log.csv", None),      # 参议员信号日快照(当日主张的历史记录,不可事后重算)
    ("btc_backtest_log.csv", None),       # BTC动量→纳指回测日裁决
    ("llm_read_log.csv", None),           # LLM 日读存档(当日 LLM 输出,不可重生成)
    ("llm_weekly_log.csv", None),         # LLM 周报存档
    ("llm_monthly_log.csv", None),        # LLM 月报存档
    ("ipo_alert_log.csv", None),          # IPO重大事件预警账(A3·事件级:去重键(cik,stage)首见即append,含pushed留痕)
    # —— forward_ledger 结算型(settle 填空后整文件重写,但行序不变、身份列不碰)——
    ("llm_prediction_log.csv",
     ["pred_date", "symbol", "direction", "confidence", "reason", "horizon_td"]),
    ("pick_ledger.csv",
     ["pick_date", "symbol", "view", "mom_pct"]),
    ("au_pick_ledger.csv",
     ["pick_date", "symbol", "view", "mom_pct"]),  # B3:澳股荐股独立账本(pick_ledger 同构;基准^AXJO不同,不与美股混)
    ("insider_signal_log.csv",
     ["filed_date", "ticker", "insider", "title", "txn_date", "shares", "value"]),
    # 极端下跌→次日反弹公开计分(overreaction_alert.py):检测日即定 5 列=身份;结算填 next_*/hit/settled。
    # 2026-07-03 收编(此前从未被 git 跟踪·见文件头)——链创世=收编日状态,无历史声明。
    ("processed/overreaction_signal_log.csv",
     ["date", "index", "ret_pct", "threshold_pct", "signal"]),
]


# ── 链 & I/O（只读账本;只 append manifest）──────────────────────────────
def chain_head(rows, fields):
    """GENESIS 起折叠 row_hash → 链头。rows=list[dict](csv.DictReader 视角,封存/校验同口径)。"""
    prev = GENESIS
    for r in rows:
        prev = row_hash(r, fields, prev)
    return prev


def _read_ledger(path):
    with open(path, encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
        return list(rdr.fieldnames or []), rows


def read_manifest(manifest=MANIFEST):
    if not Path(manifest).exists():
        return []
    with open(manifest, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def latest_records(records):
    """ledger → 最新封存记录。按 sealed_at 取最大,平局取文件序靠后(容忍 merge=union 交错)。"""
    out = {}
    for rec in records:
        cur = out.get(rec["ledger"])
        if cur is None or str(rec["sealed_at"]) >= str(cur["sealed_at"]):
            out[rec["ledger"]] = rec
    return out


def _append_records(records, manifest=MANIFEST):
    manifest = Path(manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    new = not manifest.exists()
    with open(manifest, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_HEADER)
        if new:
            w.writeheader()
        for r in records:
            w.writerow(r)


# ── 封存（verify-before-seal:身份前缀链不复现 → 拒绝,重封祝福不掉）────────
def seal_one(path, core_spec, prev_rec, *, rebless_note=None, now=None):
    """封存单账本 → (status, record|None, msg)。status ∈ {"ok","skip","refuse"}。只读账本。"""
    header, rows = _read_ledger(path)
    core = list(core_spec) if core_spec else list(header)
    missing = [c for c in core if c not in header]
    if missing:   # schema 漂移须先改代码里的 SPECS,--rebless 不放行这个
        return ("refuse", None, f"身份字段不在表头(疑似 schema 漂移,先修 SPECS): {missing}")
    if prev_rec is not None and rebless_note is None:
        n_prev = int(prev_rec["n_rows"])
        if len(rows) < n_prev:
            return ("refuse", None,
                    f"行数缩水({len(rows)} < 上次封存 {n_prev})——append-only 账本绝不删行"
                    "(查明后 --rebless 留痕放行)")
        prev_core = prev_rec["core_fields"].split("|") if prev_rec["core_fields"] else []
        if chain_head(rows[:n_prev], prev_core) != prev_rec["core_head"]:
            return ("refuse", None,
                    "上次封存的身份字段前缀链不复现——已封存历史行的身份被改,拒绝重封祝福"
                    "(查明后 --rebless 留痕放行)")
    rec = {
        "sealed_at": now or datetime.datetime.now(datetime.timezone.utc)
                                             .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ledger": Path(path).name,
        "n_rows": len(rows),
        "fields": "|".join(header),
        "core_fields": "|".join(core),
        "full_head": chain_head(rows, header),
        "core_head": chain_head(rows, core),
        "note": rebless_note or "",
    }
    if (prev_rec is not None and rebless_note is None
            and all(str(rec[k]) == str(prev_rec.get(k))
                    for k in ("n_rows", "fields", "core_fields", "full_head", "core_head"))):
        return ("skip", None, "内容与上次封存一致,不追加")   # 防 CI 小时级跑把 manifest 刷爆
    return ("ok", rec, "已封存")


def _assert_unique_basenames(specs):
    """manifest 的 ledger 键=basename(seal_one 写 Path.name)——SPECS 若两条同名不同目录会互相污染血统。"""
    names = [Path(f).name for f, _ in specs]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"SPECS basename 冲突(manifest 按 basename 记账,不允许重名): {dupes}"


def seal_all(data_dir=DATA, manifest=MANIFEST, specs=SPECS, *,
             rebless=None, note=None, write=True):
    """封存全部在册账本 → (新增记录数, 拒绝列表)。rebless=文件名(须带 note,只放行那一个)。"""
    _assert_unique_basenames(specs)
    latest = latest_records(read_manifest(manifest))
    to_append, refusals = [], []
    for fname, core_spec in specs:
        p = Path(data_dir) / fname
        if not p.exists():           # 存在才封(如 kb_ledger 首批晋升前不存在)
            continue
        rn = note if rebless == fname else None
        # 查上次记录必须用 basename——manifest 存 Path.name;子目录 fname 直查会永远 miss →
        # verify-before-seal 被静默跳过(2026-07-03 收编 processed/ 首个子目录条目时实弹演练抓到的真 bug)
        status, rec, msg = seal_one(p, core_spec, latest.get(p.name), rebless_note=rn)
        if status == "refuse":
            refusals.append(f"{fname}: {msg}")
            print(f"  ✗ {fname}: {msg}")
        elif status == "ok":
            to_append.append(rec)
            print(f"  ✓ {fname}: 封存 {rec['n_rows']} 行 head={rec['full_head'][:12]}…"
                  + (f"  [rebless 留痕: {rn}]" if rn else ""))
        else:
            print(f"  = {fname}: {msg}")
    if to_append and write:
        _append_records(to_append, manifest)
    return len(to_append), refusals


# ── 校验（verify_output §4b 调;只读)────────────────────────────────────
def verify_ledger(path, rec):
    """当前账本 vs 最新封存记录 → 错误列表(空=通过)。字段口径用**记录里存的**,防 spec 漂移。"""
    _, rows = _read_ledger(path)
    n_sealed = int(rec["n_rows"])
    if len(rows) < n_sealed:
        return [f"行数少于上次封存({len(rows)} < {n_sealed})——历史行被删/截尾"]
    fields = rec["fields"].split("|") if rec["fields"] else []
    core = rec["core_fields"].split("|") if rec["core_fields"] else []
    prefix = rows[:n_sealed]
    if chain_head(prefix, core) != rec["core_head"]:
        return [f"身份字段前缀链断裂——已封存的前 {n_sealed} 行身份字段被改"]
    if chain_head(prefix, fields) != rec["full_head"]:
        return ["全字段链与上次封存不符——历史行被外改,或合法结算后未重封"
                "(跑 ledger_sidecar.py / run_all 重封后再验)"]
    return []


def verify_all(data_dir=DATA, manifest=MANIFEST, specs=SPECS):
    """→ list[(fname, errors)]。账本或封存记录缺失 → 跳过(存在才查,bootstrap 友好)。"""
    _assert_unique_basenames(specs)
    latest = latest_records(read_manifest(manifest))
    out = []
    for fname, _core in specs:
        p = Path(data_dir) / fname
        rec = latest.get(p.name)     # 同 seal_all:manifest 键=basename(子目录 fname 直查会静默跳过校验)
        if not p.exists() or rec is None:
            continue
        out.append((fname, verify_ledger(p, rec)))
    return out


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = sys.argv[1:]
    rebless = note = None
    if "--rebless" in args:
        i = args.index("--rebless")
        rebless = args[i + 1] if i + 1 < len(args) else None
        if "--note" in args:
            j = args.index("--note")
            note = args[j + 1] if j + 1 < len(args) else None
        if not rebless or not note:
            sys.exit("--rebless <账本文件名> 必须带 --note '放行原因'(留痕进 manifest)")
    n, refusals = seal_all(rebless=rebless, note=note)
    if refusals:
        print(f"\n[FAIL] {len(refusals)} 个账本拒绝封存(疑似历史行被改,查明后 --rebless 留痕放行)")
        sys.exit(1)
    print(f"\n[OK] sidecar 封存完成(新增记录 {n};账本本体零写入)")
