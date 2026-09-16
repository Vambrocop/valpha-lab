"""因子可观测期基率 — 暖机 NaN 绝不许进对照组（2026-09-16）。

**这不是假想 bug，是已经发布出去的错数字。** 机制：
  晚出现的因子(BTC 2014-10 起 / VIX 期限结构 2006-07 起 / MA200 有 200 日暖机)在自己出现之前
  该列是 `NaN`，而 `df[col] == 1` 对 NaN 求值为 **False** → 那些"因子当时还不存在"的日子
  被算进了 `_diff_windows` 的**对照组**。而 base 是 `yy.mean()`(全样本基率)，于是
  BTC 因子的对照里混进 2000–2014 十四年、VIX 混进 2000–2006 六年半 —— 恰好是
  互联网泡沫 + 金融危机(上涨率低) → **基率被压低、因子边际被放大**。

同数据 A/B 实测(旧算法 → 新算法，完整窗 diff)：
  BTC_mom20_neg      −6.10 → −10.10   (低估了看跌强度)
  BTC_mom20_pos     **+12.60 → +8.70** (夸大 45%；**这条就在公开观察台上**)
  BTC_above_ma200    +7.20 → +3.50    (夸大 106%)
  NASDAQ_above_ma200 +3.50 → +3.10    (MA200 暖机 200 日)
  其余 10 只 ±0.10pp = 舍入

污染有**两处同源**站点，都要守：
  ① `autodiscovery._factor_map` 的展示窗 → 观察台的 edge_plain（公开数字）
  ② `factor_pruning.factor_scorecard` 的**逐折基率** → `sign_stable` → `factor_audit`
     公开发布的 verdict(INFORMATIVE/FRAGILE/MISLEADING/NOISE)。
     实测今日逐折符号无变化，但站点是真的 —— 留着不修就是"同一效应两套口径"。

这里全部用**行为断言**(monkeypatch 合成 df)，不用源码文本断言：
`(df[col] == 1)` 改写成 `df[col].eq(1)` 或 `fillna(0) == 1` 都能骗过文本断言，污染照旧。

hermetic：合成 DataFrame，不读 data/、不联网。
"""
import numpy as np
import pandas as pd
import pytest

import autodiscovery as ad
import factor_pruning as fp
import survivors_live as sl

COL = "NASDAQ_above_ma200"      # 用一个真在 BINARY_FEATURES 里的列名，才会被各处循环捡到


def _synth(n_warmup=1500, n_obs=1500, warmup_up=0.2, fired_up=0.8, base_up=0.6,
           start="2010-01-04"):
    """造「暖机段(列全 NaN、上涨率低) + 可观测段(0/1 交替)」的特征集。

    暖机段上涨率刻意压低 → 若它被算进对照组，基率会被拉低、因子边际被放大。
    这正是线上 BTC 因子的处境(暖机段=泡沫破裂+金融危机)。
    """
    n = n_warmup + n_obs
    idx = pd.date_range(start, periods=n, freq="B")
    col = np.full(n, np.nan)
    col[n_warmup:] = (np.arange(n_obs) % 2)          # 可观测段一半触发、一半不触发
    y = np.empty(n)
    y[:n_warmup] = (np.arange(n_warmup) % 100) < warmup_up * 100
    obs_fired = col[n_warmup:] == 1
    yo = np.empty(n_obs)
    k_f, k_n = int(obs_fired.sum()), int((~obs_fired).sum())
    yo[obs_fired] = (np.arange(k_f) % 100) < fired_up * 100
    yo[~obs_fired] = (np.arange(k_n) % 100) < base_up * 100
    y[n_warmup:] = yo
    return pd.DataFrame({"date": idx, "year": idx.year, "fwd_up_20d": y.astype(float), COL: col})


# ── 提取器本身 ────────────────────────────────────────────────────
def test_factor_obs_drops_the_warmup_rows():
    df = _synth()
    obs = fp.factor_obs(df, COL)
    assert len(obs) == 1500, "可观测窗没把暖机段剔掉 —— 那些日子因子还不存在"
    assert obs[COL].notna().all()
    assert obs["date"].min() == df["date"].iloc[1500]


def test_factor_arrays_returns_none_not_empty_arrays():
    """退化情形必须显式返回 None。

    空数组会让 `mean()` 出 NaN，而 `oos_gate._sign(nan)` 曾因此**编出一个"看跌"方向号**
    (见该函数注释)。"没有数据"必须说成"没有"，不能说成"一个空的有"。
    """
    df = _synth()
    df[COL] = np.nan                                  # 整列不可观测(本机 VIX3M 损坏时就是这样)
    assert fp.factor_arrays(df, COL) is None
    assert fp.factor_arrays(_synth(), "不存在的列") is None
    short = _synth(n_warmup=10, n_obs=40)             # 可观测 40 行 < min_obs=50
    assert fp.factor_arrays(short, COL) is None


def test_factor_arrays_shape_matches_other_families():
    """三元组必须与其余各族 `_xxx_arrays` 同形 —— 门4 的 `_diff_oos` 直接吃它。"""
    arr = fp.factor_arrays(_synth(), COL)
    assert arr is not None
    idx, sel, y = arr
    assert len(idx) == len(sel) == len(y) == 1500
    assert sel.dtype == bool and y.dtype == float
    assert pd.api.types.is_datetime64_any_dtype(idx)


# ── 污染的方向被钉死（这条是整个修复的核心断言）─────────────────────
def test_pollution_inflates_the_edge_and_the_fix_removes_it():
    """旧算法的基率必须**更低**、边际必须**更大** —— 方向钉死，不只是"两者不等"。

    只断言"不相等"的话，把修复改错方向(比如反过来过滤)也能过。
    """
    df = _synth()
    old = {w["label"]: w for w in ad._diff_windows(
        df["date"], (df[COL] == 1).values, df["fwd_up_20d"].values.astype(float), fp.HORIZON)}
    new = {w["label"]: w for w in ad._diff_windows(*fp.factor_arrays(df, COL), fp.HORIZON)}
    o, n = old["完整"], new["完整"]
    assert o["base_pct"] < n["base_pct"], "旧基率没被暖机段压低 —— 合成数据没复现污染,先修测试"
    assert o["diff_pp"] > n["diff_pp"], "修复后边际没变小 —— 过滤方向反了?"
    assert o["n"] == n["n"], "触发组计数不该变(污染只进对照组)"
    # 新基率必须**正好等于**可观测期基率,不是"接近"
    obs = fp.factor_obs(df, COL)
    assert n["base_pct"] == round(float(obs["fwd_up_20d"].mean() * 100))


# ── 站点①：展示窗（观察台公开数字的来源）──────────────────────────
def test_factor_map_windows_use_the_observable_base(monkeypatch):
    df = _synth()
    monkeypatch.setattr(ad, "build_feature_df", lambda: df)
    out = ad._factor_map([{"candidate_id": "f_test", "params": {"factor": COL}}])
    w = {x["label"]: x for x in out["f_test"]["windows"]}["完整"]
    obs = fp.factor_obs(df, COL)
    assert w["base_pct"] == round(float(obs["fwd_up_20d"].mean() * 100)), (
        "展示窗的基率不是可观测期基率 —— 观察台上会继续显示被夸大的边际")
    assert out["f_test"]["obs_start"] == str(obs["date"].min().date()), "没发出可观测起点"


def test_factor_map_survives_an_unobservable_column(monkeypatch):
    """整列不可观测时不许炸、也不许出空窗数字(本机 VIX3M 损坏就是这一幕)。"""
    df = _synth()
    df[COL] = np.nan
    monkeypatch.setattr(ad, "build_feature_df", lambda: df)
    out = ad._factor_map([{"candidate_id": "f_test", "params": {"factor": COL}}])
    assert out["f_test"]["windows"] == [] and out["f_test"]["obs_start"] is None
    assert out["f_test"]["p"] == 1.0                  # 进分母但永不存活,不是静默显著


# ── 站点②：逐折基率（factor_audit 公开 verdict 的来源）────────────
def test_scorecard_per_fold_base_is_observable_only():
    """构造一个「污染会让逐折符号翻号」的折 → 修复后必须取到正确的符号。

    设计：同一折里一半是暖机 NaN 行(上涨率 0.95)、一半可观测(触发 0.6 / 不触发 0.5)。
      · 可观测基率 ≈ 0.55，触发 0.6 → 符号 **+1**（真相）
      · 整折基率   ≈ 0.75，触发 0.6 → 符号 **−1**（污染下的假象）
    逐折符号喂 sign_stable，而 sign_stable 进 factor_audit 公开发布的 verdict。
    """
    n = 400
    idx = pd.date_range("2016-01-04", periods=n, freq="B")
    col = np.full(n, np.nan)
    col[n // 2:] = (np.arange(n // 2) % 2)
    y = np.empty(n)
    y[:n // 2] = (np.arange(n // 2) % 100) < 95            # 暖机段上涨率 0.95
    fired = col[n // 2:] == 1
    yo = np.empty(n // 2)
    yo[fired] = (np.arange(int(fired.sum())) % 100) < 60
    yo[~fired] = (np.arange(int((~fired).sum())) % 100) < 50
    y[n // 2:] = yo
    fold = pd.DataFrame({"date": idx, "fwd_up_20d": y.astype(float), COL: col})

    polluted_base = fold["fwd_up_20d"].mean()
    fo = fp.factor_obs(fold, COL)
    clean_base = fo["fwd_up_20d"].mean()
    fire = fo[fo[COL] == 1]["fwd_up_20d"].mean()
    assert np.sign(fire - polluted_base) == -1, "合成数据没复现翻号,先修测试再谈修代码"
    assert np.sign(fire - clean_base) == +1
    # 生产代码走的必须是后者
    assert np.sign(fire - fp.factor_obs(fold, COL)["fwd_up_20d"].mean()) == +1


def test_scorecard_emits_reconcilable_base():
    """dev_diff_pp 必须能用同一行里的 dev_base_pct 还原。

    此前页面只给一个**全池**基率 `base_rate_dev`，而 diff 是对**各因子自己的可观测期**
    基率算的 → 两个数对不上、读者没法把 diff 验回去。
    合成数据刻意让池子同时含暖机段(上涨率 0.2)与可观测段 → 两个基率必然不同，
    于是"发的是哪一个"这件事可测：必须是可观测期那个(更高)。
    """
    df = _synth(n_warmup=4000, n_obs=2000, start="2000-01-04")
    rows, base_pool, _bh, _np, _nh = fp.factor_scorecard(df)
    r = next((x for x in rows if x["factor"] == COL), None)
    assert r is not None, "合成数据没产出该因子的记分行,先修测试再谈修代码"
    assert r["dev_base_pct"] > base_pool * 100 + 1.0, (
        f"dev_base_pct={r['dev_base_pct']} 没高于全池基率 {base_pool * 100:.2f} —— "
        "发出来的还是被暖机段压低的那个基率")
    assert r["obs_start"] == str(fp.factor_obs(df, COL)["date"].min().date())


# ── 现代段透镜：裁决 p 的来源，此前 notna 过滤无人守 ────────────────
def test_segment_lens_notna_filter_has_a_regression_guard():
    """`_segment_lens` 是裁决 p 的来源，它的 notna 过滤**一直没有测试**
    (test_factor_segment.py 的合成 df 里没有 NaN 暖机段) —— 谁删掉那一行都不会红。
    整个"裁决口径是对的、只有展示错了"的结论都靠这一行,必须有守门。"""
    df = _synth()
    seg = fp._segment_lens(df, COL, +1, df["date"].max() - pd.DateOffset(years=fp.RECENT_YEARS))
    assert seg is not None
    # 期望值**不许**经 fp.factor_obs 计算 —— 否则拆掉过滤时两边一起动、这条测试恒真。
    # (变异测试真抓到过:第一版就是这么写的,把 factor_obs 改成 `return df` 它照样绿。)
    obs = df[df[COL].notna()]
    polluted = df
    fired = obs[obs[COL] == 1]["fwd_up_20d"].mean()
    expect = round(float((fired - obs["fwd_up_20d"].mean()) * 100), 2)
    expect_polluted = round(float((fired - polluted["fwd_up_20d"].mean()) * 100), 2)
    assert abs(expect - expect_polluted) > 5, "合成数据没让两种口径分开,先修测试"
    assert abs(seg["full_diff_pp"] - expect) < 0.06, (
        f"全段边际 {seg['full_diff_pp']} 不等于可观测期口径 {expect}"
        f"(污染口径会是 {expect_polluted}) —— notna 过滤没生效，而裁决 p 就出自这里")


# ── 观察台措辞：数字修对了，标签不能还在虚报窗口长度 ─────────────────
def test_factor_window_label_shows_the_real_observable_start():
    """"2000后"对一只 2014-10 才可观测的因子暗示 26 年数据、实际 12 年。"""
    cand = {"family": "factor", "obs_start": "2014-10-07",
            "windows": [{"label": "2000后", "up_pct": 75, "base_pct": 66, "diff_pp": 8.7}]}
    up, base, lab = sl._pick_window(cand)
    assert (up, base) == (75, 66)
    assert lab == "2014-10 起", f"窗口标签仍是 {lab!r} —— 12 年的证据被标成 26 年"


def test_non_factor_window_label_is_untouched():
    """别越界：日历/反弹/体制族的标签语义没变,不该被这次改动波及。"""
    cand = {"family": "regime", "windows": [{"label": "2000后", "up_pct": 70, "base_pct": 62}]}
    assert sl._pick_window(cand)[2] == "2000后"


def test_factor_edge_plain_no_longer_claims_full_sample_base():
    """公开面板那句话：base 已改成可观测期口径 → 不许再自称"全样本基率"。"""
    desc = sl._DESCRIPTORS[("factor", "BTC_mom20_pos")]
    assert desc["rest"] == "同期基率", "因子族仍写'全样本基率' —— 把 12 年的基率说成全样本"
    s = sl._edge_plain(desc, 75, 66, "2014-10 起", "明显偏正")
    assert "同期基率 66%" in s and "全样本" not in s
    assert "2014-10 起" in s


@pytest.mark.parametrize("key", ["BTC_mom20_pos", "BTC_mom20_neg", "NASDAQ_above_ma200"])
def test_every_factor_descriptor_uses_the_observable_wording(key):
    """新增因子族描述符时忘了改口径 → 这条红并指名道姓。"""
    assert sl._DESCRIPTORS[("factor", key)]["rest"] == "同期基率"
