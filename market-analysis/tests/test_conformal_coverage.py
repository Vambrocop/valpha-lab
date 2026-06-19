"""方法 E 保形预测——合成已知分布的【经验覆盖率 ≈ 名义】护栏（无网络）。

为什么再加一个文件（已有 test_conformal.py 的 test_coverage_near_nominal_iid）：
  原测试只在【单一 iid 正态、单一 seed】上断 0.85≤cov≤0.95，是"点检"。
  这里把覆盖正确性当**统计护栏**系统性地守：
    1) 多 seed 蒙特卡洛取平均覆盖 → 抹掉单 seed 抽样噪声，断言贴近 0.90/0.80（更小容差）；
    2) 跨分布（正态 / 厚尾 t / 偏态对数正态）都成立 → 保形是分布无关的，必须对厚尾/偏态也守住；
    3) 名义水平单调：80% 区间覆盖 < 90% 区间覆盖；
    4) 退化/小样本边界不崩（覆盖落在 [0,1]、字段齐全）。

split_conformal / nonoverlap_fwd_returns 是 numpy 数组上的纯函数，可独立调用，
不触网、不读数据文件、不跑全流水线 —— 无需重构即可测（与 conftest 把 scripts/ 入 path 一致）。
口径：split_conformal 用**时间序切**(旧70%校准、新30%测试)；本测试合成 iid/可交换样本，
故时间序切等价随机切，理论覆盖应≈名义；非平稳市场下经验覆盖<名义是真实信息（生产里如实呈现），
但合成 iid 下不该系统性偏离——这正是护栏要守的。
"""
import numpy as np

from conformal import nonoverlap_fwd_returns, split_conformal


# 单次抽样的覆盖在小 n_test 下方差不小；用足够大的 n + 多 seed 平均压噪声。
N_TOTAL = 6000          # cal=4200 / test=1800，test 够大使单次覆盖方差可控
N_TRIALS = 40           # 蒙特卡洛重复，取平均覆盖
ABS_TOL_MEAN = 0.02     # 平均覆盖对名义的容差（多 seed 平均后可收紧到 ±2pp）


def _mean_coverage(sampler, level, n_total=N_TOTAL, n_trials=N_TRIALS, base_seed=1000):
    """对给定分布采样器，跑 n_trials 次 split_conformal，返回平均经验覆盖。
    sampler(rng, n) -> 长度 n 的 1D 收益样本（视作非重叠窗口收益，已可交换）。"""
    covs = []
    for t in range(n_trials):
        rng = np.random.default_rng(base_seed + t)
        rets = sampler(rng, n_total)
        b = split_conformal(rets, levels=(level,), cal_frac=0.7)[0]
        assert b["empirical_coverage"] is not None
        covs.append(b["empirical_coverage"])
    return float(np.mean(covs))


# ── 三个已知分布的采样器（保形声称分布无关：厚尾/偏态都该守住覆盖）──
def _normal(rng, n):
    return rng.normal(0.001, 0.05, n)            # 略偏正(模拟股权溢价)，与方向无关


def _student_t(rng, n):
    return rng.standard_t(df=3, size=n) * 0.03   # df=3 厚尾，裸正态分位会失准、保形仍应≈名义


def _lognormal_shifted(rng, n):
    # 偏态：对数正态去均值 → 右偏、非对称，检验区间不依赖对称性
    x = rng.lognormal(mean=0.0, sigma=0.5, size=n)
    return (x - x.mean()) * 0.05


def test_coverage_near_nominal_90_normal():
    cov = _mean_coverage(_normal, 0.90)
    assert abs(cov - 0.90) <= ABS_TOL_MEAN, f"正态 90% 平均覆盖={cov:.3f}，偏离名义 0.90 超 {ABS_TOL_MEAN}"


def test_coverage_near_nominal_80_normal():
    cov = _mean_coverage(_normal, 0.80)
    assert abs(cov - 0.80) <= ABS_TOL_MEAN, f"正态 80% 平均覆盖={cov:.3f}，偏离名义 0.80 超 {ABS_TOL_MEAN}"


def test_coverage_near_nominal_90_heavy_tail():
    # 厚尾 t(df=3)：保形是分布无关的，覆盖仍应≈名义（这是保形相对参数法的卖点）
    cov = _mean_coverage(_student_t, 0.90)
    assert abs(cov - 0.90) <= ABS_TOL_MEAN, f"厚尾 t 90% 平均覆盖={cov:.3f}，偏离名义 0.90 超 {ABS_TOL_MEAN}"


def test_coverage_near_nominal_90_skewed():
    # 右偏对数正态：区间无需对称，覆盖仍应≈名义
    cov = _mean_coverage(_lognormal_shifted, 0.90)
    assert abs(cov - 0.90) <= ABS_TOL_MEAN, f"偏态 90% 平均覆盖={cov:.3f}，偏离名义 0.90 超 {ABS_TOL_MEAN}"


def test_higher_level_covers_more():
    # 名义水平单调：同一份数据上，90% 区间的经验覆盖应 ≥ 80% 区间（更宽 → 盖得更多）。
    cov90 = _mean_coverage(_normal, 0.90)
    cov80 = _mean_coverage(_normal, 0.80)
    assert cov90 >= cov80 - 1e-9, f"90% 覆盖({cov90:.3f}) 不应低于 80% 覆盖({cov80:.3f})"


def test_coverage_within_bounds_and_fields():
    # 单次调用的健壮性：覆盖落在 [0,1]，n_cal/n_test 切分正确，区间括住 0（无条件分布跨 0）。
    rng = np.random.default_rng(7)
    b = split_conformal(_normal(rng, 2000), levels=(0.90,), cal_frac=0.7)[0]
    assert 0.0 <= b["empirical_coverage"] <= 1.0
    assert b["n_cal"] == 1400 and b["n_test"] == 600
    assert b["lower_pct"] < 0 < b["upper_pct"]


def test_synthetic_end_to_end_through_window_builder():
    """端到端贴近生产路径：用 nonoverlap_fwd_returns 从合成【价格】造非重叠窗口收益，
    再过 split_conformal —— 守住窗口构造 + 区间逻辑联合的覆盖。
    几何布朗运动 → 对数收益 iid，非重叠 N 日窗口近似可交换，覆盖应≈名义。"""
    rng = np.random.default_rng(2024)
    n_days = 60000
    daily_log = rng.normal(0.0003, 0.01, n_days)        # iid 日对数收益
    px = 100.0 * np.exp(np.cumsum(daily_log))           # 合成价格路径
    rets = nonoverlap_fwd_returns(px, horizon=20)        # 非重叠 20 日窗口收益
    assert len(rets) > 1000                               # 窗口数够大，覆盖估计稳
    b = split_conformal(rets, levels=(0.90,), cal_frac=0.7)[0]
    assert abs(b["empirical_coverage"] - 0.90) <= 0.05, \
        f"端到端 90% 覆盖={b['empirical_coverage']:.3f}（单次抽样，容差放宽到 ±5pp）"
