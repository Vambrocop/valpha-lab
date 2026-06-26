"""overreaction_alert.py — 极端下跌日 → 次日反弹「敢预测·公开计分」告警（出格区）。

盘后：当日标普收益 ≤ 历史(现代段 2000 后)第 5 百分位 = 极端下跌日 → 触发一条诚实信号：
  · Telegram 推送（复用 notify_telegram·带留痕）
  · append overreaction_signal_log.csv（append-only·绝不改历史行）
  · 次日收盘后自动结算 命中/未中
  · 写 overreaction_signal.json（web+docs）给前端展示当前信号 + 公开战绩
口径与 overreaction.py 完全一致（S&P500·q=5·现代段），引用其 overreaction.json 的现代统计（不重算）。

🔴 红线：带免责、不说「买」、把「约 46% 次日仍跌」亮在明面、事后认账、不可交易(成本/滑点)、过去≠未来。
这是「敢预测敢认账·守公开计分」范式的一条信号，不是抄底建议。
"""
import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

import forward_ledger as fl

SCRIPTS = Path(__file__).parent
BASE = SCRIPTS.parent
RAW = BASE / "data" / "raw"
PROC = BASE / "data" / "processed"
WEB = BASE / "web"
LOG = PROC / "overreaction_signal_log.csv"

Q = 5.0                                  # 极端下跌日 = 当日收益 ≤ 第 5 百分位
MODERN_CUT = pd.Timestamp("2000-01-01")  # 与 overreaction.py 现代段一致
HEADER = ["date", "index", "ret_pct", "threshold_pct", "signal",
          "next_date", "next_ret_pct", "hit", "settled"]
_TRUE = ("true", "1", "yes")


def _sp_close():
    """标普收盘序列（与 overreaction.py 同源 SP500_long.csv）。返回 Series 或 None。"""
    f = RAW / "SP500_long.csv"
    if not f.exists():
        return None
    s = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]
    s = pd.to_numeric(s, errors="coerce").dropna().sort_index()
    return s if len(s) > 500 else None


def _modern_stat():
    """从 overreaction.json 取现代段次日反弹统计（诚实引用，不重算）。缺失返回 {}。"""
    for p in (WEB / "overreaction.json", PROC / "overreaction.json"):
        if p.exists():
            try:
                o = json.loads(p.read_text(encoding="utf-8"))
                rec = o.get("recent", {})
                h1 = next((d for d in (o.get("distribution") or []) if d.get("horizon") == 1), {})
                return {"bounce_next_pct": rec.get("bounce_next_pct"),
                        "other_next_pct": rec.get("other_next_pct"),
                        "p_value": rec.get("p_value"),
                        "pct_negative": h1.get("pct_negative")}
            except Exception:
                pass
    return {}


def _settle(rows, ret_by_date, dates_sorted):
    """给已触发未结算的行补 next_date（触发日之后第一个交易日）→ 有收益就结算 命中。返回新结算数。"""
    n = 0
    for r in rows:
        if str(r.get("settled")).lower() in _TRUE:
            continue
        if not r.get("next_date"):                       # 触发当日次日还没来 → 补下一交易日
            try:
                i = dates_sorted.index(r["date"])
            except ValueError:
                continue
            if i + 1 < len(dates_sorted):
                r["next_date"] = dates_sorted[i + 1]
        nd = r.get("next_date") or ""
        if nd and nd in ret_by_date:                     # 次日收益已知 → 结算
            nr = ret_by_date[nd]
            r["next_ret_pct"] = round(nr * 100, 3)
            r["hit"] = bool(nr > 0)                       # 信号是「次日偏涨」→ 次日真涨即命中
            r["settled"] = True
            n += 1
    return n


def run(write=True, push=True):
    close = _sp_close()
    if close is None:
        print("[反弹告警] 无 SP500_long.csv 或样本不足，跳过")
        return None
    ret = close.pct_change().dropna()
    modern = ret[ret.index >= MODERN_CUT]
    if len(modern) < 500:
        print("[反弹告警] 现代段样本不足，跳过")
        return None

    thr = float(np.percentile(modern.values, Q))         # 现代段第 5 百分位（负数）
    today = ret.index[-1].date().isoformat()
    today_ret = float(ret.iloc[-1])
    ret_by_date = {d.date().isoformat(): float(v) for d, v in ret.items()}
    dates_sorted = [d.date().isoformat() for d in ret.index]

    rows = fl.read_log(LOG)
    seen = {r["date"] for r in rows}

    # ① 检测：今天极端下跌 + 还没记过 → 触发（append-only，一天最多一条）
    triggered = today_ret <= thr and today not in seen
    if triggered:
        rows.append({"date": today, "index": "SP500", "ret_pct": round(today_ret * 100, 3),
                     "threshold_pct": round(thr * 100, 3), "signal": "next_day_lean_up",
                     "next_date": "", "next_ret_pct": "", "hit": "", "settled": False})

    # ② 结算所有未结算行（含历史挂账）
    settled_now = _settle(rows, ret_by_date, dates_sorted)

    # ③ 战绩
    settled = [r for r in rows if str(r.get("settled")).lower() in _TRUE]
    n_settled = len(settled)
    n_hit = sum(1 for r in settled if str(r.get("hit")).lower() in _TRUE)
    hit_pct = round(n_hit / n_settled * 100, 1) if n_settled else None
    avg_next = round(float(np.mean([float(r["next_ret_pct"]) for r in settled])), 3) if n_settled else None
    n_pending = sum(1 for r in rows if str(r.get("settled")).lower() not in _TRUE)

    ms = _modern_stat()
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "index": "SP500", "q_pctile": Q, "threshold_pct": round(thr * 100, 3),
        "today": {"date": today, "ret_pct": round(today_ret * 100, 3), "triggered": bool(triggered)},
        "modern_stat": ms,
        "track_record": {"n_settled": n_settled, "n_hit": n_hit, "hit_pct": hit_pct,
                         "avg_next_pct": avg_next, "n_pending": n_pending},
        "caveat": "出格区·敢预测敢认账。极端下跌日(标普 ≤ 历史现代段第5百分位)→ 历史次日小幅占优"
                  "（约 46% 仍跌，非必涨）。非荐股、不可交易(成本/滑点)、会错、过去≠未来。"
                  "每次触发 append 公开计分，次日自动结算。",
    }

    if write:
        from util_io import write_json
        write_json("overreaction_signal.json", out)
        fl.write_log(LOG, HEADER, rows)
        print(f"[OK] overreaction_signal.json — 今日{'⚡触发' if triggered else '未触发'}"
              f"（标普 {out['today']['ret_pct']}% vs 阈值 {out['threshold_pct']}%）· "
              f"战绩 {n_hit}/{n_settled}" + (f"={hit_pct}%" if hit_pct is not None else "")
              + f" · 本次新结算 {settled_now} · 挂账 {n_pending}")

    # ④ 推送（仅新触发时；复用 notify_telegram·带 tag 留痕）
    if triggered and push:
        try:
            import notify_telegram
            b, o, p = ms.get("bounce_next_pct"), ms.get("other_next_pct"), ms.get("p_value")
            neg = ms.get("pct_negative")
            mid = f"历史上这种日子【次日】平均 {b}%" if b is not None else "历史上这种日子次日通常小幅反弹"
            if o is not None:
                mid += f"（明显高于平常 {o}%·p={p}）"
            lines = [
                f"📉 极端下跌告警 · {today}",
                f"标普今日 {out['today']['ret_pct']}%（≤ 历史现代段第5百分位 {out['threshold_pct']}%）= 极端下跌日。",
                "",
                mid + f"——但约 {neg if neg is not None else 46}% 的时候次日仍是跌的，"
                "这是小幅统计占优、不是「必涨」。",
                "明天见分晓，本条已 append 公开计分、事后认账。",
                "",
            ] + notify_telegram.footer(extra="（出格区·非荐股·会错·过去≠未来）").splitlines()
            notify_telegram.send("\n".join(lines), tag="overreaction")
        except Exception as e:
            print(f"[反弹告警] 推送失败（非致命）: {e}")

    return out


if __name__ == "__main__":
    run()
