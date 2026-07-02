"""test_backtest.py — 贝叶斯信号回测(backtest.py) run_backtest() 聚合逻辑锁定测试。

合成数据·monkeypatch RAW_DIR 指向 tmp_path 写入的价格 CSV·不联网·不落盘真实 data/。

读了 market-analysis/scripts/backtest.py 的 run_backtest(daily, long_csv, label)：
  - daily: {date_str: {"prob":.., "tier":.., "month":..}}（同 signals.json 的 daily_signals 结构）
  - long_csv: RAW_DIR 下的长历史价格 CSV 文件名（单列，index_col=0 日期，squeeze 成 Series）
  - 输出 dict 含 baseline / by_tier / calibration_20d / tier4_strategy 等字段，
    这些字段被 build_signals.py 的 load_backtest() 直接嵌入已发布 signals.json
    （P0-1 "高度显著" 前端文案就读 by_tier/calibration_20d 的 significant 字段）。

本文件覆盖两类场景：
  (a) 三个「正常聚合」测试 —— 用已知构造的胜率分布验证 by_tier / calibration_20d /
      tier4_strategy 的计算不跑偏；
  (b) 两个「空输入/无重叠」的边界测试 —— 锁定 fail-closed 显式诊断：records=[] 时
      backtest.py 主动抛 ValueError("无重叠日期"...)，而不是深层 pandas 隐式 KeyError，
      让 run_all.py 的非零退出码带上可行动的诊断信息。细节见测试内注释。
"""
import math

import pandas as pd
import pytest

import backtest as bt

IDX = pd.bdate_range("2015-01-01", periods=400)
EXPECTED_1D_WIN = {1: 0.0, 2: 25.0, 3: 50.0, 4: 70.0, 5: 100.0}


def _write_price_csv(path, idx, prices, colname="NASDAQ_COMP"):
    pd.DataFrame({colname: prices}, index=idx).to_csv(path, index_label="Date")


def _planted_daily_signals():
    """5 档 × 20 天：tier k 的「次日涨跌」人为设定胜率 = (k-1)*5/20 → 0/25/50/75/100%。
    prob 按档递增（0.50→0.65），落进 calibration 5 个不同分桶各 n=20（>=20 门槛）。
    区块外（第 100~399 天）走温和正漂移，只为满足最长 30 日前向窗口取数不越界，不参与任何断言。
    """
    probmap = {1: 0.50, 2: 0.52, 3: 0.55, 4: 0.58, 5: 0.65}
    prices = [100.0]
    daily = {}
    for tier in range(1, 6):
        # 0,5,10,14,20——tier4 特设 70%(14/20)让其 1d p≈0.06 落进 (0.05,0.10) 判别带，
        # 使 significant 阈值 0.10 的漂移(尤其放松到 0.5)能被 test ② 的见证断言抓住(Fable 审)。
        wins = 14 if tier == 4 else (tier - 1) * 5
        for j in range(20):
            i = (tier - 1) * 20 + j
            up = j < wins
            prices.append(prices[-1] * (1.01 if up else 0.99))
            daily[IDX[i].strftime("%Y-%m-%d")] = {"prob": probmap[tier], "tier": tier, "month": 1}
    while len(prices) < len(IDX):
        prices.append(prices[-1] * 1.0005)
    return daily, prices[: len(IDX)]


@pytest.fixture
def planted(tmp_path, monkeypatch):
    daily, prices = _planted_daily_signals()
    monkeypatch.setattr(bt, "RAW_DIR", tmp_path)
    _write_price_csv(tmp_path / "TEST_long.csv", IDX, prices)
    return daily


# ── ① tier 分组胜率：合成已知分布 → 断言 by_tier 的 win_rate ────────────────
def test_by_tier_win_rate_matches_planted_distribution(planted):
    res = bt.run_backtest(planted, "TEST_long.csv", "TEST")
    by_tier = res["by_tier"]
    assert [row["tier"] for row in by_tier] == [1, 2, 3, 4, 5]
    for row in by_tier:
        assert row["n"] == 20
        assert row["horizons"]["1d"]["win_rate"] == EXPECTED_1D_WIN[row["tier"]]


# ── ② calibration 分桶结构 + significant 布尔与 p_value 一致 ────────────────
def test_significant_matches_p_value_threshold_everywhere(planted):
    """P0-1"高度显著"文案的后端锚：significant 必须严格等价于 p_value < 0.10，
    覆盖 by_tier 全部 5 档 x 5 horizon、calibration_20d 全部分桶、tier4_strategy。"""
    res = bt.run_backtest(planted, "TEST_long.csv", "TEST")
    checked = 0
    for row in res["by_tier"]:
        for h in row["horizons"].values():
            assert h["significant"] == (h["p_value"] < 0.10)
            checked += 1
    for row in res["calibration_20d"]:
        assert row["significant"] == (row["p_value"] < 0.10)
        checked += 1
    t4 = res["tier4_strategy"]
    assert t4["significant"] == (t4["p_value"] < 0.10)
    checked += 1
    assert checked == 5 * 5 + len(res["calibration_20d"]) + 1   # 防止未来误删断言导致漏检
    # 见证(Fable 审)：至少一个 cell 的 p 落在 (0.05,0.10) 判别带——否则 significant 阈值
    # 从 0.10 突变(含放松到 0.5)不会翻转任何 significant、上面的一致性断言会漏过。tier4=70% 提供该见证。
    all_p = ([h["p_value"] for row in res["by_tier"] for h in row["horizons"].values()]
             + [row["p_value"] for row in res["calibration_20d"]] + [res["tier4_strategy"]["p_value"]])
    assert any(0.05 <= p < 0.10 for p in all_p), "判别带 (0.05,0.10) 无见证 → significant 阈值突变测不出"


def test_calibration_bucket_structure(planted):
    res = bt.run_backtest(planted, "TEST_long.csv", "TEST")
    cal = res["calibration_20d"]
    known_labels = {"<51%", "51-54%", "54-57%", "57-60%", "60-63%", "63-70%", ">70%"}
    assert len(cal) == 5                                        # 5 档 prob 落进 5 个不同分桶
    for row in cal:
        assert row["bucket"] in known_labels
        assert row["n"] >= 20                                   # 门槛：n<20 的分桶不进列表
        assert set(row) == {"bucket", "prob_mid", "n", "actual_wr_20d",
                             "avg_ret_20d", "t_stat", "p_value", "significant"}


# ── ③ tier4_strategy 字段齐全 + diff ≈ win_rate − baseline ─────────────────
def test_tier4_strategy_fields_and_diff_consistency(planted):
    res = bt.run_backtest(planted, "TEST_long.csv", "TEST")
    t4 = res["tier4_strategy"]
    expected_keys = {"win_rate_20d", "baseline_win_rate", "diff", "n_days",
                      "p_value", "significant", "avg_return_20d", "baseline_avg_ret"}
    assert set(t4) == expected_keys
    assert t4["n_days"] == 40                                   # tier4(20) + tier5(20)
    # diff 用未取整原值算；win_rate_20d/baseline_win_rate 各自独立取整——两者相减
    # 与 diff 最多差 0.1+0.1=0.2（取整误差叠加），非精确相等
    assert abs(t4["diff"] - (t4["win_rate_20d"] - t4["baseline_win_rate"])) <= 0.2


# ── ④ 边界：样本不足（非空但很小）不崩 ──────────────────────────────────────
def test_tiny_nonzero_sample_no_crash(tmp_path, monkeypatch):
    """3 条信号、全 tier1（<15 门槛、无 tier>=4）：by_tier / calibration 全跳过，
    tier4_strategy 优雅退化成 NaN（不 raise）。下游 build_signals._clean() 会把
    NaN/Inf 转 null 再落盘 signals.json，所以这条路径对最终产物是安全的——
    与下面两个"空输入直接崩"的路径性质不同。"""
    idx = pd.bdate_range("2015-01-01", periods=400)
    prices = [100.0 + i * 0.1 for i in range(400)]
    monkeypatch.setattr(bt, "RAW_DIR", tmp_path)
    _write_price_csv(tmp_path / "TEST_long.csv", idx, prices)
    daily = {idx[i].strftime("%Y-%m-%d"): {"prob": 0.5, "tier": 1, "month": 1} for i in range(3)}

    res = bt.run_backtest(daily, "TEST_long.csv", "TEST")       # 不应抛异常
    assert res["by_tier"] == []
    assert res["calibration_20d"] == []
    assert res["tier4_strategy"]["n_days"] == 0
    assert math.isnan(res["tier4_strategy"]["win_rate_20d"])
    assert math.isnan(res["tier4_strategy"]["p_value"])


# ── 空输入 / 无重叠日期 → fail-closed 显式 ValueError（非隐式 KeyError）────────
def test_empty_daily_signals_raises_valueerror(tmp_path, monkeypatch):
    """daily={} 时 records=[] → backtest.py 主动 raise ValueError("无重叠日期"...)，
    而不是深层 pandas 栈里的隐式 KeyError。fail-closed 语义不变（该红仍红，
    run_all.py 逐步骤 subprocess 跑、非零退出码仍会 sys.exit(1) 终止整条流水线），
    只是把不可行动的 KeyError 换成可行动的诊断信息。"""
    idx = pd.bdate_range("2015-01-01", periods=400)
    prices = [100.0 + i * 0.1 for i in range(400)]
    monkeypatch.setattr(bt, "RAW_DIR", tmp_path)
    _write_price_csv(tmp_path / "TEST_long.csv", idx, prices)
    with pytest.raises(ValueError, match="无重叠日期"):
        bt.run_backtest({}, "TEST_long.csv", "TEST")


def test_no_overlapping_dates_also_raises_valueerror(tmp_path, monkeypatch):
    """同一诊断的第二条触发路径：daily 非空，但没有一天落在价格历史的日期范围内
    （ts not in sp_dates → continue，records 同样变成 []）——同样抛出
    ValueError("无重叠日期"...)。真实场景类比：长历史 CSV 更新滞后/格式错乱，
    导致其日期范围与当天 daily_signals 完全脱节。"""
    idx = pd.bdate_range("2015-01-01", periods=400)
    prices = [100.0 + i * 0.1 for i in range(400)]
    monkeypatch.setattr(bt, "RAW_DIR", tmp_path)
    _write_price_csv(tmp_path / "TEST_long.csv", idx, prices)
    daily = {"1990-01-01": {"prob": 0.5, "tier": 3, "month": 1}}   # 早于价格历史起点
    with pytest.raises(ValueError, match="无重叠日期"):
        bt.run_backtest(daily, "TEST_long.csv", "TEST")
