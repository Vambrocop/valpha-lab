"""
cycles.py — 方法 F 周期检验（谱分析 + 红噪声零分布）

诚实问题：市场是否真有**超出红噪声(AR1)**的周期成分？民间"周期"(4年/10年…)多半经不起检验
——与年尾数/任期年周期一脉(placebo 已打回)。**不预测周期会延续**，只检验"过去是否真有显著周期"。

方法：
- S&P 月度收益的周期图(periodogram)。
- 零模型 = **AR(1) 红噪声**(市场收益的合理零假设：弱持续性，无真周期)；生成 N 条 surrogate。
- **多重比较关键**：每个频率都比会有 ~5% 假阳性 → 用**最强谱峰 vs surrogate 最强谱峰**的
  全局检验(max-statistic)，最强峰真超过红噪声才算"有真周期"。

依赖 numpy/scipy。输出 cycles.json（processed + web + docs）。
"""
import datetime
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import signal

SCRIPTS  = Path(__file__).parent
RAW_DIR  = SCRIPTS.parent / "data" / "raw"
PROC_DIR = SCRIPTS.parent / "data" / "processed"
WEB_DIR  = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"
PROC_DIR.mkdir(parents=True, exist_ok=True)

N_SURR     = 1000
SEED       = 20260613
MIN_PERIOD = 3        # 月：滤掉高频噪声
ALPHA      = 0.05

# 民间/经济学常引用的"周期"——本工具检验 S&P 月度收益在这些周期带上是否真有超红噪声的功率。
# 注意：这些是**实体经济**周期(库存/投资/基建/技术)，并非股市收益周期；列此仅作对照检验。
NAMED_CYCLES = [
    ("基钦 Kitchin（库存）",        3,  5),
    ("朱格拉 Juglar（固定投资）",   7, 11),
    ("库兹涅茨 Kuznets（基建）",   15, 25),
    ("康波 Kondratiev（科技）",    45, 60),
]


def _sp_monthly_returns():
    f = RAW_DIR / "SP500_long.csv"
    if f.exists():
        s = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]
        s = pd.to_numeric(s, errors="coerce").dropna().sort_index()
        if len(s) > 500:
            return s.resample("ME").last().pct_change().dropna()
    try:
        import yfinance as yf
        df = yf.download("^GSPC", start="1928-01-01", auto_adjust=True, progress=False)
        c = df["Close"]
        c = (c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c).dropna()
        return c.resample("ME").last().pct_change().dropna()
    except Exception as e:
        print(f"  ⚠ 无法获取 S&P500：{e}")
        return None


def _fit_ar1(x):
    x = np.asarray(x, float) - np.mean(x)
    rho = float(np.corrcoef(x[:-1], x[1:])[0, 1])
    sigma = float(np.std(x) * np.sqrt(max(1 - rho ** 2, 1e-9)))
    return rho, sigma


def _ar1_surrogate(n, rho, sigma, rng):
    y = np.empty(n)
    e = rng.normal(0, sigma, n)
    y[0] = e[0] / np.sqrt(max(1 - rho ** 2, 1e-9))      # 平稳初值
    for t in range(1, n):
        y[t] = rho * y[t - 1] + e[t]
    return y


def cycle_test(returns, n_surr=N_SURR, seed=SEED):
    x = np.asarray(returns, float) - np.mean(returns)
    n = len(x)
    f, P = signal.periodogram(x)
    with np.errstate(divide="ignore"):
        period_m = np.where(f > 0, 1.0 / f, np.inf)      # 周期(月)
    band = (f > 0) & (period_m >= MIN_PERIOD) & (period_m <= n / 3)   # 可靠频带
    if band.sum() < 5:
        return {"status": "insufficient"}

    rho, sigma = _fit_ar1(x)
    rng = np.random.default_rng(seed)
    null = np.empty((n_surr, len(P)))                    # 全频谱 surrogate
    for i in range(n_surr):
        _, Ps = signal.periodogram(_ar1_surrogate(n, rho, sigma, rng))
        null[i] = Ps
    thr95 = np.percentile(null, 95, axis=0)              # 逐频率红噪声 95% 线
    surr_max = null[:, band].max(axis=1)                 # surrogate 最强峰分布

    obs_max = float(P[band].max())
    obs_period_m = float(period_m[band][np.argmax(P[band])])
    # 全局检验(多重比较稳健)：偏差校正 Monte-Carlo p 值(Davison-Hinkley)，
    # 分子分母各 +1 → p 永不取 0/1（裸 k/N 的 p=0 是无效估计）。
    p_global = float((np.sum(surr_max >= obs_max) + 1) / (n_surr + 1))

    # 描述性：超过逐频率红噪声 95% 线的周期（未控多重比较，仅参考）
    exc_idx = np.where(band & (P > thr95))[0]
    exceed = [round(float(period_m[j]) / 12, 2)
              for j in exc_idx[np.argsort(P[exc_idx])[::-1]]][:5]

    # 民间经济周期对照（实体经济概念，非股市收益周期；逐频率参考，超范围者诚实标注无法检验）
    MIN_BINS = 5    # 频带内可用谱点过少 → "未穿线"几乎无信息量，单列"分辨率边缘"而非干净排除
    named = []
    for label, lo_y, hi_y in NAMED_CYCLES:
        in_band = (f > 0) & (period_m >= lo_y * 12) & (period_m <= hi_y * 12)
        nbins = int(in_band.sum())
        if nbins == 0 or hi_y * 12 > n / 3:
            named.append({"cycle": label, "band_years": [lo_y, hi_y], "testable": False,
                          "note": f"超出可检验范围（数据约{n//12}年，谱分辨率不足以分辨该尺度）"})
        else:
            entry = {"cycle": label, "band_years": [lo_y, hi_y], "testable": True, "n_bins": nbins,
                     "exceeds_red_noise_95": bool((P[in_band] > thr95[in_band]).any())}
            if nbins < MIN_BINS:
                entry["low_resolution"] = True    # 频带内谱点 <5，分辨率边缘
            named.append(entry)

    sig = p_global < ALPHA
    return {"status": "ok", "n_months": n, "years": round(n / 12, 1),
            "ar1_rho": round(rho, 3), "top_period_years": round(obs_period_m / 12, 2),
            "p_global": round(p_global, 4), "significant": bool(sig),
            "exceed_pointwise_periods_years": exceed, "named_cycles": named,
            "verdict": (f"✓ 存在超红噪声的周期 ≈{obs_period_m/12:.1f}年 (全局 p={p_global:.3f})" if sig
                        else f"✗ 无显著周期：最强峰(≈{obs_period_m/12:.1f}年)未超红噪声 (全局 p={p_global:.3f})")}


def run_all():
    print("=== 方法 F：周期检验（谱 + AR1 红噪声）===")
    m = _sp_monthly_returns()
    if m is None or len(m) < 200:
        print("⚠ 数据不足，跳过")
        return None
    res = cycle_test(m.values)
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "S&P 月度收益周期图 vs AR(1) 红噪声 surrogate；最强谱峰 vs surrogate 最强峰的"
                  "全局检验(max-statistic，控多重比较)。",
        "caveat": "检验'过去是否真有超红噪声的周期成分'，**不预测周期会延续**。逐频率'超95%线'仅描述性"
                  "(未控多重比较)；结论以全局 max-statistic 为准。基于 S&P500 月度收益。",
        "source": "S&P 500 (^GSPC) 月度收益",
        "data_start": str(m.index[0].date()), "data_end": str(m.index[-1].date()),
        "n_surrogate": N_SURR, "seed": SEED, "result": res,
    }
    payload = json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False)
    for d in (PROC_DIR, WEB_DIR, DOCS_DIR):
        if d.exists():
            (d / "cycles.json").write_text(payload, encoding="utf-8")
    if res.get("status") == "ok":
        print(f"  AR1 ρ={res['ar1_rho']} · {res['verdict']}")
    print("[OK] cycles.json")
    return out


if __name__ == "__main__":
    run_all()
