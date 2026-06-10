"""
export_chart_data.py
把所有图表所需数据打包成 web/ 下的 JSON 文件（run_all.py 会统一镜像到部署目录 docs/）。

输出：
  web/prices.json       — 归一化价格走势（周采样，2015+）
  web/charts_extra.json — 相关性/GARCH/Granger/月度/年度数据
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"
WEB_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════════
# 1. 价格归一化走势（prices.json）
# ══════════════════════════════════════════════════════════════════
def export_prices():
    print("=== 导出价格数据 ===")
    combined = pd.read_csv(RAW_DIR / "combined_prices.csv",
                           index_col="Date", parse_dates=True).ffill()

    # 只保留 2015 以后，周采样（减少体积）
    combined = combined[combined.index >= "2015-01-01"]
    weekly = combined.resample("W").last().dropna(how="all")

    ASSETS = {
        "NASDAQ": {"color": "#2ecc71", "label": "纳斯达克综合"},
        "NDX100": {"color": "#27ae60", "label": "纳斯达克100"},
        "SP500":  {"color": "#3498db", "label": "S&P 500"},
        "BTC":    {"color": "#f39c12", "label": "比特币"},
        "ETH":    {"color": "#9b59b6", "label": "以太坊"},
        "DXY":    {"color": "#e74c3c", "label": "美元指数"},
        "GOLD":   {"color": "#f1c40f", "label": "黄金"},
        "VIX":    {"color": "#e67e22", "label": "VIX恐慌指数"},
    }

    series = {}
    dates = [d.strftime("%Y-%m-%d") for d in weekly.index]

    for asset, meta in ASSETS.items():
        if asset not in weekly.columns:
            print(f"  跳过 {asset}（数据不存在）")
            continue
        col = weekly[asset].dropna()
        if col.empty:
            continue
        # 归一化到起点=100（对齐到共同开始日）
        first_valid = col.first_valid_index()
        if first_valid is None:
            continue
        norm = (col / col.loc[first_valid] * 100).reindex(weekly.index)
        vals = [round(float(v), 2) if not pd.isna(v) else None for v in norm]
        series[asset] = {
            "label":  meta["label"],
            "color":  meta["color"],
            "values": vals,
        }
        print(f"  {asset}: {len(col)} 周，起点 {first_valid.date()}")

    out = {"dates": dates, "assets": series}
    path = WEB_DIR / "prices.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {path}  ({path.stat().st_size // 1024} KB)\n")
    return out


# ══════════════════════════════════════════════════════════════════
# 2. 其他图表数据（charts_extra.json）
# ══════════════════════════════════════════════════════════════════
def _safe_csv(path, **kwargs):
    try:
        return pd.read_csv(path, **kwargs)
    except Exception:
        return pd.DataFrame()


def export_charts_extra():
    print("=== 导出图表补充数据 ===")
    out = {}

    # ── 滚动相关性 ────────────────────────────────────────────────
    corr = _safe_csv(PROC_DIR / "rolling_correlation_90d.csv", index_col=0, parse_dates=True)
    if not corr.empty:
        corr = corr[corr.index >= "2015-01-01"].resample("W").last().dropna(how="all")
        out["rolling_corr"] = {
            "dates": [d.strftime("%Y-%m-%d") for d in corr.index],
            "series": {
                col: [round(float(v), 4) if not pd.isna(v) else None for v in corr[col]]
                for col in corr.columns[:8]  # 最多8条线
            }
        }
        print(f"  rolling_corr: {len(corr)} 行  {len(corr.columns)} 列")

    # ── 月度胜率 ─────────────────────────────────────────────────
    mstats = _safe_csv(PROC_DIR / "monthly_stats.csv")
    if not mstats.empty:
        out["monthly_stats"] = mstats.to_dict(orient="records")
        print(f"  monthly_stats: {len(mstats)} 行  assets: {list(mstats['asset'].unique()) if 'asset' in mstats.columns else '?'}")

    # ── GARCH 波动率 ──────────────────────────────────────────────
    for asset in ["NASDAQ", "BTC"]:
        key = f"garch_{asset.lower()}"
        gdf = _safe_csv(PROC_DIR / f"garch_{asset.lower()}.csv", index_col=0, parse_dates=True)
        if not gdf.empty:
            gdf = gdf[gdf.index >= "2015-01-01"].resample("W").last()
            out[key] = {
                "dates": [d.strftime("%Y-%m-%d") for d in gdf.index],
                "volatility": [round(float(v)*100, 2) if not pd.isna(v) else None
                               for v in (gdf.iloc[:, 0] if not gdf.empty else [])],
            }
            print(f"  {key}: {len(gdf)} 行")

    # ── Granger 因果 ──────────────────────────────────────────────
    granger = _safe_csv(PROC_DIR / "granger_causality.csv")
    if not granger.empty:
        out["granger"] = granger.to_dict(orient="records")
        print(f"  granger: {len(granger)} 行")

    # ── 年度回报 ─────────────────────────────────────────────────
    annual = _safe_csv(PROC_DIR / "annual_returns.csv")
    if not annual.empty:
        out["annual_returns"] = annual.to_dict(orient="records")
        print(f"  annual_returns: {len(annual)} 行")
    else:
        # 从 long_history.json 读取
        try:
            with open(PROC_DIR / "long_history.json", encoding="utf-8") as f:
                lh = json.load(f)
            out["annual_returns"] = lh.get("annual_returns", [])
            print(f"  annual_returns (from long_history): {len(out['annual_returns'])} 行")
        except Exception:
            pass

    # ── DOM 月内效应 ──────────────────────────────────────────────
    dom = _safe_csv(PROC_DIR / "dom_stats.csv")
    if not dom.empty:
        nd = dom[dom["asset"] == "NASDAQ"] if "asset" in dom.columns else dom
        out["dom_stats"] = nd.to_dict(orient="records")
        print(f"  dom_stats: {len(nd)} 行")

    path = WEB_DIR / "charts_extra.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {path}  ({path.stat().st_size // 1024} KB)\n")
    return out


if __name__ == "__main__":
    export_prices()
    export_charts_extra()
    print("[OK] 所有图表数据已导出到 web/")
