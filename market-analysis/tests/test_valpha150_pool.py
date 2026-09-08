"""Valpha150 池子的结构性守门(2026-09-08)。

标准写在 `docs_internal/SPEC_VALPHA150_POOL.md`。这里只钉**机器能查的那几条**,
因为它们此前**全靠人记得** —— 而我 2026-09-08 做"池子老化"时就没记得,
凭市值提了两版换血提案,两版都会破坏池子的设计属性:
  · 第一版要删陶氏(道指成分)+ 6 只纳指成分 → 破坏道指全覆盖、扩大纳指缺口;
  · 第二版缩到 3 只,但那三只是跌得最惨的 → 在一个专门演示**幸存者偏差**的看板上
    删掉输家,恰好是这页警告读者的那件事。
用户连问两次"当初为啥加这些",才把设计意图从提交历史里挖出来。
写下来 + 加测试,是为了让下一个人不用再考古,也不能再靠"记得"。

hermetic:只读 CSV/快照文件,不联网、不抓价。
"""
import csv
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POOL = ROOT / "data" / "valpha150.csv"
NDX = ROOT / "data" / "ndx_constituents.csv"

# 道指 30(2026 口径)。成分变动罕见;真变了这条会红,提醒人同步更新池子与本表。
DOW30 = {"AAPL", "AMGN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS", "DOW",
         "GS", "HD", "HON", "IBM", "JNJ", "JPM", "KO", "MCD", "MMM", "MRK",
         "MSFT", "NKE", "NVDA", "PG", "SHW", "TRV", "UNH", "V", "VZ", "WMT"}

SECTORS = {"半导体", "科技", "通信服务", "可选消费", "必需消费", "医疗",
           "金融", "工业", "能源", "公用", "材料", "房地产"}


def _rows():
    return list(csv.DictReader(POOL.read_text(encoding="utf-8").splitlines()))


def test_pool_covers_all_dow30():
    """**硬约束**:道指 30 只一只不能少。

    这是 136→152 扩容时特意补的(`73b1346`:"补全道指 3M/旅行者/陶氏")。
    陶氏市值仅 213 亿、在池子里排倒数第二 —— **纯按市值必被删,删了就破坏这条**。
    """
    pool = {r["ticker"] for r in _rows()}
    missing = sorted(DOW30 - pool)
    assert not missing, (
        f"池子缺了道指成分 {missing} —— 破坏「道指全覆盖」硬约束。"
        "若这些确实已被移出道指,请同步更新本测试的 DOW30 常量并在提交里说明。")


def test_no_duplicate_or_dual_class_of_same_company():
    """同一家公司不许两个代码(实测踩到:GOOG 是 Alphabet C 类,池子已有 A 类 GOOGL)。"""
    pool = {r["ticker"] for r in _rows()}
    for a, b in [("GOOGL", "GOOG"), ("BRK-B", "BRK-A"), ("FOXA", "FOX")]:
        assert not (a in pool and b in pool), f"{a} 与 {b} 是同一家公司的两类股,只留一个"
    tickers = [r["ticker"] for r in _rows()]
    assert len(tickers) == len(set(tickers)), "有重复代码"


def test_sectors_use_the_existing_vocabulary():
    """板块只能用既有的 12 个词 —— 引入新词会让看板的板块色标/筛选悄悄失效。"""
    bad = sorted({r["sector"] for r in _rows()} - SECTORS)
    assert not bad, f"出现了词表外的板块: {bad}(应归入 {sorted(SECTORS)})"


def test_every_row_has_a_name():
    rows = _rows()
    blank = [r["ticker"] for r in rows if not (r.get("name_cn") or "").strip()]
    assert not blank, f"这些票没有名字(自动加票最容易漏这个): {blank}"


def test_storage_makers_are_classified_as_semiconductor():
    """分类先例:存储厂商归半导体而非科技(WDC 西部数据 / SNDK 闪迪 早有先例)。

    2026-09-08 加希捷(STX)时按此归类。这条防的是"新人按 yfinance 的 Technology 直接照抄"。
    """
    m = {r["ticker"]: r["sector"] for r in _rows()}
    for t in ("WDC", "SNDK", "STX"):
        if t in m:
            assert m[t] == "半导体", f"{t} 应归半导体(对齐同为存储的其它票),实为 {m[t]}"


def test_pool_size_is_sane():
    """不死磕某个具体数字,但池子规模应在合理区间 —— 太小说明被误删过,太大说明失控。"""
    n = len(_rows())
    assert 140 <= n <= 220, f"池子 {n} 只,超出合理区间(疑似被批量误删或失控扩张)"


def test_spec_documents_the_no_removal_rule():
    """规格里必须留着"只进不出"那条 —— 它是最容易被后人"优化"掉的一条。"""
    spec = (ROOT / "docs_internal" / "SPEC_VALPHA150_POOL.md").read_text(encoding="utf-8")
    assert "只进不出" in spec and "幸存者偏差" in spec, \
        "规格里的『只进不出/幸存者偏差』理由不见了 —— 那正是这份文档存在的核心原因"


@pytest.mark.parametrize("t", ["TTD", "ON", "CL", "DOW", "CRWV"])
def test_deliberately_small_names_are_still_present(t):
    """这几只市值都不大,但**每一只都是有意留的**,别再被当成"该清理的小票":

      · TTD/ON —— 跌了 74%/45%,正是"追涨陷阱活教材"最好的几页(删了=制造幸存者偏差);
      · CL —— 必需消费只有 9 只,防御板块本就薄;
      · DOW —— **道指成分**,硬约束;
      · CRWV —— `00d9a3d` 有意补的 AI 基建票,市值小是故意的。
    """
    pool = {r["ticker"] for r in _rows()}
    assert t in pool, (
        f"{t} 被移出池子了。移除只在**退市/并购/代码失效**时才允许 —— "
        "跌得惨不是理由(见 SPEC_VALPHA150_POOL.md ⑤)")
