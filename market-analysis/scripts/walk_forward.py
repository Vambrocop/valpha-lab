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

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"

HORIZON = 20  # 主要关注20日前向胜率

# ══════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════
def _week_of_month(ts):
    first_dow = ts.replace(day=1).weekday()
    return (ts.day + first_dow - 1) // 7 + 1

def _log_odds(p):
    p = np.clip(p, 0.02, 0.98)
    return np.log(p / (1 - p))

def _sigmoid(x):
    return 1 / (1 + np.exp(-x))

def bayesian_prob(prior, lrs):
    lo = _log_odds(prior)
    for lr in lrs:
        lo += np.log(max(lr, 0.01))
    return float(np.clip(_sigmoid(lo), 0.02, 0.98))

def _tier(p):
    if p >= 0.80: return 5
    if p >= 0.60: return 4
    if p >= 0.40: return 3
    if p >= 0.20: return 2
    return 1


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
    sp_long = pd.read_csv(RAW_DIR / "SP500_long.csv",
                          index_col=0, parse_dates=True).squeeze().dropna()
    sp_long = sp_long[sp_long > 0].sort_index()

    # 日频收益
    ret = prices.pct_change()
    sp_ret = ret["SP500"].dropna()

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

        for asset in ["NASDAQ", "BTC", "DXY"]:
            if asset not in prices.columns:
                continue
            p = prices[asset]
            ma50  = p.rolling(50).mean()
            ma200 = p.rolling(200).mean()
            r20   = p.pct_change(20)
            rsi_r = ret[asset] if asset in ret.columns else pd.Series(dtype=float)

            feats[f"{asset}_above_ma200"] = int(p.iloc[i] > ma200.iloc[i]) if not pd.isna(ma200.iloc[i]) else None
            feats[f"{asset}_above_ma50"]  = int(p.iloc[i] > ma50.iloc[i])  if not pd.isna(ma50.iloc[i])  else None
            feats[f"{asset}_mom20_pos"]   = int(r20.iloc[i] > 0.05) if not pd.isna(r20.iloc[i]) else None
            feats[f"{asset}_mom20_neg"]   = int(r20.iloc[i] < -0.05) if not pd.isna(r20.iloc[i]) else None

            if asset == "NASDAQ" and len(rsi_r) > 0:
                gain = rsi_r.clip(lower=0).rolling(14).mean()
                loss = (-rsi_r.clip(upper=0)).rolling(14).mean()
                rsi  = 100 - 100 / (1 + gain / (loss + 1e-10))
                rv   = rsi.iloc[i] if i < len(rsi) else np.nan
                feats["nasdaq_rsi_overbought"] = int(rv > 75) if not pd.isna(rv) else None
                feats["nasdaq_rsi_oversold"]   = int(rv < 35) if not pd.isna(rv) else None

            if asset == "NASDAQ":
                vol20 = ret[asset].rolling(20).std() * np.sqrt(252) if asset in ret.columns else pd.Series()
                vv = vol20.iloc[i] if i < len(vol20) else np.nan
                feats["nasdaq_high_vol"] = int(vv > 0.25) if not pd.isna(vv) else None
                feats["nasdaq_low_vol"]  = int(vv < 0.15) if not pd.isna(vv) else None

        if "DXY" in prices.columns:
            dxy_tr = prices["DXY"].pct_change(20)
            dv = dxy_tr.iloc[i] if i < len(dxy_tr) else np.nan
            feats["dxy_rising"]  = int(dv > 0.01)  if not pd.isna(dv) else None
            feats["dxy_falling"] = int(dv < -0.01) if not pd.isna(dv) else None

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
]

CALENDAR_FEATURES = {
    "month": list(range(1, 13)),
    "dow":   list(range(0, 5)),
    "wom":   [1, 2, 3, 4, 5],
}

def learn_lrs(train_df):
    """从训练集经验性地估计每个特征的LR"""
    base_wr = float(train_df["fwd_up_20d"].mean())
    learned = {"base_win_rate": round(base_wr, 4), "factors": {}}

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
    """用学到的LR对单行打分，返回概率"""
    base_wr = lrs_dict["base_win_rate"]
    factors = lrs_dict["factors"]
    likelihoods = []

    # 月度先验 LR
    month_lrs = factors.get("month", {})
    m_lr = month_lrs.get(str(int(row["month"])), {}).get("lr", 1.0)
    likelihoods.append(m_lr)

    # 星期 LR
    dow_lrs = factors.get("dow", {})
    d_lr = dow_lrs.get(str(int(row["dow"])), {}).get("lr", 1.0)
    likelihoods.append(d_lr)

    # WOM LR
    wom_lrs = factors.get("wom", {})
    w_lr = wom_lrs.get(str(int(row["wom"])), {}).get("lr", 1.0)
    likelihoods.append(w_lr)

    # 技术因子 LR
    for col, _ in BINARY_FEATURES:
        val = row.get(col)
        if val == 1 and col in factors:
            likelihoods.append(factors[col]["lr"])
        elif val == 0 and col in factors:
            # 反面：wr_neg ≈ 2*base - wr_pos（近似）
            inv_wr = 2 * base_wr - factors[col]["win_rate"]
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
            "n_folds": len(fold_results),
            "mean_tier4_advantage_pp": round(float(np.mean(tier4_diffs)), 2) if tier4_diffs else None,
            "n_significant_folds":     sum(tier4_sigs),
            "horizon_days":            HORIZON,
        }
    }

    out = PROC_DIR / "walk_forward_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] 结果写入 {out}")

    # 把汇总嵌入 signals.json
    sig_path = WEB_DIR / "signals.json"
    with open(sig_path, encoding="utf-8") as f:
        sig_data = json.load(f)

    sig_data["walk_forward"] = {
        "folds": [
            {
                "train": f["train"],
                "test":  f["test"],
                "baseline_wr": f["baseline_wr"],
                "tier4_wr":   f["performance"].get("tier4_plus", {}).get("win_rate"),
                "tier4_diff": f["performance"].get("tier4_plus", {}).get("diff"),
                "tier4_sig":  f["performance"].get("tier4_plus", {}).get("significant"),
            }
            for f in fold_results
        ],
        "summary": output["summary"],
        "optimized_lr_key_factors": {
            k: {"lr": v["lr"], "wr": round(v["win_rate"]*100,1), "n": v["n"]}
            for k, v in tech.items()
            if abs(v["lr"] - 1) > 0.02
        },
    }

    with open(sig_path, "w", encoding="utf-8") as f:
        json.dump(sig_data, f, ensure_ascii=False, indent=2)
    print(f"[OK] walk_forward 写入 signals.json")

    return output


if __name__ == "__main__":
    run()
