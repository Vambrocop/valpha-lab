"""ipo_alerts.py — IPO 重大事件预警推送（A3·出格区·事实通报）。

读 ipo_enrich 分层后的 ipo_filings.json，取 tier=="major" 的行（公司级 CIK 去重），
为每家公司判定当前**状态档 stage**（取最高，listed > priced > filed）：
  · form 为 S-1/F-1 家族   → "filed"  （已递交招股书；递交≠一定上市）
  · form 为 424B 家族      → "priced" （已定价/生效招股书）
  · form 为 8-A12B 家族    → "listed" （已在交易所注册挂牌）
  · F-6（ADR 存托设施）**不算档**——程序性代递，与标的公司上市与否无必然关系。
新 (cik, stage) → append 一行进事件账 + 并入本轮 Telegram 合并消息（tag="IPO雷达"）。

🔴 诚实边界：**事实通报，非荐股非预测**——每条推送 = 「X 已递交/已定价/已挂牌」的
SEC 申报事实 + 「上市≠值得买」免责，不含任何方向判断。

═══ 账本语义（与 util_io.append_daily_log 的"每日快照"不同）═══════════════
data/ipo_alert_log.csv 是**事件账**：去重键 = (cik, stage)，不是日期——同一公司同一档
终身只记/只推一次；状态迁移（filed→priced→listed）是新事件、记新行。
自写 append（csv.writer、append 模式、默认 dialect、newline=""，同 util_io 惯例），
**只 append、绝不改历史行**（append-only 铁律；已入 ledger_sidecar 哈希链守护）。

═══ 设计取舍：推送失败不重试（拍板记录）══════════════════════════════════
**未配置 token（本地常态）→ 完全跳过、不落账不消费**：SEC 富化只能本地跑，若本地
（无 token）抢先把新事件消费成 pushed=False，CI（有 secrets）就永远没机会推——推送
通道形同虚设（Fable 主脑直审抓出的集成洞）。跳过=把「首见即推+落账」留给有 token 的
环境（CI 全量时段读已提交的富化 json）。
**配置了 token 但发送失败（网络闪断/401 等）→ 照记账、pushed=False 留痕**。下轮该
(cik, stage) 已在账 → **不再推、不再记**。为什么不重试：重试要么改历史行的 pushed
字段（违反 append-only 铁律），要么 append 重复事件行再在消息里去重（账本语义被搅浑）。
IPO 档位事件前端 ipo.html 本就展示，Telegram 只是提醒渠道，错过一条的代价 << 弄脏账本。
初始基线：2026-07-14 首录的 6 条存量 major（海力士等已上市旧闻）pushed=False 落账，
属刻意消费——防上线后拿旧事件轰炸；此后账本只进真正的新事件。

fail-soft：任何异常打印后 exit 0，不阻断流水线；无 TELEGRAM token 时照
notify_telegram 的静默跳过模式（send 返回 False），账本照记（pushed=False）。

单独跑：$env:PYTHONUTF8='1'; py market-analysis/scripts/ipo_alerts.py
"""
import csv
import datetime
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent
BASE = SCRIPTS.parent
SRC = BASE / "web" / "ipo_filings.json"
LOG = BASE / "data" / "ipo_alert_log.csv"

HEADER = ["date_utc", "cik", "company", "ticker", "stage", "form",
          "tier_reasons", "adsh", "pushed"]
_BUCKETS = ("filed", "priced", "listing", "adr")
_STAGE_RANK = {"filed": 0, "priced": 1, "listed": 2}
_STAGE_ZH = {"filed": "已递交招股书", "priced": "已定价/生效", "listed": "已注册挂牌"}


def _stage_of_form(form):
    """SEC form → 状态档。S-1/F-1 家族=filed，424B 家族=priced，8-A12B 家族=listed；
    F-6 及其他 → None（不算档）。精确匹配家族（"S-1"、"S-1/A"…），防御 S-11 这类
    形似但不同的表（fetch_ipo 现不会产出，但账本口径不赌上游）。"""
    f = str(form or "").upper()
    if f in ("S-1", "F-1") or f.startswith(("S-1/", "F-1/")):
        return "filed"
    if f.startswith("424B"):
        return "priced"
    if f.startswith("8-A12B"):
        return "listed"
    return None


def major_events(data):
    """ipo_filings.json → 每家 major 公司的当前最高状态档。
    返回 list[dict(cik, company, ticker, stage, form, tier_reasons, adsh)]，
    按 stage 高→低、公司名排序（消息/账本行序确定性）。F-6-only 的 major（无档）跳过。"""
    by_cik = {}
    for b in _BUCKETS:
        for row in data.get(b, []) or []:
            if row.get("tier") != "major" or not row.get("cik"):
                continue
            by_cik.setdefault(row["cik"], []).append(row)

    events = []
    for cik, rows in by_cik.items():
        staged = [(r, _stage_of_form(r.get("form"))) for r in rows]
        staged = [(r, s) for r, s in staged if s is not None]
        if not staged:
            continue                            # 只有 F-6 之类 → 无档，不成事件
        top = max(_STAGE_RANK[s] for _, s in staged)
        # 代表行 = 最高档里 filed 日期最新的那行
        rep, stage = max(((r, s) for r, s in staged if _STAGE_RANK[s] == top),
                         key=lambda t: str(t[0].get("filed") or ""))
        ticker = rep.get("ticker") or next(
            (r.get("ticker") for r, _ in staged if r.get("ticker")), None)
        events.append({
            "cik": cik,
            "company": rep.get("company") or "",
            "ticker": ticker or "",
            "stage": stage,
            "form": rep.get("form") or "",
            "tier_reasons": "|".join(rep.get("tier_reasons") or []),
            "adsh": rep.get("adsh") or "",
        })
    events.sort(key=lambda e: (-_STAGE_RANK[e["stage"]], e["company"]))
    return events


def _seen_keys(path=None):
    """账本里已记过的 (cik, stage) 集合（任意历史行，含 pushed=False——见文件头取舍）。"""
    p = path or LOG
    if not p.exists():
        return set()
    with open(p, encoding="utf-8", newline="") as f:
        return {(r.get("cik"), r.get("stage")) for r in csv.DictReader(f)}


def _append_rows(rows, path=None):
    """append-only 事件账写入：新文件先写 header，此后只 append（绝不改历史行）。"""
    p = path or LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(HEADER)
        for r in rows:
            w.writerow([r[k] for k in HEADER])


def _send(text):
    """推送包装（独立函数便于测试 monkeypatch）。未配置 token/失败均返回 False 不抛。"""
    import notify_telegram
    return notify_telegram.send(text, tag="IPO雷达")


def _build_message(events, today):
    """本轮全部新事件合并成一条消息，每公司一行；zh 为主 + 免责收尾。"""
    import notify_telegram
    lines = [f"🛫 IPO雷达 · 重大申报事件 · {today}"]
    for e in events:
        tick = f" ({e['ticker']})" if e["ticker"] else ""
        lines.append(f"🔴 {e['company']}{tick} {_STAGE_ZH[e['stage']]}({e['form']})"
                     "——事实通报·非荐股")
    lines += ["", "SEC 申报事实层：递交/定价/挂牌是流程节点，上市≠值得买。", ""]
    lines += notify_telegram.footer(extra="（IPO雷达·事实通报·非荐股非预测·上市≠值得买）").splitlines()
    return "\n".join(lines)


def run(push=True):
    """→ dict(n_new, pushed) | None（无输入时）。新 (cik,stage) 先推送后落账（pushed 留痕）。"""
    if not SRC.exists():
        print("[IPO告警] 无 ipo_filings.json，跳过（fetch_ipo/ipo_enrich 未产出）")
        return None
    data = json.loads(SRC.read_text(encoding="utf-8"))

    seen = _seen_keys()
    new = [e for e in major_events(data) if (e["cik"], e["stage"]) not in seen]
    if not new:
        print("[IPO告警] 无新增 major 档位事件（账本已全覆盖），零行为")
        return {"n_new": 0, "pushed": False}

    # 未配置 token → 完全跳过（不落账不消费）：把「首见即推+落账」留给有 token 的环境
    # （见文件头取舍——本地抢先消费会让 CI 永远推不出去）。push=False（测试直调）不受此限。
    import os
    if push and not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
        print(f"[IPO告警] 发现 {len(new)} 条新 major 事件，但本环境未配置 TELEGRAM token"
              "——跳过（不落账），留给有 token 的环境首见推送")
        return {"n_new": len(new), "pushed": False, "skipped_no_token": True}

    now = datetime.datetime.now(datetime.timezone.utc)
    ok = bool(push and _send(_build_message(new, now.date().isoformat())))

    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [{**e, "date_utc": stamp, "pushed": ok} for e in new]
    _append_rows(rows)
    print(f"[OK] ipo_alert_log.csv — 新事件 {len(new)} 条"
          f"（{'已推送' if ok else '未推送(无token/失败)·pushed=False 留痕'}）: "
          + "、".join(f"{e['company']}[{e['stage']}]" for e in new))
    return {"n_new": len(new), "pushed": ok}


if __name__ == "__main__":
    try:
        run()
    except Exception as e:                     # fail-soft：绝不阻断流水线
        print(f"[IPO告警] 异常（非致命，不阻断）: {type(e).__name__}: {e}")
    sys.exit(0)
