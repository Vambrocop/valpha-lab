"""离线慢查工具的守门 —— 防它退化成"恒报 0 条改判"的假绿（SPEC_MC_RESOLUTION Part D）。

## 这条守门为什么存在

规格 R1 把这个工具写成「按 N 个种子重跑 `adjudicate`」——
而 `adjudicate` **没有种子参数、也不算 p**，它只消费算好的 p。
按字面实现会 N 次得到同一个答案、**恒报 0 条改判**，
然后 §9 的"修复后应显著下降"看起来完美达成。独立审规格（B8）抓出了这一点。

教训同 CLAUDE.md 的 `fe8af0a`：**「我跑了一次是绿的」≠ 验证过，还得问它到底在测什么。**

## 守什么

① 工具必须真的重跑 `compute_results`（不是 `adjudicate`）；
② 种子 patch 必须对**两个估计器都**生效（自助的种子是默认参数、置换的来自
   `autodiscovery._seed_for`，只挪一半等于只换了一半）；
③ patch 必须可撤销（否则后续调用带着偏移、污染同一进程里的其他计算）。

hermetic：只在小数组上调估计器，不跑全量候选、不读 data/。
"""
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[2] / "tools"
AUDIT = TOOLS / "mc_stability_audit.py"


def _load():
    import importlib.util as u
    spec = u.spec_from_file_location("mc_stability_audit", AUDIT)
    m = u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_tool_reruns_compute_results_not_just_adjudicate():
    """B8 的直接回归守门：只重跑 adjudicate 会恒报 0 条改判。"""
    src = AUDIT.read_text(encoding="utf-8")
    assert "compute_results" in src, (
        "工具没重跑 compute_results —— 只重跑 adjudicate 会恒报 0 条改判（假绿，见 B8）")
    assert "_patch_seeds" in src, "没有换种子的机制，那它到底在测什么?"


def test_seed_patch_affects_the_bootstrap_estimator():
    m = _load()
    import walk_forward as wf
    sel = (np.arange(2000) % 4 == 0)
    y = np.zeros(2000)
    ns = np.where(~sel)[0]
    y[ns] = (np.arange(len(ns)) % 100) < 50
    s = np.where(sel)[0]
    y[s] = (np.arange(len(s)) % 100) < 58          # 中段 p，对种子敏感
    base = wf.block_bootstrap_diff(sel, y, block=20)["mc_x"]
    undo = m._patch_seeds(7000)
    try:
        moved = wf.block_bootstrap_diff(sel, y, block=20)["mc_x"]
    finally:
        undo()
    assert moved != base, f"自助的种子没被挪动（X 都是 {base}）—— 工具只换了一半种子"


def test_seed_patch_affects_the_permutation_estimator():
    """置换的种子来自 `autodiscovery._seed_for(cid)`，必须一起挪。"""
    m = _load()
    import autodiscovery as ad
    base = ad._seed_for("some_candidate")
    undo = m._patch_seeds(7000)
    try:
        moved = ad._seed_for("some_candidate")
    finally:
        undo()
    assert moved != base, "置换的种子没被挪动 —— 51 条日历族候选的噪声不会变"
    assert all(b + 7000 == a for b, a in zip(base, moved))


def test_patch_is_undoable():
    """撤销必须干净：不撤的话同一进程里后续计算全带着偏移。"""
    m = _load()
    import walk_forward as wf
    import autodiscovery as ad
    before_bbd, before_seed = wf.block_bootstrap_diff, ad._seed_for("x")
    undo = m._patch_seeds(1234)
    undo()
    assert wf.block_bootstrap_diff is before_bbd, "block_bootstrap_diff 没还原"
    assert ad._seed_for("x") == before_seed, "_seed_for 没还原"


def test_tool_compares_model_against_reality():
    """工具的**用处**是交叉验证那个噪声模型 —— 只报实测数字等于少了一半价值。"""
    src = AUDIT.read_text(encoding="utf-8")
    assert "change_probabilities" in src, "没跟模型化估计对照"
    assert "模型与实测" in src, "没把『模型与实测是否一致』这个结论说出来"


def test_tool_declares_it_must_not_run_in_ci():
    """每个种子约 2 分钟 → 进 CI 会撑爆预算。文档里必须写明。"""
    src = AUDIT.read_text(encoding="utf-8")
    assert "不进 CI" in src or "勿进 CI" in src


# ── B3 的回归守门（第一版实现只跑未加算的 pass-1）──────────────────────
def test_tool_shares_the_production_two_pass_flow():
    """工具必须走生产那条 `resolve_candidates`，不能自己另写一套。

    审实现 B3：第一版只调 `compute_results`（未加算）→ 它量的是**未加算管线**的
    种子敏感度，规格 §9-4 的"修前修后对照"根本做不出来，
    而结尾话术读起来像能做到。共用同一条流程才能验到修复效果。
    """
    src = AUDIT.read_text(encoding="utf-8")
    assert "resolve_candidates" in src, (
        "工具没走生产的两遍流程 —— 它量的将是未加算管线，验不到 C3 的效果（B3）")
    assert "ad.compute_results(cands)" not in src, (
        "工具还在直接调 compute_results（未加算）—— 那是 B3 的原始形态")


def test_tool_can_produce_the_before_after_comparison():
    """规格 §9-4 要的是"修前修后对照" —— 工具必须能一次跑出两种口径。"""
    src = AUDIT.read_text(encoding="utf-8")
    assert "--both" in src and "refine=False" in src, "没有未加算口径，出不了对照"
    assert "§9-4" in src, "没标明它交付的是哪条验收判据"
    assert "不下降就是没修对" in src, "对照没给判据，读者不知道该看什么"


def test_tool_no_longer_implies_an_effect_it_cannot_measure():
    """第一版结尾写"若这是加算上线之后，说明修复生效了" —— 而它测不到加算。

    把一个测不到的因果暗示给下一个人，比不说更糟。
    """
    src = AUDIT.read_text(encoding="utf-8")
    assert "若这是加算上线之后" not in src, "那句测不到的因果暗示还在"


def test_seed_patch_forwards_args_generically():
    """替身用 `*a, **k` 转发 —— 写死签名的话，`block_bootstrap_diff` 将来加参数
    会被静默丢掉（审查 N4）。"""
    src = AUDIT.read_text(encoding="utf-8")
    i = src.index("def bbd(")
    assert "*a, **k" in src[i:i + 80], f"替身签名写死了: {src[i:i+60]!r}"
