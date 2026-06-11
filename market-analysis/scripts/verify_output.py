"""
verify_output.py — 发布前自检（CI 质量门）

任何检查失败都以非零码退出 → run_all 终止 → GitHub Actions 不会把坏数据推上线。
"""
import json
import sys
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

WEB_DIR  = Path(__file__).parent.parent / "web"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
US_TODAY = datetime.datetime.now(ZoneInfo("America/New_York")).date()
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
          "overnight.json", "news.json", "signals_history.json"]:
    p = WEB_DIR / f
    check(p.exists() and p.stat().st_size > 100, f"{f} 存在且非空")

# 首屏体积守门：signals.json 发布版只含近两年（P1-3），别让它再胖回去
check((WEB_DIR / "signals.json").stat().st_size < 800_000,
      f"signals.json < 800KB（当前 {(WEB_DIR / 'signals.json').stat().st_size//1024}KB）")

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
    age = (US_TODAY - gen).days
    check(age <= 4, f"数据新鲜（generated={sig['generated']}，美东{age}天前）")
    last = max(sig["daily_signals"])
    check((US_TODAY - datetime.date.fromisoformat(last)).days <= 6,
          f"信号覆盖到近期（最新 {last}）")
    check(len(sig.get("macro_calendar", [])) > 0,
          "宏观日历非空（空了说明 MACRO_EVENTS 需要补来年日程）")
    vol = list(sig["daily_signals"].values())[-1].get("nasdaq_vol", 0)
    check(0 <= vol < 1.5, f"波动率量纲正常（{vol}，应为年化小数）")
except Exception as e:
    errors.append(f"signals.json 解析失败: {e}")
    print(f"  ✗ signals.json 解析失败: {e}")

# 3. 其余 JSON 全部严格合法
for f in ["prices.json", "charts_extra.json", "stocks.json",
          "overnight.json", "news.json", "long_history.json",
          "signals_history.json"]:
    try:
        with open(WEB_DIR / f, encoding="utf-8") as fh:
            json.load(fh)
        print(f"  ✓ {f} 合法 JSON")
    except Exception as e:
        errors.append(f"{f} 非法: {e}")
        print(f"  ✗ {f} 非法: {e}")

# 4. 账本完整性（append-only 数据的硬约束）
try:
    import csv
    for fname, keys in [("paper_ledger.csv", ("date", "strategy")),
                        ("prediction_log.csv", ("signal_date", "index", "model_version"))]:
        p = PROC_DIR / fname
        if p.exists():
            with open(p, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            seen = [tuple(str(r[k]) for k in keys) for r in rows]
            dup = len(seen) - len(set(seen))
            check(dup == 0, f"{fname} 无重复键（发现 {dup} 条重复）")
except Exception as e:
    errors.append(f"账本检查失败: {e}")

if errors:
    print(f"\n[FAIL] {len(errors)} 项检查未通过，拒绝发布")
    sys.exit(1)
print("\n[OK] 全部自检通过，可以发布")
