"""一次性审计：HTML/JS 的 ID 与函数引用交叉检查"""
import re
from pathlib import Path

web = Path(__file__).parent.parent / "web"
html = (web / "index.html").read_text(encoding="utf-8")
js   = (web / "app.js").read_text(encoding="utf-8")
css  = (web / "style.css").read_text(encoding="utf-8")

html_ids = set(re.findall(r'id="([^"]+)"', html))
js_get   = set(re.findall(r'getElementById\(["\']([^"\']+)["\']\)', js))
js_get  |= set(re.findall(r'Plotly\.newPlot\(["\']([^"\']+)["\']', js))

print("=== JS 引用但 HTML 中不存在的 ID（导致面板渲染不出来）===")
missing = sorted(i for i in js_get if i not in html_ids and "-" in i)
for i in missing:
    print(" ", i)
if not missing:
    print("  （无）")

print("\n=== HTML onclick 引用但 JS 未定义的函数 ===")
onclicks = set(re.findall(r'onclick="(\w+)\(', html))
jsfuncs  = set(re.findall(r'function\s+(\w+)\s*\(', js))
miss_fn = sorted(f for f in onclicks if f not in jsfuncs)
for f in miss_fn:
    print(" ", f)
if not miss_fn:
    print("  （无）")

print("\n=== HTML 中有容器但 JS 从未填充的 ID（可能一直空白）===")
fill_ids = js_get | set(re.findall(r'getElementById\(["\']([^"\']+)["\']', js))
never = sorted(i for i in html_ids if i not in fill_ids
               and any(k in i for k in ["chart", "panel", "list", "grid", "tab-", "section"]))
for i in never:
    print(" ", i)

print("\n=== 标签页 class 检查 ===")
print("  .tab 定义在CSS:", ".tab " in css or ".tab{" in css or ".tab:" in css)
print("  .active 相关规则数:", len(re.findall(r'\.active', css)))
tabs_html = re.findall(r'class="tab[^"]*"[^>]*onclick="(\w+)\(\'(\w+)\'', html)
print("  HTML 标签按钮:", tabs_html[:20])
tab_divs = sorted(i for i in html_ids if i.startswith("tab-"))
print("  HTML 标签容器:", tab_divs)
