"""test_llm_monthly.py — 验证 llm_monthly_read 的聚合/grounding/月度去重/节流守卫。

原则（同 test_llm_weekly_read）：绝不调真实 LLM；只测纯聚合 + 日志 + 守卫逻辑；
验证 grounding（摘要数字全来自输入、不暴露原始浮点）、降级（缺文件不崩）、YYYY-MM 去重。
"""
import csv
import datetime
import sys
import pytest
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import llm_monthly_read as lmr


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    web = tmp_path / "web"; web.mkdir()
    data = tmp_path / "data"; data.mkdir()
    monkeypatch.setattr(lmr, "WEB", web)
    monkeypatch.setattr(lmr, "DATA", data)
    monkeypatch.setattr(lmr, "LOG", data / "llm_monthly_log.csv")
    return {"web": web, "data": data}


def _write_composite(data_dir, rows):
    with open(data_dir / "composite_log.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["date", "stance", "score"])
        w.writerows(rows)


def test_load_composite_month_filters_to_month(fake_repo):
    _write_composite(fake_repo["data"], [
        ["2026-05-30", "偏防御", "-0.3"], ["2026-06-02", "偏积极", "0.2"],
        ["2026-06-29", "偏积极", "0.5"], ["2026-07-01", "中性", "0.0"]])
    rows = lmr._load_composite_month(datetime.date(2026, 6, 15))
    assert [r["date"] for r in rows] == ["2026-06-02", "2026-06-29"]   # 只本月


def test_format_stance_lines_hides_raw_score(fake_repo):
    lines, stances = lmr._format_stance_lines([{"date": "2026-06-02", "stance": "偏积极", "score": "0.5"}])
    assert "偏积极" in lines and "0.5" not in lines        # 程度词,不暴露原始浮点
    assert stances == ["偏积极"]


def test_format_stance_lines_empty_degrades(fake_repo):
    lines, stances = lmr._format_stance_lines([])
    assert "暂无" in lines and stances == []               # 缺数据不崩、给兜底


def test_monthly_dedup_yyyymm(fake_repo):
    today = datetime.date(2026, 6, 30)
    assert not lmr._already_logged_this_month(today)
    lmr._append_log(today, 6, "第一次月报")
    assert lmr._already_logged_this_month(today)
    lmr._append_log(today, 6, "同月第二次")               # 同 YYYY-MM → 不重复
    with open(fake_repo["data"] / "llm_monthly_log.csv", encoding="utf-8") as f:
        assert sum(1 for _ in f) == 1 + 1                  # header + 1 行


def test_run_grounded_with_mock_llm(fake_repo, monkeypatch):
    _write_composite(fake_repo["data"], [["2026-06-02", "偏积极", "0.2"], ["2026-06-29", "偏积极", "0.5"]])
    monkeypatch.setattr(lmr, "_llm_key", lambda: "fakekey")
    monkeypatch.setattr(lmr, "_llm", lambda prompt: "测试月度回顾文本。（这是数据回顾不是预测）")
    out = lmr.run(write=False, force=True)                 # force 跳过月末日期守卫;write=False 不落盘
    assert out["text"].startswith("测试月度回顾")
    assert out["stances"] == ["偏积极", "偏积极"]
    assert "非预测" in out["caveat"] and "会错" in out["caveat"]
    assert out["month"] == lmr._month_key(datetime.date.today())


def test_run_skips_without_key(fake_repo, monkeypatch):
    monkeypatch.setattr(lmr, "_llm_key", lambda: None)
    assert lmr.run(write=False, force=True) is None        # 无 key 静默跳过
