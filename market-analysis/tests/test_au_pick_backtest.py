"""test_au_pick_backtest.py — 澳股「同一规则零调参」回测（B3·SPEC_AU_PICKS §3 的 3/4/5/6/7/9/10 条）。

合成面板·不联网（raw/au 已 gitignore,CI 无真数据）。验的是**机制**:PIT 无前瞻、FMG 跨边界守门、
非重叠+锚定、S-2 次日入场、dropped 语义、S-6 披露机器门、N-4 两腿对齐。
"""
import json

import numpy as np
import pandas as pd

import au_pick_backtest as bt


# ── 合成面板工具 ──────────────────────────────────────────────────────────────
def _bidx(n, start="1990-01-01"):
    return pd.bdate_range(start=start, periods=n)


def _panel(n=400, k=10, seed=1, start="1990-01-01"):
    """k 只票、n 个交易日的正价面板（各票不同趋势斜率 + 轻噪声,保证可算动量/波动）。"""
    idx = _bidx(n, start)
    rng = np.random.default_rng(seed)
    data = {f"S{i}.AX": np.linspace(100, 100 + (i - k // 2) * 10, n) + rng.normal(0, 0.3, n)
            for i in range(k)}
    return pd.DataFrame(data, index=idx).clip(lower=1), idx


def _bench(idx, lo=100, hi=120):
    return pd.Series(np.linspace(lo, hi, len(idx)), index=idx, name="^AXJO")


# ── #3 PIT:未来暴涨不影响切片决策日的选择（零前瞻）──────────────────────────────
def test_pit_future_spike_does_not_change_selection():
    panel1, idx = _panel()
    bench = _bench(idx)
    days = bt._decision_days(panel1, bench)
    asof = days[len(days) // 2]
    pos = idx.get_indexer([asof])[0]
    # panel2 = panel1，仅在 asof 之后给 S0 灌 100× 暴涨（未来信息）
    panel2 = panel1.copy()
    col = panel2.columns.get_loc("S0.AX")
    panel2.iloc[pos + 1:, col] *= 100.0
    # 决策只看 asof 及之前 → 两面板切片逐字节同 → 选择必须完全一致
    assert bt._select_picks(panel1.loc[:asof]) == bt._select_picks(panel2.loc[:asof])
    # 非空测:确有未来差异存在（否则测试无意义）
    assert (panel2.loc[idx[pos + 1]:, "S0.AX"] != panel1.loc[idx[pos + 1]:, "S0.AX"]).any()


# ── #4 B-1 跨边界守门:截断后首个可选动量窗不含壳价（动量非天文数字）────────────────
def test_fmg_truncation_first_eligible_window_no_boundary_crossing():
    panel, idx = _panel(n=500, k=7, seed=4)
    cut_pos = 200
    cutoff = idx[cut_pos]
    # SHELL:截断前壳价 0.001，截断后真区 ~0.10（近乎持平）——跨边界则动量=0.10/0.001-1=9900%
    shell = np.empty(500)
    shell[:cut_pos] = 0.001
    rng = np.random.default_rng(44)
    shell[cut_pos:] = 0.10 + rng.normal(0, 0.0005, 500 - cut_pos)
    panel["SHELL.AX"] = shell
    panel.loc[panel.index < cutoff, "SHELL.AX"] = np.nan          # 宽表同款截断:前置 NaN
    bench = _bench(idx, hi=130)

    # 结构:截断前全 NaN、截断日起有值
    assert panel["SHELL.AX"].loc[:idx[cut_pos - 1]].isna().all()
    assert panel["SHELL.AX"].loc[cutoff:].notna().all()

    days = bt._decision_days(panel, bench)
    # 找首个 SHELL 可选（动量窗回看价非 NaN）的决策日
    elig = None
    for k, asof in enumerate(days):
        sub = panel.loc[:asof]
        lookback = sub["SHELL.AX"].iloc[-1 - bt.MOM_WIN]
        cur = sub["SHELL.AX"].iloc[-1]
        if pd.notna(lookback) and pd.notna(cur):
            elig = (k, asof, cur / lookback - 1.0, lookback)
            break
    assert elig is not None, "SHELL 应在窗全落真区后变为可选"
    k, asof, mom, lookback = elig
    assert abs(mom) < 5.0, f"首个可选窗动量 {mom:.1%} 应≈0(真区持平),绝非跨边界 9900%"
    assert lookback >= 0.05, "动量窗回看价须是真区价(~0.10),不含壳价(0.001)"
    # 前一决策日:窗仍跨边界 → 回看价落在 NaN 区 → 不可选
    if k > 0:
        prev = panel.loc[:days[k - 1]]
        assert pd.isna(prev["SHELL.AX"].iloc[-1 - bt.MOM_WIN])


# ── #5 非重叠 + 锚定:相邻决策日隔 HOLD_TD 交易日、首决策日=最早可行日、末端护栏 ───────
def test_decision_days_nonoverlap_anchor_and_endguard():
    panel, idx = _panel(n=400, k=8, seed=5)
    bench = _bench(idx)                       # 基准与面板同起点 → 锚点=动量窗就绪日 idx[MOM_WIN]
    days = bt._decision_days(panel, bench)
    assert len(days) >= 2
    assert days[0] == idx[bt.MOM_WIN]         # 首决策日=最早可行(≥MOM_WIN+1 行且基准已开市)
    pos = [idx.get_indexer([d])[0] for d in days]
    assert all(g == bt.HOLD_TD for g in np.diff(pos))   # 严格每 HOLD_TD 交易日一个(非重叠)
    # 末端护栏 S-7:最后一个决策日的出场落在面板内,再往后一个则越界
    assert pos[-1] + 1 + bt.HOLD_TD < len(idx)
    assert pos[-1] + bt.HOLD_TD + 1 + bt.HOLD_TD >= len(idx)


def test_anchor_waits_for_benchmark_start():
    # 基准比面板晚开市 → 锚点必须 ≥ 基准首日（结算腿需要基准）
    panel, idx = _panel(n=400, k=6, seed=15)
    bench_start = idx[bt.MOM_WIN + 40]
    bench = pd.Series(np.linspace(100, 120, len(idx) - (bt.MOM_WIN + 40)),
                      index=idx[bt.MOM_WIN + 40:], name="^AXJO")
    days = bt._decision_days(panel, bench)
    assert days[0] >= bench_start


# ── #6 S-2 入场纪律:入场=决策日次日(不抢跑)、出场=入场后满 HOLD_TD 交易日 ─────────────
def test_entry_is_next_trading_day_not_frontrun():
    panel, idx = _panel(n=400, k=10, seed=2)
    bench = _bench(idx, hi=130)
    days, records, _ = bt._backtest(panel, bench)
    settled = [r for r in records if r["status"] == "settled"]
    assert settled
    for r in settled:
        assert r["entry_date"] > r["asof"]                       # 严格晚于决策日(次日入场)
        pos = idx.get_indexer([r["asof"]])[0]
        assert r["entry_date"] == idx[pos + 1]                   # =次一个交易日
        assert r["exit_date"] == idx[pos + 1 + bt.HOLD_TD]       # 出场=入场后第 HOLD_TD 交易日


# ── #7 dropped 语义:窗内退市/缺价 → 丢弃计数、不入结算 ─────────────────────────────
def test_dropped_when_stock_delists_midwindow():
    panel, idx = _panel(n=400, k=8, seed=7)
    bench = _bench(idx, hi=130)
    days = bt._decision_days(panel, bench)
    asof = days[len(days) // 2]
    pos = idx.get_indexer([asof])[0]
    # DEAD:超强动量+零波动 → 必被选 看好；asof 后第 3 日起退市(NaN)——窗(20td)走不完
    panel["DEAD.AX"] = np.linspace(10, 1000, 400)
    panel.loc[panel.index > idx[pos + 3], "DEAD.AX"] = np.nan
    days, records, _ = bt._backtest(panel, bench)
    dead_at_asof = [r for r in records if r["symbol"] == "DEAD.AX" and r["asof"] == asof]
    assert len(dead_at_asof) == 1
    assert dead_at_asof[0]["status"] == "dropped"               # 窗内退市 → 丢弃
    # 注意:DEAD 全程超强动量,退市前的早期决策日选中并完整结算是【正确】行为——
    # 只断言退市窗口重叠起(asof 及之后)不再有 settled(窗走不完→dropped;退市后动量算不出→不选)
    assert not any(r["symbol"] == "DEAD.AX" and r["status"] == "settled" and r["asof"] >= asof
                   for r in records)
    out = bt.run(write=False, panel=panel, bench=bench)
    assert out["overall"]["n_dropped"] >= 1
    # dropped 计入 n_calls 但不入 n_settled（计数正确）
    assert out["overall"]["n_calls"] == out["overall"]["n_settled"] + out["overall"]["n_dropped"]


# ── #9 S-6 披露机器门:meta 含 幸存者偏差/FMG 截断/股息口径 三声明关键字段 ──────────────
def test_meta_disclosure_machine_gate():
    panel, idx = _panel(n=400, k=10, seed=9)
    bench = _bench(idx)
    out = bt.run(write=False, panel=panel, bench=bench)
    meta = out["meta"]
    txt = json.dumps(meta, ensure_ascii=False)
    for kw in ["幸存者偏差", "FMG 截断", "股息口径"]:
        assert kw in txt, f"披露门缺关键字段: {kw}"
    assert len(meta["declarations"]) == 6                        # §2.1 五条 + 两腿日历(双审SHOULD-1)
    for key in ["survivorship", "dividend_basis", "non_independence", "phase_lock", "descriptive"]:
        assert key in meta["declarations"]
        assert meta["declarations"][key]["zh"] and meta["declarations"][key]["en"]
    assert meta["fmg_truncation"]["cutoff"] == bt.FMG_TRUE_START


# ── #10 N-4 两腿对齐:个股腿与基准腿 entry/exit 同一交易日 ──────────────────────────
def test_two_legs_entry_exit_aligned():
    panel, idx = _panel(n=400, k=10, seed=10)
    bench = _bench(idx, hi=150)
    days, records, _ = bt._backtest(panel, bench)
    settled = [r for r in records if r["status"] == "settled"]
    assert settled
    for r in settled:
        assert r["entry_date"] == r["bench_entry"]              # 入场同日
        assert r["exit_date"] == r["bench_exit"]                # 出场同日


def test_two_legs_divergent_calendars_disclosed():
    """双审 SHOULD-1:原 test#10 与面板共用同一 idx→永远测不出真实日历漂移(假信心)。
    此测构造【异历】bench(缺面板部分交易日,模拟 1990s 稀疏数据):两腿各按自身日历计 20td,
    出场日允许漂移——断言机制如实运行(各自第 20 交易日)且披露声明在 meta(机器守门)。"""
    panel, idx = _panel(n=400, k=10, seed=11)
    bench_idx = idx.delete(slice(30, None, 7))                   # 每 7 天抽掉 1 天 → 日历错位
    bench = pd.Series(np.linspace(100, 150, len(bench_idx)), index=bench_idx, name="^AXJO")
    days, records, _ = bt._backtest(panel, bench)
    settled = [r for r in records if r["status"] == "settled"]
    assert settled
    diverged = [r for r in settled if r["exit_date"] != r["bench_exit"]]
    assert diverged, "异历面板下应出现两腿出场日漂移(否则此测没测到目标)"
    for r in settled:                                            # 各腿仍是自身日历上的严格第 20 td
        bi = bench.index[bench.index > r["asof"]]
        assert r["bench_entry"] == bi[0] and r["bench_exit"] == bi[bt.HOLD_TD]
    out = bt.run(write=False, panel=panel, bench=bench)
    assert "leg_calendars" in out["meta"]["declarations"]        # 披露声明机器守门
