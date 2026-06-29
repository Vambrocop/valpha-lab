"""knowledge_base.py — 自生长闭环 P-C「晋升/降级 → 证据知识库」。

把 quality_gate 裁决（跨族FDR存活 ∧ 现代有检验力 = verdict=='survive'）与门4 OOS(oos_gate)
合流，自动进/出库，append-only 写 kb_ledger.csv：
  · 晋升(全满足)：verdict=='survive' ∧ oos_status=='confirmed' ∧ **不在库** → promote
  · 降级       ：**在库** ∧ oos_status=='overturned' → demote
  · 单调       ：进库后只 overturn 才动（confirmed/neutral/pending 皆 no-op）；**绝不对晋升再跑 FDR**
                （那是双重惩罚）；审计痕迹 = 诚实机制，不必重算即可复核每次进/出库。
  · 滞回       ：confirm/overturn 不同阈值(0.10/0.20)已在 oos_gate 内，KB 不再加门。

铁律(红线·同 prediction_log)：kb_ledger **append-only，绝不改/删历史行**。当前库成员 = **回放账本**
(每候选取最后一次 action)推出，不另存可变状态 → 历史完全可审、无第二真相源。
注：曾 overturn 降级、日后又 confirmed 可再 promote（新证据周期，每次转换都留行）——这仍是单调的、可审的。
"""
import csv
import json
import datetime
from pathlib import Path

SCRIPTS = Path(__file__).parent
LOG = SCRIPTS.parent / "data" / "kb_ledger.csv"
_AD_JSON = SCRIPTS.parent / "data" / "processed" / "autodiscovery.json"   # 复用已算好的裁决,不重跑 autodiscovery
HEADER = ["date", "candidate_id", "key", "action", "anchor_date", "oos_n", "oos_p", "oos_sign", "trigger"]
PROMOTE, DEMOTE = "promote", "demote"


def _read(path=LOG):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def replay_members(path=LOG):
    """回放 append-only 账本 → 当前在库 candidate_id 集合（每候选取最后一次 action）。"""
    state = {}
    for r in _read(path):                       # 文件顺序 = 写入(时间)顺序 → 后行覆盖前行
        state[r["candidate_id"]] = r["action"]
    return {cid for cid, act in state.items() if act == PROMOTE}


def _row(today, v, action, trigger):
    return {"date": today, "candidate_id": v["candidate_id"], "key": v["key"], "action": action,
            "anchor_date": v["anchor_date"], "oos_n": v["oos_n"], "oos_p": v["oos_p"],
            "oos_sign": v["oos_sign"], "trigger": trigger}


def decide(verdicts, verdict_map, members, today):
    """纯函数：据 OOS 裁决 + 裁决态 + 当前成员 → 该追加的 promote/demote 行（不写盘，可单测）。"""
    rows = []
    for v in verdicts:
        cid = v["candidate_id"]
        in_kb = cid in members
        st = v["oos_status"]
        adj = verdict_map.get(cid)
        if (not in_kb) and adj == "survive" and st == "confirmed":
            rows.append(_row(today, v, PROMOTE,
                             f"survive∧confirmed(oos_p={v['oos_p']},方向{v['full_sign']})"))
        elif in_kb and st == "overturned":
            rows.append(_row(today, v, DEMOTE,
                             f"overturned(oos_p={v['oos_p']},方向{v['full_sign']}→{v['oos_sign']})"))
    return rows


def _append(rows, path=LOG):
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    need_header = not path.exists()
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        if need_header:
            w.writeheader()
        for r in rows:                          # 只 append；已写行一概不碰（append-only 红线）
            w.writerow(r)
    return len(rows)


def step(verdicts=None, results=None, today=None, path=LOG, write=True):
    """跑一轮晋升/降级。verdicts 缺省调 oos_gate.run_gate；results 缺省调 autodiscovery(取 verdict)。"""
    today = today or datetime.date.today().isoformat()
    if verdicts is None:
        import oos_gate
        verdicts = oos_gate.run_gate()
    if results is None:
        import autodiscovery as ad
        results = ad.run_all(write=False)["candidates"]
    vmap = {r["candidate_id"]: r.get("verdict") for r in results}
    missing = {v["candidate_id"] for v in verdicts} - set(vmap)
    if missing:                                 # N3:OOS 与裁决候选集漂移 → 大声报错,不静默少晋升
        raise ValueError(f"候选集漂移：{len(missing)} 个 OOS 候选无裁决态（如 {sorted(missing)[:3]}）")
    members = replay_members(path)
    rows = decide(verdicts, vmap, members, today)
    if write:
        _append(rows, path)
    return rows


def _member_details(rows, members, vmap):
    """当前在库候选的展示明细（取各自最后一次 promote 行的日期/锚/oos_p）。"""
    last = {}
    for r in rows:                              # 顺序=时间 → 留最后一次 promote
        if r.get("candidate_id") in members and r.get("action") == PROMOTE:
            last[r["candidate_id"]] = r
    out = []
    for cid in members:
        r = last.get(cid, {})
        adj = vmap.get(cid, {})
        out.append({"key": r.get("key") or adj.get("key") or cid, "candidate_id": cid,
                    "family": adj.get("family"), "since": r.get("date"),
                    "anchor_date": r.get("anchor_date"), "oos_p": r.get("oos_p"), "oos_n": r.get("oos_n")})
    return out


def export_json(verdicts, results, members, today, write=True, path=LOG):
    """导出 knowledge_base.json 供前端展示：在库成员 + 排队中(survive 待确认) + OOS 异动 + 进出库史。"""
    import datetime as _dt
    from collections import Counter
    import oos_gate
    rows = _read(path)
    vmap = {r["candidate_id"]: r for r in results}
    anchors = [v["anchor_date"] for v in verdicts if v.get("anchor_date")]
    anchor_common = Counter(anchors).most_common(1)[0][0] if anchors else None
    days = None
    if anchor_common:
        try:
            days = (_dt.date.fromisoformat(today) - _dt.date.fromisoformat(anchor_common)).days
        except ValueError:
            days = None
    queue, movements = [], []
    for v in verdicts:
        adj = vmap.get(v["candidate_id"], {})
        item = {"key": v["key"], "candidate_id": v["candidate_id"], "family": v["family"],
                "verdict": adj.get("verdict"), "oos_status": v["oos_status"], "anchor_date": v["anchor_date"],
                "oos_n": v["oos_n"], "oos_p": v["oos_p"], "full_sign": v["full_sign"], "oos_sign": v["oos_sign"]}
        if adj.get("verdict") == "survive" and v["candidate_id"] not in members:
            queue.append(item)                  # 已过全样本检验、还没进库 → 正等样本外确认
        if v["oos_status"] in (oos_gate.CONFIRMED, oos_gate.OVERTURNED, oos_gate.NEUTRAL):
            movements.append(item)              # 锚后已有动静(早于晋升的信号)
    osum = oos_gate.summarize(verdicts)
    out = {
        "generated": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "anchor_common": anchor_common, "days_since_anchor": days, "min_oos_n": oos_gate.MIN_OOS_N,
        "summary": {"in_kb": len(members), "queue": len(queue), "confirmed": osum["confirmed"],
                    "overturned": osum["overturned"], "neutral": osum["neutral"], "pending": osum["pending"]},
        "members": _member_details(rows, members, vmap),
        "queue": sorted(queue, key=lambda x: (x["oos_p"] is None, x["oos_p"] if x["oos_p"] is not None else 1)),
        "movements": movements,
        "history": [{k: r.get(k) for k in ("date", "key", "action", "anchor_date", "oos_n", "oos_p", "oos_sign", "trigger")}
                    for r in reversed(rows)],
        "caveat": ("样本外确认只认每条规律'注册锚点之后'的新数据；未到可判=数据还不够、绝不凑结论；"
                   "晋升≠未来一定重演，非荐股、会错。"),
    }
    if write:
        from util_io import write_json
        write_json("knowledge_base.json", out, allow_nan=False)
    return out


def _load_verdicts_json():
    """读已写好的 autodiscovery.json 取 verdict_map（避免在流水线里二次重算 autodiscovery）。缺失→None。"""
    if not _AD_JSON.exists():
        return None
    try:
        return json.load(open(_AD_JSON, encoding="utf-8")).get("candidates")
    except Exception:
        return None


def run_all(write=True, path=LOG):
    """流水线入口：OOS 门4(oos_gate) + 已写好的裁决 → append-only 晋升/降级 kb_ledger。
    今日全候选锚=注册日 → 锚后空 → 全 pending → 0 晋升(正确,边跑边攒,约 1 月出首批)。"""
    import oos_gate
    verdicts = oos_gate.run_gate()
    results = _load_verdicts_json()
    if results is None:                         # 兜底:json 缺失(单跑/CI 干净检出) → 现算
        import autodiscovery as ad
        results = ad.run_all(write=False)["candidates"]
    rows = step(verdicts=verdicts, results=results, path=path, write=write)
    members = replay_members(path)
    export_json(verdicts, results, members, datetime.date.today().isoformat(), write=write, path=path)
    osum = oos_gate.summarize(verdicts)
    print(f"[OK] knowledge_base — 在库 {len(members)} | 本轮 promote/demote {len(rows)} 行 | "
          f"OOS 确认{osum['confirmed']}·翻盘{osum['overturned']}·持中{osum['neutral']}·未到可判{osum['pending']}")
    for r in rows:
        print(f"  {r['action']:8s} {r['key']:24s} {r['trigger']}")
    return rows, members


if __name__ == "__main__":
    run_all(write=True)
