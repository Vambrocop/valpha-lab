"""test_quality_gate.py — v1.5 Phase 1：裁决引擎「不自欺」单测（纯合成 p 值，无数据）。

证明引擎不自欺（自动发现的命门）：
  · 纯噪声候选 → 跨族 BY 校正后存活 ≈ 0（不随 N 爆表）—— "测一千个挑最好看的"被挡住。
  · 植入真信号 → 必入选（门不会太严把真的杀了，对称护栏）。
  · 现代段检验力不足 → inconclusive，不下结论。
  · 分母完整性：漏算/偷加分母 → 直接报错。
  · 双栏（族内 vs 跨族）可不同 —— 证明 🔴-A 双栏的信息价值。
"""
import numpy as np
import pytest

from quality_gate import adjudicate, summarize


def _noise(n, seed=0):
    rng = np.random.default_rng(seed)
    ps, rps = rng.uniform(0, 1, n), rng.uniform(0, 1, n)
    return [{"candidate_id": f"n{i}", "family": "calendar", "p": float(ps[i]),
             "recent_p": float(rps[i]), "recent_powered": True} for i in range(n)]


def test_pure_noise_does_not_explode():
    # 纯噪声：跨族 BY 校正后存活应 ≈0，绝不随 N 线性膨胀
    for N in (50, 200, 1000):
        s = summarize(adjudicate(_noise(N, seed=N)))
        assert s["n_survive_cross"] <= 1, (N, s)
        assert s["n_survive_cross"] / N < 0.05, (N, s)


def test_planted_signal_survives():
    res = _noise(200, seed=7)
    for i in range(3):
        res[i]["p"] = 1e-8
        res[i]["recent_p"] = 1e-8
    adjudicate(res)
    for i in range(3):
        assert res[i]["survive_cross"], res[i]
        assert res[i]["verdict"] == "survive", res[i]


def test_underpowered_is_inconclusive():
    res = [{"candidate_id": "a", "family": "factor", "p": 1e-9,
            "recent_p": None, "recent_powered": False}]
    adjudicate(res)
    assert res[0]["verdict"] == "inconclusive"
    assert res[0]["modern_status"] == "现代检验力不足"


def test_faded_when_modern_gone():
    res = _noise(50, seed=3)
    res[0]["p"] = 1e-9          # 全段强
    res[0]["recent_p"] = 0.8    # 现代淡
    adjudicate(res)
    assert res[0]["survive_cross"]
    assert res[0]["modern_status"] == "现代已淡"
    assert res[0]["verdict"] == "faded"


def test_denominator_guard():
    with pytest.raises(ValueError):
        adjudicate(_noise(10), expect_n=11)


def test_dual_column_can_differ():
    # 族内强信号 + 一个大族全噪声 → 该候选族内过、跨族不过（双栏意义）
    res = [{"candidate_id": "A0", "family": "calA", "p": 0.001,
            "recent_p": 0.001, "recent_powered": True}]
    res += [{"candidate_id": f"A{i}", "family": "calA", "p": 0.5,
             "recent_p": 0.5, "recent_powered": True} for i in range(1, 3)]
    res += [{"candidate_id": f"B{i}", "family": "famB", "p": 0.5,
             "recent_p": 0.5, "recent_powered": True} for i in range(50)]
    adjudicate(res)
    assert res[0]["survive_family"] and not res[0]["survive_cross"]


def test_summarize_counts_add_up():
    res = _noise(100, seed=11)
    s = summarize(res := adjudicate(res))
    assert s["n_survive"] + s["n_faded"] + s["n_dead"] + s["n_inconclusive"] == len(res)
