"""factor_pruning.py — P2-5 因子样本外尸检 + 高信噪比靶子探针

模型已被对决证明无方向性优势（AUC<0.5）。本脚本不是找 alpha，而是用严格方法
给每个因子做样本外尸检，并量化"换靶子"是否可行：

1. 防泄漏切分：development = <2024；holdout = 2024-2026（从未进过任何 walk-forward 折，
   是真正干净的终审集）。开发集内做 **purged + embargoed 扩窗 CV**（embargo=20 交易日，
   等于前向窗口长度——López de Prado：训练样本的标签窗口若与测试期重叠必须切掉）。

2. 因子记分卡：每个二值因子在拼接 OOS 测试折上的"触发日胜率 − 基率"，块自助 CI + 符号稳定性；
   再在 holdout 上确认方向不翻。裁决 KEEP / PRUNE(噪声) / PRUNE-HARMFUL(反向有害)。

3. 主观事件 LR（halving/gold_spike/oil_spike/election/ipo_boom）：无任何历史样本支撑，单独标注。

4. 靶子探针：同一套特征，预测"未来20日方向" vs "未来20日实现波动率高低"，比较 holdout AUC。
   方向≈0.45（不可测）；波动率因聚集效应应显著>0.5 → 数据支持把 ML 力气转向波动率/状态。

输出：data/processed/factor_pruning.json（由 build_signals 嵌入 signals.json 的 factor_audit，
仅供"研究"面板展示，不进信号链路——遵守 ROADMAP"不上深度学习进信号"红线）。
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from walk_forward import build_feature_df, BINARY_FEATURES, block_bootstrap_diff
import stats_util as su
from signal_model import build_design_matrix
from stats_util import benjamini_hochberg, benjamini_yekutieli   # DSR/反过拟合：多重检验校正(审计S5:统一来源)

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"

HORIZON = 20
RECENT_YEARS = 8       # 现代段透镜窗口：最近 N 年（用户 2026-06-19 定 A·最近8年）
EMBARGO = 20            # 交易日，=前向窗口，切掉跨界泄漏的训练样本
HOLDOUT_START = 2024    # 2024+ 从未进过任何折
FDR_Q = 0.10           # 多重检验校正阈值（与 p_boot 显著阈一致，单一来源避免漂移）
SUBJECTIVE_EVENT_LRS = ["halving", "gold_spike", "oil_spike", "election", "ipo_boom"]

# 每个因子在模型里的假设方向（+1 看涨/-1 看跌）。
# 裁决问的是"样本外表现是否与假设方向一致"，而非"是否预测上涨"——
# 看跌因子触发后胜率下降是正确行为，不是有害。
ASSUMED_DIR = {
    "NASDAQ_above_ma200": +1, "NASDAQ_mom20_pos": +1, "NASDAQ_mom20_neg": -1,
    "BTC_above_ma200": +1, "BTC_mom20_pos": +1, "BTC_mom20_neg": -1,
    "dxy_rising": -1, "dxy_falling": +1,
    "nasdaq_rsi_overbought": -1, "nasdaq_rsi_oversold": +1,
    "nasdaq_high_vol": -1, "nasdaq_low_vol": +1,
    "vix_backwardation": +1,   # 倒挂=恐慌，contrarian 看涨（历史倒挂后20日偏强）
    "overnight_mom_pos": +1, "overnight_mom_neg": -1,
}

# 与 walk_forward.FOLDS 一致的扩窗边界（训练起点固定 2000）
DEV_FOLDS = [(2000, 2012, 2014), (2000, 2014, 2016), (2000, 2016, 2018),
             (2000, 2018, 2020), (2000, 2020, 2022), (2000, 2022, 2024)]


def _forward_vol_20d():
    """从纳指长历史算每个交易日「未来20日已实现波动率」（日对数收益 std）"""
    s = pd.read_csv(RAW_DIR / "NASDAQ_COMP_long.csv", index_col=0, parse_dates=True).squeeze()
    s = s[s > 0].sort_index().dropna()
    r = np.log(s / s.shift(1))
    # 未来 HORIZON 天的收益 std：先反转算 rolling，再移回
    fwd = r.shift(-1).rolling(HORIZON).std().shift(-(HORIZON - 1))
    return fwd  # index=date


def _purged_train(df, train_end, test_start_pos, sorted_dates):
    """扩窗训练集，并 embargo 掉前向窗口跨入测试期的尾部样本"""
    train = df[df["year"] < train_end].copy()
    if not len(train):
        return train
    # 训练样本若其 [t, t+HORIZON] 触及测试期起点，则切掉（embargo）
    cutoff_pos = max(test_start_pos - EMBARGO, 0)
    cutoff_date = sorted_dates[cutoff_pos]
    return train[train["date"] < cutoff_date]


def factor_obs(df, col):
    """因子 col 的**可观测窗口** —— 单一真相源，凡是要算该因子基率的地方都必须过这里。

    命门：晚出现的因子(BTC 2014-10 起 / VIX 期限结构 2006-07 起 / MA200 有 200 日暖机)
    在自己出现之前该列是 NaN，而 `df[col] == 1` 对 NaN 求值为 **False**
    → 那些"因子当时还不存在"的日子会被算进**对照组**、压低基率、**放大因子边际**。
    实测(2026-09-16)：BTC 三因子的基率被压 62% vs 真实 66%，
    `BTC_mom20_pos` 的边际因此从 +8.7pp 被说成 +12.6pp(夸大 45%)，而它就在公开观察台上。

    此前项目里有三份拷贝的 `notna` 过滤 + 两处漏了，正是"同一效应两套口径"。
    抽成函数不是为了少打字，是为了让漏掉这一步在物理上更难发生。
    """
    return df[df[col].notna()]


def factor_arrays(df, col, *, min_obs=50, min_fires=30):
    """因子族的 (idx, sel, y) 三元组 —— 与其余各族 `_xxx_arrays` 同形，供展示窗与门4 共用。

    样本不足(与 `_segment_lens` 同一道门)或列不存在 → 返回 **None**，
    **绝不**返回空数组：空数组会让 `mean()` 出 NaN，下游 `_sign(nan)` 曾因此
    编出一个"看跌"方向号(见 oos_gate._sign 注释)。退化情形必须显式说"没有"。
    """
    if col not in df.columns:
        return None
    obs = factor_obs(df, col)
    sel = (obs[col] == 1).values
    if len(obs) < min_obs or int(sel.sum()) < min_fires:
        return None
    return (obs["date"], sel, obs["fwd_up_20d"].values.astype(float))


def _segment_lens(df, col, assumed, cutoff):
    """描述性「时间衰减透镜」——把 placebo 的「全样本 vs 现代段」口径推广到二值因子：
    对因子的 raw edge「触发胜率 − 基率」在 全观测段 vs 最近段(cutoff 后) 各算一次(块自助)。
    **与上方 OOS 裁决口径不同**：那是从未训练过的样本外严格裁决；这里只描述「原始边际随
    时间还在不在」(in-sample、方向门控、检验力不足则不下结论)——同 placebo 的诚实纪律。

    三态：现代仍有效 / 现代已淡(全段有边际、现代测不到→很可能被套利) / 现代检验力不足。
    """
    obs = factor_obs(df, col)                    # 单一真相源(别再就地写 notna，会漂)
    sel = (obs[col] == 1).values
    if len(obs) < 50 or int(sel.sum()) < 30:
        return None
    full = block_bootstrap_diff(sel, obs["fwd_up_20d"].values, block=HORIZON)
    full_sig = bool(full["p_boot"] < 0.10 and np.sign(full["diff"]) == assumed)

    rec = obs[obs["date"] >= cutoff]
    rsel = (rec[col] == 1).values
    nfire, nnon = int(rsel.sum()), int((~rsel).sum())
    seg = {"window_years": RECENT_YEARS, "recent_start": str(pd.Timestamp(cutoff).date()),
           "full_diff_pp": full["diff"], "full_p": full["p_boot"],
           # 原始 MC 计数(SPEC_MC_RESOLUTION Part A)：因子族的 p 直接进跨族 BY-FDR，
           # 而 FDR 的刀口落在「X=1 vs X=3」之间 → 判定所需的信息在 X 里、不在舍入后的 p 里
           "mc": su.mc_meta(full["mc_x"], full["n_used"], "bootstrap"), "mc_recent": None,
           "recent_n_obs": int(len(rec)), "recent_n_fires": nfire,
           "recent_diff_pp": None, "recent_p": None}
    # 检验力门(抄 placebo recent_min_group_n：现代段够样本才下结论，否则只标"样本不足")
    if len(rec) < 200 or nfire < 30 or nnon < 30:
        seg["status"] = "现代检验力不足"
        return seg
    rb = block_bootstrap_diff(rsel, rec["fwd_up_20d"].values, block=HORIZON)
    seg["recent_diff_pp"], seg["recent_p"] = rb["diff"], rb["p_boot"]
    seg["mc_recent"] = su.mc_meta(rb["mc_x"], rb["n_used"], "bootstrap")
    recent_sig = bool(rb["p_boot"] < 0.10 and np.sign(rb["diff"]) == assumed)
    if recent_sig:
        seg["status"] = "现代仍有效"
    elif full_sig:
        seg["status"] = "现代已淡"          # 全段有边际、现代测不到 → 很可能被套利
    else:
        seg["status"] = "两段均无显著边际"   # 本就没有原始边际(多数技术因子)
    return seg


def factor_scorecard(df):
    """每个二值因子在拼接 OOS 测试折上的尸检"""
    sorted_dates = df.sort_values("date")["date"].reset_index(drop=True)
    cutoff = df["date"].max() - pd.DateOffset(years=RECENT_YEARS)   # 现代段透镜起点
    test_pools, per_fold_sign = [], {c: [] for c, _ in BINARY_FEATURES}

    for (_, train_end, test_end) in DEV_FOLDS:
        test = df[(df["year"] >= train_end) & (df["year"] < test_end)].copy()
        if len(test) < 50:
            continue
        test_start_pos = int(sorted_dates[sorted_dates == test["date"].min()].index[0])
        train = _purged_train(df, train_end, test_start_pos, sorted_dates)
        if len(train) < 200:
            continue
        test_pools.append(test)
        for col, _ in BINARY_FEATURES:
            if col not in test.columns:
                continue
            # 2026-09-16：这里原本用 `base = test["fwd_up_20d"].mean()`(**整折**基率)去和
            # `test[test[col]==1]` 比。fire 侧是对的，但 base 侧把"因子当时还不存在"的
            # NaN 行算进了对照 → 逐折符号可能反，而它喂 sign_stable → 喂 factor_audit
            # 公开发布的 verdict。基率必须取在**该因子自己的可观测折**上。
            fold_obs = factor_obs(test, col)
            fire = fold_obs[fold_obs[col] == 1]["fwd_up_20d"]
            if len(fire) >= 10 and len(fold_obs):
                per_fold_sign[col].append(np.sign(fire.mean() - fold_obs["fwd_up_20d"].mean()))

    pool = pd.concat(test_pools, ignore_index=True).sort_values("date").reset_index(drop=True)
    holdout = df[df["year"] >= HOLDOUT_START]
    base_pool = float(pool["fwd_up_20d"].mean())
    base_hold = float(holdout["fwd_up_20d"].mean()) if len(holdout) else None

    rows = []
    for col, name in BINARY_FEATURES:
        if col not in pool.columns:
            continue
        # 只在因子可观测的行上算（否则 BTC 等晚出现的因子，pre-2015 NaN 行会污染基率）
        obs = factor_obs(pool, col)              # 单一真相源
        if len(obs) < 50 or (obs[col] == 1).sum() < 30:
            continue
        sel = (obs[col] == 1).values
        y = obs["fwd_up_20d"].values
        bb = block_bootstrap_diff(sel, y, block=HORIZON)   # diff(pp)/ci95/p_boot（已对齐可观测期）
        signs = [s for s in per_fold_sign[col] if s != 0]
        # 逐折符号一致比例：BTC 仅 2015+ 可观测，折数本就少，全一致才算稳
        n_signs = len(signs)
        agree_frac = (max(signs.count(1), signs.count(-1)) / n_signs) if n_signs else 0.0
        sign_stable = bool(agree_frac == 1.0 and n_signs >= 3)

        hold_diff = None
        if len(holdout):
            hobs = factor_obs(holdout, col)      # 单一真相源
            hsel = hobs[col] == 1
            if hsel.sum() >= 10 and len(hobs):
                hbase = float(hobs["fwd_up_20d"].mean())
                hold_diff = round(float(hobs[hsel]["fwd_up_20d"].mean() - hbase) * 100, 2)

        # 裁决：样本外表现是否与因子假设方向一致 + 跨折符号是否稳定。
        # 关键：sign_stable 进裁决——拼接显著但逐折符号翻转 = regime 依赖，不可外推（FRAGILE）。
        diff, p_boot = bb["diff"], bb["p_boot"]
        assumed = ASSUMED_DIR.get(col, +1)
        seg = _segment_lens(df, col, assumed, cutoff)   # 时间衰减透镜(描述性,口径异于OOS)
        agrees_dev = np.sign(diff) == assumed
        agrees_hold = hold_diff is None or np.sign(hold_diff) == assumed
        sig = p_boot < 0.10
        if sig and not agrees_dev:
            verdict = "MISLEADING"     # 显著但与假设相反 → 该翻向或剔除
        elif sig and agrees_dev and agrees_hold and sign_stable:
            verdict = "INFORMATIVE"    # 显著、方向一致、holdout 不翻、且跨折符号稳定 → 真稳健
        elif sig and agrees_dev and agrees_hold:
            verdict = "FRAGILE"        # 显著方向对但逐折符号翻转 → regime 依赖，不可外推
        else:
            verdict = "NOISE"          # 不显著 / holdout 翻向

        rows.append({
            "factor": col, "name": name, "assumed_dir": assumed,
            "fires_pct": round(float(sel.mean()) * 100, 1), "n_obs": int(len(obs)),
            # dev_diff_pp 是"触发胜率 − **该因子可观测期**基率"，而页面上那个 base_rate_dev
            # 是**全池**单一基率 → 两个数对不上(读者没法把 diff 还原)。把本因子自己的基率
            # 和可观测起点一并发出，口径才自洽；晚出现的因子(BTC 2014-10)差得最多。
            "dev_base_pct": round(float(obs["fwd_up_20d"].mean()) * 100, 2),
            "obs_start": str(pd.Timestamp(factor_obs(df, col)["date"].min()).date()),
            "dev_diff_pp": diff, "dev_ci95": bb["ci95"], "dev_p_boot": p_boot,
            "sign_stable": sign_stable, "n_folds_signed": n_signs,
            "sign_agree_frac": round(agree_frac, 2), "holdout_diff_pp": hold_diff,
            "verdict": verdict, "segment": seg,
        })
    order = {"INFORMATIVE": 0, "FRAGILE": 1, "MISLEADING": 2, "NOISE": 3}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), -abs(r["dev_diff_pp"])))
    return rows, base_pool, base_hold, len(pool), len(holdout)


def target_probe(df):
    """同特征下，方向 vs 波动率的 holdout 可预测性对比"""
    fwd_vol = _forward_vol_20d()
    df = df.copy()
    df["fwd_vol"] = df["date"].map(fwd_vol)
    df = df.dropna(subset=["fwd_vol"])

    dev = df[df["year"] < HOLDOUT_START]
    hold = df[df["year"] >= HOLDOUT_START]
    if len(dev) < 200 or len(hold) < 50:
        return None

    Xd, _ = build_design_matrix(dev); Xh, _ = build_design_matrix(hold)

    out = {}
    # 方向靶子
    yd = dev["fwd_up_20d"].astype(int).values; yh = hold["fwd_up_20d"].astype(int).values
    if len(set(yh)) > 1:
        m = LogisticRegression(C=1.0, solver="lbfgs", max_iter=2000).fit(Xd, yd)
        out["direction_auc_holdout"] = round(float(roc_auc_score(yh, m.predict_proba(Xh)[:, 1])), 4)
    # 波动率靶子：高于开发集中位数=1
    thr = dev["fwd_vol"].median()
    yd_v = (dev["fwd_vol"] > thr).astype(int).values
    yh_v = (hold["fwd_vol"] > thr).astype(int).values
    if len(set(yh_v)) > 1:
        mv = LogisticRegression(C=1.0, solver="lbfgs", max_iter=2000).fit(Xd, yd_v)
        out["vol_auc_holdout"] = round(float(roc_auc_score(yh_v, mv.predict_proba(Xh)[:, 1])), 4)
    # 拼接多 regime 的方向 AUC 从 walk_forward 对决读取（不硬编码，避免两处数字打架）
    pooled = None
    try:
        with open(PROC_DIR / "walk_forward_results.json", encoding="utf-8") as f:
            pooled = json.load(f).get("duel_summary", {}).get("naive", {}).get("auc_pooled")
    except Exception:
        pass
    out["direction_auc_pooled_2012_2024"] = pooled
    out["note"] = ("方向 AUC 跨 regime 剧烈摆动（拼接2012-2024≈%s，单一2024-2026≈%s）——"
                   "这种不稳定本身就是非平稳性的证据；holdout 是单一强牛市 regime，"
                   "对看涨因子的确认力有限。波动率因聚集效应可预测性更稳，AUC 高于方向，"
                   "印证应把 ML 力气投向波动率/市场状态而非涨跌方向（单点 holdout，仍需多 regime 复核）"
                   % (pooled, out.get("direction_auc_holdout")))
    out["n_holdout"] = int(len(hold))
    return out


def run():
    df = build_feature_df()
    rows, base_pool, base_hold, n_pool, n_hold = factor_scorecard(df)
    probe = target_probe(df)

    # ── 因子 deflation（Fable#1 落地 / Bailey&LdP 反过拟合）──────────────
    # 难点(独立审查)：这些因子互为补/同源(mom_pos↔neg、high/low_vol…)→负相关，BH 的
    # PRDS 假设不成立 → 以 BY(任意相关下有效,保守)为稳健 FDR 口径；另报 BH(乐观)与
    # "最佳因子"的 Bonferroni(FWER,回答'最佳因子是否 N 选 1 的运气')。
    # 显著性只认与假设方向一致者(dev_p_boot 两侧，反向显著=证据相反，不算"站得住")。
    pvec = [r["dev_p_boot"] for r in rows]
    q_bh = benjamini_hochberg(pvec) if rows else []
    q_by = benjamini_yekutieli(pvec) if rows else []
    for r, qb, qy in zip(rows, q_bh, q_by):
        agrees = bool(np.sign(r["dev_diff_pp"]) == r["assumed_dir"])
        r["q_value_bh"] = round(float(qb), 4)
        r["q_value_by"] = round(float(qy), 4)
        r["bh_significant"] = bool(agrees and qb < FDR_Q)        # 乐观(假设正相关)
        r["robust_significant"] = bool(agrees and qy < FDR_Q)    # 稳健(BY,任意相关)
    m = len(rows)
    best = min(rows, key=lambda r: r["dev_p_boot"]) if rows else None
    best_bonf = round(min(1.0, best["dev_p_boot"] * m), 4) if best else None
    n_raw_sig = int(sum((r["dev_p_boot"] < FDR_Q) and (np.sign(r["dev_diff_pp"]) == r["assumed_dir"]) for r in rows))
    n_bh_sig = int(sum(r["bh_significant"] for r in rows))
    n_by_sig = int(sum(r["robust_significant"] for r in rows))

    n_info = sum(r["verdict"] == "INFORMATIVE" for r in rows)
    n_frag = sum(r["verdict"] == "FRAGILE" for r in rows)
    n_mis  = sum(r["verdict"] == "MISLEADING" for r in rows)
    seg_alive = sum((r.get("segment") or {}).get("status") == "现代仍有效" for r in rows)
    seg_faded = sum((r.get("segment") or {}).get("status") == "现代已淡" for r in rows)
    seg_weak  = sum((r.get("segment") or {}).get("status") == "现代检验力不足" for r in rows)
    print(f"\n=== P2-5 因子尸检（OOS 拼接 n={n_pool}，holdout 2024+ n={n_hold}）===")
    print(f"{'因子':<26}{'假设':>5}{'触发%':>7}{'dev差pp':>9}{'p_boot':>8}{'符号稳':>7}{'holdout':>9}  裁决")
    for r in rows:
        hd = "—" if r["holdout_diff_pp"] is None else f"{r['holdout_diff_pp']:+.1f}"
        ad = "涨" if r["assumed_dir"] > 0 else "跌"
        ss = "稳" if r["sign_stable"] else "翻"
        print(f"  {r['factor']:<24}{ad:>5}{r['fires_pct']:>6.1f}{r['dev_diff_pp']:>+9.1f}"
              f"{r['dev_p_boot']:>8.3f}{ss:>7}{hd:>9}  {r['verdict']}")
    print(f"\n  INFORMATIVE={n_info}  FRAGILE={n_frag}  MISLEADING={n_mis}  NOISE={len(rows)-n_info-n_frag-n_mis}")
    print(f"  Deflation：{m} 因子(方向一致 p<{FDR_Q}={n_raw_sig}) → BY稳健留{n_by_sig}/BH乐观留{n_bh_sig}/最佳因子Bonferroni p={best_bonf}")
    print(f"  现代段透镜(最近{RECENT_YEARS}年)：仍有效{seg_alive} / 已淡{seg_faded} / 检验力不足{seg_weak}")
    print(f"  主观事件LR（无样本支撑，建议标注/移出）：{', '.join(SUBJECTIVE_EVENT_LRS)}")
    if probe:
        print(f"\n=== 靶子探针（holdout）===")
        print(f"  方向 AUC = {probe.get('direction_auc_holdout')}  |  "
              f"波动率 AUC = {probe.get('vol_auc_holdout')}")

    out = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "method": ("拼接测试折为样本外序列算胜率差（块自助 CI）；purged+embargo(20d) 扩窗用于"
                   "跨折符号稳定性检验；2024-2026 从未参与训练，做终审保留集"),
        "horizon_days": HORIZON, "embargo_days": EMBARGO,
        "dev_period": "2000-2023", "holdout_period": "2024-2026",
        "n_dev_oos": n_pool, "n_holdout": n_hold,
        "base_rate_dev": round(base_pool, 4),
        "base_rate_holdout": round(base_hold, 4) if base_hold else None,
        "factors": rows,
        "subjective_event_lrs": SUBJECTIVE_EVENT_LRS,
        "target_probe": probe,
        "summary": {"informative": n_info, "fragile": n_frag, "misleading": n_mis,
                    "noise": len(rows) - n_info - n_frag - n_mis},
        "segment_lens": {
            "window_years": RECENT_YEARS,
            "n_alive": seg_alive, "n_faded": seg_faded, "n_underpowered": seg_weak,
            "method": (f"描述性时间衰减透镜：因子 raw edge「触发胜率−基率」在 全观测段 vs 最近 {RECENT_YEARS} 年 "
                       "各算块自助；方向门控、现代段检验力不足(<200 样本或触发<30)则不下结论。"
                       "**口径异于上方 OOS 裁决**——这里是 in-sample 描述『原始边际是否随时间消失』，"
                       "非样本外严格裁决，同 placebo 的诚实分段。"),
            "note": "「现代已淡」=全段有边际、现代段测不到 → 很可能被套利；非『会失效』的预测，仅描述历史。",
        },
        "deflation": {
            "method": "对 N 个因子(方向一致者)做多重检验校正。因子互为补/同源→负相关，BH(PRDS)不适用→以 BY(任意相关,保守)为稳健口径，另报 BH(乐观)与最佳因子 Bonferroni(FWER)。数据挖掘校正，不预测方向。",
            "q_level": FDR_Q, "n_factors": m, "n_raw_dir_sig_p10": n_raw_sig,
            "n_bh_sig_q10": n_bh_sig, "n_by_sig_q10": n_by_sig,
            "best_factor": best["factor"] if best else None,
            "best_factor_bonferroni_p": best_bonf,
            "caveat": "p 为有限次(B=2000)块自助估计，阈值附近 q 本身不确定；两侧 p、显著性已按假设方向门控。",
            "note": (f"{m} 个因子里方向一致且原始 p<{FDR_Q} 有 {n_raw_sig} 个；依赖稳健校正后 "
                     f"BY(保守)留 {n_by_sig} 个、BH(乐观)留 {n_bh_sig} 个，最佳因子 Bonferroni(FWER) p={best_bonf}。"
                     f"即便留下的也 FRAGILE(逐折符号翻转)→ 无可稳健外推的因子 alpha。"),
        },
    }
    path = PROC_DIR / "factor_pruning.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(f"\n[OK] 写入 {path}")
    return out


if __name__ == "__main__":
    run()
