"""
risk_dashboard.py — 方法 D 风险仪表盘（测风险，不测方向）

(1) VXN−VIX 价差：纳指100 vs 标普 隐含波动率溢价 + 历史分位/体制。
    走阔=市场把科技/成长定价得相对更危险；走窄=与大盘趋同。
(2) 条件下行风险：按当日 VIX 档位，看 NASDAQ 未来 20 日收益的 5% 下行分位
    （风险何时更深）——非参数条件分位，不假设线性，比点估计/方向预测诚实。

诚实红线：这两项都是**风险/体制读数**，不预测涨跌方向。
依赖仅 numpy/pandas/yfinance。输出 risk_dashboard.json（processed + web + docs）。
"""
import datetime
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

SCRIPTS  = Path(__file__).parent
RAW_DIR  = SCRIPTS.parent / "data" / "raw"
PROC_DIR = SCRIPTS.parent / "data" / "processed"
WEB_DIR  = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"
PROC_DIR.mkdir(parents=True, exist_ok=True)

HORIZON = 20      # 前瞻交易日（约一个月）
Q_TAIL  = 0.05    # 下行尾部分位
N_BINS  = 4       # VIX 档位数


def _fetch(tickers, start="2001-01-01"):
    """日收盘，自带缓存兜底（yfinance 限流时回退上次缓存）。"""
    import yfinance as yf
    end = (pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    out = {}
    for t in tickers:
        cache = RAW_DIR / f"risk_{t.replace('^', '')}.csv"
        s = None
        try:
            df = yf.download(t, start=start, end=end, auto_adjust=True, progress=False)
            if not df.empty:
                c = df["Close"]
                s = (c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c).dropna()
                s.index = pd.to_datetime(s.index)
                s.to_csv(cache)
        except Exception as e:
            print(f"  ⚠ {t} 下载失败：{e}")
        if s is None and cache.exists():
            s = pd.read_csv(cache, index_col=0, parse_dates=True).iloc[:, 0].dropna()
        if s is not None:
            out[t] = s
    return out


# ── (1) VXN − VIX 价差 ────────────────────────────────────────────
def vxn_vix_spread(vxn, vix):
    df = vxn.rename("vxn").to_frame().join(vix.rename("vix"), how="inner").sort_index()
    if len(df) < 60:
        return {"status": "insufficient"}
    spread = df["vxn"] - df["vix"]
    cur = float(spread.iloc[-1])
    pct = float((spread < cur).mean() * 100)            # 当前价差的历史分位
    regime = ("走阔 · 纳指隐含波动溢价处历史高位(相对读数,非方向预测)" if pct >= 70 else
              "走窄 · 纳指与大盘隐含波动趋同(相对读数)" if pct <= 30 else "中性(相对读数)")
    return {
        "status": "ok",
        "current": round(cur, 2), "percentile": round(pct, 1), "regime": regime,
        "vxn_last": round(float(df["vxn"].iloc[-1]), 2),
        "vix_last": round(float(df["vix"].iloc[-1]), 2),
        "mean": round(float(spread.mean()), 2),
        "min": round(float(spread.min()), 2), "max": round(float(spread.max()), 2),
        "start": str(df.index[0].date()), "end": str(df.index[-1].date()),
        "n": int(len(df)),
    }


# ── (2) 条件下行风险：VIX 分档 × NASDAQ 前瞻 20 日 5% 分位 ────────
def conditional_downside(ixic, vix, horizon=HORIZON, q=Q_TAIL, n_bins=N_BINS):
    df = ixic.rename("px").to_frame().join(vix.rename("vix"), how="inner").sort_index()
    df["fwd"] = df["px"].shift(-horizon) / df["px"] - 1     # 前瞻收益（末 horizon 行为 NaN）
    df = df.dropna()
    if len(df) < n_bins * horizon * 10:          # 重叠窗口下样本要足够大才有意义（审查 SHOULD-FIX）
        return []
    # qcut 可能因 VIX 边界并列产生 < n_bins 个档（duplicates="drop"），下游别假设恰好 n_bins 行
    df["bin"] = pd.qcut(df["vix"], n_bins, labels=False, duplicates="drop")
    rows = []
    for b in sorted(df["bin"].dropna().unique()):
        sub = df[df["bin"] == b]
        rows.append({
            "vix_lo": round(float(sub["vix"].min()), 1),
            "vix_hi": round(float(sub["vix"].max()), 1),
            "downside_q05_pct": round(float(sub["fwd"].quantile(q)) * 100, 2),
            "downside_q10_pct": round(float(sub["fwd"].quantile(0.10)) * 100, 2),  # 10% 分位作敏感性参照
            "median_pct": round(float(sub["fwd"].median()) * 100, 2),
            "n": int(len(sub)),
            "n_eff": int(len(sub) / horizon),    # 重叠窗口→有效独立样本≈n/horizon（审查 BLOCKER）
        })
    return rows


# ── (3) EVT 极值尾部风险：POT/GPD（测尾部多重/多久一遇，不预测时点/方向）──
def evt_tail(returns, threshold_pct=95.0, var_levels=(0.99, 0.999),
             loss_levels=(0.03, 0.05, 0.07, 0.10), run_gap=5):
    """对日损失超阈值部分拟合广义帕累托(GPD/POT)，估 VaR/ES + 极端跌幅重现期。
    ξ>0=厚尾。诚实点：极值日聚集→报极值指数 θ(越小越聚集)+阈值敏感性；
    重现期是长期平均频率、非规律间隔。只测严重度/稀有度，不预测时点/方向。"""
    s = returns.dropna()
    losses = -s.values                                     # 损失=负收益(正=亏)；时间序保留(去簇要用)
    n = len(losses)
    if n < 1000:
        return {"status": "insufficient"}

    def _fit(thr):
        uu = float(np.percentile(losses, thr))
        ee = losses[losses > uu] - uu
        if len(ee) < 50:
            return None, uu, None
        c, _l, b = stats.genpareto.fit(ee, floc=0.0)       # c=shape=ξ, scale=β
        return float(c), uu, float(b)

    xi, u, beta = _fit(threshold_pct)
    if xi is None:
        return {"status": "insufficient"}
    exc_pos = np.where(losses > u)[0]                      # 超阈日的时间位置
    nu = int(len(exc_pos))
    # runs 去簇：相邻超阈日间隔 > run_gap 才算新簇 → 极值指数 θ=簇数/超阈数(越小越聚集)
    n_clusters = 1 + int((np.diff(exc_pos) > run_gap).sum()) if nu else 0
    theta = round(n_clusters / nu, 3) if nu else None

    def _var(p):
        if abs(xi) < 1e-8:
            return u + beta * np.log((n / nu) / (1 - p))
        return u + (beta / xi) * (((n / nu) * (1 - p)) ** (-xi) - 1)

    var_es = []
    for p in var_levels:
        v = _var(p)
        es = min((v + beta - xi * u) / (1 - xi), 1.0) if xi < 1 else None   # 显示钳位:ξ→1 时 ES 爆炸,封顶100%(真实ξ~0.2不触发)
        var_es.append({"level": p, "var_pct": round(v * 100, 2),
                       "es_pct": round(es * 100, 2) if es is not None else None})

    rp = []
    for L in loss_levels:
        if L <= u:
            prob = float((losses > L).mean())              # 阈下用经验频率
        elif abs(xi) < 1e-8:
            prob = (nu / n) * np.exp(-(L - u) / beta)
        else:
            base = 1 + xi * (L - u) / beta                 # ξ<0 且 L 超右端点→base≤0→不可能(None)
            prob = (nu / n) * base ** (-1 / xi) if base > 0 else 0.0
        yrs = (1 / (prob * 252)) if prob > 0 else None
        rp.append({"loss_pct": round(L * 100, 1),
                   "return_period_yrs": round(yrs, 2) if yrs else None})

    xi_sens = {}                                           # 阈值敏感性：ξ 在不同阈值下是否稳定
    for t in (90.0, 95.0, 97.5):
        c, _u, _b = _fit(t)
        if c is not None:
            xi_sens[str(t)] = round(c, 3)

    return {"status": "ok", "xi": round(xi, 3), "beta": round(beta, 4),
            "threshold_loss_pct": round(u * 100, 2), "n": n, "n_exceed": nu,
            "n_clusters": n_clusters, "extremal_index": theta, "xi_sensitivity": xi_sens,
            "start": str(s.index[0].date()), "end": str(s.index[-1].date()),
            "tail": ("厚尾(ξ>0,极端损失比指数更重)" if xi > 0.05 else
                     "近指数尾(ξ≈0)" if abs(xi) <= 0.05 else "薄尾(ξ<0,损失有上界)"),
            "var_es": var_es, "return_periods": rp,
            "caveat": "重现期=长期平均频率、非规律间隔；极端日高度聚集(θ=极值指数,越小越聚集，"
                      "如 2008/2020 数周内贡献大量超阈日)，可能短期连发后多年沉寂。"
                      "ξ 对阈值敏感(见 xi_sensitivity)；样本跨多体制、假设尾部平稳。"}


def path_drawdown(ret, horizon=HORIZON):
    """非重叠 N 日窗口内最大回撤(峰到谷)幅度的分布——持有期内路径最深跌多少(风险,非方向)。
    与 EVT(单日尾部)/条件下行(期末分位)互补:刻画'持有期间最难受的回撤有多深'。"""
    r = np.asarray(ret, float)
    n = len(r)
    mags = []
    for start in range(0, n - horizon + 1, horizon):                   # +1:含最后一个完整窗口
        path = np.cumprod(1.0 + r[start:start + horizon])              # 窗口内净值路径(起点=1)
        dd = float((path / np.maximum.accumulate(path) - 1.0).min())   # 最大回撤(≤0)
        mags.append(-dd)                                               # 幅度(≥0)
    if len(mags) < 30:
        return {"status": "insufficient"}
    a = np.array(mags)
    return {"status": "ok", "horizon": int(horizon), "n_windows": int(len(a)),
            "median_pct": round(float(np.median(a)) * 100, 2),
            "p75_pct": round(float(np.percentile(a, 75)) * 100, 2),
            "p90_pct": round(float(np.percentile(a, 90)) * 100, 2),
            "p95_pct": round(float(np.percentile(a, 95)) * 100, 2),
            "worst_pct": round(float(a.max()) * 100, 2)}


def run_all():
    print("=== 方法 D：风险仪表盘（测风险不测方向）===")
    px = _fetch(["^VXN", "^VIX", "^IXIC"])
    if not px or "^VIX" not in px:
        print("⚠ 风险数据不足，跳过")
        return None

    spread = (vxn_vix_spread(px["^VXN"], px["^VIX"])
              if "^VXN" in px else {"status": "no_vxn"})
    downside = (conditional_downside(px["^IXIC"], px["^VIX"])
                if "^IXIC" in px else [])

    # EVT 尾部用长历史 S&P（含 1987/2008/2020 极端日；优先复用 long_history 的缓存）
    spf = RAW_DIR / "SP500_long.csv"
    if spf.exists():
        sp_ret = pd.read_csv(spf, index_col=0, parse_dates=True).iloc[:, 0].dropna().pct_change().dropna()
    else:
        gx = _fetch(["^GSPC"], start="1928-01-01")   # 与 SP500_long.csv 同起点，保证可复现
        sp_ret = gx["^GSPC"].pct_change().dropna() if "^GSPC" in gx else None
    evt = evt_tail(sp_ret) if sp_ret is not None else {"status": "insufficient"}
    drawdown = ([d for d in (path_drawdown(sp_ret, h) for h in (HORIZON, 60))
                 if d.get("status") == "ok"] if sp_ret is not None else [])

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "caveat": "风险/体制读数，非方向预测。条件下行=历史上某 VIX 档位后 20 日收益的 5% 分位，"
                  "刻画'风险何时更深'，不预测涨跌。注：前瞻窗口重叠→有效独立样本≈n/20(见 n_eff)，"
                  "尾部分位由极少数独立事件决定，勿过度解读精度(故并列 10% 分位作敏感性)。"
                  "价差分位为全历史(VXN 自~2003)、70/30 档为描述性约定、非体制调整。"
                  "用 VIX 作全市场风险条件变量(VXN 已用于价差读数，避免循环)。"
                  "EVT 尾部=对历史日损失超阈值部分拟合 GPD，估极端跌幅 VaR/ES 与重现期；"
                  "假设尾部行为平稳、外推有不确定性，只测严重度/稀有度，不测时点或方向。"
                  "路径回撤=非重叠 N 日窗口内峰到谷最大跌幅的分布(持有期内最深回撤)，与单日 EVT/期末下行互补，仍只测严重度、非方向。",
        "horizon": HORIZON, "q_tail": Q_TAIL,
        "vxn_vix_spread": spread,
        "downside_by_vix": downside,
        "evt": evt,
        "drawdown": drawdown,
    }
    from util_io import write_json
    write_json("risk_dashboard.json", out, proc=True, allow_nan=False)

    if spread.get("status") == "ok":
        print(f"  VXN−VIX 价差 = {spread['current']}（历史 {spread['percentile']} 分位 · {spread['regime']}）")
    if downside:
        lo, hi = downside[0], downside[-1]
        print(f"  下行尾部(20日5%分位)：VIX低档[{lo['vix_lo']}-{lo['vix_hi']}] {lo['downside_q05_pct']}%  "
              f"→ VIX高档[{hi['vix_lo']}-{hi['vix_hi']}] {hi['downside_q05_pct']}%")
    if evt.get("status") == "ok":
        v99 = next((x for x in evt["var_es"] if x["level"] == 0.99), {})
        rp7 = next((r["return_period_yrs"] for r in evt["return_periods"] if r["loss_pct"] == 7.0), "?")
        print(f"  EVT 尾部 ξ={evt['xi']}（{evt['tail']}）· 日VaR99={v99.get('var_pct')}% · "
              f"单日跌≥7% 重现期≈{rp7} 年（n={evt['n']}）")
    print(f"[OK] risk_dashboard.json")
    return out


if __name__ == "__main__":
    run_all()
