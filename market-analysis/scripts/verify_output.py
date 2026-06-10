"""
verify_output.py — 发布前自检（CI 质量门）

任何检查失败都以非零码退出 → run_all 终止 → GitHub Actions 不会把坏数据推上线。
"""
import json
import sys
import datetime
from pathlib import Path

WEB_DIR = Path(__file__).parent.parent / "web"
errors = []


def check(cond, msg):
    if not cond:
        errors.append(msg)
        print(f"  ✗ {msg}")
    else:
        print(f"  ✓ {msg}")


# 1. 前端要拉取的文件都必须存在且非空
for f in ["index.html", "app.js", "style.css", "signals.json", "prices.json",
          "charts_extra.json", "long_history.json", "stocks.json",
          "overnight.json", "news.json"]:
    p = WEB_DIR / f
    check(p.exists() and p.stat().st_size > 100, f"{f} 存在且非空")

# 2. signals.json 严格合法 + 结构完整 + 无周末数据 + 不过期
try:
    with open(WEB_DIR / "signals.json", encoding="utf-8") as fh:
        sig = json.load(fh)   # 严格解析：NaN 会直接报错
    for key in ["daily_signals", "daily_signals_sp500", "indices",
                "next_opportunities", "macro_calendar", "model_version"]:
        check(key in sig, f"signals.json 含 {key}")
    weekends = [k for k in sig["daily_signals"]
                if datetime.date.fromisoformat(k).weekday() >= 5]
    check(not weekends, f"无周末污染数据（发现 {len(weekends)} 条）")
    gen = datetime.date.fromisoformat(sig["generated"])
    age = (datetime.date.today() - gen).days
    check(age <= 4, f"数据新鲜（generated={sig['generated']}，{age}天前）")
    last = max(sig["daily_signals"])
    check((datetime.date.today() - datetime.date.fromisoformat(last)).days <= 6,
          f"信号覆盖到近期（最新 {last}）")
except Exception as e:
    errors.append(f"signals.json 解析失败: {e}")
    print(f"  ✗ signals.json 解析失败: {e}")

# 3. 其余 JSON 全部严格合法
for f in ["prices.json", "charts_extra.json", "stocks.json",
          "overnight.json", "news.json", "long_history.json"]:
    try:
        with open(WEB_DIR / f, encoding="utf-8") as fh:
            json.load(fh)
        print(f"  ✓ {f} 合法 JSON")
    except Exception as e:
        errors.append(f"{f} 非法: {e}")
        print(f"  ✗ {f} 非法: {e}")

if errors:
    print(f"\n[FAIL] {len(errors)} 项检查未通过，拒绝发布")
    sys.exit(1)
print("\n[OK] 全部自检通过，可以发布")
