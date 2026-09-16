"""block_bootstrap_diff 的特征化（golden-master）测试 —— C0，F1 的前置。

## 为什么必须先有这个

`walk_forward.block_bootstrap_diff` 是全站最"通吃"的统计核，**8 个模块**在用：
  autodiscovery（自生长候选 p）· factor_pruning（因子族 p / 分段透镜）·
  **oos_gate（门4 confirm/overturn → knowledge_base 晋升降级 → 写 append-only kb_ledger）**·
  walk_forward 自身（Tier≥4 记分，CLAUDE.md 里"最面向用户"那条）·
  backtest · fomc_study · ebm_duel · vol_model

而 2026-09-16 独立审规格 grep 了全部 97 个测试文件，发现**没有任何测试钉住它的 p 公式**：
  · test_autodiscovery.py:544   只断言"被调用过"
  · test_autodiscovery.py:582-3 `<0.05` / `>0.10` 宽带
  · test_backtest_block_bootstrap.py:96 `0 ≤ p ≤ 1`（空洞）
  · test_ebm_duel.py:286        断言 p_boot **不**存在
→ **改动 1/B（0.0005）量级的 p 公式，能通过现有全部测试而无人报警。**
而 FDR 的刀口恰在 1/B 量级：线上 c₁..c₁₄ = 0.000121–0.001696，自助 p 在这个区间里
**只有 0.000 和 0.001 两个可取值**。

F1 的 D6 要给自助 p 加 +1 平滑（修一个既有口径不一致：同一个跨族 BY 池里，
51 条置换 p 是平滑过的、97 条自助 p 没平滑，自助族系统性占了约 1/B 的便宜）。
**在无保护的情况下改这个函数是不可接受的** → 先把现状焊死，再改。

## 特征化测试的读法（重要）

下面的金标准值**描述现状，不主张现状正确**。
D6 落地时 `p_boot` 的期望值**会变**，那时**必须在同一个提交里**更新这些数值，
并把前后对照写进 commit message —— 这正是本文件的用途：让改动**可见**，而不是让它不可能。
若你只是想让红转绿而随手改数字，请停下：先问这个变化是不是你打算做的。

hermetic：确定性合成输入、固定种子、不读 data/、不联网。
"""
import re
from pathlib import Path

import numpy as np
import pytest

from walk_forward import block_bootstrap_diff as bbd

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _case(n, every, up_sel, up_base):
    """确定性 (sel, y)：sel 每 every 取 1；两组上涨率按**序**铺开（不用随机，跨机器可复现）。"""
    sel = (np.arange(n) % every == 0)
    y = np.zeros(n)
    ns = np.where(~sel)[0]
    y[ns] = (np.arange(len(ns)) % 100) < up_base * 100
    s = np.where(sel)[0]
    y[s] = (np.arange(len(s)) % 100) < up_sel * 100
    return sel, y


# ── 1. 精确金标准（生产默认 B=2000 / seed=42）────────────────────────
GOLDEN = [
    # (名称, n, every, up_sel, up_base, block, diff, ci95, p_boot, n_used)
    ("strong",   2000, 4, 0.95, 0.50, 20,  33.75, [27.55, 40.30], 0.000, 2000),
    ("weak",     2000, 4, 0.55, 0.50, 20,   4.50, [-4.05, 12.80], 0.292, 2000),
    ("null",     2000, 4, 0.50, 0.50, 20,   0.00, [-7.90,  8.05], 0.989, 2000),
    ("negative", 2000, 4, 0.20, 0.50, 20, -22.50, [-29.25, -15.70], 0.000, 2000),
    ("block1",   1500, 5, 0.80, 0.50,  1,  24.00, [19.68, 28.26], 0.000, 2000),
]


@pytest.mark.parametrize("name,n,every,us,ub,blk,diff,ci,p,nu", GOLDEN)
def test_golden_values(name, n, every, us, ub, blk, diff, ci, p, nu):
    """p / diff / ci95 / n_used 全部钉死。任何一个动了都必须是**故意的**。"""
    r = bbd(*_case(n, every, us, ub), block=blk)
    assert r is not None
    assert r["diff"] == pytest.approx(diff, abs=1e-9), f"{name}: diff 变了"
    assert r["ci95"][0] == pytest.approx(ci[0], abs=1e-9), f"{name}: ci95 下界变了"
    assert r["ci95"][1] == pytest.approx(ci[1], abs=1e-9), f"{name}: ci95 上界变了"
    assert r["p_boot"] == pytest.approx(p, abs=1e-9), (
        f"{name}: **p 公式变了**（{r['p_boot']} vs 金标准 {p}）。"
        "若这是 D6 的 +1 平滑，请在同一提交里更新金标准并把前后对照写进 commit message；"
        "若你不知道为什么变了，先停下查清楚 —— 8 个模块吃这个数，其中 oos_gate 写 append-only 账本。")
    assert r["n_used"] == nu and r["n_dropped"] == 0


# ── 2. 零穿越：D6 要改的正是这一格 ──────────────────────────────────
def test_zero_crossing_currently_returns_exact_zero():
    """**现状**：零穿越时 p 返回**精确的 0.0**（无平滑）。

    这不是"极显著"，是"低于本估计器能报的最小值"——零穿越(X=0, B=2000)时
    双侧 p 的 95% 上界 ≈0.003，和线上 rank 15 的 0.0030 **在统计上分不开**，
    却被 FDR 分到了线的两侧（线上 rank 1–5 正是这一格）。

    D6 加 +1 平滑后这里会变成 ≈ 2/(B+1) ≈ 0.001 —— **那时改这条测试是对的**，
    但必须是**故意**改，并在 commit 里记清楚它影响哪些已发布的 p。
    """
    r = bbd(*_case(3000, 4, 1.0, 0.40), block=20)
    assert r["p_boot"] == 0.0, "零穿越不再返回精确 0.0 —— 是 D6 的平滑上线了吗?"
    assert r["diff"] > 0


# ── 3. 不变量（这些**不**该随 D6 改变）──────────────────────────────
def test_deterministic_at_fixed_seed():
    """同输入同种子必须逐位相同 —— 产物可复现的地基。"""
    a = bbd(*_case(2000, 4, 0.80, 0.50), block=20)
    b = bbd(*_case(2000, 4, 0.80, 0.50), block=20)
    assert a == b


def test_p_moves_with_seed_only_near_the_floor():
    """诚实的边界：MC 噪声是**下限/阈值附近**的现象，不是普遍现象。

    远离下限处（p≈0.18）换 5 个种子只在 0.170–0.185 间动 —— 这正是 F1 的 §3
    「什么没有坏」所依据的事实。若哪天这里也开始大幅抖，说明 B 被调小了。
    """
    ps = [bbd(*_case(2000, 4, 0.58, 0.50), block=20, seed=s)["p_boot"] for s in range(5)]
    assert max(ps) - min(ps) < 0.03, f"远离下限处 p 抖动过大: {ps}（B 被调小了?）"
    assert all(0.10 < p < 0.30 for p in ps)


def test_too_few_selected_returns_none():
    """既有守卫：sel.sum() < 10 → None（不是编一个 p 出来）。"""
    sel = np.zeros(500, bool)
    sel[:5] = True
    assert bbd(sel, np.ones(500) * 0.5, block=20) is None


def test_two_sided_p_is_symmetric_in_sign():
    """双侧 p 只看|偏离|：同幅度的正负效应应给出同一个 p（口径对称性）。"""
    pos = bbd(*_case(2000, 4, 0.70, 0.50), block=20)["p_boot"]
    neg = bbd(*_case(2000, 4, 0.30, 0.50), block=20)["p_boot"]
    assert pos == pytest.approx(neg, abs=0.05), f"正负不对称: {pos} vs {neg}"


def test_n_used_excludes_dropped_resamples():
    """n_used = B − n_dropped。F1 的 Part A 要用它当 SE 的分母（不是 B）。"""
    r = bbd(*_case(2000, 4, 0.80, 0.50), block=20, B=500)
    assert r["n_used"] + r["n_dropped"] == 500


# ── 4. 消费者清单：加第 9 个消费者就会红 ─────────────────────────────
# 自动化优于"下次记得"（memory: Automation-First Fixes）。
# 谁新引这个统计核，就必须回来看一眼本文件的金标准还成不成立。
KNOWN_CONSUMERS = {
    "autodiscovery.py",   # 自生长候选 p
    "factor_pruning.py",  # 因子族 p / 分段透镜
    "oos_gate.py",        # 门4 → knowledge_base 晋升降级 → append-only kb_ledger
    "walk_forward.py",    # 自身 + Tier≥4 记分
    "backtest.py",
    "fomc_study.py",
    "ebm_duel.py",
    "vol_model.py",
}


def test_consumer_inventory_is_pinned():
    """新增消费者 → 红，并指名道姓。

    2026-09-16 独立审规格只列出 7 个消费者，实际是 8 个（漏了 ebm_duel / vol_model）
    —— 人工清点这件事本身就不可靠，所以自动化。
    """
    found = {p.name for p in SCRIPTS.glob("*.py")
             if "block_bootstrap_diff" in p.read_text(encoding="utf-8")}
    new = found - KNOWN_CONSUMERS
    gone = KNOWN_CONSUMERS - found
    assert not new, (f"发现新的 block_bootstrap_diff 消费者: {sorted(new)}。"
                     "请确认本文件的金标准对它也成立，再把它加进 KNOWN_CONSUMERS。")
    assert not gone, (f"这些模块不再用 block_bootstrap_diff: {sorted(gone)}。"
                      "若是有意移除，从 KNOWN_CONSUMERS 里删掉即可。")


def test_p_formula_lives_in_exactly_one_place():
    """p 公式必须只有一份实现 —— 8 个消费者共用，复制一份出去就会口径漂移。"""
    src = (SCRIPTS / "walk_forward.py").read_text(encoding="utf-8")
    hits = len(re.findall(r"2 \* min\(float\(\(diffs <= 0\)\.mean\(\)\)", src))
    assert hits == 1, f"p 公式出现 {hits} 次；应当只有 block_bootstrap_diff 内部那一处"


# ── 5. 关键消费者的端到端金标准（p 真的流到了它们发布的字段）────────
def test_oos_gate_diff_oos_golden():
    """门4 是唯一会写 append-only 账本的消费者（经 knowledge_base），单独钉一条。"""
    import pandas as pd
    import oos_gate as og
    n_pre, n_post = 1200, 800
    n = n_pre + n_post
    idx = pd.date_range("2000-01-03", periods=n, freq="B")
    sel = (np.arange(n) % 4 == 0)
    y = np.zeros(n)
    ns = np.where(~sel)[0]
    y[ns] = (np.arange(len(ns)) % 2)
    y[np.where(sel)[0]] = 1.0
    anchor = idx[n_pre - 1].date().isoformat()
    cand = {"candidate_id": "golden01", "key": "golden_test", "family": "rebound", "params": {}}
    v = og._diff_oos(cand, anchor, (idx, sel, y), block=5)
    assert v["oos_status"] == og.CONFIRMED
    assert v["oos_p"] == pytest.approx(0.0, abs=1e-9), (
        f"门4 的 oos_p 变了({v['oos_p']}) —— 它决定 confirmed/overturned，"
        "而那会写进 append-only kb_ledger。若是 D6 的平滑，请一并核对滞回阈值 0.10/0.20 的影响。")
    assert v["full_sign"] == 1 and v["oos_sign"] == 1


def test_factor_pruning_segment_lens_golden():
    """因子族 p 的来源（喂公开的 survive/dead 判定）。"""
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
    assert seg is not None
    assert seg["full_p"] == pytest.approx(0.0, abs=1e-9), (
        f"因子族的 full_p 变了({seg['full_p']}) —— 它直接进跨族 BY-FDR、决定公开存活名单。")
    # diff = 触发组 80% − **基率** 70%（= (80+60)/2，**含触发日、非补集**）= 10.0pp。
    # 起草这条时我按补集算成了 20pp、测试红 —— 正好把 survivors_live 那条命门
    # （"base 是全样本基率，绝不能写补集名，否则把基率数字安到补集头上"）实测钉住了。
    assert seg["full_diff_pp"] == pytest.approx(10.0, abs=0.05), (
        "因子族边际的口径变了。注意 base 是**含触发日的基率**、不是补集均值 —— "
        "若这里变成 ≈20，说明有人把 base 改成了补集，那会让全站公开的 diff 一起翻倍。")
