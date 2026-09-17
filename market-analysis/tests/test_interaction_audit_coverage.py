"""交互审计的页面清单必须覆盖"有 JS 交互"的页面（2026-09-16）。

## 起因（我自己踩的）

改了 `composite.html`（存活规律观察台，公开面板）后跑 `tools/interaction_audit.py`，
报「硬问题 0」，我差点当成验过了。结果它的 `PAGES` 是**手维护清单**，
而 `composite.html` **一直不在里面** —— 那句 0 根本没测到我改的页面。

这正是 CLAUDE.md 记的 `fe8af0a` 教训的同一形状：
**「我跑了一次是绿的」≠ 验证过，还得问它到底在测什么。**
对比 `tools/csp_audit.py` 用 `WEB.glob("*.html")` **自动发现**，不会漏。

## 策略：钉住现状、不许变大（而不是单方面把审计翻倍）

本测试第一次跑就发现有 **18 个**带 JS 交互的页面不在清单里。
全加进去会让审计从 24 页涨到 42 页、手动跑一次从 ~5 分钟变 ~9 分钟 ——
那是**成本取舍，该由用户定**，不该由一条测试单方面决定。所以：
  · 新加带交互的页面 → 必须入册，或显式进 `KNOWN_UNCOVERED` 并写原因 → 逼出一次决定；
  · 已知那 18 页仍被 `csp_audit`（glob 全站）覆盖 CSP 侧，但**没有点击级实测** ——
    改它们时别把「审计绿了」当验证过。

hermetic：只读源码文本，不起浏览器、不联网。
"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
AUDIT = Path(__file__).resolve().parents[2] / "tools" / "interaction_audit.py"

# 空集合要写 set()：`{ ... }` 里只有注释时是**空 dict**，做减法会 TypeError（起草时真踩了）
KNOWN_UNCOVERED = {
    "btcread.html", "compound.html", "evidence.html", "indexing.html", "insider.html",
    "kronos.html", "ndx.html", "ondemand.html", "options.html", "regimefwd.html",
    "risk.html", "scorecard.html", "seasonal.html", "senate.html", "stayinvested.html",
    "ticker.html", "wildhub.html", "wildpool.html",
}


def _pages_in_audit():
    src = AUDIT.read_text(encoding="utf-8")
    m = re.search(r"PAGES\s*=\s*\[(.*?)\]", src, re.S)
    assert m, "interaction_audit.py 的 PAGES 写法变了，先修本测试的正则"
    return set(re.findall(r'"([^"]+\.html)"', m.group(1)))


def _pages_with_js_interaction():
    out = set()
    for p in sorted(WEB.glob("*.html")):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "onclick" in text or "addEventListener" in text:
            out.add(p.name)
    return out


def test_coverage_gap_does_not_grow():
    """缺口只许缩小 —— 新加带交互的页面必须逼出一次"要不要入册"的决定。"""
    listed, interactive = _pages_in_audit(), _pages_with_js_interaction()
    missing = sorted(interactive - listed - KNOWN_UNCOVERED)
    assert not missing, (
        "这些页面有 JS 交互，但**既不在** interaction_audit.PAGES、**也不在**已知缺口里: "
        f"{missing}。后果：改了它们之后跑审计会报『硬问题 0』，而那个 0 根本没测到它们"
        "（2026-09-16 我在 composite.html 上真踩过）。"
        "修法：加进 tools/interaction_audit.py 的 PAGES（推荐）；"
        "或加进本测试的 KNOWN_UNCOVERED 并说明为什么不值得覆盖。")


def test_known_gap_shrinks_when_pages_get_covered():
    """已入册的页面不许还挂在「已知缺口」里 —— 否则这份清单会烂成过时的免责声明。"""
    stale = sorted(KNOWN_UNCOVERED & _pages_in_audit())
    assert not stale, f"这些页面已入册，但还留在 KNOWN_UNCOVERED 里: {stale}（从集合里删掉）"


def test_known_gap_pages_all_exist():
    """缺口清单指向已删页面 → 同样是烂清单。"""
    gone = sorted(n for n in KNOWN_UNCOVERED if not (WEB / n).exists())
    assert not gone, f"KNOWN_UNCOVERED 里这些页面已不存在: {gone}"


def test_audit_list_has_no_dangling_pages():
    """清单里指向已删页面 → 审计会静默跳过或报软 404，掩盖真问题。"""
    gone = sorted(n for n in _pages_in_audit() if not (WEB / n).exists())
    assert not gone, f"PAGES 里这些页面已不存在: {gone}（删页面时忘了同步清单）"


def test_composite_deck_is_covered():
    """点名守住那条真实缺口 —— 它是公开面板，且现在带蒙特卡洛稳定性标注。"""
    assert "composite.html" in _pages_in_audit(), (
        "存活规律观察台不在交互审计里 —— 它是最面向用户的那张表")
