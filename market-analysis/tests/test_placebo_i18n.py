"""数据层双语守门 — placebo 面板的英文覆盖率（2026-09-01）。

背景:英文模式下 registry 视图的 #placebo-overview 曾整块是中文,因为文案是 Python 生成的
(前端只是照显示)。补 *_en 字段容易,难的是**下次加第 7 条日历效应时别忘了**。

所以这里不去断言"某几句英文长啥样"(那是把译文抄两遍),而是断言**覆盖率**:
  · 源码里每个 claim="…" 字面量都必须在 CLAIM_EN 里有条目;
  · 每个 panel="…" / scope="…" 都必须被 label_en 全译;
  · detail 的每种结构化形状都要能重建成英文,且未知形状**原样退回中文**
    (宁可露出中文,也不编一句读起来像翻好了的假英文 —— 假英文比缺英文更危险)。
加新效应时忘了配英文 → 这里立刻红,并指名道姓缺哪条。

hermetic:只读源码文本 + 调纯函数,不跑流水线、不联网、不读 data/。
"""
import re
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "scripts" / "placebo_test.py"


def _literals(kw):
    """从 placebo_test.py 源码里抽 add(... kw="…" ...) 的字面量(f-string 的跳过)。"""
    text = SRC.read_text(encoding="utf-8")
    return sorted(set(re.findall(kw + r'="([^"{]+)"', text)))


def test_every_claim_has_english():
    from placebo_test import CLAIM_EN
    claims = _literals("claim")
    assert claims, "没抽到 claim 字面量 —— 正则或调用写法变了,先修这里再说"
    missing = [c for c in claims if c not in CLAIM_EN]
    assert not missing, f"这些 claim 没配英文(补进 placebo_test.CLAIM_EN): {missing}"


def test_every_panel_and_scope_is_translatable():
    from label_en import is_fully_translated
    bad = [s for s in _literals("panel") + _literals("scope") if not is_fully_translated(s)]
    assert not bad, f"这些 panel/scope 没被 label_en 全译(补片段表): {bad}"


@pytest.mark.parametrize("zh,en", [
    ("周三最高 / 周一最低", "Wed highest / Mon lowest"),
    ("7月最高 / 9月最低", "Jul highest / Sep lowest"),
    ("每组仅约 9 年", "only ~9 years per group"),
    ("节前交易日 n=262", "pre-holiday trading days n=262"),
    ("区间交易日 n=530", "trading days in window n=530"),
])
def test_detail_shapes_round_trip(zh, en):
    """数字必须原样搬运(不重算)——译文里的 9 / 262 / 530 都来自中文串本身。"""
    from placebo_test import _detail_en
    assert _detail_en(zh) == en


def test_unknown_detail_falls_back_to_chinese():
    """未知形状不硬翻:退回中文让人看见缺口,而不是悄悄编一句英文。"""
    from placebo_test import _detail_en
    weird = "某种以后才会出现的新说法"
    assert _detail_en(weird) == weird
    assert _detail_en(None) is None and _detail_en("") == ""


def test_cpcv_verdict_bands_are_single_branch():
    """CPCV 裁决的档位表必须中英同源(同一 key 取两列),不能是两套 if/elif —— 那迟早漂移。"""
    import cpcv
    src = Path(cpcv.__file__).read_text(encoding="utf-8")
    m = re.search(r'band = "high" if p >= 0\.5 else "mid" if p >= 0\.35 else "low"', src)
    assert m, "CPCV 档位判定不再是单分支了?中英文案有各判一次、进而漂移的风险,请检查"
    for band in ("high", "mid", "low"):
        assert re.search(rf'"{band}":\s*\(', src), f"TAG 表缺 {band} 档"


# ── 检验力还要等多久(2026-09-07) ────────────────────────────────────
# 「无定论(检验力不足)」原本把两件完全不同的事说成同一句话:
#   月份效应现代段再攒 4 年就够(真的只是"等") vs 年份尾数要 226 年(这辈子等不到)。
# 读者看到的都是"还在查"。这组测试钉住:速率**从数据推导**、档位分得开、双语齐。
def test_power_outlook_says_powered_when_sample_is_enough():
    from placebo_test import _power_outlook, MIN_GROUP_N
    r = _power_outlook(MIN_GROUP_N, 50)
    assert r["outlook"] == "powered" and r["years_to_power"] == 0


def test_power_rate_is_derived_from_data_not_hardcoded():
    """速率 = 每组样本 ÷ 该检验自己窗口的年数。

    同样的 min_group_n,窗口越长说明积累越慢、要等越久 —— 若写死映射表,
    上游一改起点/分组就悄悄失真,而"悄悄不准"正是要防的东西。
    """
    from placebo_test import _power_outlook
    fast = _power_outlook(20, 20)     # 1/年 → 还差 10 → 10 年
    slow = _power_outlook(20, 200)    # 0.1/年 → 还差 10 → 100 年
    assert fast["years_to_power"] == 10
    assert slow["years_to_power"] == 100
    assert slow["years_to_power"] > fast["years_to_power"], "窗口越长应意味着等得越久"


@pytest.mark.parametrize("n,span,expect", [
    (26, 26, "soon"),      # 月份效应现代段:再 4 年
    (24, 98, "decades"),   # 总统任期年:再 24 年
    (9, 98, "never"),      # 年份尾数:再 226 年 —— 一辈子等不到
])
def test_power_bands_separate_wait_a_few_years_from_never(n, span, expect):
    """三档必须分得开 —— 分不开就等于没做,读者还是只看到一句'检验力不足'。"""
    from placebo_test import _power_outlook
    assert _power_outlook(n, span)["outlook"] == expect


def test_power_outlook_is_bilingual_and_none_safe():
    from placebo_test import _power_outlook, _OUTLOOK
    cjk = re.compile(r"[一-龥]")
    r = _power_outlook(9, 98)
    assert r["outlook_zh"] and r["outlook_en"]
    assert not cjk.search(r["outlook_en"]), "英文档位里混进了中文"
    for zh, en in _OUTLOOK.values():
        assert zh and en and not cjk.search(en)
    # 缺输入不炸
    assert _power_outlook(None, 10) is None and _power_outlook(9, 0) is None


def test_frontend_only_warns_when_actually_underpowered():
    """样本够了就别啰嗦 —— 警告滥发等于没有警告。"""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "web" / "app-2.js").read_text(encoding="utf-8")
    assert "function powerNote" in js
    i = js.index("function powerNote")
    body = js[i:i + 900]
    assert 'outlook !== "powered"' in body, "没跳过'已够'的项,会给每一条都挂提示"


def test_pattern_table_shows_the_binding_half_sample_n():
    """个股规律表必须把**分半门真正面对的那个更小的 n** 显出来(§3 旧记录)。

    实证:AAPL 月份效应 `verdict=inconclusive`,全样本每组 26、**分半只有 13**。
    表里原本只有 p 值、不显示任何样本量 —— 读者看到"检验力不足"却不知道是被多小的样本卡住的;
    而只报全样本(26)等于把证据说得比实际(13)强。两个都显示,低于门槛的标色。
    """
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "web" / "app-2.js").read_text(encoding="utf-8")
    assert "function groupN" in js, "样本量列的辅助函数不见了"
    i = js.index("function groupN")
    body = js[i:i + 600]
    assert "min_group_n_half" in body, "只报全样本 n —— 证据会被说得比实际强"
    assert "min_group_n" in body
    assert "< 30" in body or "<30" in body, "低于门槛没有视觉标记"
    assert "${groupN(t2)}" in js, "列加了但没在行里用上"


def test_checkup_backend_still_emits_half_sample_n():
    """后端字段是这条展示的前提,别被'清理'掉。"""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "scripts" / "stock_checkup.py").read_text(encoding="utf-8")
    assert "min_group_n_half" in src
