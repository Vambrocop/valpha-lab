"""test_llm_weekly_read.py — 验证 llm_weekly_read 的聚合/grounding/去重。

关键设计原则：
  - 绝不调用真实 LLM（所有 LLM 调用均被 mock 或绕过）
  - 只测纯聚合函数和日志逻辑（build_weekly_summary、_append_log、_format_stance_lines 等）
  - 验证"grounding"：摘要数字全部来自测试输入，不含 LLM 编造
  - 验证"降级"：缺文件 → 不崩溃，返回合理默认值
  - 验证"ISO-week 去重"：同周只记一行
"""
import csv
import datetime
import json
import sys
import pytest
from pathlib import Path

# ── 把 scripts/ 加入路径（与 conftest.py 同方向，防止重复插入）──────────────
SCRIPTS = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import llm_weekly_read as lwr


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures：在 tmp_path 建立最小的 web/ + data/ 目录结构
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    """把模块全局路径重定向到 tmp_path 下的假仓库。"""
    web  = tmp_path / "web";  web.mkdir()
    data = tmp_path / "data"; data.mkdir()
    monkeypatch.setattr(lwr, "WEB",  web)
    monkeypatch.setattr(lwr, "DATA", data)
    monkeypatch.setattr(lwr, "LOG",  data / "llm_weekly_log.csv")
    return {"web": web, "data": data, "tmp": tmp_path}


def _write_composite_log(data_dir: Path, rows: list):
    """helper：写 composite_log.csv。rows = [(date_str, stance, score), ...]"""
    path = data_dir / "composite_log.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "stance", "score"])
        for r in rows:
            w.writerow(r)


def _write_regime(web_dir: Path, vix: float = 20.0, vix_label: str = "中性"):
    """helper：写最小 market_regime.json。"""
    payload = {
        "asof": "2026-06-23",
        "composite": "当前：波动率中性 + 曲线正常",
        "components": [
            {"name": "波动率 VIX", "value": vix, "label": vix_label, "asof": "2026-06-23"},
            {"name": "信用利差 Baa-10Y", "value": 1.5, "label": "偏低", "asof": "2026-06-22"},
        ]
    }
    (web_dir / "market_regime.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _write_scorecard(web_dir: Path, base_rate: float = 66.6, n: int = 3000):
    """helper：写最小 scorecard.json。"""
    payload = {"model_calibration": {"base_rate_pct": base_rate, "n_total": n}}
    (web_dir / "scorecard.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _write_valpha150(web_dir: Path, stocks: list):
    """helper：写最小 valpha150.json。stocks = [{"t": ..., "sec": ..., "w1": ...}, ...]"""
    payload = {"generated": "2026-06-24", "stocks": stocks}
    (web_dir / "valpha150.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. ISO-week 工具函数
# ─────────────────────────────────────────────────────────────────────────────

def test_iso_week_format():
    d = datetime.date(2026, 6, 24)  # 周二
    w = lwr._iso_week(d)
    assert w.startswith("2026-W")
    assert len(w) == 8  # YYYY-Www (W = literal, ww = 2 digits)


def test_week_label_spans_mon_to_sun():
    d = datetime.date(2026, 6, 24)  # 周二
    label = lwr._week_label(d)
    # 应包含 Monday 2026-06-22 和 Sunday 2026-06-28
    assert "2026-06-22" in label
    assert "2026-06-28" in label


def test_iso_week_same_for_all_days_in_week():
    monday    = datetime.date(2026, 6, 22)
    wednesday = datetime.date(2026, 6, 24)
    sunday    = datetime.date(2026, 6, 28)
    assert lwr._iso_week(monday) == lwr._iso_week(wednesday) == lwr._iso_week(sunday)


# ─────────────────────────────────────────────────────────────────────────────
# 2. _load_composite_week — 只返回当周行，跨周行被过滤
# ─────────────────────────────────────────────────────────────────────────────

def test_composite_week_filters_to_current_week(fake_repo):
    data_dir = fake_repo["data"]
    # ISO-week 26: Mon 2026-06-22 ~ Sun 2026-06-28
    # ISO-week 25: Mon 2026-06-15 ~ Sun 2026-06-21 (前一周，包含 06-21 周日)
    # today = 2026-06-24 (周三, W26)
    _write_composite_log(data_dir, [
        ("2026-06-15", "偏防御", "-0.2"),   # W25 — 应被过滤
        ("2026-06-21", "偏积极", "0.23"),   # W25 Sunday — 应被过滤（ISO 周从周一开始）
        ("2026-06-22", "偏积极", "0.20"),   # W26 Monday — 本周
        ("2026-06-24", "偏积极", "0.14"),   # W26 Wednesday — 本周
    ])
    today = datetime.date(2026, 6, 24)
    rows = lwr._load_composite_week(today)
    dates = [r["date"] for r in rows]
    assert "2026-06-24" in dates
    assert "2026-06-22" in dates   # same ISO week (Mon of W26)
    assert "2026-06-21" not in dates  # previous ISO week (W25 Sunday)
    assert "2026-06-15" not in dates  # previous week (W25 Monday)


def test_composite_week_missing_file_returns_empty(fake_repo):
    """文件不存在 → 返回空列表，不崩溃。"""
    rows = lwr._load_composite_week(datetime.date(2026, 6, 24))
    assert rows == []


# ─────────────────────────────────────────────────────────────────────────────
# 3. _format_stance_lines — score 转程度词、不暴露原始浮点
# ─────────────────────────────────────────────────────────────────────────────

def test_format_stance_no_raw_scores():
    """stance 文本不得出现原始 score 浮点（如 0.23 或 -0.14）。"""
    rows = [
        {"date": "2026-06-21", "stance": "偏积极", "score": "0.229"},
        {"date": "2026-06-22", "stance": "偏积极", "score": "0.205"},
        {"date": "2026-06-24", "stance": "偏积极", "score": "0.138"},
    ]
    text, stances = lwr._format_stance_lines(rows)
    # 不应出现原始浮点
    assert "0.229" not in text
    assert "0.205" not in text
    assert "0.138" not in text
    # 应有程度词
    assert "偏积极" in text
    # stances 列表完整
    assert stances == ["偏积极", "偏积极", "偏积极"]


def test_format_stance_empty_rows():
    text, stances = lwr._format_stance_lines([])
    assert "暂无" in text or text.startswith("（")
    assert stances == []


def test_format_stance_defensive_score():
    rows = [{"date": "2026-06-20", "stance": "偏防御", "score": "-0.5"}]
    text, stances = lwr._format_stance_lines(rows)
    assert "偏防御" in text
    assert "-0.5" not in text


# ─────────────────────────────────────────────────────────────────────────────
# 4. _load_regime — 提取真实值，文件缺失降级
# ─────────────────────────────────────────────────────────────────────────────

def test_load_regime_extracts_real_values(fake_repo):
    web = fake_repo["web"]
    _write_regime(web, vix=19.5, vix_label="中性")
    lines = lwr._load_regime()
    combined = "\n".join(lines)
    # 必须包含真实 VIX 数值（系统算出）
    assert "19.5" in combined
    # 必须包含标签
    assert "中性" in combined


def test_load_regime_missing_file_returns_empty(fake_repo):
    lines = lwr._load_regime()
    assert lines == []


# ─────────────────────────────────────────────────────────────────────────────
# 5. _load_scorecard_summary — 提取基准胜率
# ─────────────────────────────────────────────────────────────────────────────

def test_load_scorecard_returns_real_numbers(fake_repo):
    _write_scorecard(fake_repo["web"], base_rate=66.6, n=3018)
    rate, n = lwr._load_scorecard_summary()
    assert "66.6" in rate
    assert "3018" in n


def test_load_scorecard_missing_file_returns_dash(fake_repo):
    rate, n = lwr._load_scorecard_summary()
    assert rate == "—"
    assert n == "—"


# ─────────────────────────────────────────────────────────────────────────────
# 6. _load_movers — 只暴露板块+涨跌幅，不点个股名
# ─────────────────────────────────────────────────────────────────────────────

def test_load_movers_no_stock_names(fake_repo):
    """返回文本不得出现具体 ticker（如 NVDA、AAPL）。"""
    stocks = [
        {"t": "NVDA", "n": "英伟达", "sec": "半导体", "w1": -5.84},
        {"t": "MRNA", "n": "莫德纳", "sec": "医疗",   "w1": 17.02},
        {"t": "AAPL", "n": "苹果",   "sec": "科技",   "w1": -0.72},
        {"t": "JPM",  "n": "摩根大通","sec": "金融",   "w1":  4.61},
        {"t": "CAT",  "n": "卡特彼勒","sec": "工业",   "w1":  5.39},
        {"t": "TTD",  "n": "TradeDesk","sec": "通信服务","w1": -6.95},
    ]
    _write_valpha150(fake_repo["web"], stocks)
    text = lwr._load_movers(top_n=2)
    # 不应出现 ticker
    for ticker in ["NVDA", "MRNA", "AAPL", "JPM", "CAT", "TTD"]:
        assert ticker not in text
    # 不应出现股票中文名
    for name in ["英伟达", "莫德纳", "苹果", "摩根大通"]:
        assert name not in text
    # 应包含板块
    assert "医疗" in text or "半导体" in text or "通信服务" in text


def test_load_movers_contains_real_pct(fake_repo):
    """涨跌幅必须是真实 w1 数值。"""
    stocks = [
        {"t": "A", "n": "A", "sec": "科技", "w1": 17.0},
        {"t": "B", "n": "B", "sec": "能源", "w1": -11.0},
    ]
    _write_valpha150(fake_repo["web"], stocks)
    text = lwr._load_movers(top_n=1)
    assert "17.0" in text
    assert "11.0" in text  # 跌幅（带负号）


def test_load_movers_missing_file_returns_empty(fake_repo):
    assert lwr._load_movers() == ""


def test_load_movers_null_w1_skipped(fake_repo):
    """w1 为 null 的条目不计入排名（不崩溃）。"""
    stocks = [
        {"t": "A", "n": "A", "sec": "科技", "w1": None},
        {"t": "B", "n": "B", "sec": "能源", "w1": 5.0},
    ]
    _write_valpha150(fake_repo["web"], stocks)
    # 只有一只有效 w1，不崩溃
    text = lwr._load_movers(top_n=1)
    assert isinstance(text, str)


# ─────────────────────────────────────────────────────────────────────────────
# 7. build_weekly_summary — 完整聚合，grounding 验证
# ─────────────────────────────────────────────────────────────────────────────

def test_build_weekly_summary_grounded(fake_repo):
    """摘要中的数字（VIX、基准胜率）全部来自输入文件，不会凭空出现。"""
    web  = fake_repo["web"]
    data = fake_repo["data"]

    # 2026-06-22 (Mon W26) and 2026-06-24 (Wed W26) are in same ISO week
    _write_composite_log(data, [
        ("2026-06-22", "偏积极", "0.229"),
        ("2026-06-24", "偏积极", "0.138"),
    ])
    _write_regime(web, vix=19.5)
    _write_scorecard(web, base_rate=66.6, n=3018)

    today = datetime.date(2026, 6, 24)
    s = lwr.build_weekly_summary(today)

    # stance_trend 只含真实 stance 值
    assert set(s["stance_trend"]).issubset({"偏积极", "偏防御", "中性", "强积极", "强防御"})
    # regime_text 含真实 VIX 值
    assert "19.5" in s["regime_text"]
    # scorecard 含真实基准胜率
    assert "66.6" in s["base_rate_pct"]
    # n_days 正确（两行均在 W26 内）
    assert s["n_days"] == 2
    # week_of 格式
    assert s["week_of"].startswith("2026-W")


def test_build_weekly_summary_all_missing(fake_repo):
    """全部数据文件缺失 → 不崩溃，返回合理默认值。"""
    today = datetime.date(2026, 6, 24)
    s = lwr.build_weekly_summary(today)
    assert s["n_days"] == 0
    assert s["stance_trend"] == []
    assert s["base_rate_pct"] == "—"
    assert isinstance(s["regime_text"], str)
    assert isinstance(s["week_of"], str)


def test_build_weekly_summary_coverage_label(fake_repo):
    data = fake_repo["data"]
    # 只有 1 天 → 不足3天
    _write_composite_log(data, [("2026-06-24", "偏积极", "0.14")])
    s = lwr.build_weekly_summary(datetime.date(2026, 6, 24))
    assert "不足" in s["coverage"] or s["coverage"].startswith("不足")


# ─────────────────────────────────────────────────────────────────────────────
# 8. _append_log — ISO-week 去重（不改历史）
# ─────────────────────────────────────────────────────────────────────────────

def test_append_log_dedup_per_iso_week(fake_repo):
    """同一 ISO-week 只记一条，第二次调用返回 False 且文件不变。"""
    week = "2026-W26"
    wrote1 = lwr._append_log(week, ["偏积极", "偏积极"], "本周市场偏积极。")
    assert wrote1 is True

    log_path = fake_repo["data"] / "llm_weekly_log.csv"
    before = log_path.read_bytes()

    wrote2 = lwr._append_log(week, ["偏积极", "偏防御"], "改成偏防御。")
    assert wrote2 is False
    # 文件字节完全不变（不改历史）
    assert log_path.read_bytes() == before


def test_append_log_new_week_appends(fake_repo):
    """不同 ISO-week → 正常追加。"""
    lwr._append_log("2026-W25", ["偏防御"], "上周偏防御。")
    lwr._append_log("2026-W26", ["偏积极"], "本周偏积极。")

    log_path = fake_repo["data"] / "llm_weekly_log.csv"
    rows = list(csv.reader(open(log_path, encoding="utf-8")))
    # header + 2 data rows
    assert len(rows) == 3
    assert rows[1][0] == "2026-W25"
    assert rows[2][0] == "2026-W26"


def test_append_log_creates_file_with_header(fake_repo):
    """首次写入自动建文件并写表头。"""
    log_path = fake_repo["data"] / "llm_weekly_log.csv"
    assert not log_path.exists()
    lwr._append_log("2026-W26", ["偏积极"], "本周ok")
    assert log_path.exists()
    rows = list(csv.reader(open(log_path, encoding="utf-8")))
    assert rows[0] == ["week", "stance_trend", "text"]


# ─────────────────────────────────────────────────────────────────────────────
# 9. run() — 无 key 时静默跳过，不崩溃，不写任何文件
# ─────────────────────────────────────────────────────────────────────────────

def test_run_silent_skip_no_key(fake_repo, monkeypatch, capsys):
    """未配置 LLM key → run() 返回 None，打印跳过信息，不写任何文件。"""
    monkeypatch.setattr(lwr, "_llm_key", lambda: None)
    result = lwr.run()
    assert result is None
    out = capsys.readouterr().out
    assert "跳过" in out
    # 无任何 JSON 文件被写出
    assert not (fake_repo["web"] / "llm_weekly.json").exists()
    assert not (fake_repo["data"] / "llm_weekly_log.csv").exists()


def test_run_llm_exception_no_crash(fake_repo, monkeypatch, capsys):
    """LLM 调用抛异常 → 不阻断（返回 None，打印警告），不写文件。"""
    monkeypatch.setattr(lwr, "_llm_key", lambda: "fake-key")

    def bad_llm(_prompt):
        raise ConnectionError("network down")

    monkeypatch.setattr(lwr, "_llm", bad_llm)

    # 填充最小数据文件，避免因缺文件导致其他路径出错
    _write_composite_log(fake_repo["data"], [("2026-06-24", "偏积极", "0.14")])
    _write_regime(fake_repo["web"])
    _write_scorecard(fake_repo["web"])

    result = lwr.run(force=True)   # force 绕过周五节流门,真正走到 LLM 异常路径
    assert result is None
    out = capsys.readouterr().out
    assert "失败" in out or "跳过" in out


def test_run_writes_json_on_success(fake_repo, monkeypatch):
    """LLM 成功返回时，写 llm_weekly.json 并 append 日志。"""
    monkeypatch.setattr(lwr, "_llm_key", lambda: "fake-key")
    monkeypatch.setattr(lwr, "_active_model", lambda: "gemini-test")
    monkeypatch.setattr(lwr, "_llm", lambda _: "本周市场整体偏积极，风险环境较为平稳。（这是数据读数不是预测，会错，过去不代表未来）")

    # 写入数据文件
    _write_composite_log(fake_repo["data"], [("2026-06-24", "偏积极", "0.14")])
    _write_regime(fake_repo["web"])
    _write_scorecard(fake_repo["web"])

    # 临时 web/docs 让 util_io.write_json 能写
    import util_io
    monkeypatch.setattr(util_io, "WEB",  fake_repo["web"])
    monkeypatch.setattr(util_io, "DOCS", fake_repo["tmp"] / "docs")  # docs 不存在 → 跳过
    (fake_repo["tmp"] / "docs").mkdir()  # 创建让它也写进去

    result = lwr.run(force=True)   # force 绕过周五节流门,测生成/写文件路径
    assert result is not None
    assert result["text"] != ""
    assert "caveat" in result
    # 文件已写出
    out_path = fake_repo["web"] / "llm_weekly.json"
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert "week_of" in payload
    assert "text" in payload
    assert "stance_trend" in payload
    # 日志已追加
    log_path = fake_repo["data"] / "llm_weekly_log.csv"
    assert log_path.exists()


# ─────────────────────────────────────────────────────────────────────────────
# 10. 节流门(2026-07-07 接入 run_all)：周五前跳过 / 本周已记跳过 / 周五生成
#     —— 周读此前漏接 run_all,靠此门在流水线里"每交易日多跑不烧 API、周五才生成完整交易周"
# ─────────────────────────────────────────────────────────────────────────────

def _mock_gen(monkeypatch):
    monkeypatch.setattr(lwr, "_llm_key", lambda: "fake-key")
    monkeypatch.setattr(lwr, "_active_model", lambda: "gemini-test")
    monkeypatch.setattr(lwr, "_llm", lambda _: "本周市场偏积极。（这是数据读数不是预测，会错，过去不代表未来）")


def test_run_skips_before_friday(fake_repo, monkeypatch, capsys):
    """周五前(weekday<4)不生成(等交易周攒满)——避免周一只有1天数据的低质周报。"""
    _mock_gen(monkeypatch)
    _write_composite_log(fake_repo["data"], [("2026-06-23", "偏积极", "0.14")])
    tuesday = datetime.date(2026, 6, 23)   # 周二
    assert tuesday.weekday() == 1
    result = lwr.run(today=tuesday)
    assert result is None
    assert "未到周五" in capsys.readouterr().out
    assert not (fake_repo["web"] / "llm_weekly.json").exists()


def test_run_skips_if_week_already_logged(fake_repo, monkeypatch, capsys):
    """本 ISO 周已在日志 → 跳过(每周只调一次 LLM,防 run_all 每次跑都烧 API)。"""
    _mock_gen(monkeypatch)
    friday = datetime.date(2026, 6, 26)    # 周五, W26
    lwr._append_log(lwr._iso_week(friday), ["偏积极"], "本周已记")
    result = lwr.run(today=friday)
    assert result is None
    assert "本周已生成" in capsys.readouterr().out


def test_run_generates_on_friday_fresh_week(fake_repo, monkeypatch):
    """周五 + 本周未记 → 正常生成(节流门放行的唯一路径)。"""
    _mock_gen(monkeypatch)
    _write_composite_log(fake_repo["data"], [("2026-06-26", "偏积极", "0.14")])
    _write_regime(fake_repo["web"])
    _write_scorecard(fake_repo["web"])
    import util_io
    monkeypatch.setattr(util_io, "WEB", fake_repo["web"])
    monkeypatch.setattr(util_io, "DOCS", fake_repo["tmp"] / "docs")
    (fake_repo["tmp"] / "docs").mkdir()
    friday = datetime.date(2026, 6, 26)    # 周五
    assert friday.weekday() == 4
    result = lwr.run(today=friday)          # 不传 force,靠真门放行
    assert result is not None
    assert (fake_repo["web"] / "llm_weekly.json").exists()
