"""test_docs_mirror.py — web/↔docs/ 镜像守卫的守门测试。

守卫本身(check_docs_mirror.run)是 verify_output 门禁的一环,靠字节哈希抓"手改 web/ 忘镜像"。
本测聚焦**守卫的纳入规则**——历史上 vp_i18n.js 因"显式点名"漏网(2026-07-07),故把
"手写核心必被守、厂商包必排除"焊成回归锁,并核真实 web/ 目录里每个手写 .js 都在守卫范围内。
纯逻辑+真目录只读,不联网、不改盘。
"""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_docs_mirror as cdm


@pytest.mark.parametrize("name,guarded", [
    ("vp_i18n.js", True),          # 回归锁:曾漏网的 i18n 核心必须被守
    ("vp_gloss.js", True),
    ("vp_future_core.js", True),   # 未来新增 vp_ 核心自动纳入(泛化规则,防再漏点名)
    ("app-1.js", True),
    ("app-5.js", True),
    ("plotly-cartesian-2.35.2.min.js", False),   # 厂商打包必须排除
    ("something.min.js", False),
    ("style.css", False),          # 非 .js 交给 _should_compare 的其它分支
])
def test_handwritten_js_rule(name, guarded):
    assert cdm._is_handwritten_js(name) is guarded


def test_every_real_web_js_is_classified_not_dropped_by_accident():
    """真实 web/ 目录里每个 .js:要么手写核心(app-*/vp_*)被守,要么厂商包(plotly)被排除——
    绝不能出现"手写核心却没被守卫认出"的第三种情况(那正是 vp_i18n 当初的处境)。"""
    web = cdm.WEB_DIR
    if not web.exists():
        pytest.skip("web/ 不存在")
    for js in sorted(web.glob("*.js")):
        n = js.name
        vendored = "plotly" in n or n.endswith(".min.js")
        if vendored:
            assert not cdm._is_handwritten_js(n), f"{n} 是厂商包却被当手写守卫"
        else:
            assert cdm._is_handwritten_js(n), f"{n} 是手写 .js 却没被守卫纳入(会漏镜像漂移)"


def test_should_compare_covers_html_css_and_handwritten_js():
    assert cdm._should_compare(Path("dashboard.html"))
    assert cdm._should_compare(Path("vp.css"))
    assert cdm._should_compare(Path("vp_i18n.js"))
    assert cdm._should_compare(Path("app-4.js"))
    assert not cdm._should_compare(Path("valpha150.json"))          # 生成数据不比对
    assert not cdm._should_compare(Path("plotly-cartesian-2.35.2.min.js"))
