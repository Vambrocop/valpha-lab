"""test_build_valpha150.py — Valpha150 逐股指标（6月/1年涨幅、20日年化波动、距52周高）。

只测 compute_metrics 纯逻辑（合成价格序列，无网络/yfinance）。
为可测把原 main 循环体抽成 compute_metrics(p)，并把 yfinance 下载/文件写入
搬进 build_all()（仅 __main__ 调用），使 import 该模块不触网。行为不变。
"""
import numpy as np
import pandas as pd

from build_valpha150 import compute_metrics, MIN_HIST


def _series(values):
    """构造带工作日 DatetimeIndex 的收盘价序列。"""
    idx = pd.bdate_range("2024-01-01", periods=len(values))
    return pd.Series(values, index=idx, dtype="float64")


def test_too_short_history_returns_none():
    # 历史 < 130 天：返回 None（main 里会被记入 miss 跳过）
    p = _series([100.0] * (MIN_HIST - 1))
    assert compute_metrics(p) is None


def test_short_history_after_dropna_returns_none():
    # 表观够长但含 NaN，dropna 后不足 130 —— 仍判定为史短
    vals = [100.0] * (MIN_HIST - 1) + [np.nan] * 5
    p = _series(vals)
    assert compute_metrics(p) is None


def test_exactly_min_hist_is_computed():
    # 恰好 130 天：过史短门(>=130)；130>126 → c6 算得出(全100→0%)，但 130 不>252 → c1 仍 None
    p = _series([100.0] * MIN_HIST)
    m = compute_metrics(p)
    assert m is not None
    assert m["c6"] == 0.0     # len==130 > 126 → 算出来
    assert m["c1"] is None    # 不满足 >252


def test_flat_series_zero_change_zero_vol():
    # 完全平的 300 天序列：所有涨幅/波动/距高都应为 0
    p = _series([50.0] * 300)
    m = compute_metrics(p)
    assert m["p"] == 50.0
    assert m["c6"] == 0.0
    assert m["c1"] == 0.0
    assert m["v"] == 0.0
    assert m["fh"] == 0.0     # last == 52周最高，距高 0%


def test_six_month_and_one_year_change_handcomputed():
    # 300 天序列，精确放置参照点，手算 c6 / c1
    vals = [100.0] * 300
    n = len(vals)                # 300；p.iloc[-126] = 位置 n-126 = 174（非 299-126，off-by-one）
    vals[n - 126] = 80.0         # p.iloc[-126] = 80 → last/80-1 = +25%
    vals[n - 252] = 50.0         # p.iloc[-252] = 50 → last/50-1 = +100%
    p = _series(vals)            # last = 100.0
    m = compute_metrics(p)
    assert m["c6"] == 25.0       # (100/80 - 1)*100
    assert m["c1"] == 100.0      # (100/50 - 1)*100


def test_dist_from_52w_high_handcomputed():
    # 近 252 天里曾摸高 200，最后收 150 → 距高 = (150/200-1)*100 = -25%
    vals = [150.0] * 300
    vals[100] = 200.0            # 落在最后 252 天窗口内的最高点
    p = _series(vals)            # last = 150.0
    m = compute_metrics(p)
    assert m["fh"] == -25.0


def test_dist_from_high_excludes_old_peak_outside_window():
    # 极早的高点(在 tail(252) 窗口外)不应拉低距高读数
    vals = [120.0] * 300
    vals[0] = 999.0             # 第 0 天，落在 tail(252) 之外（300-252=48 之前）
    p = _series(vals)           # last = 120, 窗口内最高也是 120
    m = compute_metrics(p)
    assert m["fh"] == 0.0       # 老高点被正确排除


def test_volatility_annualization_handcomputed():
    # 构造已知日收益序列，独立手算 20日年化波动以抓回归
    # 让最后 21 个价格产生交替 +1% / -1% 的 20 个日收益
    n = 200
    vals = [100.0] * (n - 21)
    price = 100.0
    tail_prices = [price]
    for k in range(20):
        price = price * (1.01 if k % 2 == 0 else 1.0 / 1.01)
        tail_prices.append(price)
    vals += tail_prices  # 共 n 个点
    p = _series(vals[:n])
    m = compute_metrics(p)

    # 独立复算：最后 20 个日收益的样本标准差 * sqrt(252) * 100
    rets = pd.Series(tail_prices).pct_change().dropna().tail(20)
    expected = round(float(rets.std() * np.sqrt(252) * 100), 1)
    assert m["v"] == expected
    assert m["v"] > 0          # 有波动 → 非 0（不是平序列）


def test_metric_keys_are_stable_contract():
    # 返回 dict 的键集是前端契约，别悄悄改名/漏字段
    m = compute_metrics(_series([100.0] * 260))
    assert set(m) == {"p", "c6", "c1", "v", "fh"}
