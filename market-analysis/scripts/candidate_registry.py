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


if __name__ == "__main__":
    n = sync()
    anchors = load_anchors()
    print(f"[OK] candidate_registry — 新登记 {n} · 在册 {len(anchors)} / 候选空间 {cs.N_DECLARED}")
