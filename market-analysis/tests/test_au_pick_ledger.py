"""test_au_pick_ledger.py — 澳股荐股账本(B3)单测。SPEC_AU_PICKS.md §3 的 1/2/8 条:
① 规则零克隆守门（同一对象,非同名复制品——防漂移命门）
② 账本幂等/append-only（照 test_ipo_alerts 范式：重复出榜不重记、历史行逐字节不变）
⑧ 美股 pick_ledger 路径回归守门（forward_ledger 零改；au 线绝不该动到美股配置/签名）

全部 canned fixtures·不碰网络（prices= 注入旁路 fl.settle 的真实取价；不落盘 web/docs）。
"""
import csv
import inspect

import numpy as np
import pandas as pd
import pytest

import au_pick_ledger as apl
import forward_ledger as fl
import pick_ledger as pk
import util_io


def _line(p0, p1, periods=10, start="2026-05-01"):
    idx = pd.bdate_range(start=start, periods=periods)
    return pd.Series(np.linspace(p0, p1, periods), index=idx)


def _pick(symbol, view="看好", date="2026-05-01", mom=100.0):
    return {"pick_date": date, "symbol": symbol, "view": view, "mom_pct": mom}


def _rows(log):
    with open(log, encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def patched(tmp_path, monkeypatch):
    monkeypatch.setattr(apl, "LOG", tmp_path / "au_pick_log.csv")
    monkeypatch.setattr(util_io, "write_json", lambda *a, **k: None)
    return tmp_path


# ── ① 规则/命中口径零克隆守门（S-1：防漂移命门）─────────────────────────
def test_rule_zero_clone_identity():
    """au_pick_ledger 必须直接 import 美股 pick_ledger 的挑票/命中函数与常量——
    同一对象（`is`），不是行为相似的复制品。任何人把这几个改成自写实现，此测立刻炸。"""
    assert apl._select_picks is pk._select_picks
    assert apl._outcome is pk._outcome
    assert apl._followable is pk._followable
    assert apl.MOM_WIN is pk.MOM_WIN
    assert apl.VOL_WIN is pk.VOL_WIN
    assert apl.N_PICKS is pk.N_PICKS


# ── ② 账本幂等 / append-only ────────────────────────────────────────────
def test_ledger_idempotent_no_duplicate(patched, monkeypatch):
    """同一荐股(同 symbol/pick_date/view)重复出榜 → 第二轮零新增（幂等）。"""
    monkeypatch.setattr(apl, "_load_picks", lambda: [_pick("BHP.AX", "看好")])
    prices = {"BHP.AX": _line(100, 120), "^AXJO": _line(100, 105)}

    out1 = apl.run(write=True, prices=prices)
    assert len(_rows(apl.LOG)) == 1
    assert out1["benchmark"] == "^AXJO"

    out2 = apl.run(write=True, prices=prices)
    assert len(_rows(apl.LOG)) == 1                    # 未重复 append
    assert out2["track_record"]["n_pending"] + out2["track_record"]["n_settled"] == 1


def test_ledger_append_only_history_byte_identical(patched, monkeypatch):
    """新一天出新票 → 只 append，历史前缀逐字节不变（照 test_ipo_alerts 范式）。"""
    monkeypatch.setattr(apl, "_load_picks", lambda: [_pick("BHP.AX", "看好")])
    prices = {"BHP.AX": _line(100, 120), "^AXJO": _line(100, 105)}
    apl.run(write=True, prices=prices)
    before = apl.LOG.read_bytes()

    monkeypatch.setattr(apl, "_load_picks",
                         lambda: [_pick("BHP.AX", "看好"),
                                  _pick("CBA.AX", "看淡", date="2026-05-02")])
    apl.run(write=True, prices={**prices, "CBA.AX": _line(50, 45)})
    after = apl.LOG.read_bytes()
    assert after[:len(before)] == before                # append-only:历史前缀一字节不改
    rows = _rows(apl.LOG)
    assert len(rows) == 2
    assert rows[0]["symbol"] == "BHP.AX" and rows[1]["symbol"] == "CBA.AX"


def test_load_picks_failsoft_when_universe_missing(patched, monkeypatch, tmp_path):
    """§1.4/任务描述:宽表(raw/au/au_stocks_prices.csv)暂缺(另一条线在建)时空跑不炸。
    显式指向 tmp_path 下不存在的路径(hermetic,不依赖本地 raw/au 是否已被另一条线填上)。"""
    monkeypatch.setattr(apl, "UNIVERSE", tmp_path / "does_not_exist.csv")
    assert apl._load_picks() == []                       # 不抛异常,空列表(非报错)
    out = apl.run(write=True, prices={})
    assert out["track_record"]["n_settled"] == 0         # 空跑不炸,诚实的0结算态


# ── ⑧ 美股 pick_ledger 路径回归守门(forward_ledger 零改;au 线不该动到美股配置)──
def test_us_pick_ledger_config_unchanged():
    """au_pick_ledger 只 import 不改写——美股 pick_ledger 的路径/基准/持有期须逐字节不变。"""
    assert pk.UNIVERSE == pk.RAW / "stocks_prices.csv"
    assert pk.BENCH == "QQQ"
    assert pk.HOLD_TD == 20
    assert pk.LOG == pk.BASE / "data" / "pick_ledger.csv"


def test_forward_ledger_settle_signature_unchanged():
    """S-1:forward_ledger 一个字节不动——au_pick_ledger._settle 靠关键字传参喂 fl.settle,
    签名一旦漂移这里先炸(比线上悄悄传错参更早发现)。"""
    sig = list(inspect.signature(fl.settle).parameters)
    assert sig == ["rows", "px", "bench", "hold", "trading_days",
                   "symbol_key", "followable_of", "outcome_of"]


def test_us_pick_ledger_still_settles_correctly(tmp_path, monkeypatch):
    """回归冒烟:美股 pick_ledger 自身在 au 线存在后仍能正常结算(未被共享 import 拖累)。"""
    monkeypatch.setattr(pk, "LOG", tmp_path / "pick_log.csv")
    monkeypatch.setattr(util_io, "write_json", lambda *a, **k: None)
    monkeypatch.setattr(pk, "_load_picks", lambda: [_pick("AAA", "看好")])
    prices = {"AAA": _line(100, 200, periods=35), "QQQ": _line(100, 101, periods=35)}
    out = pk.run(write=True, prices=prices)
    assert out["track_record"]["n_settled"] == 1
    assert out["track_record"]["call_hit_pct"] == 100.0
