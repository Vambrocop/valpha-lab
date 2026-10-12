"""F2：状态型 sel 的 block 放大（regime / rebound / factor 三族补上项目自己的 H-3）。

## 项目自己立的规矩，三族一直没照办

`autodiscovery` 早在 2026-07-04 就写明：「状态型 sel（可连续多周）→
block = hold + EXTRA，**绝不 block=hold**」。positioning（+51）与 trailing_extreme（+77）
照办了，而：

  · `regime` 是**全系统最状态型的一族** —— 金叉/均线上方可以连续成立上千天
    （实测 sel 连续段长 p90 = 661、最长段 1020），用的却是 block = hold = 20，**欠块 33 倍**；
  · `factor` 段长 p90 = 143（`BTC_above_ma200` 143、`NASDAQ_above_ma200` 136），
    用 block = HORIZON = 20，**欠块 7 倍**；
  · `rebound` 段长 p90 = 2，欠得不多，但口径要一致。

## 为什么这几条测试必须存在

F2 把 `golden_cross_sp500` 的现代窗 p 从 .0250 推到 .1869（**越过 q=0.10 存活线**），
而改动前**全量 1084 条测试没有一条会因此变红** —— 三族的 block 从来没被钉住过。
positioning/trailing 有 `test_trailing_extreme_oos_block_matches_discovery` 这类守门，
这三族没有。这就是本文件补的洞。

**discovery 与 OOS 两处必须同一公式、同一常量** —— 不一致 = 同一效应两套显著性口径。

hermetic：只读常量与函数签名，不联网、不跑统计。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import autodiscovery as ad          # noqa: E402
import factor_pruning as fp         # noqa: E402
import oos_gate as og               # noqa: E402
from walk_forward import HORIZON    # noqa: E402


# ── 常量本身（实测锁定；改动要连 tools/block_calibration.py --runlengths 一起改）──

@pytest.mark.parametrize("name,got,want", [
    ("REGIME_BLOCK_EXTRA", ad.REGIME_BLOCK_EXTRA, 661),
    ("REBOUND_BLOCK_EXTRA", ad.REBOUND_BLOCK_EXTRA, 2),
    ("FACTOR_BLOCK_EXTRA", fp.FACTOR_BLOCK_EXTRA, 144),
])
def test_extra_constants_are_the_measured_values(name, got, want):
    """段长 p90 的 ceil。可复现：py tools/block_calibration.py --runlengths"""
    assert got == want, (
        f"{name} 从 {want} 改成了 {got}。这是实测常量(全族 sel 连续段长 p90 的最大值 ceil)，"
        "不是可调参数 —— 若数据变长要重测，请跑 tools/block_calibration.py --runlengths 并"
        "在提交里贴出新的测量表")


def test_amplification_is_real_not_a_no_op():
    """反退化：EXTRA 必须真的 > 0，否则下面所有断言都测不出命门。"""
    assert ad._regime_block(20) > 20
    assert ad._rebound_block(5) > 5
    assert fp.factor_block() > HORIZON


@pytest.mark.parametrize("hold", [1, 5, 20, 63])
def test_block_formulas_are_hold_plus_extra(hold):
    assert ad._regime_block(hold) == hold + ad.REGIME_BLOCK_EXTRA
    assert ad._rebound_block(hold) == hold + ad.REBOUND_BLOCK_EXTRA
    assert fp.factor_block(hold) == hold + fp.FACTOR_BLOCK_EXTRA


# ── 命门：discovery 与 OOS 同一 block（不一致 = 同一效应两套口径）──────────────

def _spy(monkeypatch, mod):
    seen = []
    orig = mod.block_bootstrap_diff

    def spy(sel, y, block=20, **kw):
        seen.append(int(block))
        return orig(sel, y, block=block, **kw)

    monkeypatch.setattr(mod, "block_bootstrap_diff", spy)
    return seen


def _spy_diff_oos(monkeypatch):
    """窥探 `_diff_oos` 收到的 block 实参。

    **不能**窥探 `block_bootstrap_diff`：放大之后体制族需要 10×681=6810 个锚后观测，
    任何现实锚点都会先被 `_diff_oos` 的块数门拦下 → 自助根本不会被调用，
    那样的断言会变成"没调到"而不是"口径不一致"。要钉的契约是**传下去的 block**。
    """
    seen = []
    orig = og._diff_oos

    def spy(cand, anchor, arr, *, block):
        seen.append(int(block))
        return orig(cand, anchor, arr, block=block)

    monkeypatch.setattr(og, "_diff_oos", spy)
    return seen


def test_regime_oos_block_matches_discovery(monkeypatch):
    """B1 命门：oos_gate 的体制族必须用 ad._regime_block，不是写死的 20。"""
    seen = _spy_diff_oos(monkeypatch)
    cand = {"candidate_id": "rg1", "key": "k", "family": "regime",
            "params": {"signal": "golden_cross", "index": "sp500"}}
    og._regime_oos(cand, "2001-01-01")
    assert seen == [ad._regime_block(20)], (
        f"OOS 用了 {seen}，discovery 用 {ad._regime_block(20)} —— 同一效应两套显著性口径")


def test_rebound_oos_block_matches_discovery(monkeypatch):
    seen = _spy_diff_oos(monkeypatch)
    hold = 5
    cand = {"candidate_id": "rb1", "key": "k", "family": "rebound",
            "params": {"pctl": 5, "hold": hold, "index": "sp500"}}
    og._rebound_oos(cand, "2001-01-01")
    assert seen == [ad._rebound_block(hold)], (
        f"OOS 用了 {seen}，discovery 用 {ad._rebound_block(hold)}")


# ── 命门：展示窗与裁决用同一 block（照 _positioning 的先例）────────────────────

# ⚠ 2026-10-13：下面两条原先直接调 `ad._regime(...)` / `ad._factor_map(...)`，
# 那要读 `data/raw/` —— 而 `data/raw` 在 **.gitignore** 里，CI 的干净检出没有它
# → arrays 为 None → `seen` 为空 → 断言失败。**把周一的刷新连干红两次**
# （pytest 门正确地拦住了发布，但红的是我的测试）。
# `autodiscovery.py` 里早写着这个坑：「CI 干净检出无 data/raw/，#104 连挂根因」，
# 而 memory 里也记着「门禁测试不能依赖 gitignore 生成数据」—— 我两条都没照。
# 改成**全合成数据**：要验的是"展示窗有没有拿到放大后的 block"，
# 跟真价格毫无关系，本来就不该依赖真数据。

def _synth_price(n=9000, seed=7):
    """造一条够长的价格序列：`_regime` 全段窗要 >= MIN_BLOCKS*681 = 6810 个观测，
    否则 `block_bootstrap_diff` 返回 None、`_regime` 在跑到展示窗之前就 return 了。"""
    idx = pd.date_range("1990-01-02", periods=n, freq="B")
    rng = np.random.default_rng(seed)
    # 带趋势漂移，保证 50/200 日均线有交叉（否则 sel 恒真/恒假、sel.sum()<10）
    drift = np.sin(np.arange(n) / 400.0) * 0.0012
    rets = drift + rng.normal(0, 0.009, n)
    return pd.Series(100 * np.cumprod(1 + rets), index=idx)


def test_regime_display_windows_use_the_same_amplified_block(monkeypatch):
    """展示窗若仍用 block=hold，同一条规律会出现两个不同的 p。

    `_positioning` 早就把放大后的 block 传给 `_diff_windows` —— 这是项目已有的先例，
    不是我新发明的取舍。
    """
    monkeypatch.setattr(ad, "_daily_price", lambda index: _synth_price())
    seen = _spy(monkeypatch, ad)
    r = ad._regime("golden_cross", "sp500", "cid")
    assert r is not None, "合成数据没让 _regime 跑完（夹具要调长/调参）"
    assert seen, "根本没跑到自助"
    assert set(seen) == {ad._regime_block(20)}, (
        f"体制族出现了不止一种 block：{sorted(set(seen))}（展示窗漏了放大？）")


def test_factor_display_windows_use_the_same_amplified_block(monkeypatch):
    """因子族同理 —— `_factor_map` 里的 `_diff_windows` 此前写死 fp.HORIZON。"""
    n = 3000                      # > MIN_BLOCKS * factor_block() = 1640
    rng = np.random.default_rng(3)
    col = "NASDAQ_above_ma200"
    df = pd.DataFrame({
        "date": pd.date_range("2005-01-03", periods=n, freq="B"),
        col: rng.integers(0, 2, n).astype(float),
        "fwd_up_20d": (rng.random(n) > 0.45).astype(float),
    })
    monkeypatch.setattr(ad, "build_feature_df", lambda: df)
    seen = []
    orig = ad._diff_windows

    def spy(idx, sel, y, block):
        seen.append(int(block))
        return orig(idx, sel, y, block)

    monkeypatch.setattr(ad, "_diff_windows", spy)
    ad._factor_map([{"candidate_id": "f1", "params": {"factor": col}}])
    assert seen, "因子展示窗没被调用"
    assert set(seen) == {fp.factor_block()}, (
        f"因子展示窗用了 {sorted(set(seen))}，裁决用 {fp.factor_block()}")


# ── 与 MIN_BLOCKS 的交互：放大之后检验力门必须跟着抬 ──────────────────────────

def test_recent_power_gate_is_block_aware():
    """F2 的隐患：放大到 164 之后，原来的 `len(rec) >= 200` 只够 2 块。

    2 块处纯噪声拒真率实测 0.298（名义 0.10）—— "样本够多"和"独立信息够多"
    在状态型 sel 上差 8 倍。门必须按 block 抬，否则 F2 反而制造出一批反保守的 recent_p。
    """
    from walk_forward import MIN_BLOCKS
    need = MIN_BLOCKS * fp.factor_block()
    assert need > 200, "常量变了,这条断言的前提要重看"
    import pandas as pd
    n = 400                                   # > 200 但 < need
    rec_dates = pd.date_range("2024-01-01", periods=n, freq="B")
    g = np.random.default_rng(0)
    df = pd.DataFrame({"date": list(rec_dates) * 2,
                       "fwd_up_20d": g.random(2 * n) > 0.5,
                       "f": g.integers(0, 2, 2 * n).astype(float)})
    seg = fp._segment_lens(df, "f", +1, pd.Timestamp("2024-01-01"))
    if seg is not None:                       # 全段块数够的话,现代段必须被门挡住
        assert seg["status"] == "现代检验力不足", seg["status"]
        assert seg["recent_p"] is None
        assert seg.get("recent_need_n") == need, "没报出还差多少样本"


def test_factor_pruning_horizon_is_not_a_second_source_of_truth():
    """`factor_pruning` 既拿 HORIZON 当前向窗口、又拿它当 block 的基数。

    它原本自己写死 `HORIZON = 20`，与 `walk_forward.HORIZON` 是两份真相 ——
    漂开就是「前向窗 20 天、块长按 25 天算」这种没人看得见的错配。
    """
    import walk_forward as wf2
    assert fp.HORIZON is wf2.HORIZON or fp.HORIZON == wf2.HORIZON, (
        f"factor_pruning.HORIZON={fp.HORIZON} != walk_forward.HORIZON={wf2.HORIZON}")
    assert fp.factor_block() == wf2.HORIZON + fp.FACTOR_BLOCK_EXTRA
