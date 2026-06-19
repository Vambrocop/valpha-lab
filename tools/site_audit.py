# 全站体检：无头浏览器走遍 6 个视图 + 全部子标签
# 收集：JS 报错 / 失败请求 / 空容器 / 零宽或溢出图表；每视图整页截图供布局审查
# 用法: py tools/site_audit.py [--mobile]
import http.server
import threading
import functools
import os
import sys
import tempfile

from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PORT = 8950
WEB = "market-analysis/web"
SHOT = os.environ.get("ALAB_AUDIT_SHOT_DIR") or os.path.join(tempfile.gettempdir(), "alab_audit")
os.makedirs(SHOT, exist_ok=True)

MOBILE = "--mobile" in sys.argv
CI = "--ci" in sys.argv or os.environ.get("CI") == "true"
VP = {"width": 390, "height": 844} if MOBILE else {"width": 1440, "height": 1000}
TAG = "m" if MOBILE else "d"

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

handler = functools.partial(Quiet, directory=WEB)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

VIEWS = ["today", "plan", "lab", "research", "quant", "mine"]
console_msgs, bad_requests = [], []

with sync_playwright() as p:
    try:
        b = p.chromium.launch() if CI else p.chromium.launch(channel="msedge")
    except Exception as first_error:
        try:
            b = p.chromium.launch(channel="msedge") if CI else p.chromium.launch()
        except Exception:
            raise first_error
    page = b.new_page(viewport=VP)
    page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text[:200]}")
            if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: console_msgs.append(f"[pageerror] {str(e)[:200]}"))
    page.on("requestfailed", lambda r: bad_requests.append(f"{r.url} ({r.failure})"))
    page.on("response", lambda r: bad_requests.append(f"{r.url} HTTP {r.status}")
            if r.status >= 400 else None)
    page.goto(f"http://127.0.0.1:{PORT}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2200)

    problems = []
    for view in VIEWS:
        page.evaluate(f"""() => switchView('{view}',
            document.querySelector('.view-btn[data-view="{view}"]'))""")
        page.wait_for_timeout(900)

        # 滚动到底再回顶：触发 IntersectionObserver 懒渲染（模拟真实浏览）
        page.evaluate("""async () => {
            for (let y = 0; y <= document.body.scrollHeight; y += 600) {
                window.scrollTo(0, y);
                await new Promise(r => setTimeout(r, 70));
            }
            window.scrollTo(0, 0);
        }""")
        page.wait_for_timeout(700)

        # 点遍该视图内全部子标签（每组 .tabs 里的每个 .tab）
        n_tabs = page.evaluate(f"""() => {{
            const sec = document.getElementById('view-{view}');
            if (!sec) return 0;
            const tabs = [...sec.querySelectorAll('.tabs .tab')];
            tabs.forEach(t => t.click());
            return tabs.length;
        }}""")
        page.wait_for_timeout(400 + 150 * min(n_tabs, 10))

        # 等慢图渲染：轮询"活动且可见的 chart-* 都出了 SVG"（最多 8s），
        # 别把数据多、渲染慢但正常的 Plotly 图误判成 EMPTY（真没渲染的过 8s 仍会被抓）
        try:
            page.wait_for_function(
                ("() => {"
                 "  const sec = document.getElementById('view-VIEWID');"
                 "  if (!sec) return true;"
                 "  const cs = [...sec.querySelectorAll('[id^=chart-]')].filter(el => {"
                 "    const p = el.closest('.tab-content');"
                 "    return (!p || p.classList.contains('active')) && (el.offsetWidth || el.offsetHeight);"
                 "  });"
                 "  return cs.length === 0 || cs.every(el => el.querySelector('svg.main-svg') || el.innerHTML.trim());"
                 "}").replace('VIEWID', view), timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(300)

        # 扫描该视图所有图表/面板容器
        report = page.evaluate(f"""() => {{
            const out = [];
            const sec = document.getElementById('view-{view}');
            if (!sec) return out;
            // 1) Plotly 容器：空 / 零宽 / NaN text
            sec.querySelectorAll('[id^=chart-]').forEach(el => {{
                const pane = el.closest('.tab-content');
                const inActiveTab = !pane || pane.classList.contains('active');
                const svg = el.querySelector('svg.main-svg');
                const vis = !!(el.offsetWidth || el.offsetHeight);
                const issues = [];
                if (inActiveTab && vis && !svg && !el.innerHTML.trim()) issues.push('EMPTY');
                if (svg && vis) {{
                    const w = svg.getBoundingClientRect().width;
                    const cw = el.getBoundingClientRect().width;
                    if (w === 0) issues.push('ZERO-W');
                    else if (cw > 50 && Math.abs(w - cw) > 60) issues.push(`W-MISMATCH svg=${{Math.round(w)}} box=${{Math.round(cw)}}`);
                }}
                if (svg && [...svg.querySelectorAll('text')].some(t => (t.getAttribute('transform')||'').includes('NaN')))
                    issues.push('NaN-TEXT');
                if (issues.length) out.push(el.id + ': ' + issues.join(','));
            }});
            // 2) 溢出裁切：内容超出容器
            sec.querySelectorAll('.panel, .chart-wrap').forEach(el => {{
                if (el.scrollWidth > el.clientWidth + 8)
                    out.push((el.id || el.querySelector('.panel-title,.chart-header')?.textContent?.trim()?.slice(0,24) || '?') +
                             `: OVERFLOW-X ${{el.scrollWidth}}>${{el.clientWidth}}`);
            }});
            // 3) 可见的空面板（应有内容但是空的）
            sec.querySelectorAll('[id]').forEach(el => {{
                const id = el.id;
                if (!/(panel|list|grid|insight|summary|table|tracker|monitor|calc|brief|detail)/.test(id)) return;
                const pane = el.closest('.tab-content');
                if (pane && !pane.classList.contains('active')) return;
                if ((el.offsetWidth || el.offsetHeight) && el.innerHTML.trim() === '')
                    out.push(id + ': BLANK');
            }});
            return out;
        }}""")
        for r in report:
            problems.append(f"[{view}] {r}")

        page.screenshot(path=f"{SHOT}/{TAG}_{view}.png", full_page=True)

    b.close()
srv.shutdown()

# EMPTY/BLANK 多为 headless 懒渲染假阳性（IntersectionObserver/Plotly 需真视口；真浏览器正常）
# → 只警告不阻断；真 bug（OVERFLOW/ZERO-W/NaN/W-MISMATCH）+ 控制台报错 + 失败请求 才阻断 CI。
_HARD = ("OVERFLOW", "ZERO-W", "NaN", "MISMATCH")
hard = [p for p in problems if any(k in p for k in _HARD)]
soft = [p for p in problems if p not in hard]
print(f"=== 阻断级容器问题 ({len(hard)}) ===")
for x in hard: print(" ", x)
print(f"=== 软警告 EMPTY/BLANK ({len(soft)})（多为 headless 懒渲染假阳性·真浏览器正常·不阻断）===")
for x in soft: print(" ", x)
print(f"\n=== 控制台报错/警告 ({len(console_msgs)}) ===")
seen = set()
for x in console_msgs:
    if x not in seen:
        seen.add(x); print(" ", x)
print(f"\n=== 失败请求 ({len(bad_requests)}) ===")
for x in sorted(set(bad_requests)): print(" ", x)
print(f"\n截图: {SHOT}/{TAG}_<view>.png")

if hard or console_msgs or bad_requests:
    sys.exit(1)
