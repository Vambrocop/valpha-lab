"""
factor_model.py
核心因子分析：
  1. PCA 主成分分析  → 哪些因子在背后真正驱动市场？
  2. 因子相关性矩阵  → 全量资产 + 宏观指标
  3. 加息周期统计    → 每次加息前后市场表现
  4. 模型对比       → Logistic / RandomForest / XGBoost / SVM
  5. SHAP 特征贡献  → 哪个因子最重要、最准
  6. 预测结果输出   → signals.json 扩展
"""

import pandas as pd
import numpy as np
import json
import warnings
warnings.filterwarnings("ignore")
from pathlib import Path

from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.svm import SVC
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import accuracy_score, roc_auc_score
import xgboost as xgb

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
PROC_DIR.mkdir(exist_ok=True)

MARKET_ASSETS  = ["NASDAQ", "SP500", "BTC", "ETH", "DXY", "OIL", "GOLD", "TNX", "VIX"]
MACRO_COLS     = ["M2", "FED_RATE", "CPI", "UNRATE", "YIELD_10Y"]

# ── 加载数据 ──────────────────────────────────────────────────────
def load():
    df = pd.read_csv(RAW_DIR / "combined_prices.csv",
                     index_col="Date", parse_dates=True)
    df = df.sort_index().ffill()
    return df

def build_features(df):
    """构建月度特征矩阵，目标：SP500下月涨跌"""
    # 月度重采样
    m = df.resample("ME").last()

    feat = pd.DataFrame(index=m.index)

    # ── 收益率动量 ────────────────────────────────────────────────
    for col in ["NASDAQ", "SP500", "BTC", "DXY", "OIL", "GOLD", "VIX"]:
        if col not in m.columns: continue
        r = m[col].pct_change()
        feat[f"{col}_ret1m"]  = r
        feat[f"{col}_ret3m"]  = m[col].pct_change(3)
        feat[f"{col}_ret6m"]  = m[col].pct_change(6)
        feat[f"{col}_ret12m"] = m[col].pct_change(12)

    # ── 宏观水平 ─────────────────────────────────────────────────
    if "M2" in m.columns:
        feat["M2_growth"]   = m["M2"].pct_change(12)     # M2同比增速
        feat["M2_accel"]    = feat["M2_growth"].diff()   # M2加速度
    if "FED_RATE" in m.columns:
        feat["fed_rate"]    = m["FED_RATE"]
        feat["fed_chg"]     = m["FED_RATE"].diff()       # 利率变化
        feat["fed_chg3m"]   = m["FED_RATE"].diff(3)
    if "CPI" in m.columns:
        feat["cpi_yoy"]     = m["CPI"].pct_change(12) * 100
        feat["cpi_accel"]   = feat["cpi_yoy"].diff()
    if "UNRATE" in m.columns:
        feat["unrate"]      = m["UNRATE"]
        feat["unrate_chg"]  = m["UNRATE"].diff(3)
    if "TNX" in m.columns or "YIELD_10Y" in m.columns:
        ycol = "YIELD_10Y" if "YIELD_10Y" in m.columns else "TNX"
        feat["yield_10y"]   = m[ycol]
        feat["yield_chg"]   = m[ycol].diff(3)
        if "FED_RATE" in m.columns:
            feat["yield_spread"] = m[ycol] - m["FED_RATE"]  # 期限溢价（倒挂信号）

    # ── VIX 恐慌 ──────────────────────────────────────────────────
    if "VIX" in m.columns:
        feat["vix_level"]   = m["VIX"]
        feat["vix_chg"]     = m["VIX"].pct_change()
        feat["vix_hi30"]    = (m["VIX"] > 30).astype(int)  # VIX > 30 = 极度恐慌

    # ── 历法特征 ─────────────────────────────────────────────────
    feat["month"]       = feat.index.month
    feat["is_q_end"]    = feat.index.month.isin([3, 6, 9, 12]).astype(int)
    feat["is_tax_apr"]  = (feat.index.month == 4).astype(int)
    feat["is_sep"]      = (feat.index.month == 9).astype(int)
    feat["is_nov"]      = (feat.index.month == 11).astype(int)
    feat["pres_cycle"]  = ((feat.index.year - 2017) % 4) + 1

    # ── 目标变量：SP500下个月涨跌 ────────────────────────────────
    sp = m["SP500"] if "SP500" in m.columns else m["NASDAQ"]
    feat["target"] = (sp.shift(-1) > sp).astype(int)

    return feat.dropna()

# ── 1. PCA 主成分分析 ─────────────────────────────────────────────
def run_pca(feat):
    print("\n=== PCA 主成分分析 ===")
    X_cols = [c for c in feat.columns if c != "target"]
    X = feat[X_cols].dropna()
    y = feat["target"].reindex(X.index)

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    pca = PCA(n_components=min(10, len(X_cols)))
    pca.fit(Xs)

    # 解释方差
    explained = pd.DataFrame({
        "PC": [f"PC{i+1}" for i in range(len(pca.explained_variance_ratio_))],
        "explained_var":     pca.explained_variance_ratio_,
        "cumulative_var":    np.cumsum(pca.explained_variance_ratio_),
    })
    explained.to_csv(PROC_DIR / "pca_explained.csv", index=False)

    # 因子载荷（每个原始因子在PC上的权重）
    loadings = pd.DataFrame(
        pca.components_.T,
        index=X_cols,
        columns=[f"PC{i+1}" for i in range(pca.n_components_)]
    )
    loadings.to_csv(PROC_DIR / "pca_loadings.csv")

    print("  前5个主成分解释方差：")
    for _, row in explained.head(5).iterrows():
        bar = "█" * int(row["explained_var"] * 100)
        print(f"  {row['PC']}: {bar} {row['explained_var']*100:.1f}%  累计={row['cumulative_var']*100:.1f}%")

    # 每个PC的主要贡献因子
    print("\n  各PC主要因子（载荷最大的3个）：")
    for pc in ["PC1", "PC2", "PC3"]:
        top = loadings[pc].abs().nlargest(3)
        items = [f"{k}({loadings[pc][k]:+.2f})" for k in top.index]
        print(f"  {pc}: {', '.join(items)}")

    return explained, loadings

# ── 2. 加息周期分析 ───────────────────────────────────────────────
def rate_hike_analysis(df, feat):
    print("\n=== 加息周期统计 ===")
    if "FED_RATE" not in df.columns:
        print("  ⚠ 无FED_RATE数据")
        return None

    monthly = df.resample("ME").last()
    rate = monthly["FED_RATE"].dropna()
    sp = (monthly["SP500"] if "SP500" in monthly.columns else monthly["NASDAQ"]).dropna()

    # 识别加息月和降息月
    rate_chg = rate.diff()
    hike_months = rate_chg[rate_chg > 0].index
    cut_months  = rate_chg[rate_chg < 0].index

    rows = []
    for label, dates in [("加息", hike_months), ("降息", cut_months), ("不变", rate_chg[rate_chg == 0].index)]:
        sp_ret = []
        for d in dates:
            if d in sp.index:
                idx = sp.index.get_loc(d)
                if idx + 1 < len(sp):
                    ret = (sp.iloc[idx+1] / sp.iloc[idx]) - 1
                    sp_ret.append(ret)
        if sp_ret:
            vals = pd.Series(sp_ret)
            rows.append({
                "action":     label,
                "avg_return": vals.mean(),
                "win_rate":   (vals > 0).mean(),
                "count":      len(vals),
                "std":        vals.std(),
            })
            print(f"  {label}: n={len(vals)}  下月涨幅均值={vals.mean()*100:.2f}%  胜率={vals.mean()>0 and (vals>0).mean()*100:.0f}%")

    df_out = pd.DataFrame(rows)
    df_out.to_csv(PROC_DIR / "rate_hike_stats.csv", index=False)
    return df_out

# ── 3. VIX 区间分析 ───────────────────────────────────────────────
def vix_regime_analysis(df):
    print("\n=== VIX恐慌区间分析 ===")
    if "VIX" not in df.columns:
        print("  ⚠ 无VIX数据"); return None

    monthly = df.resample("ME").last()
    vix = monthly["VIX"].dropna()
    sp = (monthly["SP500"] if "SP500" in monthly.columns else monthly["NASDAQ"]).reindex(vix.index).pct_change().shift(-1)

    bins   = [0, 15, 20, 30, 40, 100]
    labels = ["低恐慌(<15)", "正常(15-20)", "警惕(20-30)", "恐慌(30-40)", "极度恐慌(>40)"]
    zones  = pd.cut(vix, bins=bins, labels=labels)

    rows = []
    for zone in labels:
        mask = zones == zone
        vals = sp[mask].dropna()
        if len(vals) < 3: continue
        rows.append({
            "vix_zone":   zone,
            "avg_return": vals.mean(),
            "win_rate":   (vals > 0).mean(),
            "count":      len(vals),
        })
        sig = "🟢买入机会" if vals.mean() > 0.01 else "🔴谨慎" if vals.mean() < -0.01 else "🟡中性"
        print(f"  {zone}: 下月均值={vals.mean()*100:.2f}%  胜率={(vals>0).mean()*100:.0f}%  {sig}")

    out = pd.DataFrame(rows)
    out.to_csv(PROC_DIR / "vix_regime.csv", index=False)
    return out

# ── 4. M2 与股市关系 ──────────────────────────────────────────────
def m2_analysis(df):
    print("\n=== M2货币供应与股市关系 ===")
    if "M2" not in df.columns:
        print("  ⚠ 无M2数据"); return None

    monthly = df.resample("ME").last()
    m2_yoy  = monthly["M2"].pct_change(12)
    sp_ret  = (monthly["SP500"] if "SP500" in monthly.columns else monthly["NASDAQ"]).pct_change(12)

    combined = pd.DataFrame({"M2_yoy": m2_yoy, "SP_yoy": sp_ret}).dropna()
    corr = combined.corr().iloc[0, 1]
    print(f"  M2同比增速 vs SP500同比：相关系数 = {corr:.3f}")

    # 按M2增速分区间
    bins   = [-np.inf, 0, 5, 10, 15, np.inf]
    labels_m2 = ["M2收缩", "M2低增(0-5%)", "M2中增(5-10%)", "M2高增(10-15%)", "M2极高(>15%)"]
    zones  = pd.cut(m2_yoy, bins=bins, labels=labels_m2)

    rows = []
    sp_fwd = sp_ret.shift(-1)
    for zone in labels_m2:
        mask = zones == zone
        vals = sp_fwd[mask].dropna()
        if len(vals) < 3: continue
        rows.append({"m2_zone": zone, "avg_sp_fwd": vals.mean(), "count": len(vals)})
        print(f"  {zone}: 未来12月SP500均值={vals.mean()*100:.1f}%  n={len(vals)}")

    out = pd.DataFrame(rows)
    out.to_csv(PROC_DIR / "m2_analysis.csv", index=False)
    return out, corr

# ── 5. 模型对比 ───────────────────────────────────────────────────
def model_comparison(feat):
    print("\n=== 模型对比（预测下月涨跌）===")
    X_cols = [c for c in feat.columns if c != "target"]
    X = feat[X_cols]
    y = feat["target"]

    scaler = StandardScaler()
    Xs = pd.DataFrame(scaler.fit_transform(X), index=X.index, columns=X_cols)

    tscv = TimeSeriesSplit(n_splits=5)

    models = {
        "逻辑回归":        LogisticRegression(max_iter=1000, random_state=42),
        "随机森林":        RandomForestClassifier(n_estimators=200, max_depth=5, random_state=42),
        "XGBoost":         xgb.XGBClassifier(n_estimators=150, max_depth=4, learning_rate=0.05,
                                              eval_metric="logloss", random_state=42, verbosity=0),
        "梯度提升(GBDT)":  GradientBoostingClassifier(n_estimators=150, max_depth=3, random_state=42),
        "SVM":             SVC(kernel="rbf", probability=True, random_state=42),
    }

    results = []
    for name, model in models.items():
        scores_acc = cross_val_score(model, Xs, y, cv=tscv, scoring="accuracy")
        scores_auc = cross_val_score(model, Xs, y, cv=tscv, scoring="roc_auc")
        results.append({
            "model":   name,
            "acc_mean": scores_acc.mean(),
            "acc_std":  scores_acc.std(),
            "auc_mean": scores_auc.mean(),
            "auc_std":  scores_auc.std(),
        })
        bar = "█" * int(scores_acc.mean() * 40)
        print(f"  {name:<16} Acc={scores_acc.mean():.3f}±{scores_acc.std():.3f}  AUC={scores_auc.mean():.3f}  {bar}")

    df_res = pd.DataFrame(results).sort_values("auc_mean", ascending=False)
    df_res.to_csv(PROC_DIR / "model_comparison.csv", index=False)

    # 用最佳模型计算特征重要性
    best_name = df_res.iloc[0]["model"]
    best_model = models[best_name]
    best_model.fit(Xs, y)
    print(f"\n  最优模型：{best_name}（AUC={df_res.iloc[0]['auc_mean']:.3f}）")

    if hasattr(best_model, "feature_importances_"):
        imp = pd.DataFrame({"feature": X_cols,
                            "importance": best_model.feature_importances_}
                           ).sort_values("importance", ascending=False)
        imp.to_csv(PROC_DIR / "best_model_importance.csv", index=False)
        print("\n  Top 10 最重要因子：")
        for _, row in imp.head(10).iterrows():
            bar = "█" * int(row["importance"] * 300)
            print(f"  {row['feature']:<25} {bar} {row['importance']:.4f}")

    # 当前预测
    latest_prob = best_model.predict_proba(Xs.iloc[[-1]])[0][1]
    print(f"\n  当前预测：下月SP500上涨概率 = {latest_prob*100:.1f}%")

    return df_res, latest_prob

# ── 6. 收益率相关性矩阵（全量） ───────────────────────────────────
def full_corr_matrix(df):
    print("\n=== 全量相关性矩阵 ===")
    cols = [c for c in MARKET_ASSETS if c in df.columns]
    monthly = df[cols].resample("ME").last().pct_change().dropna()
    corr = monthly.corr()
    corr.to_csv(PROC_DIR / "full_corr_matrix.csv")
    print("  已保存 full_corr_matrix.csv")
    return corr

# ── 主流程 ────────────────────────────────────────────────────────
def run_all():
    print("加载数据...")
    df   = load()
    feat = build_features(df)
    print(f"  特征矩阵：{feat.shape}  目标涨率={(feat['target']==1).mean()*100:.1f}%")

    full_corr_matrix(df)
    explained, loadings = run_pca(feat)
    rate_hike_analysis(df, feat)
    vix_regime_analysis(df)
    m2_analysis(df)
    df_models, latest_prob = model_comparison(feat)

    # 输出摘要 JSON
    summary = {
        "pca_top3": {
            f"PC{i+1}": loadings[f"PC{i+1}"].abs().nlargest(3).index.tolist()
            for i in range(min(3, len(loadings.columns)))
        },
        "model_ranking": df_models[["model","auc_mean"]].to_dict(orient="records"),
        "latest_prob": round(latest_prob, 4),
    }
    with open(PROC_DIR / "factor_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*55}")
    print(f"  因子分析完成 | 最优模型预测上涨概率 {latest_prob*100:.1f}%")
    print(f"{'='*55}")

if __name__ == "__main__":
    run_all()
