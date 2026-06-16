"""
market_regime.py — 当前市场风险/流动性体制盘(R1，描述性,非预测)

诚实定位:回答"现在处于什么风险环境"——把波动率、收益率曲线、VIX 期限结构几个
**够长、跨完整周期**的指标各自定位(现值 + 历史分位 + 体制标签),给一句综合描述。
🔴 红线:**只描述当前环境,绝不预测方向、不构成操作建议**。"曲线倒挂与衰退相关"等是
历史关联的【描述】,非"会跌"的预测。

数据可行性(诚实):**信用利差 HY(FRED BAMLH0A0HYM2)缓存仅 2 年,跨不了信用周期,暂不纳入**
(待修复其抓取/合并截断后再加,见 OPTIMIZATION_LOG)。本盘只用 VIX(2000+)/收益率曲线(2000+)/
VIX 期限结构(2006+)——都跨了 2008、2020。

依赖 numpy/pandas。输出 market_regime.json(PROC+WEB+DOCS 三处, allow_nan=False)。
"""
import datetime
import json
import numpy as np
import pandas as pd
from pathlib import Path

SCRIPTS  = Path(__file__).parent
RAW_DIR  = SCRIPTS.parent / "data" / "raw"
PROC_DIR = SCRIPTS.parent / "data" / "processed"
WEB_DIR  = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"
PROC_DIR.mkdir(parents=True, exist_ok=True)


def _col(df, name):
    return pd.to_numeric(df[name], errors="coerce").dropna() if name in df.columns else None


def _pct(series, val):
    return round(float((series < val).mean()) * 100, 1)


def compute_regime(df):
    """从 combined_prices.csv 算各风险指标的现值/历史分位/体制标签 + 综合描述。"""
    comps = []
    vix = _col(df, "VIX")
    if vix is None or len(vix) < 500:
        return {"status": "insufficient"}
    v = float(vix.iloc[-1]); vp = _pct(vix, v)
    vix_label = "极端高" if vp >= 95 else "偏高" if vp >= 75 else "偏低" if vp <= 25 else "中性"
    comps.append({"name": "波动率 VIX", "value": round(v, 1), "percentile": vp, "label": vix_label,
                  "asof": str(vix.index[-1].date()),
                  "note": "股市波动/恐慌水平(现值在历史的分位)"})

    y10, y2 = _col(df, "YIELD_10Y"), _col(df, "YIELD_2Y")
    if y10 is not None and y2 is not None:
        curve = float(y10.iloc[-1] - y2.iloc[-1])
        c_label = "倒挂" if curve < 0 else "正斜率偏平" if curve < 0.5 else "正常(正斜率)"
        comps.append({"name": "收益率曲线 10Y-2Y", "value": round(curve, 2), "label": c_label,
                      "inverted": bool(curve < 0),
                      "asof": str(min(y10.index[-1], y2.index[-1]).date()),     # GS10/GS2 月频,会滞后
                      "note": "期限利差(月频GS10/GS2,日期可能滞后);倒挂在历史上与衰退相关(描述性关联，非方向预测)"})

    vix3m = _col(df, "VIX3M")
    if vix3m is not None and len(vix3m) > 200:
        term = float(vix3m.iloc[-1] - v)
        t_label = "倒挂(近月恐慌>远月)" if term < 0 else "正常(远月更高)"
        comps.append({"name": "VIX 期限结构 (VIX3M-VIX)", "value": round(term, 2), "label": t_label,
                      "backwardation": bool(term < 0),
                      "asof": str(min(vix3m.index[-1], vix.index[-1]).date()),
                      "note": "倒挂=近月恐慌高于远月，通常对应急性市场压力(描述当前状态，非预测)"})

    # 综合(纯描述,不给方向/操作)
    bits = [f"波动率{vix_label}"]
    cv = next((c for c in comps if c["name"].startswith("收益率")), None)
    if cv:
        bits.append("曲线" + cv["label"])
    tv = next((c for c in comps if c["name"].startswith("VIX 期限")), None)
    if tv and tv.get("backwardation"):
        bits.append("期限结构倒挂(近月恐慌>远月)")
    composite = "当前环境：" + " + ".join(bits) + "。"

    return {"status": "ok", "asof": str(vix.index[-1].date()), "components": comps,
            "composite": composite}


def run_all():
    print("=== R1 当前市场风险体制盘(描述性,非预测)===")
    f = RAW_DIR / "combined_prices.csv"
    if not f.exists():
        print("⚠ 无 combined_prices.csv，跳过")
        return None
    df = pd.read_csv(f, index_col=0, parse_dates=True)
    res = compute_regime(df)
    if res.get("status") != "ok":
        print("⚠ 数据不足，跳过")
        return None
    for c in res["components"]:
        print(f"  {c['name']:<22} {c['value']}  [{c['label']}]")
    print("  " + res["composite"])

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "caveat": "这是【当前风险环境的客观描述】——现值在历史的位置 + 体制标签,"
                  "**绝不预测方向、不构成买卖建议**。如'曲线倒挂与衰退相关'是历史关联的描述,非'会跌'。"
                  "诚实:信用利差(HY)可得序列仅 2 年、跨不了信用周期,暂不纳入(待修复抓取截断)。"
                  "用 VIX(2000+)/收益率曲线(2000+)/VIX 期限结构(2006+),均跨 2008、2020。",
        **res,
    }
    payload = json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False)
    for d in (PROC_DIR, WEB_DIR, DOCS_DIR):
        if d.exists():
            (d / "market_regime.json").write_text(payload, encoding="utf-8")
    print("[OK] market_regime.json")
    return out


if __name__ == "__main__":
    run_all()
