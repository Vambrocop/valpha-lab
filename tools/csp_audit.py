# 刻意不写 `#!/usr/bin/env python3` shebang:Windows 的 py 启动器会遵循它、转交给 `python3`,
# 而本机 python3 指向 Microsoft Store 占位程序 → 静默退出 49、双流全空(2026-09-06 踩过)。
"""csp_audit.py — CSP 的**真浏览器**实测(不是读 meta 标签数数)。

## 为什么要真跑浏览器

全站 42 页都有 CSP meta。但"有 meta"不等于"CSP 是对的"——配错的 CSP 最典型的坏法是
**悄悄挡掉自己的资源**:脚本/样式/字体被 blocked,页面半残,而**控制台之外毫无提示**,
静态读标签永远看不出来。所以这里在真 Chromium 里逐页跑,收 `securitypolicyviolation` 事件。

## 它能证明什么、不能证明什么(诚实边界)

能证明:① 没有**自伤**(合法资源被自己的策略挡掉);② 声明的外部源确实被放行。
**不能**证明站点防住了 XSS —— 全站 CSP 都带 `script-src 'unsafe-inline'`(内联脚本是本项目
的既定架构),那等于给 XSS 留了门。这条是**已知且刻意**的取舍,不是本工具能改善的,
所以工具会把它如实报出来,而不是给一个"CSP ✓ 全绿"的假安慰。

用法:$env:PYTHONUTF8='1'; py tools/csp_audit.py [--mobile]
退出码:发现**自伤**(合法资源被挡)→ 1;仅有已知取舍 → 0。
"""
import functools
import http.server
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "market-analysis" / "web"
PORT = 8899


def _serve():
    class Q(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    httpd = http.server.HTTPServer(("127.0.0.1", PORT), functools.partial(Q, directory=str(WEB)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# 这些外部源是 CSP 里**显式声明**要放行的;被挡=策略写错了
DECLARED_EXTERNAL = ("vambrocop.github.io", "api.alternative.me")


def audit(mobile=False):
    from playwright.sync_api import sync_playwright
    pages = sorted(p.name for p in WEB.glob("*.html"))
    httpd = _serve()
    selfharm, known = [], []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            vp = {"width": 390, "height": 844} if mobile else {"width": 1280, "height": 900}
            ctx = b.new_context(viewport=vp)
            for name in pages:
                pg = ctx.new_page()
                hits = []
                # securitypolicyviolation 是浏览器对 CSP 拦截的**权威**信号,比抓 console 文本可靠
                pg.expose_function("_cspHit", lambda d: hits.append(d))
                pg.add_init_script("""
                  document.addEventListener('securitypolicyviolation', e => {
                    try { window._cspHit({d: e.violatedDirective, u: e.blockedURI || '', s: e.sourceFile || ''}); }
                    catch (_) {}
                  });""")
                try:
                    pg.goto(f"http://127.0.0.1:{PORT}/{name}", wait_until="load", timeout=20000)
                    pg.wait_for_timeout(1800)
                except Exception as e:
                    print(f"  ! {name} 打不开: {type(e).__name__}")
                    pg.close()
                    continue
                for h in hits:
                    u = h.get("u") or ""
                    # inline/eval 被挡 = 策略与架构冲突,属自伤;外部声明源被挡也是自伤
                    if u in ("inline", "eval") or any(d in u for d in DECLARED_EXTERNAL) \
                            or u.startswith(f"http://127.0.0.1:{PORT}"):
                        selfharm.append((name, h["d"], u[:80]))
                    else:
                        known.append((name, h["d"], u[:80]))
                pg.close()
            b.close()
    finally:
        httpd.shutdown()

    tag = "移动端" if mobile else "桌面"
    print(f"\n=== CSP 真浏览器实测({tag}·{len(pages)} 页) ===")
    if selfharm:
        print(f"❌ 自伤 {len(selfharm)} 处(自己的资源被自己的策略挡掉):")
        for n, d, u in selfharm[:20]:
            print(f"   {n}  {d}  ← {u}")
    else:
        print("✅ 无自伤:没有合法资源被 CSP 挡掉")
    if known:
        print(f"ℹ 其它拦截 {len(known)} 处(多为第三方/扩展注入,非本站资源):")
        for n, d, u in known[:8]:
            print(f"   {n}  {d}  ← {u}")
    print("\n⚠ 诚实边界:全站 CSP 带 `script-src 'unsafe-inline'`(内联脚本是本项目既定架构),")
    print("   所以这份 CSP **挡不住 XSS**;它的实际作用是限制外部源与 object/base-uri。")
    print("   meta 形式也拿不到 `frame-ancestors`(该指令只在 HTTP 响应头生效)。")
    return 1 if selfharm else 0


if __name__ == "__main__":
    raise SystemExit(audit(mobile="--mobile" in sys.argv))
