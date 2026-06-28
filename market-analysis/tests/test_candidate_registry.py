"""test_candidate_registry.py — 自生长 P-A 地基:注册登记簿的 append-only / 锚点不变 / 新候选自动登记。"""
import csv

import pytest

import candidate_registry as reg
import candidate_space as cs


def _rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_seed_registers_all_candidates_at_today(tmp_path):
    p = tmp_path / "reg.csv"
    n = reg.sync(today="2026-06-26", path=p)
    assert n == cs.N_DECLARED                       # 首次 sync 登记全部候选(N_DECLARED)
    rows = _rows(p)
    assert len(rows) == cs.N_DECLARED
    assert all(r["declared_date"] == "2026-06-26" for r in rows)   # 旧候选锚=采纳日
    ids = {c["candidate_id"] for c in cs.enumerate_candidates()}
    assert {r["candidate_id"] for r in rows} == ids


def test_resync_is_append_only_no_change(tmp_path):
    p = tmp_path / "reg.csv"
    reg.sync(today="2026-06-26", path=p)
    # 隔天再 sync:已登记的一个不加、锚点一字不改
    n2 = reg.sync(today="2026-07-15", path=p)
    assert n2 == 0
    rows = _rows(p)
    assert len(rows) == cs.N_DECLARED
    assert all(r["declared_date"] == "2026-06-26" for r in rows)   # 历史行不被改成新日期


def test_new_candidate_gets_its_own_later_anchor(tmp_path, monkeypatch):
    p = tmp_path / "reg.csv"
    reg.sync(today="2026-06-26", path=p)
    base = cs.enumerate_candidates()
    extra = {"family": "calendar", "key": "fake_new", "params": {"x": 1},
             "candidate_id": "cal_fake000new"}
    monkeypatch.setattr(cs, "enumerate_candidates", lambda: base + [extra])
    n = reg.sync(today="2026-09-01", path=p)        # 新候选首次出现 → 锚=当天
    assert n == 1
    anchors = reg.load_anchors(p)
    assert anchors["cal_fake000new"] == "2026-09-01"           # 新候选更晚的锚
    assert anchors[base[0]["candidate_id"]] == "2026-06-26"    # 老候选锚不变


def test_load_anchors_covers_space(tmp_path):
    p = tmp_path / "reg.csv"
    reg.sync(today="2026-06-26", path=p)
    anchors = reg.load_anchors(p)
    assert set(anchors) == {c["candidate_id"] for c in cs.enumerate_candidates()}
