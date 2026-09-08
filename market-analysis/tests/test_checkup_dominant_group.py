"""个股规律真伪:主导组口径 + 近期不可测的两种成因(2026-09-07·§3 旧记录收口)。

## ① 主导组必须是"偏离总均值最远"的组,不是"均值最高"的组

分半稳健要求「两半的主导组一致」,而检验统计量 SSB = Σ n·(组均值-总均值)² 对**低**离群组
一样敏感。原来用 argmax(均值最高),遇到"某组特别弱"驱动的效应(九月最弱、周一最差都是这种)
时,argmax 指向的是剩下那些组里的噪声 —— 两半自然对不上,把真效应误判成不稳;
反过来也可能因为"某个无关组恰好在两半都最高"而**虚假地**判成稳定。

实测 AAPL 星期几就是后者:前半真正驱动 SSB 的是**周五特别弱**(偏离 0.30%),
后半是**周一特别强**(偏离 0.15%) —— 两半根本不是同一个效应,旧规则却因为
"周一在两半都最高"判成稳定。改口径后 split_half_stable 正确地变 False。

**同一份数据下 A/B 实测:裁决翻转 0 条**(改的是稳健性判据,当前无样本跨过裁决阈值)。

## ② 近期测不了,要说清是哪一种测不了

月度效应在 5 年窗里只有 ~60 个观测,门槛 100 → **永远**测不到,不是"再等等"。
实测 18 条月份检验**全部** structural。混成一句"近期未测"会让人以为还在攒数据。

hermetic:纯函数 + 合成数据,不联网、不读真产物。
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def _dominant_by_deviation(gm, grand):
    """复刻生产口径,便于直接断言(生产实现在 stock_checkup._effect_test._p_dom)。"""
    return int(np.nanargmax(np.abs(gm - grand)))


def test_low_outlier_group_is_recognised_as_the_driver():
    """核心:某组**特别弱**驱动效应时,主导组必须指向它,而不是剩下组里最高的那个。"""
    gm = np.array([-0.0214, -0.00093, -0.00037, -0.00183, -0.00075])
    grand = float(gm.mean())
    assert int(np.nanargmax(gm)) == 2, "构造前提:均值最高的是第 2 组(噪声)"
    assert _dominant_by_deviation(gm, grand) == 0, "真正驱动 SSB 的第 0 组没被认出来"


def test_high_outlier_still_works():
    """高离群组不能因为改口径而认错 —— 新规则要两头都对。"""
    gm = np.array([0.001, 0.0012, 0.02, 0.0009, 0.0011])
    assert _dominant_by_deviation(gm, float(gm.mean())) == 2


def test_production_uses_absolute_deviation_not_argmax_of_means():
    """防回退:生产代码不许改回 nanargmax(gm)。"""
    src = (ROOT / "scripts" / "stock_checkup.py").read_text(encoding="utf-8")
    i = src.index("def _p_dom")
    body = src[i:i + 1400]
    assert "np.abs(gm" in body, "主导组不再按 |偏离| 取 —— 低离群组驱动的效应会被误判"
    assert "nanargmax(gm)" not in body, "退回了 argmax(均值最高),低离群组会被漏掉"


def test_recent_block_distinguishes_structural_from_short_history():
    """近期不可测的两种成因必须分开标 —— 一种永远好不了,一种补数据就行。"""
    src = (ROOT / "scripts" / "stock_checkup.py").read_text(encoding="utf-8")
    assert "recent_block" in src and '"structural"' in src and '"short_history"' in src
    assert "recent_n" in src, "没透传近期窗观测数,前端无法说明'只有约 N 个'"


def test_frontend_shows_na_for_structural_not_a_bare_dash():
    """前端必须把 structural 显示成 n/a 并给出原因,不能和'历史太短'共用一个 —— 。"""
    js = (ROOT / "web" / "app-2.js").read_text(encoding="utf-8")
    assert "function recentCell" in js and "function recentTitle" in js
    i = js.index("function recentCell")
    assert '"structural"' in js[i:i + 500], "没区分 structural"
    assert "n/a" in js[i:i + 500]
    assert "结构上测不了" in js, "脚注没说清'不是还在攒'"
