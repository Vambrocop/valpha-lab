"""
export_multivariate_json.py
从所有 processed/ 文件汇总生成 multivariate.json
"""
import pandas as pd, json, numpy as np, datetime, shutil
from pathlib import Path

PROC = Path(__file__).parent.parent / "data" / "processed"
WEB  = Path(__file__).parent.parent / "web"
DOCS = Path(__file__).parent.parent.parent / "docs"

result = {}

# ── SHAP ─────────────────────────────────────────────────
shap_imp = pd.read_csv(PROC / "shap_importance.csv", header=None, names=["feature","importance"])
shap_imp = shap_imp.dropna().sort_values("importance", ascending=False).head(15)
result["shap"] = [{"feature": r["feature"], "importance": round(float(r["importance"]), 4)}
                  for _, r in shap_imp.iterrows()]

shap_lat = pd.read_csv(PROC / "shap_latest.csv")
result["shap_latest"] = {
    "bullish": [{"feature": r["feature"], "shap": round(float(r["shap"]), 3)}
                for _, r in shap_lat.sort_values("shap", ascending=False).head(3).iterrows()],
    "bearish": [{"feature": r["feature"], "shap": round(float(r["shap"]), 3)}
                for _, r in shap_lat.sort_values("shap").head(3).iterrows()],
}

# ── Prophet ───────────────────────────────────────────────
prophet = pd.read_csv(PROC / "prophet_forecast.csv")
prophet["ds"] = pd.to_datetime(prophet["ds"])
today = datetime.date.today()
future = prophet[prophet["ds"].dt.date >= today].head(12)
result["prophet"] = [{"date": r["ds"].strftime("%Y-%m"), "yhat": int(r["yhat"]),
                       "lower": int(r["yhat_lower"]), "upper": int(r["yhat_upper"])}
                     for _, r in future.iterrows()]

# ── Kalman ────────────────────────────────────────────────
kalman = pd.read_csv(PROC / "kalman_filter.csv")
kalman["date"] = pd.to_datetime(kalman["date"])
result["kalman"] = [{"date": r["date"].strftime("%Y-%m"),
                      "observed": round(float(r["observed_ret"]) * 100, 2),
                      "trend":    round(float(r["kalman_trend"]) * 100, 2)}
                    for _, r in kalman.tail(48).iterrows()]
result["kalman_current"] = round(float(kalman["kalman_trend"].iloc[-1]) * 100, 2)

# ── CCA ──────────────────────────────────────────────────
cca = json.load(open(PROC / "cca_result.json"))
result["cca"] = cca

# ── RDA ──────────────────────────────────────────────────
rda = pd.read_csv(PROC / "rda_result.csv")
result["rda"] = [{"macro": r["macro"], "marginal_r2": round(float(r["marginal_r2"]) * 100, 2)}
                 for _, r in rda.iterrows()]

# ── Path analysis ─────────────────────────────────────────
path = pd.read_csv(PROC / "path_analysis.csv")
result["path"] = [{"path": r["path"], "beta": round(float(r["beta"]), 4),
                   "pvalue": round(float(r["pvalue"]), 4), "r2": round(float(r["r2"]), 3),
                   "significant": bool(r["significant"])}
                  for _, r in path.iterrows()]

# ── Rolling betas ─────────────────────────────────────────
rolling = pd.read_csv(PROC / "rolling_betas.csv", index_col=0)
rolling.index = pd.to_datetime(rolling.index)
rolling = rolling.dropna().tail(48)
result["rolling_betas"] = {
    "dates": [str(d)[:7] for d in rolling.index],
    "VIX":   [round(float(v), 4) for v in rolling.get("VIX", pd.Series()).fillna(0)],
    "DXY":   [round(float(v), 4) for v in rolling.get("DXY", pd.Series()).fillna(0)],
    "OIL":   [round(float(v), 4) for v in rolling.get("OIL", pd.Series()).fillna(0)],
    "TNX":   [round(float(v), 4) for v in rolling.get("TNX", pd.Series()).fillna(0)],
}

# ── 模型解释率综合对比 ────────────────────────────────────
model_cmp = pd.read_csv(PROC / "model_comparison.csv")
cca_corrs = cca.get("canonical_corrs", [])
cca_r2_pct = round(cca_corrs[0] ** 2 * 100, 1) if cca_corrs else 0
rda_total  = round(sum(r["marginal_r2"] for r in result["rda"]), 1)

result["model_comparison"] = {
    # ML分类模型：预测下月涨跌
    "ml_models": [
        {"name": str(row["model"]),
         "auc":  round(float(row["auc_mean"]), 3),
         "acc":  round(float(row["acc_mean"]), 3),
         "type": "classification"}
        for _, row in model_cmp.iterrows()
    ],
    # 统计模型：解释方差 / 因果强度
    "stats_models": [
        {"name": "VIX→SP500（路径OLS）", "r2_pct": 56.0,      "note": "单因子R²=56%，最强关系", "significant": True},
        {"name": "CCA 典型相关 r²",       "r2_pct": cca_r2_pct, "note": "宏观↔资产最大共变方向", "significant": True},
        {"name": "油价→SP500（路径OLS）", "r2_pct": 7.1,       "note": "R²=7.1%，p=0.006",     "significant": True},
        {"name": "RDA 宏观总解释力",       "r2_pct": rda_total,  "note": "宏观只能解释这么多",   "significant": True},
        {"name": "加息→SP500（直接）",    "r2_pct": 0.5,        "note": "p=0.47，不显著",        "significant": False},
        {"name": "M2→SP500",            "r2_pct": 2.4,        "note": "p=0.12，不显著",         "significant": False},
    ]
}

# ── 写出文件 ──────────────────────────────────────────────
for dest in [WEB / "multivariate.json", DOCS / "multivariate.json"]:
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

# 同步 signals.json
shutil.copy(WEB / "signals.json", DOCS / "signals.json")

print("multivariate.json exported, size:", len(json.dumps(result)), "chars")
print()
print("=== 模型解释率汇总 ===")
for m in result["model_comparison"]["ml_models"]:
    print(f"  ML {m['name']:<18} AUC={m['auc']:.3f}  Acc={m['acc']:.3f}")
print()
for s in result["model_comparison"]["stats_models"]:
    sig = "✓" if s["significant"] else "✗"
    print(f"  统计 {s['name']:<20} R²={s['r2_pct']}%  {sig}  {s['note']}")
