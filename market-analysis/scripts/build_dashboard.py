"""
build_dashboard.py
生成单页HTML仪表盘，可直接托管到 GitHub Pages
运行：python build_dashboard.py → ../web/charts.html
（旧版9图统计页；主仪表盘 web/index.html 为手工维护，勿用脚本覆盖）
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from events import EVENTS, EVENT_COLORS, EVENT_SYMBOLS

PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
WEB_DIR  = Path(__file__).parent.parent / "web"
WEB_DIR.mkdir(exist_ok=True)

ASSET_COLORS = {
    "NASDAQ": "#2ecc71",
    "DXY":    "#3498db",
    "BTC":    "#f39c12",
    "ETH":    "#9b59b6",
}

MONTH_NAMES = ["", "1月", "2月", "3月", "4月", "5月", "6月",
               "7月", "8月", "9月", "10月", "11月", "12月"]

# ── 图1：四资产归一化价格走势 + 事件标注 ─────────────────────────
def fig_price_history():
    prices = pd.read_csv(RAW_DIR / "combined_prices.csv",
                         index_col="Date", parse_dates=True)
    normed = prices / prices.dropna().iloc[0] * 100

    fig = go.Figure()
    for asset, color in ASSET_COLORS.items():
        if asset not in normed.columns: continue
        fig.add_trace(go.Scatter(
            x=normed.index, y=normed[asset],
            name=asset, line=dict(color=color, width=2),
            hovertemplate=f"<b>{asset}</b><br>%{{x|%Y-%m-%d}}<br>指数：%{{y:.1f}}<extra></extra>"
        ))

    for e in EVENTS:
        d = pd.Timestamp(e["date"])
        if d < normed.index[0] or d > normed.index[-1]: continue
        color = EVENT_COLORS.get(e["type"], "#888")
        fig.add_vline(x=d, line_width=1, line_dash="dot", line_color=color, opacity=0.6)
        fig.add_annotation(x=d, y=1.02, yref="paper",
            text=EVENT_SYMBOLS.get(e["type"], "●"),
            showarrow=False, font=dict(color=color, size=12),
            hovertext=e["label"])

    fig.update_layout(
        title="四大资产归一化走势（基准=100）",
        xaxis_title="日期", yaxis_title="指数（起点=100）",
        hovermode="x unified", template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=480,
    )
    return fig

# ── 图2：滚动90天相关性 ───────────────────────────────────────────
def fig_rolling_corr():
    df = pd.read_csv(PROC_DIR / "rolling_correlation_90d.csv",
                     index_col="Date", parse_dates=True)
    fig = go.Figure()
    colors = ["#f39c12", "#9b59b6", "#3498db"]
    labels = ["NASDAQ vs BTC", "NASDAQ vs ETH", "NASDAQ vs DXY"]
    for col, color, label in zip(df.columns, colors, labels):
        fig.add_trace(go.Scatter(
            x=df.index, y=df[col], name=label,
            line=dict(color=color, width=2),
            hovertemplate=f"<b>{label}</b><br>%{{x|%Y-%m-%d}}<br>相关性：%{{y:.2f}}<extra></extra>"
        ))
    fig.add_hline(y=0, line_dash="dash", line_color="#888")
    fig.add_hline(y=0.7, line_dash="dot", line_color="#e74c3c",
                  annotation_text="强正相关(0.7)")
    fig.add_hline(y=-0.7, line_dash="dot", line_color="#3498db",
                  annotation_text="强负相关(-0.7)")
    fig.update_layout(
        title="滚动90天相关性（以NASDAQ为基准）",
        xaxis_title="日期", yaxis_title="皮尔逊相关系数",
        template="plotly_dark", height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig

# ── 图3：月度胜率热力图 ───────────────────────────────────────────
def fig_monthly_heatmap():
    df = pd.read_csv(PROC_DIR / "monthly_stats.csv")
    pivot = df.pivot(index="asset", columns="month", values="win_rate")
    pivot = pivot.reindex(["NASDAQ", "DXY", "BTC", "ETH"])
    pivot.columns = [MONTH_NAMES[m] for m in pivot.columns]

    fig = go.Figure(go.Heatmap(
        z=pivot.values * 100,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale="RdYlGn",
        zmid=50,
        text=[[f"{v:.0f}%" for v in row] for row in pivot.values * 100],
        texttemplate="%{text}",
        hovertemplate="<b>%{y}</b><br>%{x}<br>胜率：%{z:.1f}%<extra></extra>",
        colorbar=dict(title="胜率%"),
    ))
    fig.update_layout(
        title="各资产月度胜率（上涨概率）",
        template="plotly_dark", height=300,
    )
    return fig

# ── 图4：月度平均涨幅柱状图 ──────────────────────────────────────
def fig_monthly_returns():
    df = pd.read_csv(PROC_DIR / "monthly_stats.csv")
    fig = go.Figure()
    for asset, color in ASSET_COLORS.items():
        sub = df[df["asset"] == asset].sort_values("month")
        fig.add_trace(go.Bar(
            x=[MONTH_NAMES[m] for m in sub["month"]],
            y=sub["avg_return"] * 100,
            name=asset,
            marker_color=color,
            hovertemplate=f"<b>{asset}</b><br>%{{x}}<br>平均涨幅：%{{y:.2f}}%<extra></extra>"
        ))
    fig.update_layout(
        title="月度平均收益率（%）",
        barmode="group", template="plotly_dark",
        xaxis_title="月份", yaxis_title="平均涨幅(%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=400,
    )
    return fig

# ── 图5：年度收益热力图 ───────────────────────────────────────────
def fig_annual_heatmap():
    df = pd.read_csv(PROC_DIR / "annual_returns.csv", index_col="year")
    df = df[["NASDAQ", "DXY", "BTC", "ETH"]].dropna(how="all") * 100

    fig = go.Figure(go.Heatmap(
        z=df.values.T,
        x=df.index.astype(str).tolist(),
        y=df.columns.tolist(),
        colorscale="RdYlGn",
        zmid=0,
        text=[[f"{v:.0f}%" for v in row] for row in df.values.T],
        texttemplate="%{text}",
        hovertemplate="<b>%{y}</b><br>%{x}年<br>涨幅：%{z:.1f}%<extra></extra>",
        colorbar=dict(title="年度涨幅%"),
    ))
    fig.update_layout(
        title="年度收益热力图（绿涨红跌）",
        template="plotly_dark", height=320,
    )
    return fig

# ── 图6：总统任期周期 ─────────────────────────────────────────────
def fig_presidential_cycle():
    df = pd.read_csv(PROC_DIR / "presidential_cycle.csv", index_col="cycle_year")
    cycle_labels = {1: "第1年\n(新总统)", 2: "第2年\n(中期选举)", 3: "第3年\n(最强)", 4: "第4年\n(大选年)"}
    fig = go.Figure()
    for asset, color in ASSET_COLORS.items():
        if asset not in df.columns: continue
        fig.add_trace(go.Bar(
            x=[cycle_labels.get(i, str(i)) for i in df.index],
            y=df[asset] * 100,
            name=asset,
            marker_color=color,
            hovertemplate=f"<b>{asset}</b><br>%{{x}}<br>平均收益：%{{y:.1f}}%<extra></extra>"
        ))
    fig.update_layout(
        title="总统任期周期 × 各资产平均年度收益",
        barmode="group", template="plotly_dark",
        xaxis_title="任期年份", yaxis_title="平均年度收益(%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=400,
    )
    return fig

# ── 图7：相关性矩阵 ───────────────────────────────────────────────
def fig_correlation_matrix():
    df = pd.read_csv(PROC_DIR / "correlation_full.csv", index_col=0)
    df = df.loc[["NASDAQ", "DXY", "BTC", "ETH"], ["NASDAQ", "DXY", "BTC", "ETH"]]
    fig = go.Figure(go.Heatmap(
        z=df.values,
        x=df.columns.tolist(),
        y=df.index.tolist(),
        colorscale="RdBu_r",
        zmid=0, zmin=-1, zmax=1,
        text=[[f"{v:.2f}" for v in row] for row in df.values],
        texttemplate="%{text}",
        hovertemplate="<b>%{y} vs %{x}</b><br>相关性：%{z:.3f}<extra></extra>",
        colorbar=dict(title="相关性"),
    ))
    fig.update_layout(
        title="全期相关性矩阵（日收益率）",
        template="plotly_dark", height=350,
    )
    return fig

# ── 图8：BTC减半前后涨幅 ──────────────────────────────────────────
def fig_halving():
    df = pd.read_csv(PROC_DIR / "halving_analysis.csv")
    btc = df[(df["asset"] == "BTC") & (df["period"] == "180d")]
    ndx = df[(df["asset"] == "NASDAQ") & (df["period"] == "180d")]

    fig = go.Figure()
    for sub, label, color in [(btc, "BTC", "#f39c12"), (ndx, "NASDAQ", "#2ecc71")]:
        fig.add_trace(go.Bar(
            x=sub["halving"], y=sub["post_return"] * 100,
            name=f"{label} 减半后180天",
            marker_color=color,
            hovertemplate=f"<b>{label}</b><br>%{{x}}<br>+180天涨幅：%{{y:.1f}}%<extra></extra>"
        ))
    fig.update_layout(
        title="BTC减半后180天：BTC vs NASDAQ涨幅对比",
        template="plotly_dark", barmode="group",
        xaxis_title="减半日期", yaxis_title="涨幅(%)",
        height=380,
    )
    return fig

# ── 图9：黑天鹅冲击 ───────────────────────────────────────────────
def fig_black_swan():
    df = pd.read_csv(PROC_DIR / "black_swan_impact.csv")
    df20 = df[df["days"] == 20].copy()
    fig = px.bar(
        df20, x="event", y="return", color="asset",
        barmode="group",
        color_discrete_map=ASSET_COLORS,
        labels={"return": "20日后涨幅(%)", "event": "事件", "asset": "资产"},
        title="黑天鹅事件冲击：各资产20日后表现",
        template="plotly_dark",
    )
    fig.update_traces(hovertemplate="<b>%{x}</b><br>%{y:.1f}%<extra></extra>")
    fig.update_yaxes(tickformat=".0%")
    fig.update_layout(height=450, xaxis_tickangle=-30)
    return fig

# ── 组装HTML ──────────────────────────────────────────────────────
def build_html():
    figs = [
        ("四资产历史走势", fig_price_history()),
        ("相关性矩阵", fig_correlation_matrix()),
        ("滚动相关性", fig_rolling_corr()),
        ("月度胜率热力图", fig_monthly_heatmap()),
        ("月度平均涨幅", fig_monthly_returns()),
        ("年度收益热力图", fig_annual_heatmap()),
        ("总统任期周期", fig_presidential_cycle()),
        ("BTC减半效应", fig_halving()),
        ("黑天鹅冲击", fig_black_swan()),
    ]

    charts_html = ""
    for title, fig in figs:
        div = fig.to_html(full_html=False, include_plotlyjs=False)
        charts_html += f"""
        <section class="card">
            <div class="chart-container">{div}</div>
        </section>
        """

    legend_html = "".join(
        f'<span class="legend-item" style="color:{c}">{EVENT_SYMBOLS[t]} {t}</span>'
        for t, c in EVENT_COLORS.items()
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alpha Lab | 四大资产统计分析</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --accent: #2ecc71;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, 'PingFang SC', sans-serif; }}
  header {{ background: var(--surface); border-bottom: 1px solid var(--border);
            padding: 1.5rem 2rem; display: flex; align-items: center; gap: 1rem; }}
  header h1 {{ font-size: 1.5rem; }}
  header h1 span {{ color: var(--accent); }}
  .subtitle {{ color: #8b949e; font-size: 0.85rem; }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 1rem; padding: 1rem 2rem;
             background: var(--surface); border-bottom: 1px solid var(--border); font-size: 0.8rem; }}
  .legend-item {{ opacity: 0.85; }}
  main {{ max-width: 1400px; margin: 0 auto; padding: 1.5rem; display: grid;
          grid-template-columns: 1fr; gap: 1.5rem; }}
  .card {{ background: var(--surface); border: 1px solid var(--border);
           border-radius: 8px; overflow: hidden; }}
  .chart-container {{ padding: 0.5rem; }}
  footer {{ text-align: center; padding: 2rem; color: #8b949e; font-size: 0.8rem;
            border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<header>
  <div>
    <h1>⬡ <span>Alpha Lab</span> | 四大资产统计分析</h1>
    <div class="subtitle">NASDAQ · DXY美元指数 · Bitcoin · Ethereum &nbsp;|&nbsp; 数据来源：Yahoo Finance &nbsp;|&nbsp; 更新：2026-06</div>
  </div>
</header>
<div class="legend">
  <strong style="color:#8b949e">事件图例：</strong>
  {legend_html}
</div>
<main>
{charts_html}
</main>
<footer>
  Alpha Lab · <a href="https://github.com/Vambrocop/alpha-lab" style="color:#2ecc71">github.com/Vambrocop/alpha-lab</a>
  · 仅供个人学习研究，不构成投资建议
</footer>
</body>
</html>"""

    # 注意：写 charts.html 而不是 index.html！
    # web/index.html 是手工维护的主仪表盘，曾经被这个脚本覆盖过
    out = WEB_DIR / "charts.html"
    out.write_text(html, encoding="utf-8")
    print(f"✓ 旧版统计图表页生成：{out}")
    return out

if __name__ == "__main__":
    build_html()
    print("完成！将 web/ 目录推送到 GitHub 并开启 GitHub Pages 即可在线访问。")
