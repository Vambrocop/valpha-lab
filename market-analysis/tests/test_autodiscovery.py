"""test_autodiscovery.py — v1.5 Phase 1b：两处性能向量化的「等价性」回归门（独立审 P1-a）。

把"提速不改结果"焊成自动门：若未来有人再优化、悄悄破坏了块索引或前向收益的等价性，
立刻失败。block_bootstrap 是 placebo/factor/walk_forward 的共享原语，错了会污染公开统计链。
纯数学等价、无数据依赖、快。

2026-07-04(#7 扩声明)：加仓位族(COT)/期权情绪族(P/C) 的 H-1 反退化(必须显式路由,不许静默落
p=1.0)、H-2 数组裁剪(裁到首个可判定状态)、H-3 防泄漏(改未来段不改过去 sel)、156份"报告"非天守门。
全部合成数据·monkeypatch 内部加载函数，不联网、不依赖真实 data/cot.csv|cboe_putcall.csv 的具体内容
（那两个文件的真实解析由 test_fetch_cot.py / test_fetch_putcall.py 单独覆盖）。
"""
import numpy as np
import pandas as pd
import pytest


def test_block_index_vectorization_equiv():
    # walk_forward.block_bootstrap_diff 的块索引向量化必须逐位 == 旧 Python 推导式
    rng = np.random.default_rng(0)
    for n, block in [(13958, 1), (6635, 5), (1000, 20), (500, 3), (300, 1)]:
        n_blocks = int(np.ceil(n / block))
        starts = rng.integers(0, n, n_blocks)
        old = np.concatenate([(s + np.arange(block)) % n for s in starts])[:n]
        new = ((starts[:, None] + np.arange(block)) % n).ravel()[:n]
        assert np.array_equal(old, new), (n, block)


def test_rebound_fwd_vectorization_equiv():
    # autodiscovery._rebound 的 cumsum 前向收益必须 == 旧 rolling().apply(np.prod)
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.012, 3000)
    for hold in (1, 5, 10):
        C = np.log1p(r).cumsum()
        fwd_vec = np.full(len(r), np.nan)
        m = len(r) - hold
        fwd_vec[:m] = np.expm1(C[hold:hold + m] - C[:m])
        s = pd.Series(r)
        fwd_old = ((1 + s).rolling(hold).apply(np.prod, raw=True).shift(-hold) - 1).values
        mask = ~np.isnan(fwd_old)
        assert np.allclose(fwd_vec[mask], fwd_old[mask], atol=1e-10), hold
        # 尾部 hold 个应为 NaN（无前向窗口）
        assert np.all(np.isnan(fwd_vec[m:]))


# ══════════════════════════════════════════════════════════════════════════
# 仓位族(COT)/期权情绪族(P/C) — #7 2026-07-04 扩声明：H-1反退化 / H-2数组裁剪 / H-3防泄漏 / 156周频守门
# ══════════════════════════════════════════════════════════════════════════
def _synthetic_reports(n=250, start="2000-01-04", seed=0):
    """合成 COT 报告级数据：n 份周频报告(report_date 每 7 天一份)，usable_from=report_date+6天。"""
    dates = pd.date_range(start, periods=n, freq="7D")
    usable = dates + pd.Timedelta(days=6)
    rng = np.random.default_rng(seed)
    values = rng.normal(0, 1, n)
    return pd.DataFrame({"report_date": dates, "usable_from": usable, "value": values})


def _synthetic_price(start="1998-01-01", end="2012-12-31", seed=1):
    idx = pd.date_range(start, end, freq="B")
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0003, 0.01, len(idx))
    px = 100 * np.cumprod(1 + rets)
    return pd.Series(px, index=idx)


# ── _rolling_pctrank：window 单位是"报告篇数"，绝非日历天(156周频守门的最底层单测)──
def test_rolling_pctrank_window_is_report_count():
    import autodiscovery as ad
    vals = np.arange(200, dtype=float)          # 严格递增，无并列 → 排名无歧义
    out = ad._rolling_pctrank(vals, window=156)
    assert np.all(np.isnan(out[:155]))          # 前 155 个暖机不足 → NaN
    assert not np.isnan(out[155])               # 第 156 个(index155)起可判
    assert out[155] == pytest.approx(100.0)     # 递增序列里，窗口内最后一个值必是窗口最大 → 100 分位


def test_positioning_window_is_156_reports_not_156_days(monkeypatch):
    """156 份"周频报告"滚动分位，绝非 156 个日历天——若误当成 156 天，暖机在两周内就结束。
    (fixture n=300：n=200 时暖机后仅 45 份可判报告→hi 状态 ~20 交易日 < 实现里正当的 30 天
    检验力守卫——那是守卫工作正常不是 bug，故造够数据而非放松守卫。)"""
    import autodiscovery as ad
    reports = _synthetic_reports(n=300)
    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: reports)
    monkeypatch.setattr(ad, "_daily_price", lambda index: _synthetic_price())
    arr = ad._positioning_arrays("sp500", "legacy_noncomm_pct_oi", "hi", 20)
    assert arr is not None
    idx, sel, y = arr
    span_days = (idx.min() - reports["report_date"].iloc[0]).days
    assert span_days > 500          # 156 份周报≈3年(>500天)，远超"156天"误判的量级


# ── H-2:数组裁到该 series 首个"可判定"状态生效的交易日(暖机/无报告段绝不当 False)──
def test_positioning_truncates_before_first_usable_state(monkeypatch):
    import autodiscovery as ad
    reports = _synthetic_reports(n=250)
    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: reports)
    monkeypatch.setattr(ad, "_daily_price", lambda index: _synthetic_price())
    arr = ad._positioning_arrays("sp500", "legacy_noncomm_pct_oi", "hi", 20)
    assert arr is not None
    idx, sel, y = arr
    first_valid_usable = pd.Timestamp(reports["usable_from"].iloc[ad._POS_WINDOW - 1])
    assert pd.Timestamp(idx.min()) >= first_valid_usable


# ── H-3:防泄漏守门——改动"未来"那份报告/未来那段 P/C 的值，绝不能改变过去日的 sel ──
def test_positioning_future_report_change_does_not_alter_past_sel(monkeypatch):
    import autodiscovery as ad
    n = 260
    rng = np.random.default_rng(3)
    base_vals = rng.normal(0, 1, n)

    def _reports_with_last(v_last):
        reports = _synthetic_reports(n=n)
        vals = base_vals.copy()
        vals[-1] = v_last
        reports = reports.assign(value=vals)
        return reports

    monkeypatch.setattr(ad, "_daily_price", lambda index: _synthetic_price())

    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: _reports_with_last(1000.0))
    arr_a = ad._positioning_arrays("sp500", "legacy_noncomm_pct_oi", "hi", 20)
    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: _reports_with_last(-1000.0))
    arr_b = ad._positioning_arrays("sp500", "legacy_noncomm_pct_oi", "hi", 20)
    assert arr_a is not None and arr_b is not None
    idx_a, sel_a, _ = arr_a
    idx_b, sel_b, _ = arr_b

    last_usable = pd.Timestamp(_reports_with_last(1000.0)["usable_from"].iloc[-1])
    mask_a, mask_b = idx_a < last_usable, idx_b < last_usable
    assert list(idx_a[mask_a]) == list(idx_b[mask_b])            # 未来段改动前，日期集合必须完全一致
    assert np.array_equal(sel_a[mask_a], sel_b[mask_b])          # 且逐日 sel 必须完全一致(零泄漏)


def _optsent_base_with_spikes(seed, n=1600, spike_val=2.5):
    """P/C 合成基础序列：噪声 + **过去段**确定性尖峰(index 300..1500 每 25 天一个 ≈ 49 个 hi 极端日)。
    尖峰必须放在过去段——否则 hi 极端日几乎全靠"未来段"贡献,一改未来段整个候选就跌破 30 天检验力
    守卫返回 None(守卫按整段样本量拒绝、不改任何过去 sel,是正当行为非泄漏,但会让本测试测不到点时间)。"""
    idx_all = pd.date_range("2006-11-01", periods=n, freq="B")
    rng = np.random.default_rng(seed)
    base = rng.normal(0.9, 0.15, n)
    base[300:1500:25] = spike_val               # 过去段尖峰(全部早于末尾 50 天)
    return idx_all, base


def test_optsent_future_change_does_not_alter_past_sel(monkeypatch):
    import autodiscovery as ad
    idx_all, base = _optsent_base_with_spikes(seed=4)

    def _putcall_with_tail(tail_val):
        vals = base.copy()
        vals[-50:] = tail_val                   # 两版都是合法 P/C 值(非 NaN/负数),只测点时间不测守卫
        return pd.DataFrame({"total_pc": vals, "equity_pc": vals}, index=idx_all)

    monkeypatch.setattr(ad, "_daily_price", lambda index: _synthetic_price(start="2006-01-01", end="2015-12-31"))

    monkeypatch.setattr(ad, "_putcall_daily", lambda: _putcall_with_tail(2.0))   # 版本A:尾段偏高
    arr_a = ad._optsent_arrays("total_pc", "hi", 10)
    monkeypatch.setattr(ad, "_putcall_daily", lambda: _putcall_with_tail(0.9))   # 版本B:尾段中性
    arr_b = ad._optsent_arrays("total_pc", "hi", 10)
    assert arr_a is not None and arr_b is not None
    idx_a, sel_a, _ = arr_a
    idx_b, sel_b, _ = arr_b

    cutoff = idx_all[-50]
    mask_a, mask_b = idx_a < cutoff, idx_b < cutoff
    assert list(idx_a[mask_a]) == list(idx_b[mask_b])
    assert np.array_equal(sel_a[mask_a], sel_b[mask_b])


# ── H-1 反退化：compute_results 必须显式路由两新族到真统计，绝不静默落 fac.get(None)→p=1.0 ──
def test_compute_results_routes_positioning_not_silent_fallback(monkeypatch):
    import autodiscovery as ad
    reports = _synthetic_reports(n=260)
    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: reports)
    monkeypatch.setattr(ad, "_daily_price", lambda index: _synthetic_price())
    cand = {"candidate_id": "pos_test", "key": "test_key", "family": "positioning",
            "params": {"market": "sp500", "series": "legacy_noncomm_pct_oi", "extreme": "hi", "hold": 20}}
    results = ad.compute_results([cand])
    r = results[0]
    # 静默落 else 分支的话会是 {"p":1.0,"recent_p":None,"recent_powered":False}（无 windows/effect 字段）
    assert "windows" in r and "effect" in r
    assert r["effect"] == "仓位极端状态下未来持有期上涨率 vs 基率"
    assert r["p"] != 1.0


def test_compute_results_routes_optsent_not_silent_fallback(monkeypatch):
    """H-1:optsent 显式路由 + 真 p。fixture 造【真效应】：尖峰日(hi 极端)后 10 天注入正漂移
    → sel 日前向上涨率≈1 vs 基率≈0.5 → p 必然很小(而非指望噪声碰巧 p≠1.0)。"""
    import autodiscovery as ad
    idx_all, vals = _optsent_base_with_spikes(seed=5)
    df = pd.DataFrame({"total_pc": vals, "equity_pc": vals}, index=idx_all)

    # 价格与 P/C 同索引：默认小噪声收益；每个尖峰日后 10 天 +1%/天(真效应,非碰运气)
    rng = np.random.default_rng(6)
    rets = rng.normal(0.0, 0.004, len(idx_all))
    for i in range(300, 1500, 25):
        rets[i + 1: i + 11] += 0.01
    px = pd.Series(100 * np.cumprod(1 + rets), index=idx_all)

    monkeypatch.setattr(ad, "_putcall_daily", lambda: df)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    cand = {"candidate_id": "opt_test", "key": "test_key", "family": "options_sentiment",
            "params": {"series": "total_pc", "extreme": "hi", "hold": 10}}
    results = ad.compute_results([cand])
    r = results[0]
    assert "windows" in r and "effect" in r
    assert r["effect"] == "期权情绪极端状态下未来持有期上涨率 vs 基率"
    assert r["p"] != 1.0
    assert r["p"] < 0.10                    # 真效应必须被测出(路由+统计链端到端)


def test_compute_results_unrouted_family_raises():
    """H-1 反退化的防御端：未知 family 必须炸,不许静默落 p=1.0（防未来再漏接一族）。"""
    import autodiscovery as ad
    cand = {"candidate_id": "x", "key": "x", "family": "totally_unknown", "params": {}}
    with pytest.raises(ValueError):
        ad.compute_results([cand])


def test_arrays_exclude_days_without_realized_forward_window(monkeypatch):
    """审④阻断修回归锁(合成版·CI 恒跑):数组最后一天必须早于最后价格日至少 hold 个交易日——
    尾部"前向窗未实现"的日子绝不许以 y=0(捏造下跌)进数组(修正前正是这样,
    系统性压制'当前正处极端态'的活信号,翻转过 legacy_lo_h60_nasdaq100 公开头条)。
    价格序列刻意在最后报告后不足 hold 日就截止 → 不裁剪的话尾部必混入未实现窗。"""
    import autodiscovery as ad
    hold = 20
    # positioning:最后 usable_from≈2004-12-27,价格 2005-01-08 截止(仅 ~8 交易日 < hold)
    reports = _synthetic_reports(n=260)
    px_short = _synthetic_price(start="1998-01-01", end="2005-01-08")
    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: reports)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px_short)
    arr = ad._positioning_arrays("sp500", "legacy_noncomm_pct_oi", "hi", hold)
    assert arr is not None
    idx, sel, y = arr
    pos = px_short.index.get_indexer([idx.max()])[0]
    assert pos + hold <= len(px_short.index) - 1, (
        f"positioning: idx.max()={idx.max().date()} 距最后价格日不足 {hold} 交易日——尾部未实现前向窗混入")
    assert not np.isnan(y).any()

    # optsent:P/C 与价格同索引同截止 → 最后 hold 天必须被裁掉
    idx_all, vals = _optsent_base_with_spikes(seed=7)
    df = pd.DataFrame({"total_pc": vals, "equity_pc": vals}, index=idx_all)
    rng = np.random.default_rng(8)
    px = pd.Series(100 * np.cumprod(1 + rng.normal(0.0003, 0.008, len(idx_all))), index=idx_all)
    monkeypatch.setattr(ad, "_putcall_daily", lambda: df)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    arr = ad._optsent_arrays("total_pc", "hi", hold)
    assert arr is not None
    idx, sel, y = arr
    pos = px.index.get_indexer([idx.max()])[0]
    assert pos + hold <= len(px.index) - 1, (
        f"optsent: idx.max()={idx.max().date()} 距最后价格日不足 {hold} 交易日——尾部未实现前向窗混入")
    assert not np.isnan(y).any()


def test_arrays_exclude_days_without_realized_forward_window_real_data():
    """同一锁的真数据集成版。CI 干净检出无 data/raw/ 价格(gitignore 生成数据) → skip——
    门禁测试不依赖 gitignore 数据是铁律(2026-07-07 CI #100-104 连挂教训),合成版已恒跑同一性质。"""
    import autodiscovery as ad
    if ad._daily_price("sp500") is None or ad._daily_price("nasdaq") is None:
        pytest.skip("data/raw/ 价格缺失(CI 干净检出)——合成版已覆盖本锁")
    for maker, args, hold in [
        (ad._positioning_arrays, ("sp500", "legacy_noncomm_pct_oi", "lo", 60), 60),
        (ad._positioning_arrays, ("nasdaq100", "legacy_noncomm_pct_oi", "lo", 20), 20),
        (ad._optsent_arrays, ("total_pc", "hi", 20), 20),
    ]:
        arr = maker(*args)
        assert arr is not None, f"{args} 真数据下不应返回 None"
        idx, sel, y = arr
        px = ad._daily_price("sp500" if args[0] == "sp500" or maker is ad._optsent_arrays else "nasdaq")
        last_price_day = px.index.max()
        # idx 最后一天 + hold 个交易日必须 <= 最后价格日(即该日的前向窗已完整实现)
        pos = px.index.get_indexer([idx.max()])[0]
        assert pos + hold <= len(px.index) - 1, (
            f"{args}: idx.max()={idx.max().date()} 距最后价格日不足 {hold} 交易日——尾部未实现前向窗混入")
        assert not np.isnan(y).any()
