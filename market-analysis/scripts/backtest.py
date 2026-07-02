"""
backtest.py — 贝叶斯信号系统历史回测验证

核心问题：当我们的信号显示第3/4/5档时，
          S&P 500 接下来实际上涨的频率是多少？

方法：
  1. 读取已计算好的每日信号（prob + tier）
  2. 与实际 S&P 500 前向收益对比
  3. 按档位分组，计算实际胜率和均值
  4. 校准曲线：模型预测概率 vs 实际实现率
  5. t检验：各档位与基准的差异是否显著

输出：
  data/processed/backtest_results.json
  （由 build_signals.py 嵌入 signals.json 的 backtest 字段）
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from scipy import stats

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"

HORIZONS = [1, 5, 10, 20, 30]   # 前向天数


def run_backtest(daily, long_csv, label):
    """用「信号对应指数自身」的长历史验证（纳指信号→纳指收益，标普→标普）"""
    print(f"=== 贝叶斯信号回测验证（{label}）===\n")
    print(f"  信号数量：{len(daily)} 天")

    # ── 加载该指数长历史 ──────────────────────────────────────────
    sp = pd.read_csv(RAW_DIR / long_csv, index_col=0, parse_dates=True).squeeze()
    sp = sp.sort_index().dropna()
    # 只保留日频价格（去掉非交易日的 NaN）
    sp = sp[sp > 0]
    print(f"  {label}：{sp.index[0].date()} – {sp.index[-1].date()}，{len(sp)} 行\n")

    # ── 构建每日记录 ───────────────────────────────────────────────
    records = []
    sp_dates = sp.index

    for date_str, sig in daily.items():
        ts = pd.Timestamp(date_str)
        if ts not in sp_dates:
            continue

        pos = sp_dates.get_loc(ts)
        row = {
            "date":  date_str,
            "prob":  sig["prob"],
            "tier":  int(sig["tier"]),
            "month": int(sig.get("month", 0)),
        }

        for h in HORIZONS:
            if pos + h < len(sp):
                p0  = sp.iloc[pos]
                ph  = sp.iloc[pos + h]
                ret = float((ph - p0) / p0)
                row[f"ret_{h}d"] = round(ret * 100, 4)
                row[f"up_{h}d"]  = int(ret > 0)

        records.append(row)

    if not records:
        raise ValueError(f"信号与 {long_csv} 无重叠日期(0 条可回测记录)——上游数据损坏或错位,fail-closed 中止")

    df = pd.DataFrame(records).dropna(subset=[f"ret_{h}d" for h in HORIZONS])
    print(f"  可回测记录：{len(df)} 天（含完整前向数据）\n")

    results = {
        # 方法论提示：前向窗口逐日采样，相邻样本高度重叠（20日窗口共享19天），
        # 有效样本量约为名义值的1/20，p值偏乐观；显著性仅作参考。
        # 另注意：先验/LR由全历史估计，本回测属样本内验证；
        # 真实样本外表现以 walk_forward 结果为准。
        "index": label,
        "method_note": "样本内验证；重叠窗口t检验p值偏乐观，样本外表现见walk_forward",
    }

    # ── 1. 全样本基准 ──────────────────────────────────────────────
    print("=== 基准（全样本）===")
    baseline = {}
    for h in HORIZONS:
        wr  = float(df[f"up_{h}d"].mean() * 100)
        avg = float(df[f"ret_{h}d"].mean())
        baseline[f"{h}d"] = {
            "win_rate":   round(wr,  1),
            "avg_return": round(avg, 2),
            "n":          len(df),
        }
        print(f"  {h:>2}日：胜率={wr:.1f}%  均值={avg:+.2f}%")
    results["baseline"] = baseline

    # ── 2. 按档位（Tier）分组 ───────────────────────────────────────
    print("\n=== 各档位表现 ===")
    tier_rows = []
    for tier in [1, 2, 3, 4, 5]:
        sub = df[df["tier"] == tier]
        if len(sub) < 15:
            print(f"  Tier {tier}: 样本不足 ({len(sub)})，跳过")
            continue

        row = {"tier": tier, "n": len(sub), "horizons": {}}
        print(f"\n  Tier {tier}（n={len(sub)}）")

        for h in HORIZONS:
            col_up  = f"up_{h}d"
            col_ret = f"ret_{h}d"
            s   = sub[col_up].values
            r   = sub[col_ret].values
            base_wr = df[col_up].mean()

            wr       = float(s.mean() * 100)
            avg_ret  = float(r.mean())
            med_ret  = float(np.median(r))
            t_stat, p_val = stats.ttest_1samp(s, base_wr)
            diff_wr  = round(wr - float(base_wr * 100), 1)

            row["horizons"][f"{h}d"] = {
                "win_rate":   round(wr, 1),
                "avg_return": round(avg_ret, 2),
                "med_return": round(med_ret, 2),
                "diff_vs_baseline": diff_wr,
                "t_stat":     round(float(t_stat), 3),
                "p_value":    round(float(p_val), 4),
                "significant":bool(p_val < 0.10),
            }
            sig_str = "[*]" if p_val < 0.10 else "   "
            print(f"    {h:>2}日: 胜率={wr:.1f}%({diff_wr:+.1f}pp)  "
                  f"均值={avg_ret:+.2f}%  p={p_val:.3f} {sig_str}")

        tier_rows.append(row)
    results["by_tier"] = tier_rows

    # ── 3. 校准曲线（概率区间 → 实际胜率）─────────────────────────
    print("\n=== 校准曲线（20日窗口）===")
    bins   = [0.48, 0.51, 0.54, 0.57, 0.60, 0.63, 0.70, 1.0]
    labels = ["<51%","51-54%","54-57%","57-60%","60-63%","63-70%",">70%"]
    df["bucket"] = pd.cut(df["prob"], bins=bins, labels=labels, right=True)

    cal_rows = []
    for lbl in labels:
        sub = df[df["bucket"] == lbl]
        if len(sub) < 20:
            continue
        s = sub["up_20d"]
        r = sub["ret_20d"]
        mid = float(lbl.replace("<","").replace(">","")
                       .split("-")[0].replace("%","")) / 100
        wr   = float(s.mean() * 100)
        avg  = float(r.mean())
        t_stat, p_val = stats.ttest_1samp(s.values, df["up_20d"].mean())
        cal_rows.append({
            "bucket":        lbl,
            "prob_mid":      round(mid, 3),
            "n":             len(sub),
            "actual_wr_20d": round(wr,  1),
            "avg_ret_20d":   round(avg, 2),
            "t_stat":        round(float(t_stat), 3),
            "p_value":       round(float(p_val), 4),
            "significant":   bool(p_val < 0.10),
        })
        sig_str = "[*]" if p_val < 0.10 else "   "
        print(f"  {lbl:>9}: 实际胜率={wr:.1f}%  均值={avg:+.2f}%  n={len(sub)} {sig_str}")
    results["calibration_20d"] = cal_rows

    # ── 4. 高档位集中持有策略 vs 买入持有对比 ──────────────────────
    print("\n=== 策略对比（仅在信号≥第4档时买入）===")
    h = 20
    tier4_up = df[df["tier"] >= 4][f"up_{h}d"]
    all_up   = df[f"up_{h}d"]

    wr4  = float(tier4_up.mean() * 100)
    wra  = float(all_up.mean() * 100)
    n4   = len(tier4_up)
    t_stat, p_val = stats.ttest_ind(tier4_up.values, all_up.values)

    print(f"  仅Tier≥4买入：胜率={wr4:.1f}%  n={n4}天  "
          f"vs 全时间买入={wra:.1f}%  p={p_val:.4f}")

    results["tier4_strategy"] = {
        "win_rate_20d":       round(wr4, 1),
        "baseline_win_rate":  round(wra, 1),
        "diff":               round(wr4 - wra, 1),
        "n_days":             n4,
        "p_value":            round(float(p_val), 4),
        "significant":        bool(p_val < 0.10),
        "avg_return_20d":     round(float(df[df["tier"]>=4]["ret_20d"].mean()), 2),
        "baseline_avg_ret":   round(float(df["ret_20d"].mean()), 2),
    }

    return results


if __name__ == "__main__":
    # 全量信号流在 processed/（signals.json 发布版只含近两年，P1-3 瘦身）
    full = PROC_DIR / "daily_signals_full.json"
    if full.exists():
        with open(full, encoding="utf-8") as f:
            sig_data = json.load(f)
    else:
        with open(WEB_DIR / "signals.json", encoding="utf-8") as f:
            sig_data = json.load(f)

    results = {
        "NASDAQ": run_backtest(sig_data["daily_signals"],
                               "NASDAQ_COMP_long.csv", "NASDAQ"),
    }
    sp_daily = sig_data.get("daily_signals_sp500")
    if sp_daily:
        results["SP500"] = run_backtest(sp_daily, "SP500_long.csv", "SP500")

    # 写入 processed/，由 build_signals.py 统一嵌入 signals.json
    out = PROC_DIR / "backtest_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 回测结果已写入 {out}（重跑 build_signals.py 后生效）")
