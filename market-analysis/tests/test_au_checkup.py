"""test_au_checkup.py — 澳股体检(B2)单测:流动性分档边界 + beta_key 参数化守门 + 数据卫生标记守门。"""
import numpy as np
import pandas as pd

import au_checkup as ac
import stock_checkup as sc
import fetch_data_au as fau


# ── 流动性档位:机械分档边界(规则公示口径,勿漂移) ────────────────────────
def test_liquidity_tier_boundaries():
    assert ac.liquidity_tier(10e6)["tier"] == "high"          # ≥$10M 含边界
    assert ac.liquidity_tier(9.99e6)["tier"] == "mid"
    assert ac.liquidity_tier(1e6)["tier"] == "mid"            # ≥$1M 含边界
    assert ac.liquidity_tier(0.99e6)["tier"] == "low"
    low = ac.liquidity_tier(0.5e6)
    assert "note_zh" in low and "谨慎" in low["note_zh"]       # 低档必须带谨慎解读标
    unk = ac.liquidity_tier(None)
    assert unk["status"] == "unknown" and "tier" not in unk    # 缺数据如实 unknown,绝不猜档


def test_liquidity_tier_nan_is_unknown():
    assert ac.liquidity_tier(float("nan"))["status"] == "unknown"


# ── beta_key 参数化:默认=美股原键(回归门语义);AU 键独立 ─────────────────
def _toy_px(n=300, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, n)), index=idx)


def test_compute_basic_risk_beta_key_default_unchanged():
    px, bench = _toy_px(), _toy_px(seed=8)
    out = sc.compute_basic_risk(px, bench)
    assert "beta_nasdaq" in out and "beta_axjo" not in out     # 默认=美股原行为


def test_compute_basic_risk_beta_key_axjo():
    px, bench = _toy_px(), _toy_px(seed=8)
    out = sc.compute_basic_risk(px, bench, beta_key="beta_axjo")
    assert "beta_axjo" in out and "beta_nasdaq" not in out
    # 键名只改名不改值:两次调用 β 数值必须一致
    assert out["beta_axjo"] == sc.compute_basic_risk(px, bench)["beta_nasdaq"]


# ── 数据卫生标记守门:B0 结论的常量别被将来误删(FMG 身份/COL 短史) ─────────
def test_data_hygiene_notes_present():
    assert "FMG" in fau.IDENTITY_NOTES, "FMG 身份连续性标记被删——B3 回测门依赖它"
    assert "COL" in fau.SHORT_HISTORY_NOTES, "COL 短史标记被删"
    assert "NCM" not in fau.STOCK_TICKERS, "NCM 已退市,不该回到池子"
    assert len(fau.STOCK_TICKERS) == 28


def test_au_names_cover_pool():
    missing = [n for n in fau.STOCK_TICKERS if n not in ac.AU_NAMES]
    assert not missing, f"AU 池有票缺中文名映射: {missing}"
