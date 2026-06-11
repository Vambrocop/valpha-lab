"""
walk_forward.py — 滚动验证 + 模型优化

两个任务：
1. Walk-Forward Test：用训练期数据学习LR，在测试期验证，获得真实样本外准确率
2. 优化LR：找到每个技术因子的经验LR（不再手动设定），输出供 build_signals.py 使用

滚动窗口：
  2000-2012训练 → 2012-2014测试
  2000-2014训练 → 2014-2016测试
  2000-2016训练 → 2016-2018测试
  2000-2018训练 → 2018-2020测试
  2000-2020训练 → 2020-2022测试
  2000-2022训练 → 2022-2024测试

输出：
  walk_forward_results.json — 每个测试期的性能
  optimized_lr.json         — 从全量数据学到的最优LR
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from scipy import stats
from datetime import date, timedelta

# 模型核心原语统一来自 signal_model（与 build_signals.py 生产打分共用，禁止本地复制）。
# 打分时对学到的 LR 套用与生产相同的收缩——验证的配置必须等于部署的配置。
from signal_model import (
    tier as _tier, bayesian_update as bayesian_prob,
    week_of_month as _week_of_month, rsi as _rsi, shrink_lr,
    BTC_MOM_THRESH, DXY_TREND_THRESH, VOL_HIGH, VOL_LOW,
    RSI_OVERBOUGHT, RSI_OVERSOLD,
)

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"

HORIZON = 20  # 主要关注20日前向胜率


# ══════════════════════════════════════════════════════════════════
# 1. 构建特征数据集（每天的原始特征 + 前向收益）
# ══════════════════════════════════════════════════════════════════
def build_feature_df():
    """
    读取价格数据，计算每天的特征（日历 + 技术），
    和后续20日 S&P 500 收益
    """
    print("构建特征数据集...")
    prices = pd.read_csv(RAW_DIR / "combined_prices.csv",
                         index_col="Date", parse_dates=True).ffill()
    # 特征基于纳指 → 前向收益也用纳指（不再用标普验证纳指信号）
    sp_long = pd.read_csv(RAW_DIR / "NASDAQ_COMP_long.csv",
                          index_col=0, parse_dates=True).squeeze().dropna()
    sp_long = sp_long[sp_long > 0].sort_index()

    # 日频收益
    ret = prices.pct_change()

    # ── 预计算所有滚动指标（循环内只做索引，避免 O(n²)）──────────
    ind = {}
    for asset in ["NASDAQ", "BTC", "DXY"]:
        if asset not in prices.columns:
            continue
        p = prices[asset]
        ind[asset] = {
            "ma50":  p.rolling(50).mean(),
            "ma200": p.rolling(200).mean(),
            "r20":   p.pct_change(20),
        }
    rsi_nasdaq = vol_nasdaq = None
    if "NASDAQ" in ret.columns:
        r = ret["NASDAQ"]
        rsi_nasdaq = _rsi(r, 14)
        vol_nasdaq = r.rolling(20).std() * np.sqrt(252)
    dxy_tr = prices["DXY"].pct_change(20) if "DXY" in prices.columns else None

    # VIX期限结构（2009+）
    vix_bwd = None
    if "VIX" in prices.columns and "VIX3M" in prices.columns:
        vix_bwd = (prices["VIX"] >= prices["VIX3M"]).where(prices["VIX3M"].notna())
    # 隔夜动量（QQQ隔夜段近20日累计，overnight_analysis.py 生成）
    ov_mom = None
    try:
        ov = pd.read_csv(PROC_DIR / "overnight_daily.csv",
                         index_col="Date", parse_dates=True)
        col = "NASDAQ100" if "NASDAQ100" in ov.columns else ov.columns[-1]
        ov_mom = ov[col].rolling(20).sum().reindex(prices.index)
    except Exception:
        pass

    rows = []
    dates = prices.index

    for i, ts in enumerate(dates):
        if ts.weekday() >= 5:
            continue
        if ts not in sp_long.index:
            continue

        # ── 日历特征 ──────────────────────────────────────────────
        month = ts.month
        dow   = ts.weekday()
        wom   = _week_of_month(ts)

        # ── 技术特征（二值化）────────────────────────────────────
        feats = {}

        for asset, d in ind.items():
            p = prices[asset]
            ma50, ma200, r20 = d["ma50"].iloc[i], d["ma200"].iloc[i], d["r20"].iloc[i]
            feats[f"{asset}_above_ma200"] = int(p.iloc[i] > ma200) if not pd.isna(ma200) else None
            feats[f"{asset}_above_ma50"]  = int(p.iloc[i] > ma50)  if not pd.isna(ma50)  else None
            feats[f"{asset}_mom20_pos"]   = int(r20 > BTC_MOM_THRESH)  if not pd.isna(r20) else None
            feats[f"{asset}_mom20_neg"]   = int(r20 < -BTC_MOM_THRESH) if not pd.isna(r20) else None

        if rsi_nasdaq is not None:
            rv = rsi_nasdaq.iloc[i]
            feats["nasdaq_rsi_overbought"] = int(rv > RSI_OVERBOUGHT) if not pd.isna(rv) else None
            feats["nasdaq_rsi_oversold"]   = int(rv < RSI_OVERSOLD)   if not pd.isna(rv) else None
        if vol_nasdaq is not None:
            vv = vol_nasdaq.iloc[i]
            feats["nasdaq_high_vol"] = int(vv > VOL_HIGH) if not pd.isna(vv) else None
            feats["nasdaq_low_vol"]  = int(vv < VOL_LOW)  if not pd.isna(vv) else None

        if dxy_tr is not None:
            dv = dxy_tr.iloc[i]
            feats["dxy_rising"]  = int(dv > DXY_TREND_THRESH)  if not pd.isna(dv) else None
            feats["dxy_falling"] = int(dv < -DXY_TREND_THRESH) if not pd.isna(dv) else None

        if vix_bwd is not None:
            vb = vix_bwd.iloc[i]
            feats["vix_backwardation"] = int(bool(vb)) if not pd.isna(vb) else None
        if ov_mom is not None:
            om = ov_mom.iloc[i]
            feats["overnight_mom_pos"] = int(om > 0) if not pd.isna(om) else None
            feats["overnight_mom_neg"] = int(om < 0) if not pd.isna(om) else None

        # ── 前向收益 ──────────────────────────────────────────────
        pos = sp_long.index.get_loc(ts) if ts in sp_long.index else None
        fwd_ret = None
        fwd_up  = None
        if pos is not None and pos + HORIZON < len(sp_long):
            fwd_ret = float((sp_long.iloc[pos + HORIZON] - sp_long.iloc[pos]) / sp_long.iloc[pos])
            fwd_up  = int(fwd_ret > 0)

        row = {
            "date":  ts.strftime("%Y-%m-%d"),
            "year":  ts.year,
            "month": month,
            "dow":   dow,
            "wom":   wom,
            "fwd_ret_20d": round(fwd_ret * 100, 4) if fwd_ret is not None else None,
            "fwd_up_20d":  fwd_up,
        }
        row.update(feats)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["fwd_up_20d"])
    print(f"  特征数据集：{len(df)} 天（{df['year'].min()}-{df['year'].max()}）")
    return df


# ══════════════════════════════════════════════════════════════════
# 2. 从训练期学习经验LR
# ══════════════════════════════════════════════════════════════════
BINARY_FEATURES = [
    ("NASDAQ_above_ma200",   "NASDAQ在MA200上方"),
    ("NASDAQ_mom20_pos",     "NASDAQ近20日涨>5%"),
    ("NASDAQ_mom20_neg",     "NASDAQ近20日跌<-5%"),
    ("BTC_above_ma200",      "BTC在MA200上方"),
    ("BTC_mom20_pos",        "BTC近20日涨>5%"),
    ("BTC_mom20_neg",        "BTC近20日跌<-5%"),
    ("dxy_rising",           "美元走强"),
    ("dxy_falling",          "美元走弱"),
    ("nasdaq_rsi_overbought","NASDAQ RSI超买>75"),
    ("nasdaq_rsi_oversold",  "NASDAQ RSI超卖<35"),
    ("nasdaq_high_vol",      "NASDAQ高波动>25%"),
    ("nasdaq_low_vol",       "NASDAQ低波动<15%"),
    ("vix_backwardation",    "VIX期限结构倒挂(恐慌)"),
    ("overnight_mom_pos",    "隔夜动量为正(20日)"),
    ("overnight_mom_neg",    "隔夜动量为负(20日)"),
]

CALENDAR_FEATURES = {
    "month": list(range(1, 13)),
    "dow":   list(range(0, 5)),
    "wom":   [1, 2, 3, 4, 5],
}

def learn_lrs(train_df):
    """从训练集经验性地估计每个特征的LR"""
    base_wr = float(train_df["fwd_up_20d"].mean())
    learned = {"base_win_rate": round(base_wr, 4),
               "n_total": int(len(train_df)), "factors": {}}

    # 技术因子（二值）
    for col, name in BINARY_FEATURES:
        if col not in train_df.columns:
            continue
        sub = train_df[train_df[col] == 1]["fwd_up_20d"].dropna()
        if len(sub) < 50:
            continue
        wr = float(sub.mean())
        lr = wr / base_wr if base_wr > 0 else 1.0
        learned["factors"][col] = {
            "name": name,
            "win_rate": round(wr, 4),
            "lr": round(lr, 4),
            "n": len(sub),
        }

    # 日历因子（分组）
    for feat, vals in CALENDAR_FEATURES.items():
        learned["factors"][feat] = {}
        for v in vals:
            sub = train_df[train_df[feat] == v]["fwd_up_20d"].dropna()
            if len(sub) < 20:
                continue
            wr = float(sub.mean())
            lr = wr / base_wr if base_wr > 0 else 1.0
            learned["factors"][feat][str(v)] = {
                "win_rate": round(wr, 4),
                "lr": round(lr, 4),
                "n": len(sub),
            }
    return learned


# ══════════════════════════════════════════════════════════════════
# 3. 用学到的LR在测试期生成信号并验证
# ══════════════════════════════════════════════════════════════════
def score_row(row, lrs_dict):
    """用学到的LR对单行打分，返回概率。

    所有经验 LR 都先经 shrink_lr 收缩——与 build_signals._learned_on/_learned_off
    的生产路径一致，保证验证评估的就是部署配置。
    """
    base_wr = lrs_dict["base_win_rate"]
    factors = lrs_dict["factors"]
    likelihoods = []

    # 日历因子 LR（month/dow/wom，收缩后）
    for feat, key in [("month", "month"), ("dow", "dow"), ("wom", "wom")]:
        f = factors.get(feat, {}).get(str(int(row[key])))
        likelihoods.append(shrink_lr(f["lr"], f["n"]) if f else 1.0)

    # 技术因子 LR
    n_total = lrs_dict.get("n_total", 0)
    for col, _ in BINARY_FEATURES:
        val = row.get(col)
        if val == 1 and col in factors:
            likelihoods.append(shrink_lr(factors[col]["lr"], factors[col]["n"]))
        elif val == 0 and col in factors:
            # 反面：由全概率公式从收缩后的触发侧还原 wr_neg = (base - p1*wr_pos) / (1-p1)
            p1 = factors[col]["n"] / n_total if n_total > 0 else 0.5
            if p1 < 1.0:
                wr_on  = shrink_lr(factors[col]["lr"], factors[col]["n"]) * base_wr
                inv_wr = (base_wr - p1 * wr_on) / (1 - p1)
                inv_lr = inv_wr / base_wr if base_wr > 0 else 1.0
                likelihoods.append(max(inv_lr, 0.5))

    return bayesian_prob(base_wr, likelihoods)


def evaluate_on_test(test_df, lrs_dict):
    """在测试期计算各档位实际胜率"""
    probs = test_df.apply(lambda r: score_row(r, lrs_dict), axis=1)
    tiers = probs.apply(_tier)
    actual = test_df["fwd_up_20d"].values
    base_wr = float(actual.mean() * 100)

    result = {"baseline_wr": round(base_wr, 1), "n_total": len(test_df), "tiers": {}}
    for tier in [2, 3, 4, 5]:
        mask = tiers == tier
        if mask.sum() < 10:
            continue
        sub = actual[mask]
        wr  = float(sub.mean() * 100)
        t_stat, p_val = stats.ttest_1samp(sub, actual.mean())
        result["tiers"][tier] = {
            "n":        int(mask.sum()),
            "win_rate": round(wr, 1),
            "diff":     round(wr - base_wr, 1),
            "p_value":  round(float(p_val), 4),
            "significant": bool(p_val < 0.10),
        }

    # Tier≥4 汇总
    mask4 = tiers >= 4
    if mask4.sum() >= 10:
        sub4 = actual[mask4]
        t_stat4, p_val4 = stats.ttest_1samp(sub4, actual.mean())
        result["tier4_plus"] = {
            "n":        int(mask4.sum()),
            "win_rate": round(float(sub4.mean() * 100), 1),
            "diff":     round(float(sub4.mean() * 100) - base_wr, 1),
            "p_value":  round(float(p_val4), 4),
            "significant": bool(p_val4 < 0.10),
        }
    return result


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
FOLDS = [
    (2000, 2012, 2014),
    (2000, 2014, 2016),
    (2000, 2016, 2018),
    (2000, 2018, 2020),
    (2000, 2020, 2022),
    (2000, 2022, 2024),
]

def run():
    df = build_feature_df()

    fold_results = []
    print("\n=== Walk-Forward 滚动验证 ===")
    print(f"{'训练期':<18}{'测试期':<14}{'基准WR':>8}{'Tier4 WR':>10}{'差距':>7}{'p值':>8}{'显著':>6}")
    print("-" * 75)

    for (train_start, train_end, test_end) in FOLDS:
        train = df[(df["year"] >= train_start) & (df["year"] <  train_end)].copy()
        test  = df[(df["year"] >= train_end)   & (df["year"] <  test_end)].copy()

        if len(train) < 200 or len(test) < 50:
            continue

        lrs = learn_lrs(train)
        perf = evaluate_on_test(test, lrs)

        t4 = perf.get("tier4_plus", {})
        base = perf["baseline_wr"]
        wr4  = t4.get("win_rate", float("nan"))
        diff = t4.get("diff", float("nan"))
        pval = t4.get("p_value", float("nan"))
        sig  = "[*]" if t4.get("significant") else "   "

        print(f"  {train_start}-{train_end:<6}  {train_end}-{test_end:<6}  "
              f"{base:>7.1f}%  {wr4:>9.1f}%  {diff:>+6.1f}pp  {pval:>7.4f}  {sig}")

        fold_results.append({
            "train": f"{train_start}-{train_end}",
            "test":  f"{train_end}-{test_end}",
            "n_train": len(train),
            "n_test":  len(test),
            "baseline_wr": base,
            "performance": perf,
        })

    # ── 全量数据学习最优LR（用于实际部署）──────────────────────────
    print("\n=== 全量数据学习最优LR（2000-2024）===")
    full_train = df[df["year"] <= 2024].copy()
    optimized_lrs = learn_lrs(full_train)

    print(f"\n  基准胜率：{optimized_lrs['base_win_rate']*100:.1f}%")
    print("  关键技术因子LR（前8）：")
    tech = {k: v for k, v in optimized_lrs["factors"].items()
            if isinstance(v, dict) and "lr" in v}
    for k, v in sorted(tech.items(), key=lambda x: abs(x[1]["lr"]-1), reverse=True)[:8]:
        print(f"    {k:<28}: LR={v['lr']:.4f}  胜率={v['win_rate']*100:.1f}%  n={v['n']}")

    # ── 汇总统计 ────────────────────────────────────────────────────
    tier4_diffs = [f["performance"].get("tier4_plus", {}).get("diff", 0)
                   for f in fold_results if "tier4_plus" in f["performance"]]
    tier4_sigs  = [f["performance"].get("tier4_plus", {}).get("significant", False)
                   for f in fold_results if "tier4_plus" in f["performance"]]

    print(f"\n=== 汇总 ===")
    print(f"  折数：{len(fold_results)}")
    if tier4_diffs:
        print(f"  Tier≥4 样本外平均优势：{np.mean(tier4_diffs):+.1f}pp")
        print(f"  显著折数：{sum(tier4_sigs)} / {len(tier4_sigs)}")

    # ── 写入结果 ────────────────────────────────────────────────────
    output = {
        "folds": fold_results,
        "optimized_lr": optimized_lrs,
        "summary": {
            "index":   "NASDAQ",
            "n_folds": len(fold_results),
            "mean_tier4_advantage_pp": round(float(np.mean(tier4_diffs)), 2) if tier4_diffs else None,
            "n_significant_folds":     sum(tier4_sigs),
            "horizon_days":            HORIZON,
        }
    }

    out = PROC_DIR / "walk_forward_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] 结果写入 {out}（重跑 build_signals.py 后嵌入 signals.json）")

    return output


if __name__ == "__main__":
    run()
