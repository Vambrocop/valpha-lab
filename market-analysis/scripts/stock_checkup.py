"""
stock_checkup.py — 个股诚实体检（块0 脊柱：基础风险画像）

诚实定位：描述一只股票**是什么样**（风险/规律真伪），**绝不预测涨跌、绝不荐股/给买卖点**。
本块只产出基础风险：年化波动、历史最深回撤、对纳指的 β（OLS 斜率）+ 数据可行性探针。
数据不足的票如实标 insufficient，绝不编造。后续块（EVT/依赖度/规律真伪/区间/异动）见 STOCK_CHECKUP_SPEC.md。

复用已缓存的 data/raw/stocks_prices.csv（个股全量日线）+ combined_prices.csv 的 NASDAQ 列（β 基准）；
清单里若有未缓存的票（如 KO 首次），回退 yfinance 直接抓。依赖 numpy/pandas（yfinance 仅缺数据时用）。
输出 stock_checkup.json（PROC + WEB + DOCS 三处，allow_nan=False）。
"""
import datetime
import json
import numpy as np
import pandas as pd
from pathlib import Path

from risk_dashboard import evt_tail   # 块1：复用已审的 EVT/GPD 尾部风险

SCRIPTS  = Path(__file__).parent
RAW_DIR  = SCRIPTS.parent / "data" / "raw"
PROC_DIR = SCRIPTS.parent / "data" / "processed"
WEB_DIR  = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"
PROC_DIR.mkdir(parents=True, exist_ok=True)

# 精选清单（大盘流动龙头 + KO）；与 STOCK_CHECKUP_SPEC.md 一致
TICKER_NAMES = {
    "AAPL": "苹果", "MSFT": "微软", "GOOGL": "谷歌", "AMZN": "亚马逊", "NVDA": "英伟达",
    "META": "Meta", "TSLA": "特斯拉", "AVGO": "博通", "TSM": "台积电", "COST": "好市多",
    "LLY": "礼来", "BRK-B": "伯克希尔", "KO": "可口可乐",
}
MIN_DAYS = 250          # 基础风险至少需 ~1 年日线，否则判 insufficient


# ── 纯函数（可单测，不碰网络）──────────────────────────────────────
def annualized_vol(returns, periods=252):
    """日收益序列 → 年化波动率（小数）。"""
    r = np.asarray(returns, float)
    if len(r) < 2:
        return None
    return float(np.std(r, ddof=1) * np.sqrt(periods))


def max_drawdown(prices):
    """价格序列 → 历史最深回撤（峰到谷，返回最负的小数，如 -0.82）。"""
    p = np.asarray(prices, float)
    if len(p) < 2:
        return None
    peak = np.maximum.accumulate(p)
    return float((p / peak - 1.0).min())


def beta(stock_ret, mkt_ret):
    """对齐后的日收益数组 → 对基准的 β（OLS 斜率 = cov/var）。"""
    s = np.asarray(stock_ret, float)
    m = np.asarray(mkt_ret, float)
    if len(s) < 2 or len(m) != len(s):
        return None
    vm = float(np.var(m, ddof=1))
    if vm == 0:
        return None
    return float(np.cov(s, m, ddof=1)[0, 1] / vm)


def compute_evt(px):
    """块1：单票日损失的 EVT/GPD 尾部（ξ + 日 VaR/ES）。复用 risk_dashboard.evt_tail（需 ~1000+ 天）。
    返回紧凑子集；样本不足 → insufficient。只测尾部严重度/稀有度，不预测时点/方向。"""
    px = pd.to_numeric(px, errors="coerce").dropna().sort_index()
    ret = px.pct_change().dropna()
    r = evt_tail(ret)
    if r.get("status") != "ok":
        return {"status": r.get("status", "insufficient")}
    return {"status": "ok", "xi": r["xi"], "tail": r["tail"],
            "extremal_index": r["extremal_index"], "n_exceed": r["n_exceed"],
            "var_es": r["var_es"]}


def compute_basic_risk(px, nasdaq):
    """单票价格序列 px + 纳指价格序列 nasdaq（皆 pd.Series，索引=日期）→ 基础风险字典。"""
    px = pd.to_numeric(px, errors="coerce").dropna().sort_index()
    if len(px) < MIN_DAYS:
        return {"status": "insufficient", "n_days": int(len(px))}
    ret = px.pct_change().dropna()
    nas_ret = pd.to_numeric(nasdaq, errors="coerce").dropna().sort_index().pct_change().dropna()
    common = ret.index.intersection(nas_ret.index)
    b = None
    if len(common) >= 100:
        s = ret.reindex(common).to_numpy(float)
        m = nas_ret.reindex(common).to_numpy(float)
        ok = ~np.isnan(s) & ~np.isnan(m)
        b = beta(s[ok], m[ok])
    return {
        "status": "ok",
        "n_days": int(len(px)),
        "start": str(px.index[0].date()), "end": str(px.index[-1].date()),
        "ann_vol_pct": round(annualized_vol(ret.to_numpy()) * 100, 1),
        "max_drawdown_pct": round(max_drawdown(px.to_numpy()) * 100, 1),
        "beta_nasdaq": round(b, 2) if b is not None else None,
    }


# ── 取数（缓存优先，缺失回退 yfinance）────────────────────────────────
def _load_cached_stocks():
    f = RAW_DIR / "stocks_prices.csv"
    if f.exists():
        return pd.read_csv(f, index_col=0, parse_dates=True)
    return pd.DataFrame()


def _load_nasdaq():
    f = RAW_DIR / "combined_prices.csv"
    if f.exists():
        df = pd.read_csv(f, index_col=0, parse_dates=True)
        if "NASDAQ" in df.columns:
            return pd.to_numeric(df["NASDAQ"], errors="coerce").dropna()
    f2 = RAW_DIR / "NASDAQ_COMP_long.csv"
    if f2.exists():
        return pd.read_csv(f2, index_col=0, parse_dates=True).iloc[:, 0]
    return None


def _fetch_ticker(ticker):
    try:
        import yfinance as yf
        df = yf.download(ticker, start="2000-01-01",
                         end=(pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                         auto_adjust=True, progress=False)
        c = df["Close"]
        return (c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c).dropna().sort_index()
    except Exception as e:
        print(f"  ⚠ {ticker} 抓取失败：{e}")
        return None


def run_all():
    print("=== 个股诚实体检（块0：基础风险画像，非荐股非预测）===")
    nasdaq = _load_nasdaq()
    if nasdaq is None:
        print("⚠ 无纳指基准，β 将为空")
        nasdaq = pd.Series(dtype=float)
    cached = _load_cached_stocks()

    out_tickers = {}
    for tk in TICKER_NAMES:
        if tk in cached.columns:
            px = cached[tk]
        else:
            print(f"  {tk} 不在缓存，回退 yfinance…")
            px = _fetch_ticker(tk)
        if px is None or len(pd.to_numeric(px, errors="coerce").dropna()) == 0:
            out_tickers[tk] = {"name": TICKER_NAMES[tk], "status": "unavailable"}
            print(f"  {tk:<6} 数据不可得")
            continue
        risk = compute_basic_risk(px, nasdaq)
        risk["name"] = TICKER_NAMES[tk]
        if risk["status"] == "ok":
            risk["evt"] = compute_evt(px)                       # 块1：EVT 尾部
        out_tickers[tk] = risk
        if risk["status"] == "ok":
            ev = risk.get("evt", {})
            evtxt = (f" · EVT ξ={ev['xi']}" if ev.get("status") == "ok" else "")
            print(f"  {tk:<6} 波动 {risk['ann_vol_pct']}% · 最深回撤 {risk['max_drawdown_pct']}% · β={risk['beta_nasdaq']}{evtxt}")
        else:
            print(f"  {tk:<6} {risk['status']}（n={risk.get('n_days')}）")

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "caveat": "这是个股的**风险画像**，描述它历史上是什么样——**不预测涨跌、不荐股、不给买卖点**。"
                  "年化波动=历史日收益波动；最深回撤=历史峰到谷最大跌幅（可能极深，提示风险非机会）；"
                  "β=对纳指的敏感度（>1 比大盘更颠，<1 更稳），是风险特征不是收益承诺。数据不足的票如实标注。",
        "benchmark": "NASDAQ", "min_days": MIN_DAYS,
        "tickers": out_tickers,
    }
    payload = json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False)
    for d in (PROC_DIR, WEB_DIR, DOCS_DIR):
        if d.exists():
            (d / "stock_checkup.json").write_text(payload, encoding="utf-8")
    print(f"[OK] stock_checkup.json（{len(out_tickers)} 票）")
    return out


if __name__ == "__main__":
    run_all()
