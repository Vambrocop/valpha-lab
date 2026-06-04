"""
multivariate_analysis.py — 完整统计方法库

方法                用途（金融场景）
────────────────────────────────────────────────────
CCA                 宏观变量组 ↔ 资产收益组 最大相关组合
RDA                 宏观变量能解释多少资产方差？（约束PCA）
SEM/路径分析        Fed→USD→Oil→Stock 因果链路量化
VECM               协整资产的误差修正（长期均衡）
滚动OLS回归        时变β系数（市场结构漂移）
分位数回归          尾部风险建模（最坏20%场景下发生什么）
贝叶斯变点检测      何时发生了体制性转变？
卡尔曼滤波          从噪声中提取真实趋势（状态空间）
SHAP可解释性        为什么模型这样预测？每个因子的贡献
Prophet预测         带不确定性区间的未来走势
"""

import pandas as pd
import numpy as np
import json
import warnings
warnings.filterwarnings("ignore")
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.cross_decomposition import CCA
from sklearn.linear_model import QuantileRegressor, LinearRegression
from sklearn.model_selection import TimeSeriesSplit
from statsmodels.tsa.vector_ar.vecm import coint_johansen, VECM
from statsmodels.regression.rolling import RollingOLS
import statsmodels.api as sm

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
PROC_DIR.mkdir(exist_ok=True)


def load():
    df = pd.read_csv(RAW_DIR / "combined_prices.csv",
                     index_col="Date", parse_dates=True)
    return df.sort_index().ffill()


def monthly(df):
    return df.resample("ME").last()


# ══════════════════════════════════════════════════════════════════
# 1. CCA — 典型相关分析
#    问：宏观因子的哪个线性组合与资产收益的哪个线性组合相关性最强？
# ══════════════════════════════════════════════════════════════════
def run_cca(df):
    print("\n=== 1. CCA 典型相关分析 ===")
    m = monthly(df)

    macro_cols = [c for c in ["M2","FED_RATE","CPI","UNRATE","YIELD_10Y"] if c in m.columns]
    asset_cols = [c for c in ["SP500","NASDAQ","BTC","GOLD","OIL"] if c in m.columns]

    if len(macro_cols) < 2 or len(asset_cols) < 2:
        print("  ⚠ 宏观或资产数据不足，跳过")
        return None

    X = m[macro_cols].pct_change().dropna()
    Y = m[asset_cols].pct_change().reindex(X.index).dropna()
    X = X.reindex(Y.index).dropna()
    Y = Y.reindex(X.index)

    n_comp = min(len(macro_cols), len(asset_cols), 3)
    cca = CCA(n_components=n_comp)
    cca.fit(X, Y)
    X_c, Y_c = cca.transform(X, Y)

    # 典型相关系数
    canonical_corrs = []
    for i in range(n_comp):
        r = np.corrcoef(X_c[:, i], Y_c[:, i])[0, 1]
        canonical_corrs.append(r)
        print(f"  第{i+1}典型相关: r={r:.3f}")

    # 宏观因子在第1典型变量上的载荷
    print("  \n  宏观→资产 第1组合载荷:")
    x_load = pd.Series(cca.x_weights_[:, 0], index=macro_cols).sort_values(key=abs, ascending=False)
    y_load = pd.Series(cca.y_weights_[:, 0], index=asset_cols).sort_values(key=abs, ascending=False)
    for k, v in x_load.items():
        print(f"    宏观 {k:<12}: {v:+.3f}")
    for k, v in y_load.items():
        print(f"    资产 {k:<12}: {v:+.3f}")

    result = {
        "canonical_corrs": canonical_corrs,
        "macro_loadings": x_load.to_dict(),
        "asset_loadings": y_load.to_dict(),
    }
    with open(PROC_DIR / "cca_result.json", "w") as f:
        json.dump(result, f, indent=2)
    return result


# ══════════════════════════════════════════════════════════════════
# 2. RDA — 冗余分析（约束PCA）
#    问：宏观变量能解释多少资产收益的总方差？
# ══════════════════════════════════════════════════════════════════
def run_rda(df):
    print("\n=== 2. RDA 冗余分析（约束PCA）===")
    m = monthly(df)

    macro_cols = [c for c in ["M2","FED_RATE","CPI","YIELD_10Y"] if c in m.columns]
    asset_cols = [c for c in ["SP500","NASDAQ","BTC","GOLD"] if c in m.columns]
    if not macro_cols or not asset_cols:
        print("  ⚠ 数据不足，跳过"); return None

    Y = m[asset_cols].pct_change().dropna()
    X = m[macro_cols].pct_change().reindex(Y.index).dropna()
    Y = Y.reindex(X.index)

    sc_x = StandardScaler(); sc_y = StandardScaler()
    Xs = sc_x.fit_transform(X)
    Ys = sc_y.fit_transform(Y)

    # RDA: 用X的线性组合（帽子矩阵）预测Y
    H = Xs @ np.linalg.pinv(Xs.T @ Xs) @ Xs.T   # 投影矩阵
    Y_fitted = H @ Ys                              # 约束拟合值

    # 解释方差比
    ss_total      = np.sum(Ys ** 2)
    ss_constrained = np.sum(Y_fitted ** 2)
    r2_constrained = ss_constrained / ss_total

    print(f"  宏观变量解释资产方差：{r2_constrained*100:.1f}%")
    print(f"  未被宏观解释的方差：{(1-r2_constrained)*100:.1f}%（市场自身动量/情绪）")

    # 每个宏观变量的边际贡献
    rows = []
    for col in macro_cols:
        others = [c for c in macro_cols if c != col]
        if others:
            Xo = sc_x.fit_transform(X[others])
            Ho = Xo @ np.linalg.pinv(Xo.T @ Xo) @ Xo.T
            r2_without = np.sum((Ho @ Ys) ** 2) / ss_total
            marginal = r2_constrained - r2_without
        else:
            marginal = r2_constrained
        rows.append({"macro": col, "marginal_r2": marginal})
        bar = "█" * int(marginal * 200)
        print(f"  {col:<14}: 边际贡献={marginal*100:.2f}%  {bar}")

    pd.DataFrame(rows).to_csv(PROC_DIR / "rda_result.csv", index=False)
    return r2_constrained


# ══════════════════════════════════════════════════════════════════
# 3. VECM — 向量误差修正模型
#    问：协整资产偏离均衡后，多快回归？谁调整谁？
# ══════════════════════════════════════════════════════════════════
def run_vecm(df):
    print("\n=== 3. VECM 协整 + 误差修正 ===")
    m = monthly(df)
    cols = [c for c in ["SP500","NASDAQ","GOLD"] if c in m.columns]
    if len(cols) < 2:
        print("  ⚠ 数据不足，跳过"); return None

    data = m[cols].dropna()

    # Johansen协整检验
    try:
        jres = coint_johansen(data, det_order=0, k_ar_diff=2)
        n_coint = int((jres.lr1 > jres.cvt[:, 1]).sum())
        print(f"  Johansen检验: {n_coint} 个协整关系（95%置信）")

        if n_coint > 0:
            model = VECM(data, k_ar_diff=2, coint_rank=n_coint, deterministic="co")
            res   = model.fit()
            # 调整速度（α系数）
            print("  调整速度（α）— 越大=越快回归均衡：")
            for i, col in enumerate(cols):
                alpha = res.alpha[i, 0]
                print(f"    {col}: α={alpha:.4f}  {'回归均衡↑' if alpha < 0 else '偏离均衡↓'}")
            res.summary_to_file = lambda: None
        else:
            print("  无显著协整关系，资产长期独立漂移")
    except Exception as e:
        print(f"  ⚠ VECM计算失败: {e}")
    return n_coint if 'n_coint' in dir() else 0


# ══════════════════════════════════════════════════════════════════
# 4. 滚动OLS回归 — 时变β系数
#    问：NASDAQ对VIX、利率的敏感性随时间如何变化？
# ══════════════════════════════════════════════════════════════════
def run_rolling_ols(df):
    print("\n=== 4. 滚动OLS回归（时变β）===")
    m = monthly(df)

    y_col = "SP500" if "SP500" in m.columns else "NASDAQ"
    x_cols = [c for c in ["VIX","TNX","DXY","OIL"] if c in m.columns]
    if not x_cols:
        print("  ⚠ 数据不足，跳过"); return None

    ret = m.pct_change().dropna()
    Y = ret[y_col]
    X = ret[x_cols].reindex(Y.index).dropna()
    Y = Y.reindex(X.index)

    X_const = sm.add_constant(X)
    window  = 36  # 3年滚动窗口

    model  = RollingOLS(Y, X_const, window=window)
    result = model.fit()

    betas = result.params.drop(columns=["const"], errors="ignore")
    betas.to_csv(PROC_DIR / "rolling_betas.csv")

    # 最新β值
    latest = betas.iloc[-1]
    print(f"  最新（过去{window}月）敏感度：")
    for col, val in latest.items():
        direction = "正相关" if val > 0 else "负相关"
        print(f"    SP500 对 {col:<8}: β={val:+.4f}  ({direction})")

    return betas


# ══════════════════════════════════════════════════════════════════
# 5. 分位数回归 — 尾部风险建模
#    问：在最坏10%的场景下，VIX每上升1点SP500跌多少？
# ══════════════════════════════════════════════════════════════════
def run_quantile_regression(df):
    print("\n=== 5. 分位数回归（尾部风险）===")
    m = monthly(df)

    y_col = "SP500" if "SP500" in m.columns else "NASDAQ"
    x_cols = [c for c in ["VIX","FED_RATE","DXY","OIL"] if c in m.columns]
    if not x_cols:
        print("  ⚠ 数据不足，跳过"); return None

    ret = m.pct_change().dropna()
    Y = ret[y_col].values
    X = ret[x_cols].reindex(ret[y_col].index).fillna(0).values

    rows = []
    for q in [0.10, 0.25, 0.50, 0.75, 0.90]:
        qr = QuantileRegressor(quantile=q, alpha=0.1, solver="highs")
        qr.fit(X, Y)
        rows.append({
            "quantile": q,
            **{f"β_{x_cols[i]}": round(qr.coef_[i], 4) for i in range(len(x_cols))}
        })

    out = pd.DataFrame(rows)
    out.to_csv(PROC_DIR / "quantile_regression.csv", index=False)

    print("  VIX对SP500收益的分位数效应：")
    for _, row in out.iterrows():
        q_label = f"Q{int(row['quantile']*100):02d}"
        vix_b   = row.get("β_VIX", 0)
        scene   = "最坏10%" if row["quantile"]==0.10 else \
                  "最坏25%" if row["quantile"]==0.25 else \
                  "中位数"  if row["quantile"]==0.50 else \
                  "最好25%" if row["quantile"]==0.75 else "最好10%"
        print(f"  {scene}场景 β_VIX={vix_b:+.4f}  "
              f"→ VIX+1点时SP500月收益{'下跌' if vix_b<0 else '上涨'}{abs(vix_b)*100:.2f}%")
    return out


# ══════════════════════════════════════════════════════════════════
# 6. 贝叶斯变点检测
#    问：市场何时发生了结构性断裂？
# ══════════════════════════════════════════════════════════════════
def run_changepoint(df):
    print("\n=== 6. 贝叶斯变点检测 ===")
    try:
        import ruptures as rpt
    except ImportError:
        print("  安装: pip install ruptures")
        try:
            import subprocess, sys
            subprocess.run([sys.executable, "-m", "pip", "install", "ruptures", "-q"])
            import ruptures as rpt
        except:
            print("  ⚠ 安装失败，跳过"); return None

    m = monthly(df)
    col = "SP500" if "SP500" in m.columns else "NASDAQ"
    ret = m[col].pct_change().dropna()

    # PELT算法（Pruned Exact Linear Time）
    signal = ret.values.reshape(-1, 1)
    model  = rpt.Pelt(model="rbf", min_size=6, jump=1)
    model.fit(signal)
    breakpoints = model.predict(pen=3)  # penalty值越大=越少变点

    # 转为日期
    bp_dates = [ret.index[b-1].strftime("%Y-%m") for b in breakpoints if b < len(ret)]

    print(f"  检测到 {len(bp_dates)} 个结构性变点：")
    for d in bp_dates:
        print(f"    {d}")

    pd.DataFrame({"breakpoint_date": bp_dates}).to_csv(
        PROC_DIR / "changepoints.csv", index=False)
    return bp_dates


# ══════════════════════════════════════════════════════════════════
# 7. 卡尔曼滤波 — 从噪声中提取真实趋势
#    问：市场真实状态（信号）vs 观测噪声
# ══════════════════════════════════════════════════════════════════
def run_kalman(df):
    print("\n=== 7. 卡尔曼滤波（信号提取）===")
    m = monthly(df)
    col = "SP500" if "SP500" in m.columns else "NASDAQ"
    prices = m[col].dropna()
    ret    = prices.pct_change().dropna()

    # 简单局部水平模型：μ_t = μ_{t-1} + ε_t, y_t = μ_t + η_t
    n = len(ret)
    y = ret.values

    # 手动实现卡尔曼滤波
    mu  = np.zeros(n)   # 滤波后状态（真实趋势）
    P   = np.zeros(n)   # 状态方差
    Q   = 0.0001        # 过程噪声（趋势漂移速度）
    R   = np.var(y)     # 观测噪声

    mu[0] = y[0]; P[0] = R
    for t in range(1, n):
        # 预测步
        mu_pred = mu[t-1]
        P_pred  = P[t-1] + Q
        # 更新步（卡尔曼增益）
        K       = P_pred / (P_pred + R)
        mu[t]   = mu_pred + K * (y[t] - mu_pred)
        P[t]    = (1 - K) * P_pred

    out = pd.DataFrame({
        "date":          ret.index,
        "observed_ret":  y,
        "kalman_trend":  mu,
        "uncertainty":   np.sqrt(P),
    })
    out.to_csv(PROC_DIR / "kalman_filter.csv", index=False)

    # 当前信号
    current_trend = mu[-1]
    direction = "上升趋势" if current_trend > 0 else "下降趋势"
    print(f"  当前卡尔曼趋势信号: {current_trend*100:+.2f}%/月  → {direction}")
    print(f"  信号不确定性(±1σ): {np.sqrt(P[-1])*100:.2f}%")
    return out


# ══════════════════════════════════════════════════════════════════
# 8. SHAP — 模型可解释性
#    问：这次预测为什么是涨/跌？每个因子贡献多少？
# ══════════════════════════════════════════════════════════════════
def run_shap(df):
    print("\n=== 8. SHAP 模型可解释性 ===")
    try:
        import shap
    except ImportError:
        print("  安装: pip install shap")
        try:
            import subprocess, sys
            subprocess.run([sys.executable, "-m", "pip", "install", "shap", "-q"])
            import shap
        except:
            print("  ⚠ 安装失败，跳过"); return None

    import xgboost as xgb

    # 复用 factor_model 的特征构建
    from factor_model import build_features
    feat = build_features(df)
    X_cols = [c for c in feat.columns if c != "target"]
    X = feat[X_cols]; y = feat["target"]

    sc = StandardScaler()
    Xs = pd.DataFrame(sc.fit_transform(X), index=X.index, columns=X_cols)

    model = xgb.XGBClassifier(n_estimators=150, max_depth=4,
                               eval_metric="logloss", random_state=42, verbosity=0)
    model.fit(Xs, y)

    explainer  = shap.TreeExplainer(model)
    shap_vals  = explainer.shap_values(Xs)

    # 全局重要性（平均|SHAP|）
    mean_shap = pd.Series(np.abs(shap_vals).mean(axis=0), index=X_cols)
    mean_shap = mean_shap.sort_values(ascending=False)
    mean_shap.to_csv(PROC_DIR / "shap_importance.csv")

    print("  Top 10 SHAP因子（全局平均影响）：")
    for feat_name, val in mean_shap.head(10).items():
        bar = "█" * int(val * 500)
        print(f"  {feat_name:<28}: {bar} {val:.4f}")

    # 最新一条预测的SHAP解释
    latest_shap = dict(zip(X_cols, shap_vals[-1]))
    top_pos = sorted(latest_shap.items(), key=lambda x: x[1], reverse=True)[:3]
    top_neg = sorted(latest_shap.items(), key=lambda x: x[1])[:3]
    print(f"\n  当前预测解释：")
    print(f"  支持上涨的因子: {[(k, f'{v:+.3f}') for k,v in top_pos]}")
    print(f"  支持下跌的因子: {[(k, f'{v:+.3f}') for k,v in top_neg]}")

    # 保存最新SHAP
    latest_df = pd.DataFrame([{"feature": k, "shap": v}
                               for k,v in latest_shap.items()]).sort_values("shap")
    latest_df.to_csv(PROC_DIR / "shap_latest.csv", index=False)
    return mean_shap


# ══════════════════════════════════════════════════════════════════
# 9. Prophet — 时间序列预测（带不确定性区间）
# ══════════════════════════════════════════════════════════════════
def run_prophet(df):
    print("\n=== 9. Prophet 时间序列预测 ===")
    try:
        from prophet import Prophet
    except ImportError:
        print("  安装: pip install prophet")
        try:
            import subprocess, sys
            subprocess.run([sys.executable, "-m", "pip", "install", "prophet", "-q"],
                          capture_output=True)
            from prophet import Prophet
        except:
            print("  ⚠ Prophet安装失败（需要C++编译环境），跳过"); return None

    m = monthly(df)
    col = "SP500" if "SP500" in m.columns else "NASDAQ"
    prices = m[col].dropna().reset_index()
    prices.columns = ["ds", "y"]
    prices["ds"] = prices["ds"].dt.tz_localize(None)

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.1,
        seasonality_mode="multiplicative",
    )
    model.fit(prices, iter=500)

    future   = model.make_future_dataframe(periods=12, freq="ME")
    forecast = model.predict(future)

    out = forecast[["ds","yhat","yhat_lower","yhat_upper"]].tail(15)
    out.to_csv(PROC_DIR / "prophet_forecast.csv", index=False)

    print("  未来12个月预测（月末收盘）：")
    future_only = forecast[forecast["ds"] > prices["ds"].max()]
    for _, row in future_only.head(6).iterrows():
        print(f"  {row['ds'].strftime('%Y-%m')}: "
              f"预测={row['yhat']:.0f}  "
              f"区间=[{row['yhat_lower']:.0f}, {row['yhat_upper']:.0f}]")
    return forecast


# ══════════════════════════════════════════════════════════════════
# 10. SEM路径分析（简化版：逐步OLS量化因果链）
#     Fed Rate → DXY → OIL → SP500
# ══════════════════════════════════════════════════════════════════
def run_path_analysis(df):
    print("\n=== 10. SEM路径分析（因果链量化）===")
    m = monthly(df)
    ret = m.pct_change().dropna()

    # 因果链：Fed → DXY → OIL → SP500
    chain = [
        ("FED_RATE", "DXY",   "加息→美元"),
        ("DXY",      "OIL",   "美元→油价"),
        ("OIL",      "SP500", "油价→标普"),
        ("FED_RATE", "SP500", "加息→标普（直接）"),
        ("VIX",      "SP500", "恐慌→标普"),
        ("M2",       "SP500", "M2→标普"),
    ]

    rows = []
    for cause, effect, label in chain:
        if cause not in ret.columns or effect not in ret.columns:
            continue
        x = sm.add_constant(ret[cause].dropna())
        y = ret[effect].reindex(x.index).dropna()
        x = x.reindex(y.index)
        res = sm.OLS(y, x).fit()
        rows.append({
            "path":   label,
            "cause":  cause,
            "effect": effect,
            "beta":   res.params.get(cause, 0),
            "pvalue": res.pvalues.get(cause, 1),
            "r2":     res.rsquared,
            "significant": res.pvalues.get(cause, 1) < 0.05,
        })
        sig = "✓" if res.pvalues.get(cause,1) < 0.05 else "✗"
        print(f"  {label:<14}: β={res.params.get(cause,0):+.4f}  "
              f"R²={res.rsquared:.3f}  p={res.pvalues.get(cause,1):.3f}  {sig}")

    out = pd.DataFrame(rows)
    out.to_csv(PROC_DIR / "path_analysis.csv", index=False)
    return out


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
def run_all():
    print("加载数据...")
    df = load()

    results = {}
    results["cca"]       = run_cca(df)
    results["rda"]       = run_rda(df)
    results["vecm"]      = run_vecm(df)
    results["rolling"]   = run_rolling_ols(df)
    results["quantile"]  = run_quantile_regression(df)
    results["changepoint"]= run_changepoint(df)
    results["kalman"]    = run_kalman(df)
    results["shap"]      = run_shap(df)
    results["prophet"]   = run_prophet(df)
    results["path"]      = run_path_analysis(df)

    print(f"\n{'='*60}")
    print("  全部高级分析完成")
    print(f"{'='*60}")
    return results


if __name__ == "__main__":
    run_all()
