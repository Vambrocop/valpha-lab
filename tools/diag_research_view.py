# 诊断脚本：无头浏览器逐标签检查"研究"视图图表渲染（截图 + NaN 错误定位）
# 用法: py tools/diag_research_view.py
import http.server
import threading
import functools
from playwright.sync_api import sync_playwright

PORT = 8941
WEB = "market-analysis/web"
SHOT = "C:/Users/Vambr/AppData/Local/Temp/alab_diag"

import os
os.makedirs(SHOT, exist_ok=True)

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

handler = functools.partial(Quiet, directory=WEB)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

errors = []
def snap_errors(label):
    n = len(errors)
    return lambda: print(f"  [{label}] 新增错误 {len(errors)-n} 条" + ("" if len(errors)==n else " <<<<"))

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    page = b.new_page(viewport={"width": 1280, "height": 2200})
    page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
    page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
    page.wait_for_timeout(1500)
    print(f"加载后错误数: {len(errors)}")

    page.evaluate("""() => {
        const btn = document.querySelector('.view-btn[data-view="research"]');
        if (btn) switchView('research', btn);
    }""")
    page.wait_for_timeout(1200)
    print(f"切研究视图后错误数: {len(errors)}")

    def pane_state(pane_id):
        return page.evaluate(f"""() => {{
            const pane = document.getElementById('{pane_id}');
            if (!pane) return 'no pane';
            const out = [];
            pane.querySelectorAll('[id^=chart-]').forEach(el => {{
                const svg = el.querySelector('svg.main-svg');
                const r = svg ? svg.getBoundingClientRect() : null;
                out.push(el.id + ': svg=' + (svg? Math.round(r.width)+'x'+Math.round(r.height) : 'NONE'));
            }});
            return out.join(' | ');
        }}""")

    # 日历子标签逐个点
    for i, tab in enumerate(["cycle", "party", "calholiday", "digit"]):
        before = len(errors)
        page.evaluate(f"""() => {{
            const btns = [...document.querySelectorAll('#cal-tabs .tab')];
            switchCalTab('{tab}', btns[{{"digit":0,"cycle":1,"party":2,"calholiday":3}}['{tab}']]);
        }}""")
        page.wait_for_timeout(800)
        state = pane_state(f"caltab-{tab}")
        print(f"cal[{tab}]: {state}  | 新增错误 {len(errors)-before}")
        page.locator("#caltab-"+tab).screenshot(path=f"{SHOT}/cal_{tab}.png")

    # 多元分析子标签（chart-corr 等所在区域）—— 找到其标签容器
    mv_tabs = page.evaluate("""() => {
        const ids = ['chart-corr','chart-monthly','chart-garch','chart-granger','chart-annual',
                     'chart-shap','chart-prophet','chart-kalman','chart-rolling','chart-path','chart-cca',
                     'chart-backtest-tier','chart-backtest-cal'];
        return ids.map(id => {
            const el = document.getElementById(id);
            if (!el) return id + ': MISSING';
            // 找最近的 .tab-content 祖先
            const pane = el.closest('.tab-content');
            return id + ' -> pane=' + (pane ? pane.id : 'none') + ' active=' + (pane ? pane.classList.contains('active') : '?');
        });
    }""")
    print("\n多元分析图所属面板:")
    for line in mv_tabs:
        print(" ", line)

    # 点一遍多元分析的标签（如果存在 switch 函数）
    mv_panes = page.evaluate("""() => {
        const fns = Object.getOwnPropertyNames(window).filter(n => /^switch.*Tab$/.test(n));
        return fns;
    }""")
    print("\n页面上的 switch*Tab 函数:", mv_panes)

    b.close()
srv.shutdown()

print(f"\n=== 全部控制台错误 ({len(errors)}) ===")
for e in errors[:30]:
    print(e[:240])
print(f"\n截图目录: {SHOT}")
