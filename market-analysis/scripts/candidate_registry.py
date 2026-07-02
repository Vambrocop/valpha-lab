"""candidate_registry.py — 自生长闭环 P-A 地基：候选的 append-only 注册登记簿（OOS 锚点的唯一真相）。

每个候选首次进入候选空间(candidate_space) → 在此登记一行 {candidate_id, family, key, declared_date, reason, reviewer}。
`declared_date` = 该候选的 **OOS 锚点**：门4(待建)只认 declared_date 之后的数据是否仍成立（防事后挪靶）。

铁律（红线）：
- **append-only，绝不改历史行**。一行的 declared_date 一旦写下永不改——这正是"没法偷偷挪靶"的诚实机制。
- candidate_id = candidate_space 里 family+params 的稳定哈希 → **改参数 = 换 id = 被迫新登记 + 更晚锚点**。
- 旧候选(首批 N_DECLARED) 无历史注册日 → 锚 = 计划采纳日(首次 sync 当天)，前向累积(**不回填数据起点 = 不造假长 OOS**)。
- 新候选（以后扩 N，走 candidate_space 双审）→ 锚 = 它首次出现在枚举里的当天（本脚本自动 stamp）。

本文件只做"登记 + 取锚点"，**不算任何统计**（OOS 门4 在 P-A 核心另起、单独审）。
"""
import csv
import datetime
import io
import re
from pathlib import Path

import candidate_space as cs

SCRIPTS = Path(__file__).parent
LOG = SCRIPTS.parent / "data" / "candidate_registry.csv"
HEADER = ["candidate_id", "family", "key", "declared_date", "reason", "reviewer"]
_REASON = "首次进入候选空间·自动锚定 declared_date 为 OOS 锚（扩 N 的判断/理由走 candidate_space 双审）"
_REVIEWER = "auto-sync"


def _read(path=LOG):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_anchors(path=LOG):
    """candidate_id → declared_date（OOS 锚点）。供 P-A 门4 引擎读。"""
    return {r["candidate_id"]: r["declared_date"] for r in _read(path)}


def sync(today=None, path=LOG, write=True):
    """给所有【尚未登记】的当前候选 append 一行（declared_date=today）。已登记行绝不改动。返回新登记数。"""
    today = today or datetime.date.today().isoformat()
    existing = {r["candidate_id"] for r in _read(path)}
    new = [{"candidate_id": c["candidate_id"], "family": c["family"], "key": c["key"],
            "declared_date": today, "reason": _REASON, "reviewer": _REVIEWER}
           for c in cs.enumerate_candidates() if c["candidate_id"] not in existing]
    if new and write:
        path.parent.mkdir(parents=True, exist_ok=True)
        need_header = not path.exists()
        with open(path, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HEADER)
            if need_header:
                w.writeheader()
            for r in new:                       # 只 append 新候选；已登记的一行都不碰（append-only 红线）
                w.writerow(r)
    return len(new)


def _parse(text):
    """CSV 文本 → (header 列表, 行 dict 列表)。用 csv 模块解析(容 CRLF/引号，不比字节)。"""
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return list(reader.fieldnames or []), rows


def check_registry_immutable(old_text, new_text):
    """P2-10 门:比较新旧两版 registry 文本(**语义行**，不比字节) → 违反 append-only 的问题串列表(空=通过)。

    三条不变量(用 candidate_id 做行身份对齐):
    ① old 里已有的每一行，在 new 同 candidate_id 下逐字段不变(**限 old 的列集**——new 加新列不算违反)。
    ② new 里 candidate_id 无重复(防 load_anchors 静默二选一)。
    ③ new 新增行的 declared_date ≥ old 里最晚的 declared_date(防倒填造假长 OOS)。
    old_text 为空(首次建档)→ 无历史行可比，只查②。
    """
    problems = []
    new_cols, new_rows = _parse(new_text)

    ids = [r.get("candidate_id") for r in new_rows]
    dupes = sorted({i for i in ids if i and ids.count(i) > 1})
    if dupes:
        problems.append(f"candidate_id 重复(new 中出现 >1 次): {dupes}")

    old_cols, old_rows = _parse(old_text) if old_text.strip() else ([], [])
    if not old_rows:
        return problems              # 首次建档:无历史行需要保护，只需查重(上面已做)

    new_by_id = {}
    for r in new_rows:
        new_by_id.setdefault(r.get("candidate_id"), r)   # 重复已在②报过，这里取第一条即可

    for old_r in old_rows:
        cid = old_r.get("candidate_id")
        new_r = new_by_id.get(cid)
        if new_r is None:
            problems.append(f"历史候选 {cid} 在新版本中消失(append-only 不许删行/改名)")
            continue
        for col in old_cols:         # 限 old 的列集——new 加新列不算违反
            if str(old_r.get(col, "")) != str(new_r.get(col, "")):
                problems.append(f"历史候选 {cid} 字段 {col!r} 被篡改: "
                                 f"{old_r.get(col)!r} → {new_r.get(col)!r}")

    old_ids = {r.get("candidate_id") for r in old_rows}
    old_max_date = max((r.get("declared_date") or "" for r in old_rows), default="")
    iso = re.compile(r"^\d{4}-\d{2}-\d{2}$")     # ③ 依赖字典序≡时间序,只对零填充 ISO 成立
    for r in new_rows:
        if r.get("candidate_id") in old_ids:
            continue                 # 已有行，字段不变性已在上面查过
        d = (r.get("declared_date") or "").strip()
        # Opus 审洞:非零填充日期(如 '2026-1-1')字典序 > '2026-06-26' 但语义是 1 月 → 绕过倒填检查。
        # sync() 恒写 isoformat() 规范格式 → 非规范只可能来自手工篡改(正在威胁模型内),直接拒。
        if not iso.match(d):
            problems.append(f"新增候选 {r.get('candidate_id')} 的 declared_date={d!r} "
                             f"非规范 ISO(YYYY-MM-DD)——拒绝(防非规范格式绕过倒填检查)")
        elif old_max_date and d < old_max_date:
            problems.append(f"新增候选 {r.get('candidate_id')} 的 declared_date={d!r} "
                             f"早于历史最晚锚点 {old_max_date!r}(疑似倒填造假长 OOS)")
    return problems


if __name__ == "__main__":
    n = sync()
    anchors = load_anchors()
    print(f"[OK] candidate_registry — 新登记 {n} · 在册 {len(anchors)} / 候选空间 {cs.N_DECLARED}")
