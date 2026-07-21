"""test_pick_ledger_v2.py — v2(6-1 跳月动量,SPEC_PICKS_V2.md·R2)单测。规格 §2 的 10 条:
① 分歧机制(v1 选/v2 不选) ② 窗口精确(iloc[-22]/iloc[-148]) ③ 两账本互不污染
④ v2 幂等 append-only ⑤ v1 回归靶子(pick_ledger.csv 逐字节 + run() 返回不变,非 picks.json 整文件)
⑥ 短面板守门(128~147行→[]不抛) ⑦ sidecar 可 seal+verify ⑧ 合并完整性(v1 字段 + v2 块共存)
⑨ v2 整腿 fail-soft(异常不连坐 v1) ⑩(N3)最近21日走平→v1/v2 选票一致(重合 sanity)。

全部合成数据·不联网(prices= 注入旁路 fl.settle 的真实取价;不落盘 web/docs)。
"""
import csv

import numpy as np
import pandas as pd
import pytest

import ledger_sidecar as ls
import pick_ledger as pk
import util_io


def _line(p0, p1, periods=35, start="2026-05-01"):
    idx = pd.bdate_range(start=start, periods=periods)
    return pd.Series(np.linspace(p0, p1, periods), index=idx)


def _pick(symbol, view="看好", date="2026-05-01", mom=100.0):
    return {"pick_date": date, "symbol": symbol, "view": view, "mom_pct": mom}


def _rows(log):
    with open(log, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _strip_generated(d):
    return {k: v for k, v in d.items() if k != "generated"}


@pytest.fixture
def patched(tmp_path, monkeypatch):
    monkeypatch.setattr(pk, "LOG", tmp_path / "pick_log.csv")
    monkeypatch.setattr(pk, "LOG_V2", tmp_path / "pick_log_v2.csv")
    monkeypatch.setattr(util_io, "write_json", lambda *a, **k: None)
    return tmp_path


# ── ① 分歧机制:合成"最近21日暴涨票"——v1 选中、v2 不选(规格核心示范) ─────────
def test_v1_v2_diverge_on_recent_spike():
    """SPIKE:前段(超过21日前)与 8 只基线票同量级的温和走势 + 少量真实感噪声,最近 21 个交易日
    平滑拉高 35%。v1(动量含最近21日)会看到这段拉升、v2(跳过最近21日)看不到。
    固定随机种子(同既有 test_select_picks_momentum_lowvol 的惯例)——经脚本扫种子验证,
    seed=3 两侧 margin 均 >0.2(非临界 tie),不是巧合幸存的脆弱构造。"""
    idx = pd.bdate_range("2025-01-01", periods=160)
    n = len(idx)
    rng = np.random.default_rng(3)
    data = {}
    for i in range(1, 9):
        growth = 1.0 + 0.03 * i
        daily_r = growth ** (1.0 / n) - 1.0
        noise = rng.normal(0, 0.008, n)
        data[f"B{i}"] = 100 * np.cumprod(1 + daily_r + noise)
    spike_days = 21
    flat_noise = rng.normal(0, 0.004, n - spike_days)
    flat = 100 * np.cumprod(1 + flat_noise)
    daily_spike_r = (1 + 0.35) ** (1.0 / spike_days) - 1.0
    ramp = flat[-1] * np.cumprod(1 + np.full(spike_days, daily_spike_r))
    data["SPIKE"] = np.concatenate([flat, ramp])
    prices = pd.DataFrame(data, index=idx)

    v1 = pk._select_picks(prices)
    v2 = pk._select_picks_v2(prices)
    v1_bull = {p["symbol"] for p in v1 if p["view"] == "看好"}
    v2_bull = {p["symbol"] for p in v2 if p["view"] == "看好"}
    assert "SPIKE" in v1_bull                     # v1:最近21日的拉升被算进动量 → 头部看好
    assert "SPIKE" not in v2_bull                  # v2:跳过最近21日 → 看不到这段拉升,选不中


# ── ② 窗口精确:v2 动量 == iloc[-22]/iloc[-148](148行·off-by-one 守门线上) ────
def test_v2_momentum_window_precision():
    idx = pd.bdate_range("2025-01-01", periods=148)
    prices = pd.DataFrame({
        "AAA": np.linspace(50, 200, 148),
        "BBB": np.linspace(200, 50, 148),
    }, index=idx)
    expected = round(float(prices["AAA"].iloc[-22] / prices["AAA"].iloc[-148] - 1) * 100, 1)
    v1_formula = round(float(prices["AAA"].iloc[-1] / prices["AAA"].iloc[-127] - 1) * 100, 1)
    picks = pk._select_picks_v2(prices)
    aaa = next(p for p in picks if p["symbol"] == "AAA")
    assert aaa["mom_pct"] == expected
    assert expected != v1_formula                  # 确实是跳月公式,不是裸 v1 公式换皮


# ── ③ 两账本互不污染:同一 symbol/date/view 两版都出票,各记各的、零交叉 ────────
def test_ledgers_no_cross_pollution(patched, monkeypatch):
    same_pick = [_pick("CCC", "看好", date="2026-06-01")]
    monkeypatch.setattr(pk, "_load_picks", lambda: same_pick)
    monkeypatch.setattr(pk, "_load_picks_v2", lambda: same_pick)
    px = {"CCC": _line(100, 120, periods=10), "QQQ": _line(100, 105, periods=10)}

    pk.run(write=True, prices=px)
    pk.run_v2(write=True, prices=px, existing={})

    v1_rows, v2_rows = _rows(pk.LOG), _rows(pk.LOG_V2)
    assert len(v1_rows) == 1 and v1_rows[0]["symbol"] == "CCC"
    assert len(v2_rows) == 1 and v2_rows[0]["symbol"] == "CCC"
    assert pk.LOG != pk.LOG_V2                      # 独立文件路径


# ── ④ v2 幂等 append-only ──────────────────────────────────────────────
def test_v2_idempotent_append_only(patched, monkeypatch):
    monkeypatch.setattr(pk, "_load_picks_v2", lambda: [_pick("AAA", "看好")])
    px = {"AAA": _line(100, 120, periods=10), "QQQ": _line(100, 105, periods=10)}
    pk.run_v2(write=True, prices=px, existing={})
    pk.run_v2(write=True, prices=px, existing={})
    assert len(_rows(pk.LOG_V2)) == 1


# ── ⑤ v1 回归靶子(S2 澄清):pick_ledger.csv 逐字节 + run() 返回 dict(除时间戳)不变 ──
def test_v1_regression_byte_identical_log_and_stable_return(patched, monkeypatch):
    monkeypatch.setattr(pk, "_load_picks", lambda: [_pick("AAA", "看好")])
    px = {"AAA": _line(100, 200), "QQQ": _line(100, 101)}
    out1 = pk.run(write=True, prices=px)
    log_before = pk.LOG.read_bytes()

    # 跑一轮真实 v2(独立选票/独立数据)——不得动到 v1 账本
    monkeypatch.setattr(pk, "_load_picks_v2", lambda: [_pick("BBB", "看淡")])
    pk.run_v2(write=True, prices={"BBB": _line(150, 100), "QQQ": _line(100, 101)}, existing={})
    assert pk.LOG.read_bytes() == log_before

    # 同样输入重跑 run():AAA 已结算、_load_picks 仍只给 AAA → 幂等,无新增/无重结算
    out2 = pk.run(write=True, prices=px)
    assert _strip_generated(out1) == _strip_generated(out2)


# ── ⑥ 短面板守门:128~147 行 → v2 返回 [] 不抛(B2) ───────────────────────
def test_short_panel_gate_no_raise():
    for length in (128, 140, 147):
        idx = pd.bdate_range("2025-01-01", periods=length)
        prices = pd.DataFrame({"AAA": np.linspace(100, 110, length)}, index=idx)
        assert pk._select_picks_v2(prices) == []
    idx148 = pd.bdate_range("2025-01-01", periods=148)
    prices148 = pd.DataFrame({"AAA": np.linspace(100, 200, 148),
                               "BBB": np.linspace(200, 100, 148)}, index=idx148)
    assert pk._select_picks_v2(prices148) != []     # 148 行起能正常出票


# ── ⑦ sidecar:pick_ledger_v2.csv 可 seal+verify(S4) ─────────────────────
def test_sidecar_pick_ledger_v2_seal_and_verify(tmp_path):
    core = ["pick_date", "symbol", "view", "mom_pct"]
    assert ("pick_ledger_v2.csv", core) in ls.SPECS       # 已挂进 SPECS
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    p = data_dir / "pick_ledger_v2.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pk.HEADER_V2)
        w.writeheader()
        w.writerow({**{k: "" for k in pk.HEADER_V2},
                    "pick_date": "2026-07-21", "symbol": "AAA", "view": "看好", "mom_pct": "5.0",
                    "settled": "False", "dropped": "False"})
    manifest = tmp_path / "chain.csv"
    specs = [("pick_ledger_v2.csv", core)]
    n, refusals = ls.seal_all(data_dir=data_dir, manifest=manifest, specs=specs)
    assert n == 1 and refusals == []
    assert ls.verify_all(data_dir=data_dir, manifest=manifest, specs=specs) == [("pick_ledger_v2.csv", [])]


# ── ⑧ 合并完整性:picks.json 同时有完整 v1 字段与 v2 块,v1 子结构未被破坏 ─────
def test_merge_completeness_v1_and_v2_coexist(tmp_path, monkeypatch):
    monkeypatch.setattr(pk, "LOG", tmp_path / "pick_log.csv")
    monkeypatch.setattr(pk, "LOG_V2", tmp_path / "pick_log_v2.csv")
    captured = {}
    monkeypatch.setattr(util_io, "write_json",
                         lambda name, payload, **k: captured.setdefault(name, []).append(payload))

    monkeypatch.setattr(pk, "_load_picks", lambda: [_pick("AAA", "看好")])
    px = {"AAA": _line(100, 120, periods=10), "QQQ": _line(100, 105, periods=10)}
    v1_out = pk.run(write=True, prices=px)
    assert captured["picks.json"][-1]["pick_rule"] == pk.PICK_RULE
    assert "v2" not in captured["picks.json"][-1]          # v1 那次写入还没有 v2 块

    monkeypatch.setattr(pk, "_load_picks_v2", lambda: [_pick("BBB", "看淡")])
    px_v2 = {"BBB": _line(150, 100, periods=10), "QQQ": _line(100, 105, periods=10)}
    v2_block = pk.run_v2(write=True, prices=px_v2, existing=v1_out)

    merged = captured["picks.json"][-1]                    # run_v2 那次 write_json 的实际 payload
    assert merged["pick_rule"] == pk.PICK_RULE              # v1 字段完整保留,子结构未被破坏
    assert merged["track_record"] == v1_out["track_record"]
    assert merged["recent"] == v1_out["recent"]
    assert "v2" in merged
    assert merged["v2"] == v2_block
    assert merged["v2"]["pick_rule"] == pk.PICK_RULE_V2
    assert merged["v2"]["launch_date"] == pk.LAUNCH_DATE_V2


# ── ⑨ v2 fail-soft:v2 腿抛异常 → v1 输出与退出码不受影响(B3) ────────────────
def test_v2_failsoft_does_not_affect_v1(patched, monkeypatch):
    monkeypatch.setattr(pk, "_load_picks", lambda: [_pick("AAA", "看好")])
    px = {"AAA": _line(100, 200), "QQQ": _line(100, 101)}
    out1 = pk.run(write=True, prices=px)

    def _boom():
        raise RuntimeError("模拟 v2 选票逻辑崩了")
    monkeypatch.setattr(pk, "_load_picks_v2", _boom)

    result = pk.run_v2(write=True, existing={})     # 不应抛异常出函数
    assert result is None                             # fail-soft:吞异常返回 None

    out2 = pk.run(write=True, prices=px)               # v1 完全不受影响(幂等重跑同结果)
    assert _strip_generated(out1) == _strip_generated(out2)


# ── ⑩(N3)最近21日走平的合成面板 → v1 选票 == v2 选票(重合 sanity,示范 S5)────
def test_recent_flat_overlap_v1_v2_agree():
    """全程恒定日收益率(无近端 vs 远端的结构性差异)→ 任一 126 日窗口(不论是否跳过最近21日)
    算出的动量都相同 → v1/v2 选票完全一致——示范 S5 披露"多数时期两版几乎同票"。"""
    idx = pd.bdate_range("2025-01-01", periods=160)
    n = len(idx)
    rates = np.linspace(-0.0008, 0.0012, 9)
    data = {f"S{i}": 100 * np.cumprod(1 + np.full(n, r)) for i, r in enumerate(rates)}
    prices = pd.DataFrame(data, index=idx)
    v1 = pk._select_picks(prices)
    v2 = pk._select_picks_v2(prices)
    key = lambda picks: {(p["symbol"], p["view"]) for p in picks}
    assert key(v1) == key(v2)
    assert len(v1) == len(v2) == 6
