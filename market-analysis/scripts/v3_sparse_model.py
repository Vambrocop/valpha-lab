"""v3_sparse_model.py — v3.0 稀疏模型嵌套验证实验（计划：docs_internal/V3_SPARSE_PLAN.md rev2）

假设：只用 BTC 20日动量 + 日历的稀疏模型能否过 AUC 0.5（15 因子全家桶已证 0.445）。

预注册要点（rev2，经 Opus 独立审查修订）：
- 4 变体固定菜单，只有 A(v3-sparse) 进决策；B/C 消融、D 参照
- 主口径 = 4 个 BTC 全程可观测的折（2016-2024 测试期），purged+embargo 复用 factor_pruning
- 决策只看 dev：① 拼接 AUC 块自助 95%CI 下界>0.50 ② pooled 与 mean-of-folds 分歧≤0.03
  ③ Tier≥4 块自助 diff>0 且 p_boot<0.05
- holdout(2024-2026) 仅报告：假设在它上面选出（P2-5 尸检），无独立证据力
- 实验通过 ≠ 部署：通过 → benchmark 影子前向（≥120 交易日、Tier≥4 ≥20 次、前向 diff>0 才 bump）
- 消融预注册：若 B≥A → "BTC 增量为零，与尸检矛盾，触发复查"，不进影子前向

子集实现锁死：仅删 lrs_dict["factors"] 的 key；learn_lrs 全量学习，n_total/base_win_rate 不动。
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

from sklearn.metrics import roc_auc_score

from walk_forward import build_feature_df, learn_lrs, score_row, block_bootstrap_diff
from factor_pruning import _purged_train, DEV_FOLDS, HOLDOUT_START
from signal_model import tier as _tier

PROC_DIR = Path(__file__).parent.parent / "data" / "processed"

HORIZON = 20
# 主口径：BTC 全程可观测的 4 折（精确列出，禁止按"年≥2016"过滤行）
PRIMARY_FOLDS = [(2000, 2016, 2018), (2000, 2018, 2020),
                 (2000, 2020, 2022), (2000, 2022, 2024)]

CAL_KEYS = ("month", "dow", "wom")
VARIANTS = {
    "v3_sparse":     {"binary": ["BTC_mom20_pos", "BTC_mom20_neg"], "calendar": True},
    "calendar_only": {"binary": [],                                  "calendar": True},
    "btc_only":      {"binary": ["BTC_mom20_pos", "BTC_mom20_neg"], "calendar": False},
    "v2_full":       {"binary": None,                                "calendar": True},  # None=全保留
}

HONESTY = [
    "holdout 选择污染：v3.0 假设来自 P2-5 尸检，尸检用过同一个 2024-2026 holdout 确认 BTC 动量——holdout 结果仅供参考，无独立确认力",
    "holdout 为单一强牛市 regime，对看涨因子的确认力本就有限",
    "块自助在拼接折边界处缝合不连续序列，p 值可能略乐观（沿用现有实现，已知局限）",
    "即使实验通过，结论上限：dev 嵌套验证通过、待 benchmark 影子前向终审（≥120 交易日、Tier≥4 触发 ≥20 次、前向 diff>0 才部署）",
]


def filter_lrs(lrs_dict, variant):
    """子集 = 仅删 factors 字典的 key。n_total/base_win_rate 原样保留（val==0 反面还原依赖它们）。"""
    spec = VARIANTS[variant]
    keep_bin = spec["binary"]
    factors = {}
    for k, v in lrs_dict["factors"].items():
        if k in CAL_KEYS:
            if spec["calendar"]:
                factors[k] = v
        elif keep_bin is None or k in keep_bin:
            factors[k] = v
    out = dict(lrs_dict)
    out["factors"] = factors
    return out


def block_bootstrap_auc(y, probs, block=HORIZON, B=2000, seed=42):
    """拼接 OOS 序列上 AUC 的循环块自助 95% CI。单类重采样轮次跳过并计数。"""
    y = np.asarray(y, dtype=int)
    probs = np.asarray(probs, dtype=float)
    n = len(y)
    if n == 0 or len(set(y)) < 2:
        return None
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    aucs, skipped = [], 0
    for _ in range(B):
        starts = rng.integers(0, n, n_blocks)
        idx = np.concatenate([(s + np.arange(block)) % n for s in starts])[:n]
        ys = y[idx]
        if len(set(ys)) < 2:
            skipped += 1
            continue
        aucs.append(roc_auc_score(ys, probs[idx]))
    point = float(roc_auc_score(y, probs))
    lo, hi = np.percentile(aucs, [2.5, 97.5])
    return {"auc": round(point, 4), "ci95": [round(float(lo), 4), round(float(hi), 4)],
            "n_boot": len(aucs), "n_skipped_single_class": skipped}


def _active_binary_factors(filtered_lrs, test_df):
    """该折该变体实际可能生效的二值因子数（在测试期可观测 = 至少一行非 NaN）"""
    n = 0
    for k in filtered_lrs["factors"]:
        if k in CAL_KEYS:
            continue
        if k in test_df.columns and test_df[k].notna().any():
            n += 1
    return n


def run_dev(df, folds, scope_label):
    """dev 折评估：返回每变体 {pooled, per_fold}。先于 holdout 执行并打印锁定。"""
    sorted_dates = df.sort_values("date")["date"].reset_index(drop=True)
    pools = {v: [] for v in VARIANTS}
    y_pool, fold_rows = [], []

    for (train_start, train_end, test_end) in folds:
        test = df[(df["year"] >= train_end) & (df["year"] < test_end)].copy()
        if len(test) < 50:
            continue
        test_start_pos = int(sorted_dates[sorted_dates == test["date"].min()].index[0])
        train = _purged_train(df, train_end, test_start_pos, sorted_dates)
        if len(train) < 200:
            continue
        lrs = learn_lrs(train)
        y = test["fwd_up_20d"].astype(int).values
        y_pool.append(y)

        row = {"fold": f"{train_end}-{test_end}", "n_test": int(len(test)),
               "base_rate": round(float(y.mean()), 4), "auc": {}, "n_active_binary": {}}
        for v in VARIANTS:
            flrs = filter_lrs(lrs, v)
            probs = test.apply(lambda r: score_row(r, flrs), axis=1).values
            pools[v].append(probs)
            row["auc"][v] = round(float(roc_auc_score(y, probs)), 4) if len(set(y)) > 1 else None
            row["n_active_binary"][v] = _active_binary_factors(flrs, test)
        fold_rows.append(row)

    y_cat = np.concatenate(y_pool)
    out = {"scope": scope_label, "folds": fold_rows, "n_pooled": int(len(y_cat)),
           "base_rate_pooled": round(float(y_cat.mean()), 4), "variants": {}}
    for v in VARIANTS:
        p_cat = np.concatenate(pools[v])
        bb_auc = block_bootstrap_auc(y_cat, p_cat)
        fold_aucs = [r["auc"][v] for r in fold_rows if r["auc"][v] is not None]
        sel = np.array([_tier(p) >= 4 for p in p_cat])
        out["variants"][v] = {
            "pooled_auc": bb_auc,
            "mean_fold_auc": round(float(np.mean(fold_aucs)), 4) if fold_aucs else None,
            "n_tier4": int(sel.sum()),
            "tier4_boot": block_bootstrap_diff(sel, y_cat, block=HORIZON),
        }
    return out


def run_holdout(df):
    """holdout 2024-2026：训练 = 全部 <2024（purged），评估一次。仅报告，不进决策。"""
    sorted_dates = df.sort_values("date")["date"].reset_index(drop=True)
    hold = df[df["year"] >= HOLDOUT_START].copy()
    if len(hold) < 50:
        return None
    test_start_pos = int(sorted_dates[sorted_dates == hold["date"].min()].index[0])
    train = _purged_train(df, HOLDOUT_START, test_start_pos, sorted_dates)
    lrs = learn_lrs(train)
    y = hold["fwd_up_20d"].astype(int).values

    out = {"period": "2024-2026", "n": int(len(hold)),
           "base_rate": round(float(y.mean()), 4),
           "role": "report-only（假设在此集上选出，无独立证据力）", "variants": {}}
    for v in VARIANTS:
        flrs = filter_lrs(lrs, v)
        probs = hold.apply(lambda r: score_row(r, flrs), axis=1).values
        sel = np.array([_tier(p) >= 4 for p in probs])
        out["variants"][v] = {
            "auc": round(float(roc_auc_score(y, probs)), 4) if len(set(y)) > 1 else None,
            "n_tier4": int(sel.sum()),
            "tier4_boot": block_bootstrap_diff(sel, y, block=HORIZON),  # n<10 → None（输出 null）
        }
    return out


def decide(primary):
    """预注册决策规则（rev2）：只看 dev 主口径的变体 A。"""
    a = primary["variants"]["v3_sparse"]
    b = primary["variants"]["calendar_only"]
    c = primary["variants"]["btc_only"]

    auc = a["pooled_auc"] or {}
    ci_lo = auc.get("ci95", [None])[0]
    cond1 = ci_lo is not None and ci_lo > 0.50
    gap = (abs(auc.get("auc", 0) - a["mean_fold_auc"])
           if a["mean_fold_auc"] is not None and auc else None)
    cond2 = gap is not None and gap <= 0.03
    t4 = a["tier4_boot"] or {}
    cond3 = bool(t4) and t4["diff"] > 0 and t4["p_boot"] < 0.05

    passed = cond1 and cond2 and cond3

    # 消融预注册解读
    a_auc = auc.get("auc")
    b_auc = (b["pooled_auc"] or {}).get("auc")
    c_auc = (c["pooled_auc"] or {}).get("auc")
    ablation = None
    if a_auc is not None and b_auc is not None and b_auc >= a_auc:
        ablation = "BTC 增量为零（calendar-only ≥ v3-sparse）——与尸检结论矛盾，触发复查，不进影子前向"
        passed = False
    elif a_auc is not None and ((b_auc is not None and a_auc < b_auc)
                                or (c_auc is not None and a_auc < c_auc)):
        ablation = "子集负交互（A 低于某消融对照），触发复查"
        passed = False

    return {
        "passed": bool(passed),
        "conditions": {
            "1_auc_ci_lower_gt_0.50": {"value": ci_lo, "pass": bool(cond1)},
            "2_pooled_vs_meanfold_gap_le_0.03": {"value": round(gap, 4) if gap is not None else None,
                                                 "pass": bool(cond2)},
            "3_tier4_diff_pos_p_lt_0.05": {"diff": t4.get("diff"), "p_boot": t4.get("p_boot"),
                                           "pass": bool(cond3)},
        },
        "ablation_flag": ablation,
        "action": ("进入 benchmark 影子前向追踪（不 bump MODEL_VERSION；前向 ≥120 交易日且 "
                   "Tier≥4 ≥20 次且 diff>0 才部署）" if passed
                   else "诚实零结果：现行模型不动，结果存档供研究面板展示"),
    }


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        o = o.item()
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return None
    return o


def run():
    df = build_feature_df()

    print("\n=== v3.0 稀疏模型嵌套验证（计划 rev2，dev 先锁定，holdout 仅报告）===")
    primary = run_dev(df, PRIMARY_FOLDS, "primary: 4 folds 2016-2024 (BTC fully observable)")
    secondary = run_dev(df, DEV_FOLDS, "secondary: all 6 folds 2012-2024")

    print(f"\n-- 主口径（拼接 n={primary['n_pooled']}，基率 {primary['base_rate_pooled']:.1%}）--")
    print(f"{'变体':<16}{'pooled AUC':>12}{'CI95':>18}{'mean-fold':>11}{'T4 diff':>9}{'p_boot':>8}")
    for v, r in primary["variants"].items():
        bb, t4 = r["pooled_auc"] or {}, r["tier4_boot"] or {}
        ci = bb.get("ci95", ["—", "—"])
        print(f"  {v:<14}{bb.get('auc', '—'):>12}{str(ci):>18}{r['mean_fold_auc']:>11}"
              f"{t4.get('diff', '—'):>9}{t4.get('p_boot', '—'):>8}")

    decision = decide(primary)
    print(f"\n-- 预注册决策（dev 主口径锁定后才算 holdout）--")
    for k, c in decision["conditions"].items():
        print(f"  {k}: {c} ")
    if decision["ablation_flag"]:
        print(f"  消融: {decision['ablation_flag']}")
    print(f"  => {'PASS' if decision['passed'] else 'FAIL'} · {decision['action']}")

    holdout = run_holdout(df)
    if holdout:
        print(f"\n-- holdout 2024-2026（仅报告，n={holdout['n']}，基率 {holdout['base_rate']:.1%}）--")
        for v, r in holdout["variants"].items():
            print(f"  {v:<14} AUC={r['auc']}  Tier≥4 n={r['n_tier4']}  boot={r['tier4_boot']}")

    out = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "plan": "docs_internal/V3_SPARSE_PLAN.md (rev2, Opus-reviewed)",
        "hypothesis": "只用 BTC 20日动量 + 日历的稀疏模型，方向 AUC 能否过 0.5",
        "variants_spec": {v: spec for v, spec in VARIANTS.items()},
        "primary": primary,
        "secondary": secondary,
        "decision": decision,
        "holdout": holdout,
        "honesty": HONESTY,
    }
    path = PROC_DIR / "v3_sparse.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_clean(out), f, ensure_ascii=False, indent=2, allow_nan=False)
    print(f"\n[OK] 写入 {path}")
    return out


if __name__ == "__main__":
    run()
