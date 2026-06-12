"""benchmark：verdict 纯函数测试（硬基线 · 样本外/前向 · 前向不足不判输赢）

直接 import 生产模块的 verdict 函数，不复制逻辑。
"""
import benchmark
from benchmark import (
    _verdict_auc, _verdict_diff, _verdict_gain, _forward_verdict,
    V_BEATS, V_TIE, V_LOSE, V_INSUF,
)


# ── 行1：AUC vs 0.50（硬基线=随机无区分度）────────────────────────
def test_verdict_auc_below_is_lose():
    # 0.4448 是真实的拼接样本外方向 AUC，弱于随机 → 未达
    assert _verdict_auc(0.4448, 0.50) == V_LOSE


def test_verdict_auc_random_is_tie():
    # 恰为 0.50 → 落在持平带（0.485..0.515）
    assert _verdict_auc(0.50, 0.50) == V_TIE


def test_verdict_auc_above_is_beat():
    # 0.55 明显高于上界 0.515 → 打败
    assert _verdict_auc(0.55, 0.50) == V_BEATS


# ── 行2：胜率−基率(pp) vs 0，看块自助 p ──────────────────────────
def test_verdict_diff_negative_is_lose():
    # -3.18 是真实 tier4_boot.diff，diff<0 直接未达（p 不救场）
    assert _verdict_diff(-3.18, 0.058) == V_LOSE


def test_verdict_diff_positive_significant_is_beat():
    # +2 且 p=0.05 < 0.10 → 打败
    assert _verdict_diff(2.0, 0.05) == V_BEATS


def test_verdict_diff_positive_insignificant_is_tie():
    # diff>0 但 p 不显著（或缺失）→ 持平，不夸张判打败
    assert _verdict_diff(2.0, 0.20) == V_TIE
    assert _verdict_diff(2.0, None) == V_TIE


# ── 行3：模型 AUC 相对只看 VIX 的增益 ────────────────────────────
def test_verdict_gain_tiny_is_tie():
    # +0.002 是真实波动率模型相对 VIX 的增益，微乎其微 → 持平
    assert _verdict_gain(0.002) == V_TIE


def test_verdict_gain_large_is_beat():
    # +0.05 超过 0.02 阈值 → 打败
    assert _verdict_gain(0.05) == V_BEATS


def test_verdict_gain_negative_is_lose():
    assert _verdict_gain(-0.05) == V_LOSE


# ── 前向规则（行4/5）：样本不足一律「数据不足」，无论 delta ──────
def test_forward_insufficient_regardless_of_delta():
    # enough=False → 数据不足，哪怕 delta 大正/大负都不判输赢
    assert _forward_verdict(False, -2.54) == V_INSUF
    assert _forward_verdict(False, 10.0) == V_INSUF
    assert _forward_verdict(False, 0.0) == V_INSUF
    assert _forward_verdict(False, None) == V_INSUF


def test_forward_enough_judges_by_delta():
    # 样本足够后才按 delta 正负判
    assert _forward_verdict(True, 3.0) == V_BEATS
    assert _forward_verdict(True, -3.0) == V_LOSE
    assert _forward_verdict(True, 0.0) == V_TIE


# ── 烟雾测试：build 不崩、结构完整、6 行 ─────────────────────────
def test_build_smoke_structure():
    card = benchmark.build()
    assert set(card.keys()) >= {"generated", "principle", "rows", "summary", "headline"}
    assert len(card["rows"]) == 6
    for r in card["rows"]:
        assert {"name", "metric", "model_value", "baseline_label",
                "baseline_value", "delta", "verdict", "basis", "note"} <= set(r.keys())
    s = card["summary"]
    assert set(s.keys()) == {"beats", "ties", "loses", "insufficient"}
