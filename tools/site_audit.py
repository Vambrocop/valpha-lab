# 全站体检：无头浏览器走遍 6 个视图 + 全部子标签
# 收集：JS 报错 / 失败请求 / 空容器 / 零宽或溢出图表；每视图整页截图供布局审查
# 用法: py tools/site_audit.py [--mobile]
import http.server
import threading
import functools
import os
import sys

from playwright.sync_api import sync_playwright

PORT = 8950
WEB = "market-analysis/web"
SHOT = "C:/Users/Vambr/AppData/Local/Temp/alab_audit"
os.makedirs(SHOT, exist_ok=True)

MOBILE = "--mobile" in sys.argv
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
    b = p.chromium.launch(channel="msedge")
    page = b.new_page(viewport=VP)
    page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text[:200]}")
            if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: console_msgs.append(f"[pageerror] {str(e)[:200]}"))
    page.on("requestfailed", lambda r: bad_requests.append(f"{r.url} ({r.failure})"))
    page.on("response", lambda r: bad_requests.append(f"{r.url} HTTP {r.status}")
            if r.status >= 400 else None)
    page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
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

print(f"=== 容器问题 ({len(problems)}) ===")
for x in problems: print(" ", x)
print(f"\n=== 控制台报错/警告 ({len(console_msgs)}) ===")
seen = set()
for x in console_msgs:
    if x not in seen:
        seen.add(x); print(" ", x)
print(f"\n=== 失败请求 ({len(bad_requests)}) ===")
for x in sorted(set(bad_requests)): print(" ", x)
print(f"\n截图: {SHOT}/{TAG}_<view>.png")
