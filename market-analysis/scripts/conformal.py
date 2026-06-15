"""
conformal.py — 方法 E 保形预测（split-conformal 覆盖区间）

给未来 N 日收益一个**分布无关、有覆盖保证**的区间 [L, U]。
诚实定位：**这是校准的不确定性区间，不是方向预测**——只回答"区间多宽 / 历史多少比例落在内"，
不说涨还是跌。区间通常略偏正（股权溢价是真实规律），但 L<0<U 同时展示上行与下行风险。

方法：
- 非重叠 N 日窗口（保 exchangeability；重叠窗会高估有效样本、破坏覆盖保证）。
- **时间序切**校准/测试（旧=校准定区间，新=测试验覆盖）——比随机切更严，检验"出样本外是否仍校准"
  （若经验覆盖 < 名义，说明市场非平稳，如实呈现，本身就是信息）。
- split-conformal：校准集的 [α/2, 1-α/2] 分位(秩调整)作区间。在 exchangeable(如随机切)下有
  ≥1-α 有限样本保证；本脚本用**时间序切**(非 exchangeable)，故**不主张该保证**，只报实测覆盖。

依赖 numpy/pandas/yfinance。输出 conformal.json（processed + web + docs）。
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

HORIZONS = (5, 20, 60)        # 约 1 周 / 1 月 / 3 月（交易日）
LEVELS   = (0.80, 0.90)
CAL_FRAC = 0.70               # 旧 70% 校准，新 30% 测试覆盖


def _sp_prices():
    f = RAW_DIR / "SP500_long.csv"
    if f.exists():
        s = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]
        s = pd.to_numeric(s, errors="coerce").dropna()
        if len(s) > 500:
            return s.sort_index()
    try:
        import yfinance as yf
        df = yf.download("^GSPC", start="1928-01-01",
                         end=(pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                         auto_adjust=True, progress=False)
        c = df["Close"]
        return (c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c).dropna().sort_index()
    except Exception as e:
        print(f"  ⚠ 无法获取 S&P500：{e}")
        return None


def nonoverlap_fwd_returns(px, horizon):
    """非重叠 N 日前瞻收益（块与块不共享日，近似 exchangeable）。"""
    v = np.asarray(px, float)
    starts = np.arange(0, len(v) - horizon, horizon)
    return v[starts + horizon] / v[starts] - 1.0


def split_conformal(rets, levels=LEVELS, cal_frac=CAL_FRAC):
    n = len(rets)
    ncal = int(n * cal_frac)
    cal, test = rets[:ncal], rets[ncal:]            # 时间序切：旧校准 / 新测试
    rows = []
    for lvl in levels:
        a = 1.0 - lvl
        # split-conformal 有限样本秩调整(比裸经验分位略宽、偏保守；小样本如 60 日更明显)
        p_lo = max(0.0, np.floor((ncal + 1) * (a / 2)) / ncal)
        p_hi = min(1.0, np.ceil((ncal + 1) * (1 - a / 2)) / ncal)
        lo = float(np.quantile(cal, p_lo))
        hi = float(np.quantile(cal, p_hi))
        cov = float(((test >= lo) & (test <= hi)).mean()) if len(test) else None
        rows.append({"level": lvl,
                     "lower_pct": round(lo * 100, 2), "upper_pct": round(hi * 100, 2),
                     "empirical_coverage": round(cov, 3) if cov is not None else None,
                     "n_cal": int(ncal), "n_test": int(len(test))})
    return rows


def _load_vix():
    """复用 risk_dashboard 缓存的 VIX(risk_dashboard 在 run_all 中先于 conformal 运行)。"""
    f = RAW_DIR / "risk_VIX.csv"
    if f.exists():
        s = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]
        return pd.to_numeric(s, errors="coerce").dropna()
    return None


def conditional_by_vix(px, vix, horizon=20, level=0.90, n_bins=3):
    """按【起始 VIX 体制】(三分位)分组,各组单独 split-conformal 区间+覆盖。
    与 risk_dashboard 的单边条件下行互补:这里给**双边区间**,展示不确定性(区间宽度)如何随体制放大。
    诚实红线:仍是区间不是方向;且是体制-条件的历史区间,非'未来一定落在内'。"""
    common = px.index.intersection(vix.index)
    if len(common) < 500:
        return []
    p = px.reindex(common).to_numpy(float)
    v = vix.reindex(common).to_numpy(float)
    n = len(p)
    starts = np.arange(0, n - horizon, horizon)
    rets = p[starts + horizon] / p[starts] - 1.0
    svix = v[starts]                                          # 窗口【起始】VIX
    ok = ~np.isnan(svix) & ~np.isnan(rets)
    rets, svix = rets[ok], svix[ok]
    if len(rets) < 60:
        return []
    edges = np.quantile(svix, np.linspace(0, 1, n_bins + 1))   # VIX 连续,并列罕见;若边界重合致某 bin 样本<40 则跳过(下游容忍 <n_bins 行)
    rows = []
    for b in range(n_bins):
        m = (svix >= edges[b]) & ((svix <= edges[b + 1]) if b == n_bins - 1 else (svix < edges[b + 1]))
        rb = rets[m]
        if len(rb) < 40:
            continue
        band = split_conformal(rb, levels=(level,), cal_frac=CAL_FRAC)[0]
        rows.append({"vix_lo": round(float(edges[b]), 1), "vix_hi": round(float(edges[b + 1]), 1),
                     "n": int(len(rb)), "lower_pct": band["lower_pct"], "upper_pct": band["upper_pct"],
                     "width_pct": round(band["upper_pct"] - band["lower_pct"], 2),
                     "empirical_coverage": band["empirical_coverage"]})
    return rows


def run_all():
    print("=== 方法 E：保形预测（split-conformal 覆盖区间，非方向）===")
    px = _sp_prices()
    if px is None or len(px) < 500:
        print("⚠ 数据不足，跳过")
        return None

    horizons = []
    for h in HORIZONS:
        rets = nonoverlap_fwd_returns(px, h)
        if len(rets) < 50:
            continue
        bands = split_conformal(rets)
        horizons.append({"horizon_days": h, "n_windows": int(len(rets)), "bands": bands})
        b90 = next((b for b in bands if b["level"] == 0.90), bands[-1])
        print(f"  {h:>3}日: 90% 区间 [{b90['lower_pct']:+.1f}%, {b90['upper_pct']:+.1f}%]  "
              f"经验覆盖={b90['empirical_coverage']}（名义0.90, n_test={b90['n_test']}）")

    vix = _load_vix()
    conditional = conditional_by_vix(px, vix, horizon=20) if vix is not None else []
    cond_period = ""
    if conditional:
        c = px.index.intersection(vix.index)                  # 条件区间仅覆盖 VIX 可得期(≈2001+),与上表(全样本)期间不同
        cond_period = f"{c[0].date()}–{c[-1].date()}"
        print("  条件区间(20日,按VIX体制): "
              + " | ".join(f"VIX{cc['vix_lo']}-{cc['vix_hi']} 宽{cc['width_pct']}%" for cc in conditional))

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "split-conformal：非重叠 N 日收益(秩调整分位)，旧70%校准定区间、新30%测试。"
                  "时间序切(非随机)，故不主张 exchangeable 下的有限样本覆盖保证；下列为出样本外【实测】覆盖。",
        "caveat": "这是**校准的不确定性区间，不是方向预测**——只说区间多宽、历史多少落在内，不预测涨跌。"
                  "区间略偏正只反映历史无条件分布的位置，不构成方向判断；且这是历史**无条件**区间、非对"
                  "【当前】市场状态的条件预测——不等于'未来 N 日一定落在此区间'。时间序切：经验覆盖<名义="
                  "较校准期更动荡(非平稳)，如实呈现。基于 S&P500。"
                  "'按 VIX 体制'区间=体制-条件(复用 split-conformal 分组),展示不确定性宽度随体制放大，仍是区间非方向、非'未来必落在内'。",
        "source": "S&P 500 (^GSPC)", "cal_frac": CAL_FRAC,
        "data_start": str(px.index[0].date()), "data_end": str(px.index[-1].date()),
        "horizons": horizons,
        "conditional_by_vix": conditional,
        "conditional_period": cond_period,
    }
    payload = json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False)
    for d in (PROC_DIR, WEB_DIR, DOCS_DIR):
        if d.exists():
            (d / "conformal.json").write_text(payload, encoding="utf-8")
    print(f"[OK] conformal.json")
    return out


if __name__ == "__main__":
    run_all()
