"""防历史塌缩守卫 — 取数不许用短序列覆盖长历史（2026-09-16 实测事故）。

事故经过（真事，不是假想）：
  `^VIX3M` 的 `yf.download(start=2000)` 返回空 → 落到 `Ticker.history(period="3mo")` 兜底
  → **该兜底立刻写缓存**，把 6717 行的 VIX3M.csv 覆盖成 1 行。
  而 `_record_health` 当时只查 `rows == 0` 和日期新鲜度，于是写出
  `{"rows": 1, "status": "ok"}` —— 历史静默消失，看板还报"新鲜 ✓"。
  下游 `vix_backwardation` 因子的 556 个观测全丢 → `_segment_lens` 返回 None → p 变 1.0
  → **公开裁决静默改变**。`data/raw` 在 .gitignore 里，git 拿不回来。

所以守门点是三条，缺一条这个事故就会重演：
  ① 写入前拦（`_save_series` 保留缓存、不覆盖）—— 事后发现来不及，数据已经没了；
  ② 拦下来要**可见**（status="shrunk"，不是 "ok"）—— 悄悄自愈等于下次还犯；
  ③ freshness 必须跟着变非 ok —— 前端 `renderFreshness` 只看 freshness，
     只改 status 不改 freshness，页面照样绿字"新鲜 ✓"，等于白拦。

hermetic：monkeypatch RAW_DIR 到 tmp_path，纯本地 CSV，不联网、不碰 data/。
"""
import pandas as pd
import pytest

import fetch_data as fd


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.setattr(fd, "RAW_DIR", tmp_path)
    fd.HEALTH["sources"] = {}          # 模块级全局，逐测试清干净
    return tmp_path


def _series(n, name="VIX3M", start="2000-01-03"):
    idx = pd.date_range(start, periods=n, freq="B")
    s = pd.Series(range(n), index=idx, dtype=float, name=name)
    s.index.name = "Date"
    return s


def _write_cache(raw, n, name="VIX3M"):
    _series(n, name).to_csv(raw / f"{name}.csv")


# ── ① 写入前拦住 ────────────────────────────────────────────────────
def test_short_fetch_does_not_clobber_long_cache(raw):
    """就是事故那一幕：缓存 6717 行、新取 1 行 → 必须保留缓存。"""
    _write_cache(raw, 6717)
    got = fd._save_series("VIX3M", _series(1, start="2026-09-15"))
    assert len(got) == 6717, "短序列覆盖了长历史 —— 事故会重演"
    on_disk = pd.read_csv(raw / "VIX3M.csv", index_col=0).squeeze("columns")
    assert len(on_disk) == 6717, "磁盘上的缓存被覆写了"
    assert got.attrs.get("shrink_blocked") == [1, 6717], "拦下了但没留痕,事后查不出哪天开始坏的"


def test_normal_growth_is_written(raw):
    """正常情况必须照常写 —— 守卫不能把每天多一行的正常增长也挡掉。"""
    _write_cache(raw, 500)
    got = fd._save_series("VIX3M", _series(501))
    assert len(got) == 501
    assert len(pd.read_csv(raw / "VIX3M.csv", index_col=0)) == 501
    assert "shrink_blocked" not in got.attrs


def test_small_shrink_within_tolerance_is_allowed(raw):
    """供应商回修个别点位（仍 ≥90%）不该触发 —— 留容忍带，免得天天误报。"""
    _write_cache(raw, 1000)
    got = fd._save_series("VIX3M", _series(950))
    assert len(got) == 950 and "shrink_blocked" not in got.attrs


def test_short_cache_is_not_guarded(raw):
    """缓存本身很短（新 ticker 刚开始积累）时不设防,否则挡住正常起步。"""
    _write_cache(raw, 50)                     # < SHRINK_MIN_CACHE
    got = fd._save_series("VIX3M", _series(5))
    assert len(got) == 5, "对刚上市的新序列也设防会挡住正常积累"


def test_no_cache_writes_through(raw):
    got = fd._save_series("BRANDNEW", _series(3, name="BRANDNEW"))
    assert len(got) == 3 and (raw / "BRANDNEW.csv").exists()


# ── ② 拦下来必须可见 ──────────────────────────────────────────────
def test_blocked_shrink_is_reported_as_shrunk_not_ok(raw):
    """数据保住了,但**这一轮取数塌缩了**必须报出来 —— 报 ok 等于白拦。"""
    _write_cache(raw, 6717)
    kept = fd._save_series("VIX3M", _series(1, start="2026-09-15"))
    fd._record_health("VIX3M", "asset", "Yahoo Finance", "^VIX3M", "history_fallback", kept)
    h = fd.HEALTH["sources"]["asset:VIX3M"]
    assert h["status"] == "shrunk", f"塌缩被报成 {h['status']!r} —— 事故当天报的就是 'ok'"
    assert h["rows"] == 6717
    assert h["shrink_blocked"] == [1, 6717]


def test_healthy_series_still_ok(raw):
    """别把守卫做成人人喊狼：正常序列仍须是 ok。"""
    s = _series(500, start="2024-01-01")
    s.index = pd.date_range(pd.Timestamp.today().normalize() - pd.Timedelta(days=499),
                            periods=500, freq="D")
    fd._record_health("NASDAQ", "asset", "Yahoo Finance", "^IXIC", "live", s)
    assert fd.HEALTH["sources"]["asset:NASDAQ"]["status"] == "ok"


# ── ③ freshness 必须跟着变 ────────────────────────────────────────
def test_shrunk_degrades_freshness(raw, monkeypatch):
    """前端 renderFreshness 只看 summary.freshness;不打成非 ok 页面照样显示"新鲜 ✓"。"""
    monkeypatch.setattr(fd, "WEB_DIR", raw)
    _write_cache(raw, 6717)
    kept = fd._save_series("VIX3M", _series(1, start="2026-09-15"))
    fd._record_health("VIX3M", "asset", "Yahoo Finance", "^VIX3M", "history_fallback", kept)
    fd._write_health()
    sm = fd.HEALTH["summary"]
    assert sm["shrunk"] == 1, "summary 里没有 shrunk 计数 → 看板上根本看不到"
    assert sm["freshness"] != "ok", "取数塌缩了 freshness 仍报 ok —— 页面会显示绿字新鲜 ✓"


def test_history_fallback_path_goes_through_the_guard():
    """源码守门:Ticker.history 兜底路径**就是**事故现场,不许再裸写 to_csv。"""
    from pathlib import Path
    src = Path(fd.__file__).read_text(encoding="utf-8")
    i = src.index("Ticker.history 回退")
    body = src[i:i + 400]
    assert "_save_series" in body, "兜底路径绕过了防塌缩闸 —— 事故会原样重演"
    assert 'to_csv(RAW_DIR / f"{name}.csv")' not in body, "兜底路径仍在裸写缓存"


def test_all_per_name_cache_writes_go_through_the_guard():
    """全局守门:per-name 缓存只许由 _save_series 落盘,新增取数路径忘了走闸就会红。"""
    from pathlib import Path
    src = Path(fd.__file__).read_text(encoding="utf-8")
    bare = src.count('to_csv(RAW_DIR / f"{name}.csv")')
    assert bare == 1, (f"发现 {bare} 处裸写 per-name 缓存;应当只剩 _save_series 内部那一处"
                       "(新加的取数路径请改走 _save_series)")
