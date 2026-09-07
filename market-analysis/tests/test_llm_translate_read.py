"""LLM 解读的英文版守门(2026-09-07·用户拍板"让 LLM 出英文版")。

## 一个刻意的设计:翻译,不是重新生成

英文版是把**已生成的中文**翻过去,而不是"用同一份数据再生成一版英文"。
独立生成会让两个版本**说不一样的话** —— 英文读者看到的结论与中文不同。在一个双语的
诚实计分站点上这是硬伤(同 market_regime/composite_read 档位表"中英同源"的道理:
两套分支迟早漂移)。顺带还便宜:提示词只有原文,短得多。

## 失败时的铁律:宁可没有英文,不许编英文

缺 key / 调用失败 / 空返回 → 一律 None,前端 vpD() 回落中文。
缺英文你看得见(页面是中文),假英文你以为翻好了 —— 后者危险得多。

hermetic:monkeypatch 掉 _llm,不联网、不花钱。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import llm_core  # noqa: E402


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(llm_core, "_llm_key", lambda: "fake-key")


def test_returns_translation_when_llm_answers(with_key, monkeypatch):
    monkeypatch.setattr(llm_core, "_llm", lambda p: "  Today the market looks calm.  ")
    assert llm_core.translate_read("今天市场平静。") == "Today the market looks calm."


def test_prompt_carries_the_chinese_source_and_forbids_re_analysis(with_key, monkeypatch):
    """提示词必须把中文原文喂进去,并明确禁止"另加观点/丢免责"。"""
    seen = {}
    monkeypatch.setattr(llm_core, "_llm", lambda p: seen.setdefault("p", p) and "ok" or "ok")
    llm_core.translate_read("金叉成立，但这不是买入建议。")
    p = seen["p"]
    assert "金叉成立，但这不是买入建议。" in p, "原文没被喂进提示词 —— 那就不是翻译了"
    low = p.lower()
    assert "do not re-analyse" in low or "not re-analyse" in low
    assert "disclaimer" in low, "没要求保留免责声明 —— 英文版可能把风险提示丢掉"
    assert "exactly" in low, "没要求数字原样保留"


def test_no_key_returns_none_without_calling(monkeypatch):
    """没配 key → 直接 None,不该调用(也就不会报错/花钱)。"""
    monkeypatch.setattr(llm_core, "_llm_key", lambda: "")
    called = []
    monkeypatch.setattr(llm_core, "_llm", lambda p: called.append(1) or "x")
    assert llm_core.translate_read("有中文") is None
    assert not called, "没 key 还去调 LLM"


def test_llm_failure_degrades_to_none_not_exception(with_key, monkeypatch):
    """调用炸了不许把流水线带崩 —— 英文缺失只是少一份译文。"""
    def boom(p):
        raise RuntimeError("429 rate limited")
    monkeypatch.setattr(llm_core, "_llm", boom)
    assert llm_core.translate_read("有中文") is None


def test_empty_llm_reply_is_none_not_empty_string(with_key, monkeypatch):
    """空返回要变 None,不能是 ''。前端用 `text_en || text` 回落,
    空串虽然也 falsy,但 None 语义更明确:'没有英文',而不是'英文是空的'。"""
    monkeypatch.setattr(llm_core, "_llm", lambda p: "   ")
    assert llm_core.translate_read("有中文") is None


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_blank_source_short_circuits(with_key, monkeypatch, bad):
    """中文原文本身是空的 → 直接 None,不浪费一次调用。"""
    called = []
    monkeypatch.setattr(llm_core, "_llm", lambda p: called.append(1) or "x")
    assert llm_core.translate_read(bad) is None
    assert not called


def test_all_three_reads_emit_text_en():
    """日读/周报/月读三处都要出 text_en —— 少一处那块在英文模式下就还是中文。"""
    missing = []
    for name in ("llm_daily_read", "llm_weekly_read", "llm_monthly_read"):
        src = (ROOT / "scripts" / f"{name}.py").read_text(encoding="utf-8")
        if "text_en" not in src or "translate_read" not in src:
            missing.append(name)
    assert not missing, f"这些脚本没接英文版: {missing}"


def test_frontend_falls_back_to_chinese_when_english_missing():
    """前端必须是「有英文用英文,没有回落中文」,不能写成只认 text_en(那会开天窗)。"""
    for f, needle in (("dashboard.html", "text_en"), ("composite.html", "text_en")):
        src = (ROOT / "web" / f).read_text(encoding="utf-8")
        assert needle in src, f"{f} 没接 text_en"
        # 回落写法:`(_lang==="en"&&X.text_en)||X.text`  —— 必须有 `||` 兜底
        assert "text_en)||" in src.replace(" ", ""), f"{f} 缺中文回落,英文缺失时会空白"
