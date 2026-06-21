"""seasonality.py — 野蛮区「周期与季节性」原始计数引擎（**补 placebo，不重复**）。

placebo_test.py 已严格算 6 个日历效应的置换 p + 现代段 + FDR（裁决来自 placebo_tests.json）。
本模块**只补 placebo 没有的**：
  · 原始计数（每组 平均% / 涨的年数 / n，即用户要的"X年里Y年涨"）
  · placebo 未覆盖的新模式：Sell in May（冬/夏半年）、世界杯年、月度逐月、（可选）BTC 减半
诚实：纯描述性、非可交易、小样本/confounding 标注、过去≠未来。复用 placebo 的数据加载，不重算 p 值。
输出 seasonality.json，由「周期季节性」子页消费（与 placebo_tests.json 的裁决并列展示）。
"""
import json
import datetime
import numpy as np
import pandas as pd
from pathlib import Path

import placebo_test as pb

SCRIPTS = Path(__file__).parent
WEB = SCRIPTS.parent / "web"
DOCS = SCRIPTS.parent.parent / "docs"
PROC = SCRIPTS.parent / "data" / "processed"
RAW = SCRIPTS.parent / "data" / "raw"
# 全部世界杯年（1930 起；1942/1946 因二战取消）——SP500 数据 1928+ 全覆盖，用全样本不人为截断
WORLD_CUP_YEARS = [1930, 1934, 1938, 1950, 1954, 1958, 1962, 1966, 1970, 1974, 1978,
                   1982, 1986, 1990, 1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022]


def _counts(vals):
    """原始计数：平均% / 上涨比例% / 上涨年数 / 样本 n。"""
    v = np.asarray(vals, dtype=float) * 100
    n = len(v)
    up = int((v > 0).sum())
    return {"avg_pct": round(float(v.mean()), 2), "med_pct": round(float(np.median(v)), 2),
            "up": up, "n": n, "pos_pct": round(up / n * 100, 0) if n else None}


def _sp500_returns():
    s = pb.load_sp500_daily()        # 日收益（与 placebo/autodiscovery 同源同口径）
    return s.dropna()


def monthly(ret):
    m = (1 + ret).resample("ME").prod(min_count=1).dropna() - 1
    names = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]
    out = []
    for mo in range(1, 13):
        c = _counts(m[m.index.month == mo].values)
        c["label"] = names[mo - 1]
        out.append(c)
    return out


def term_year(ret):
    """大选/任期年：选举年(div by 4)=第4年，次年=第1年。"""
    an = (1 + ret).resample("YE").prod(min_count=1).dropna() - 1
    an = an[an.index.year < pd.Timestamp.today().year]
    term = ((an.index.year - 1) % 4) + 1
    labels = {1: "第1年(选举次年)", 2: "第2年(中期选举年)", 3: "第3年(选举前年)", 4: "第4年(大选年)"}
    out = []
    for t in [1, 2, 3, 4]:
        c = _counts(an.values[term == t])
        c["label"] = labels[t]
        out.append(c)
    return out


def sell_in_may(ret):
    m = (1 + ret).resample("ME").prod(min_count=1).dropna() - 1
    df = pd.DataFrame({"r": m.values, "y": m.index.year, "mo": m.index.month})
    win, summ = [], []
    for y in sorted(df.y.unique()):
        w = df[((df.y == y - 1) & (df.mo >= 11)) | ((df.y == y) & (df.mo <= 4))]["r"]
        s = df[(df.y == y) & (df.mo >= 5) & (df.mo <= 10)]["r"]
        if len(w) == 6:
            win.append(np.prod(1 + w.values) - 1)
        if len(s) == 6:
            summ.append(np.prod(1 + s.values) - 1)
    a = _counts(win); a["label"] = "冬半年(11-4月)"
    b = _counts(summ); b["label"] = "夏半年(5-10月)"
    return [a, b]


def world_cup(ret):
    m = (1 + ret).resample("ME").prod(min_count=1).dropna() - 1
    df = pd.DataFrame({"r": m.values, "y": m.index.year, "mo": m.index.month})
    jja = df[(df.mo >= 6) & (df.mo <= 8)].groupby("y")["r"].apply(lambda x: np.prod(1 + x.values) - 1)
    wc = _counts(jja[jja.index.isin(WORLD_CUP_YEARS)].values); wc["label"] = "世界杯年夏季(6-8月)"
    al = _counts(jja.values); al["label"] = "所有年夏季(6-8月)"
    return [wc, al]


def btc_halving():
    """BTC 减半后 12 个月收益（若有 BTC 长史；样本极少，仅展示）。"""
    f = RAW / "BTC_long.csv"
    if not f.exists():
        return {"available": False, "note": "无 BTC 长史数据"}
    try:
        s = pd.read_csv(f, index_col=0, parse_dates=True).squeeze()
        s = pd.to_numeric(s, errors="coerce").dropna()
        s = s[s > 0].sort_index()
        halvings = ["2016-07-09", "2020-05-11", "2024-04-20"]
        rows = []
        for h in halvings:
            hd = pd.Timestamp(h)
            after = s[(s.index >= hd) & (s.index <= hd + pd.Timedelta(days=365))]
            if len(after) > 30:
                rows.append({"halving": h, "ret_12m_pct": round(float(after.iloc[-1] / after.iloc[0] - 1) * 100, 0)})
        return {"available": True, "halvings": rows, "n": len(rows)}
    except Exception as e:
        return {"available": False, "note": str(e)[:60]}


def run_all(write=True):
    ret = _sp500_returns()
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "SP500 日收益（1928+），原始计数补 placebo 的裁决",
        "caveat": "纯描述性历史原始计数（每组 平均/涨的年数/n），**非可交易、非预测**。多重检验下"
                  "测得多总有几个像样的（看 placebo/autodiscovery 的 FDR 裁决）；全样本真过≠现代还在"
                  "（周几/圣诞现代已淡）；小样本(世界杯n≈7/减半n≈3)无法确认、看个意思；世界杯年与危机年"
                  "(2002/2008)重叠，差异可能是危机非赛事。过去≠未来。",
        "sample_years": [int(ret.index.year.min()), int(ret.index.year.max())],
        "monthly": monthly(ret),
        "term_year": term_year(ret),
        "sell_in_may": sell_in_may(ret),
        "world_cup": world_cup(ret),
        "btc_halving": btc_halving(),
    }
    payload = json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False)
    if write:
        for d in (PROC, WEB, DOCS):
            if d.exists():
                (d / "seasonality.json").write_text(payload, encoding="utf-8")
        sep = out["monthly"]
        worst = min(sep, key=lambda x: x["avg_pct"]); best = max(sep, key=lambda x: x["pos_pct"])
        print(f"[OK] seasonality.json — 最差月 {worst['label']}({worst['avg_pct']}%/{worst['pos_pct']}%涨)、"
              f"最稳月 {best['label']}({best['pos_pct']}%涨)；世界杯年夏 {out['world_cup'][0]['avg_pct']}%")
    return out


if __name__ == "__main__":
    run_all()
