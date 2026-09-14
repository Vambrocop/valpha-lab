"""门4 pending 原因必须说清是哪一组不足(2026-09-14·实测踩到)。

## 起因

自生长闭环等了 77 天,`golden_cross_sp500` 的 `oos_n` 终于到 33(≥ 门槛 30),却仍是 pending,
note 写着「锚后**触发组**样本不足」—— **这句话是错的**:33 ≥ 30,触发组明明够了。
真正缺的是**对照组**:锚点后标普金叉**一天都没断过**(n_ctrl=0),没有"不成立"的日子可比。

原因是两个条件共用了一句 note:

    if n_trig < MIN_OOS_N or n_ctrl < MIN_OOS_N:
        return _result(..., note="锚后触发组样本不足")   # ← 对照组不足时也说这句

## 为什么这个区别很要紧

  · **触发组不足** → 攒时间就行,等下去一定会到;
  · **对照组不足** → **光等不一定来**,得等条件真的转向(金叉跌破)才会累积。
CLAUDE.md 原本写自生长"只能等"——技术上对,但把这两种处境混成一句,
就看不出"等什么、等不等得到"。自生长的第一次晋升决策必须解释得清。

hermetic:纯函数 + 合成输入,不联网、不读真数据。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import oos_gate as og  # noqa: E402


CAND = {"candidate_id": "test_x", "key": "test_key", "family": "regime"}


def _arr(n_trig_after, n_ctrl_after, anchor="2026-06-26", n_before=1200):
    """造 (idx, sel, y):锚前一大段,锚后按指定数量给触发/对照日。"""
    total = n_before + n_trig_after + n_ctrl_after
    idx = pd.bdate_range(end="2026-12-31", periods=total)
    a = pd.Timestamp(anchor)
    # 把锚点放到倒数 (n_trig_after+n_ctrl_after) 之前
    cut = total - (n_trig_after + n_ctrl_after)
    idx = pd.DatetimeIndex(list(pd.bdate_range(end=a, periods=cut)) +
                           list(pd.bdate_range(start=a + pd.Timedelta(days=1),
                                               periods=n_trig_after + n_ctrl_after)))
    sel = np.zeros(total, bool)
    sel[:cut] = np.random.default_rng(1).random(cut) < 0.5      # 锚前两组都有
    sel[cut:cut + n_trig_after] = True                          # 锚后触发
    sel[cut + n_trig_after:] = False                            # 锚后对照
    y = np.random.default_rng(2).normal(0, 0.01, total)
    return idx, sel, y


def test_control_group_shortage_is_named_not_blamed_on_trigger():
    """核心:触发组够、对照组不够时,note 必须说**对照组** —— 这正是线上 golden_cross 的处境。"""
    r = og._diff_oos(CAND, "2026-06-26", _arr(n_trig_after=40, n_ctrl_after=0), block=20)
    assert r["oos_status"] == og.PENDING
    assert r["oos_n"] >= og.MIN_OOS_N, "构造前提:触发组应当够"
    assert r["n_ctrl"] == 0
    assert "对照组" in r["note"], f"没点明是对照组不足: {r['note']}"
    assert "触发组不足" not in r["note"], f"仍在错怪触发组: {r['note']}"


def test_trigger_group_shortage_still_says_trigger():
    """反向:真的是触发组不够时,别说成对照组。"""
    r = og._diff_oos(CAND, "2026-06-26", _arr(n_trig_after=2, n_ctrl_after=60), block=20)
    assert r["oos_status"] == og.PENDING
    assert "触发组不足" in r["note"], f"{r['note']}"
    assert "对照组**不足" not in r["note"]


def test_both_short_says_both_with_counts():
    """两边都不够时说"都不足",并把两个数字都报出来(不报数就无法判断还差多远)。"""
    r = og._diff_oos(CAND, "2026-06-26", _arr(n_trig_after=3, n_ctrl_after=4), block=20)
    assert "都不足" in r["note"]
    assert "触发 3" in r["note"] and "对照 4" in r["note"], f"没报具体数字: {r['note']}"


def test_note_carries_the_threshold_so_reader_knows_how_far():
    """note 里要带门槛值 —— 只说"不足"读者不知道差多少。"""
    r = og._diff_oos(CAND, "2026-06-26", _arr(n_trig_after=3, n_ctrl_after=4), block=20)
    assert str(og.MIN_OOS_N) in r["note"]


def test_n_ctrl_is_exposed_in_the_record():
    """`n_ctrl` 必须进产物 —— 只有 oos_n 的话,前端/人都分不出是哪种处境。"""
    r = og._diff_oos(CAND, "2026-06-26", _arr(n_trig_after=40, n_ctrl_after=5), block=20)
    assert "n_ctrl" in r and r["n_ctrl"] == 5


def test_single_label_after_anchor_is_explained_not_mislabeled():
    """日历族那支:锚后只剩单一标签时,要说"无对照组",不是含糊的"触发组不足"。"""
    src = (ROOT / "scripts" / "oos_gate.py").read_text(encoding="utf-8")
    i = src.index("if len(labs) < 2 or counts.min() < MIN_OOS_N:")
    body = src[i:i + 700]
    assert "单一标签" in body and "无对照组" in body, "日历族那支仍在用含糊措辞"
