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

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "caveat": "风险/体制读数，非方向预测。条件下行=历史上某 VIX 档位后 20 日收益的 5% 分位，"
                  "刻画'风险何时更深'，不预测涨跌。注：前瞻窗口重叠→有效独立样本≈n/20(见 n_eff)，"
                  "尾部分位由极少数独立事件决定，勿过度解读精度(故并列 10% 分位作敏感性)。"
                  "价差分位为全历史(VXN 自~2003)、70/30 档为描述性约定、非体制调整。"
                  "用 VIX 作全市场风险条件变量(VXN 已用于价差读数，避免循环)。",
        "horizon": HORIZON, "q_tail": Q_TAIL,
        "vxn_vix_spread": spread,
        "downside_by_vix": downside,
    }
    payload = json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False)
    for d in (PROC_DIR, WEB_DIR, DOCS_DIR):
        if d.exists():
            (d / "risk_dashboard.json").write_text(payload, encoding="utf-8")

    if spread.get("status") == "ok":
        print(f"  VXN−VIX 价差 = {spread['current']}（历史 {spread['percentile']} 分位 · {spread['regime']}）")
    if downside:
        lo, hi = downside[0], downside[-1]
        print(f"  下行尾部(20日5%分位)：VIX低档[{lo['vix_lo']}-{lo['vix_hi']}] {lo['downside_q05_pct']}%  "
              f"→ VIX高档[{hi['vix_lo']}-{hi['vix_hi']}] {hi['downside_q05_pct']}%")
    print(f"[OK] risk_dashboard.json")
    return out


if __name__ == "__main__":
    run_all()
