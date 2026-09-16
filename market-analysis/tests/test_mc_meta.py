"""蒙特卡洛元数据 —— 存原始计数，别把估计器下限当精确值（SPEC_MC_RESOLUTION Part A / C1）。

## 为什么要存 (X, n) 而不是 p 或 SE

线上实测（`docs/autodiscovery.json`，2026-09-15）：跨族 BY-FDR 拒绝到 k=14，而

  · rank 1–5   自助 **0 次穿越 / 2000**
  · rank 6–13  置换 **0 次命中 / 1000**
  · rank 14    自助 **1 次穿越 / 2000** ← `golden_cross_sp500`，公开存活者
  · rank 15    自助 **3 次穿越 / 2000** ← 被判 dead

**FDR 的刀口落在「1 次穿越」与「3 次穿越」之间。** 在这个尺度上：
  · `p = 0.0000` 不是"极显著"，是"低于本估计器能报的最小值"
    —— X=0/B=2000 时双侧 p 的 95% 上界 ≈0.003，与那条 0.0030 的 dead **统计上分不开**；
  · 只存 p → 这件事被抹掉；
  · 只存 SE → 更糟：X=0 时 SE=0，会**编出"精确到 0"的假象**
    （同 `oos_gate._sign(nan)` 那次教训：退化情形必须显式说"没有"，不能编个 0）。

所以：**存 (X, n)，一切可导出**。

## 这批测试守什么

① `p` 必须能从 `(X, n)` **精确复原** —— 复原不了说明两者已经漂开，元数据就没意义了；
② `p_at_floor` 只看 `X == 0`，不看 p 被舍入成多少；
③ 分母必须是 `n_used`（=B−n_dropped）而不是 B；
④ **`mc=None`（根本没跑过统计）与 `mc_x=0`（跑了 n 次、一次都没穿过）绝不可混**
   —— 两者在产物里的含义完全不同，混掉就等于把"没测"说成"测了但极显著"。

hermetic：确定性合成输入 + 固定种子，不读 data/、不联网。
"""
import numpy as np
import pytest

import stats_util as su
from walk_forward import block_bootstrap_diff as bbd


def _case(n, every, up_sel, up_base):
    sel = (np.arange(n) % every == 0)
    y = np.zeros(n)
    ns = np.where(~sel)[0]
    y[ns] = (np.arange(len(ns)) % 100) < up_base * 100
    s = np.where(sel)[0]
    y[s] = (np.arange(len(s)) % 100) < up_sel * 100
    return sel, y


# ── mc_meta 本体 ────────────────────────────────────────────────────
def test_bootstrap_floor_and_flag():
    m = su.mc_meta(0, 2000, "bootstrap")
    assert m["p_at_floor"] is True
    assert m["p_floor"] == pytest.approx(2 / 2000)
    assert m["mc_x"] == 0 and m["mc_n"] == 2000 and m["mc_kind"] == "bootstrap"


def test_permutation_floor_and_flag():
    m = su.mc_meta(0, 1000, "permutation")
    assert m["p_at_floor"] is True
    assert m["p_floor"] == pytest.approx(1 / 1001)


def test_one_crossing_is_not_at_floor():
    """X=1 与 X=0 必须分开 —— 线上 rank 14(X=1,存活) 与 rank 1-5(X=0) 正是两种处境。"""
    assert su.mc_meta(1, 2000, "bootstrap")["p_at_floor"] is False
    assert su.mc_meta(0, 2000, "bootstrap")["p_at_floor"] is True


def test_missing_counts_return_none_not_a_fabricated_zero():
    """「根本没跑」必须是 None，**绝不**是 x=0 的元数据。

    这是 Part A/D10 的命门：`mc=None` = 没跑过统计（如样本不足、数据缺失）；
    `mc_x=0` = 跑了 n 次、一次都没穿过。两者在产物里含义完全不同 ——
    混掉就等于把"没测"说成"测了但极显著"。
    """
    assert su.mc_meta(None, 2000, "bootstrap") is None
    assert su.mc_meta(0, None, "bootstrap") is None
    assert su.mc_meta(0, 0, "bootstrap") is None
    assert su.mc_meta(0, -1, "bootstrap") is None


def test_unknown_kind_raises_not_silently_guesses():
    """新增估计器时必须显式给 kind —— 静默猜一个下限公式会让整个判据失真。"""
    with pytest.raises(ValueError, match="mc_meta"):
        su.mc_meta(0, 2000, "jackknife")


@pytest.mark.parametrize("n", [500, 2000, 20000])
def test_floor_tracks_n_not_a_hardcoded_constant(n):
    """下限必须随 n 变 —— 写死 0.001 的话 B 一改就静默失真（T1 的意图）。

    断言钉的是**生产的实际契约**（公式 + 舍入到 8 位，为 JSON 卫生），
    不是我脑子里的理想值：起草时我按精确值比，n=20000 时
    `1/20001 = 4.99975e-05` 舍入成 `5e-05` → 测试假红。
    舍入位数本身也一起钉住，以后谁改精度都会被看见。
    """
    for kind, exact in (("bootstrap", 2 / n), ("permutation", 1 / (n + 1))):
        got = su.mc_meta(0, n, kind)["p_floor"]
        assert got == round(exact, 8), f"{kind} 的下限公式或舍入位数变了: {got} vs {round(exact, 8)}"
        assert got == pytest.approx(exact, rel=1e-3), f"{kind} 的下限偏离精确值过多"


# ── 与估计器的往返一致性（漂开了元数据就失效）────────────────────────
@pytest.mark.parametrize("n,every,us,ub", [
    (3000, 4, 1.00, 0.40),    # 零穿越
    (2000, 4, 0.55, 0.50),    # 中等
    (2000, 4, 0.50, 0.50),    # 无效应
    (2000, 4, 0.20, 0.50),    # 反向
])
def test_bootstrap_p_reconstructs_from_counts(n, every, us, ub):
    """`p == round(2X/n_used, 4)` 必须成立 —— 这是元数据有意义的前提。"""
    r = bbd(*_case(n, every, us, ub), block=20)
    assert "mc_x" in r and "n_used" in r
    recon = round(min(2 * r["mc_x"] / r["n_used"], 1.0), 4)
    assert recon == pytest.approx(r["p_boot"], abs=1e-9), (
        f"p({r['p_boot']}) 无法从 X={r['mc_x']}/n={r['n_used']} 复原({recon}) —— "
        "p 公式与 mc_x 已经漂开了，元数据失效")


def test_bootstrap_denominator_is_n_used_not_B():
    """分母必须是 n_used（=B−n_dropped）。用 B 会让下限与 SE 都偏。"""
    r = bbd(*_case(2000, 4, 0.80, 0.50), block=20, B=500)
    assert r["n_used"] + r["n_dropped"] == 500
    m = su.mc_meta(r["mc_x"], r["n_used"], "bootstrap")
    assert m["mc_n"] == r["n_used"]


def test_permutation_p_reconstructs_from_counts():
    import placebo_test as pb
    rng = np.random.default_rng(7)
    vals = np.random.default_rng(11).normal(size=2000)
    lab = (np.arange(2000) % 5 == 0).astype(int)
    stat = pb.make_ssb_stat(2)
    r = pb.perm_test(vals, lab, stat, rng)
    assert "mc_x" in r and "mc_n" in r
    recon = round((r["mc_x"] + 1) / (r["mc_n"] + 1), 6)
    assert recon == pytest.approx(r["p_value"], abs=1e-9)


def test_mc_x_is_the_min_side_for_two_sided_p():
    """双侧 p = 2·min(两侧)，所以 mc_x 必须是**取到 min 那一侧**的计数。

    取错一侧的话，强效应的 X 会接近 n（而非接近 0），p_at_floor 恒为 False，
    整个"下限"判据当场失效。
    """
    r = bbd(*_case(3000, 4, 1.00, 0.40), block=20)     # 极强正效应
    assert r["mc_x"] == 0, f"强效应的 mc_x 应接近 0(取 min 侧)，实为 {r['mc_x']}"
    r2 = bbd(*_case(2000, 4, 0.50, 0.50), block=20)    # 无效应 → 两侧各半
    assert 700 < r2["mc_x"] <= r2["n_used"] // 2 + 50


# ── 接线：7 族 + 因子族都要带出来 ─────────────────────────────────────
def test_all_families_carry_mc_fields():
    """源码守门：7 个族函数的返回里都要有 mc/mc_recent。

    新加一族忘了带 → 这里红。只测源码是因为跑真数据要 2 分钟、不适合进单测；
    端到端的对账在 C4a 的守门里做（那时有 mc_change_prob 可以逐条验）。
    """
    from pathlib import Path
    import autodiscovery as ad
    src = Path(ad.__file__).read_text(encoding="utf-8")
    n_ret = src.count('"recent_powered": bool(powered),')
    assert n_ret == 7, f"族函数返回点数变了({n_ret})，先确认新增/删除了哪一族"
    assert src.count('"mc": su.mc_meta(') == 7, (
        "有族函数没带 mc —— 那一族的候选在产物里会缺原始计数，C4a 的改判概率算不出来")
    assert src.count('"mc_recent": mc_recent,') == 7


def test_factor_family_carries_mc_via_segment_lens():
    """因子族的 p 来自 `_segment_lens`，元数据也必须从那里带出来。"""
    import pandas as pd
    import factor_pruning as fp
    COL = "NASDAQ_above_ma200"
    n = 3000
    idx = pd.date_range("2010-01-04", periods=n, freq="B")
    col = np.full(n, np.nan)
    col[1000:] = (np.arange(n - 1000) % 2)
    y = np.zeros(n)
    y[:1000] = (np.arange(1000) % 100) < 20
    fired = col[1000:] == 1
    yo = np.empty(n - 1000)
    yo[fired] = (np.arange(int(fired.sum())) % 100) < 80
    yo[~fired] = (np.arange(int((~fired).sum())) % 100) < 60
    y[1000:] = yo
    df = pd.DataFrame({"date": idx, "year": idx.year, "fwd_up_20d": y.astype(float), COL: col})
    seg = fp._segment_lens(df, COL, +1, df["date"].max() - pd.DateOffset(years=fp.RECENT_YEARS))
    assert seg["mc"] is not None and seg["mc"]["mc_kind"] == "bootstrap"
    recon = round(min(2 * seg["mc"]["mc_x"] / seg["mc"]["mc_n"], 1.0), 4)
    assert recon == pytest.approx(seg["full_p"], abs=1e-9)


def test_insufficient_sample_gets_mc_none_not_zero_counts():
    """样本不足 → `mc` 必须是 None（没跑），不是 `mc_x=0`（跑了但没穿过）。"""
    from pathlib import Path
    import autodiscovery as ad
    src = Path(ad.__file__).read_text(encoding="utf-8")
    # 两处兜底(p=1.0)都必须显式写 mc=None
    assert src.count('"mc": None, "mc_recent": None') >= 2, (
        "p=1.0 的兜底没显式给 mc=None —— 会让'没测'与'测了但极显著'混在一起")
