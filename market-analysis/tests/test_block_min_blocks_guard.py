"""块数门（`walk_forward.MIN_BLOCKS`）—— 挡住"块长 >= 样本长度时检验反而必然显著"。

## 这是什么雷

`block_bootstrap_diff` 里 `n_blocks = ceil(n/block)`。当 `block >= n` 时 `n_blocks == 1`，
于是每次重采样的索引是 `(start + arange(block)) % n` 的前 n 个 —— **整条序列的循环平移**。
而 `sel` 与 `y` 用的是**同一个** idx，平移对二者同步生效 →
`ys[ss]` 挑出的 (y, sel) 配对与原始一模一样 → **每次重采样都原样复现观测统计量**。
自助分布方差为 0 → 一次都不穿零 → `mc_x=0` → `p = 2/(B+1) = 0.0010`，
也就是**这个估计器能报出的最显著的值**。

纯噪声（sel 与 y 独立，真相 = 无关联）实测拒真率，名义 0.10：

    1 块 **1.000** · 2 块 0.298 · 3 块 0.208 · 4 块 0.202 · 6 块 0.158
    · 8 块 0.158 · 10 块 0.135 · 20 块 0.092 · 50 块 0.107

即：**块长一旦顶到样本长度，这个检验不是"不准"，是"恒定输出最显著"。**

## 它差点被 F2 大面积引爆

F2（状态型 sel 补块放大）要把 `regime` 的 block 提到 661、`factor` 提到 164。
而 `oos_gate` 的 positioning/trailing **早就**在用放大块长（hold+51 / hold+77），
对上 `MIN_OOS_N` 给出的 n>=60 下限 → **1~2 块**。
2026-09-21 线上 148 条全是 PENDING（没有一条跑到过自助）→ 没有已发布结论受影响，
但那是"还没踩上"，不是"没有雷" —— 同 `fe8af0a` 的教训。

hermetic：全部用合成数据，不联网、不读产物。
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import walk_forward as wf                                    # noqa: E402
from walk_forward import block_bootstrap_diff, MIN_BLOCKS    # noqa: E402


def _noise(n, seed, rate=0.35):
    g = np.random.default_rng(seed)
    return g.random(n) < rate, g.standard_normal(n)


# ── 雷本身：先证明它真的存在，再证明门挡住了它 ──────────────────────────────

def test_block_ge_n_reproduces_the_observed_statistic_exactly(monkeypatch):
    """**先证明雷是真的**：把门降到 1，block==n 时自助分布退化成一个点。

    这条不是在测我写的门，是在测"门存在的理由"。若哪天重采样索引的写法改了、
    这条变绿失败，说明退化机制本身没了 —— 那时门可以重新讨论。
    """
    monkeypatch.setattr(wf, "MIN_BLOCKS", 1)
    sel, y = _noise(200, seed=11)
    r = block_bootstrap_diff(sel, y, block=200, B=500, seed=3)
    assert r is not None and r["n_blocks"] == 1
    # 一次都没穿零 → 取到估计器的下限 = 最显著
    assert r["mc_x"] == 0, f"退化机制变了：mc_x={r['mc_x']}"
    # 注意断言的是**生产的舍入契约**（p_boot 四位小数），不是理论值 2/501=0.003992。
    # 这个区别我本轮已经写错过三次，专门记在这里。
    assert r["p_boot"] == round(2 / 501, 4) == 0.004, r["p_boot"]


def test_pure_noise_at_one_block_is_always_maximally_significant(monkeypatch):
    """纯噪声 30 次全部报"最显著" —— 拒真率 100%，这就是不能放行的理由。"""
    monkeypatch.setattr(wf, "MIN_BLOCKS", 1)
    hits = 0
    for s in range(30):
        sel, y = _noise(150, seed=500 + s)
        r = block_bootstrap_diff(sel, y, block=150, B=200, seed=s)
        if r and r["p_boot"] < 0.10:
            hits += 1
    assert hits == 30, f"退化不再是恒定的（{hits}/30）—— 机制变了，门的依据要重测"


def test_the_guard_refuses_instead_of_reporting_that_p():
    """同样的输入，门在位时返回 None（= 不可判），而不是 0.0010。"""
    sel, y = _noise(150, seed=511)
    assert block_bootstrap_diff(sel, y, block=150, B=200, seed=0) is None
    assert block_bootstrap_diff(sel, y, block=200, B=200, seed=0) is None   # block > n


@pytest.mark.parametrize("nb,ok", [(MIN_BLOCKS - 1, False), (MIN_BLOCKS, True)])
def test_boundary_is_exactly_min_blocks(nb, ok):
    """边界逐块钉死：少一块就拒，刚好够就放行。"""
    block = 40
    sel, y = _noise(nb * block, seed=77)
    r = block_bootstrap_diff(sel, y, block=block, B=200, seed=1)
    assert (r is not None) is ok, f"{nb} 块的放行与否不对"
    if ok:
        assert r["n_blocks"] == nb


def test_n_blocks_is_reported_so_thinness_stays_visible():
    """过了门不等于块数充裕（10 块实测拒真率仍 0.135）→ 必须把块数报出来。"""
    sel, y = _noise(3000, seed=99)
    r = block_bootstrap_diff(sel, y, block=20, B=200, seed=1)
    assert r["n_blocks"] == 150


def test_healthy_sample_is_untouched_by_the_guard():
    """反退化：门不许误伤正常样本（线上 discovery 全部 >=33 块）。"""
    sel, y = _noise(6695, seed=4)
    r = block_bootstrap_diff(sel, y, block=20, B=400, seed=1)
    assert r is not None and r["n_blocks"] == 335


def test_rejection_rate_above_the_floor_is_same_order_as_nominal():
    """校准冒烟：10 块处纯噪声拒真率应回到与名义 0.10 同一数量级（实测 0.135）。

    宽带断言(<0.25)是有意的 —— 这条是防"门形同虚设"的回归，不是精确校准声明；
    精确曲线在 SPEC_F2_BLOCK_H3.md §0'，由 tools/block_calibration.py 离线复现。
    """
    block, R = 40, 120
    hits = 0
    for s in range(R):
        sel, y = _noise(MIN_BLOCKS * block, seed=20000 + s)
        r = block_bootstrap_diff(sel, y, block=block, B=300, seed=s)
        if r and r["p_boot"] < 0.10:
            hits += 1
    rate = hits / R
    assert rate < 0.25, f"10 块处拒真率 {rate:.3f} —— 远高于实测的 0.135，门的依据要重测"


# ── oos_gate：拒绝要说清「在等什么、还要等多久」 ──────────────────────────────
# 这两族的 block 是放大过的(hold+51 / hold+77)，而 MIN_OOS_N 只保证 n>=60 → 1~2 块。
# 若只挂一句含糊的「锚后自助不可算」，它们会这么挂上几年而没人知道在等什么
# —— 正是 bf857cd 修过的那个毛病(「等 4 年」和「等 226 年」说成同一句话)。

def _oos_gate():
    import oos_gate
    return oos_gate


def _fake_cand(cid="c1", key="k1", fam="positioning"):
    return {"candidate_id": cid, "key": key, "family": fam}


def _arr(n, seed=5, rate=0.5):
    import pandas as pd
    g = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    sel = g.random(n) < rate
    return np.asarray(idx), sel, g.standard_normal(n)


def test_short_post_anchor_sample_is_pending_with_a_concrete_wait():
    """锚后 200 日、block=71（positioning hold=20）→ 需 710 日 → pending + 报出还要等多久。"""
    og = _oos_gate()
    idx, sel, y = _arr(260, seed=5)
    anchor = "2020-01-01"            # 全部样本都在锚后
    r = og._diff_oos(_fake_cand(), anchor, (idx, sel, y), block=71)
    assert r["oos_status"] == og.PENDING
    assert r["oos_p"] is None, "块数不足却给出了 p —— 那正是这道门要挡的"
    note = r["note"]
    assert "710" in note, f"没报出需要多少样本: {note}"
    assert ("年" in note or "个月" in note), f"没报出还要等多久: {note}"
    assert "攒时间一定会到" in note, f"没说清是哪一种等待: {note}"


def test_long_enough_post_anchor_sample_still_gets_a_p():
    """反退化：样本够长时这道门不许拦路。"""
    og = _oos_gate()
    idx, sel, y = _arr(900, seed=6)
    r = og._diff_oos(_fake_cand(), "2019-01-01", (idx, sel, y), block=71)
    assert r["oos_p"] is not None, f"样本够长却被拦: {r['note']}"


def test_the_wait_note_distinguishes_itself_from_the_control_group_case():
    """「样本还不够长」与「对照组不足」是两种处境，措辞必须分得开。

    前者攒时间一定会到；后者**光等不一定来**（得等条件真的转向）——
    09-14 线上 golden_cross 就是被这两句混用说错的。
    """
    og = _oos_gate()
    idx, sel, y = _arr(260, seed=5)
    short = og._diff_oos(_fake_cand(), "2020-01-01", (idx, sel, y), block=71)["note"]
    # 对照组不足：锚后 sel 几乎恒为真
    idx2, _, y2 = _arr(900, seed=7)
    sel2 = np.ones(900, dtype=bool)
    ctrl = og._diff_oos(_fake_cand(), "2019-01-01", (idx2, sel2, y2), block=71)["note"]
    assert "对照组" in ctrl and "攒时间一定会到" not in ctrl, ctrl
    assert "对照组" not in short or "块长" in short, short
    assert short != ctrl
