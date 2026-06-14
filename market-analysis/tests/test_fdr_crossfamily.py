"""test_fdr_crossfamily.py — #5 跨检验族 FDR 收口单元测试

要点：BH step-up 正确、BY 比 BH 严(拒绝集是子集)、全空 p 不误拒、step-up 带过性质、
以及真实产物冒烟(BY 存活 ≤ BH 存活,这是头条诚实不变式)。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fdr_crossfamily as fc  # noqa: E402


def test_bh_reject_basic():
    rej = fc._bh_reject([0.001, 0.002, 0.5, 0.6], 0.10)
    assert 0 in rej and 1 in rej
    assert 2 not in rej and 3 not in rej


def test_all_large_p_rejects_none():
    assert len(fc._bh_reject([0.4, 0.5, 0.6, 0.7, 0.8], 0.10)) == 0


def test_by_is_subset_of_bh():
    p = [0.001, 0.02, 0.03, 0.2, 0.5]
    bh = fc._bh_reject(p, 0.10)
    by, c_m = fc._by_reject(p, 0.10)
    assert by.issubset(bh)        # BY = BH 在更小 q 上 → 更保守
    assert c_m > 1                # 调和数 c(m) > 1


def test_step_up_carries_moderate_p():
    # m=4, q=0.1：rank4 阈值=0.1，0.04<=0.1 → step-up 带过全部
    assert len(fc._bh_reject([0.001, 0.001, 0.001, 0.04], 0.10)) == 4


def test_zero_p_always_rejected():
    rej = fc._bh_reject([0.0, 0.9, 0.95], 0.10)
    assert 0 in rej


def test_run_all_smoke_and_invariant():
    out = fc.run_all(write=False)   # 不写生产 JSON,避免 pytest 污染工作树
    if out is not None:                                   # 真实产物存在才校验
        assert out["m_total"] >= 2
        assert out["n_survive_by_10"] <= out["n_survive_bh_10"]   # 头条不变式：BY ≤ BH
        assert 0 <= out["n_survive_by_10"] <= out["m_total"]
        assert out["by_c_m"] > 1
