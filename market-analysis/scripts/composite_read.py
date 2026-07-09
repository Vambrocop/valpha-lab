"""composite_read.py — 🧠 综合读数/建议器（出格区·把诚实证据加权成当下倾向，非预测非荐股）。

把全站已算好的诚实证据（市场体制/信用/羊群/季节性/方向信号）按**写死、透明、可复现**的权重，
合成一个"当下倾向"（强防御..强积极）+ 每个因子推哪边为什么 + 置信 + 可用倾斜 + 诚实免责。
**不预测涨跌、不保证、出格区娱乐参考**；每日 append 到 composite_log.csv 公开计分（可追责）。

红线：方向信号 walk-forward 无样本外 edge → 权重压到最低 + 明标；主权重给"真可用"的体制/风险因子。
倾向 ≠ 预测，是"条件加权读数"——给你一个有理有据、分级置信、可追责的当下参考，自己拍。
"""
import csv
import json
import datetime
from pathlib import Path

SCRIPTS = Path(__file__).parent
WEB = SCRIPTS.parent / "web"
DOCS = SCRIPTS.parent.parent / "docs"
PROC = SCRIPTS.parent / "data" / "processed"
LOG = SCRIPTS.parent / "data" / "composite_log.csv"


def _load(name):
    try:
        return json.load(open(WEB / name, encoding="utf-8"))
    except Exception:
        return None


def _clip(x):
    return max(-1.0, min(1.0, float(x)))


def build_factors():
    """每因子 → {name, push(-1防御..+1积极), weight, reason}。push/weight 透明写死。"""
    F = []
    reg = _load("market_regime.json")
    comps = {c.get("name"): c for c in (reg.get("components") or [])} if reg else {}

    c = comps.get("波动率 VIX")
    if c and c.get("percentile") is not None:
        p = c["percentile"]
        F.append({"name": "波动率 VIX", "push": _clip(-(p - 50) / 50), "weight": 0.20,
                  "reason": f"VIX {c.get('value')}（{p:.0f} 分位·{c.get('label')}）；高波动=风险高=偏防御"})

    c = comps.get("收益率曲线 10Y-2Y")
    if c and c.get("value") is not None:
        v = c["value"]
        push = 0.10 if v > 0.2 else (-0.5 if v < 0 else -0.1)
        F.append({"name": "收益率曲线", "push": push, "weight": 0.15,
                  "reason": f"10Y-2Y {v}（{c.get('label')}）；倒挂=衰退预警=防御"})

    c = comps.get("信用利差 Baa-10Y")
    if c and c.get("percentile") is not None:
        p = c["percentile"]
        F.append({"name": "信用利差", "push": _clip((50 - p) / 50 * 0.6), "weight": 0.15,
                  "reason": f"Baa-10Y {c.get('value')}（{p:.0f} 分位·{c.get('label')}）；利差低=信用宽松偏积极，但极低或属晚周期"})

    c = comps.get("个股共动(羊群)")
    if c and c.get("percentile") is not None:
        p = c["percentile"]
        F.append({"name": "个股共动(羊群)", "push": _clip((50 - p) / 50 * 0.4), "weight": 0.10,
                  "reason": f"相关性 {c.get('value')}（{p:.0f} 分位·{c.get('label')}）；低共动=分散有效偏健康"})

    sea = _load("seasonality.json")
    if sea:
        mo = datetime.date.today().month
        cur = next((m for m in sea.get("monthly", []) if m.get("label") == f"{mo}月"), None)
        if cur and cur.get("pos_pct") is not None:
            F.append({"name": "季节性(当月)", "push": _clip((cur["pos_pct"] - 55) / 45 * 0.6), "weight": 0.10,
                      "reason": f"{mo}月历史 {cur['pos_pct']:.0f}% 上涨 / 平均 {cur['avg_pct']}%（描述性·弱倾斜·过去≠未来）"})

    sig = _load("signals.json")
    if sig and sig.get("latest_prob") is not None:
        pr = sig["latest_prob"]
        F.append({"name": "纳指方向信号", "push": _clip((pr - 0.5) * 2), "weight": 0.05,
                  "reason": f"tier {sig.get('latest_tier')} / prob {pr:.2f}（⚠️ walk-forward 无样本外 edge，权重压最低、仅参考）"})
    return F


def synthesize(F):
    sw = sum(f["weight"] for f in F)
    if not sw:
        return {"stance": "数据不足", "score": None}
    s = round(sum(f["push"] * f["weight"] for f in F) / sw, 3)
    stance = ("强防御" if s < -0.4 else "偏防御" if s < -0.13 else
              "中性" if s <= 0.13 else "偏积极" if s <= 0.4 else "强积极")
    return {"stance": stance, "score": s}


def _tilt(s):
    if s is None:
        return "数据不足，无倾向"
    if s < -0.13:
        return "若要配置 → 倾向防御 / 降波动 / 留现金缓冲"
    if s > 0.13:
        return "环境相对友好 → 可正常配置，但仍分散、控单仓"
    return "中性 → 无明显倾斜，按你的计划定投/分散即可"


def _action(s):
    """干脆的行动结论(买/持/避)+程度；阈值与 synthesize 的 stance 严格对齐，边界不打架。
    synthesize: s<-0.4 强防御 / s<-0.13 偏防御 / s<=0.13 中性 / s<=0.4 偏积极 / else 强积极。"""
    if s is None:
        return "数据不足"
    if s > 0.4:
        return "买 · 可积极配置"      # 强积极
    if s > 0.13:
        return "偏多 · 可逢低加"      # 偏积极
    if s >= -0.13:
        return "持 · 观望为主"        # 中性（含 ±0.13 边界，与 synthesize 一致）
    if s >= -0.4:
        return "减 · 控波动 / 留缓冲"  # 偏防御
    return "避 · 重避险 / 留现金"      # 强防御


def _conf(s, n):
    """置信(高/中/低):倾向越极端 + 因子覆盖越全 → 越有底气。"""
    if s is None or n < 3:
        return "低"
    m = abs(s)
    if m >= 0.4 and n >= 5:
        return "高"
    if m >= 0.2:
        return "中"
    return "低"


def _append_log(today, out):
    from util_io import append_daily_log
    append_daily_log(LOG, ["date", "stance", "score"],
                     [[today, out["stance"], out["score"]]], date=today)


def _read_history(n=30):
    """近 n 日倾向分走势（D2 微图表用）——**纯聚合**自家 composite_log.csv 末 n 行 → [{d, s}]。

    只读不写、不碰任何统计口径；score 缺失/非数的行（如"数据不足"日）跳过该点。"""
    try:
        with open(LOG, encoding="utf-8") as f:
            rows = list(csv.reader(f))
    except OSError:
        return []
    hist = []
    for r in rows[1:]:                                 # 跳过 header 行
        if len(r) >= 3 and r[0]:
            try:
                hist.append({"d": r[0], "s": float(r[2])})
            except (TypeError, ValueError):
                pass                                   # score 为空/非数 → 该日无有效读数，跳过
    return hist[-n:]


def run_all(write=True):
    F = build_factors()
    syn = synthesize(F)
    today = datetime.date.today().isoformat()
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "asof": today,
        "stance": syn["stance"], "score": syn["score"],
        "action": _action(syn["score"]), "confidence_level": _conf(syn["score"], len(F)),
        "factors": F,
        "confidence": "低-中（条件加权读数）",
        "usable_tilt": _tilt(syn["score"]),
        "caveat": "🚩出格区 · 把诚实证据按**写死透明权重**加权出的当下**行动倾向（买/持/避）**。"
                  "**敢给方向，但每条 append composite_log 公开计分、可追责**；方向信号 walk-forward 无样本外优势（权重已压最低）。"
                  "非保证、会错、过去≠未来——给你有据的判断，自己拍。",
    }
    if write:
        from util_io import write_json
        _append_log(today, out)              # 先记账（append-only·同日幂等），今天的读数才进走势
        out["history"] = _read_history()     # 30日走势 = 纯聚合自家日志末30行（D2 微图表）
        write_json("composite_read.json", out, proc=True, allow_nan=False)
        print(f"[OK] composite_read.json — {out['action']}（{out['stance']} score {out['score']} · 置信{out['confidence_level']}）· {len(F)} 因子")
    else:
        out["history"] = _read_history()
    return out


if __name__ == "__main__":
    run_all()
