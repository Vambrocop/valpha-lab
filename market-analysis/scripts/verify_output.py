"""
verify_output.py — 发布前自检（CI 质量门）

任何检查失败都以非零码退出 → run_all 终止 → GitHub Actions 不会把坏数据推上线。
"""
import json
import sys
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from ledger_hash import verify_hash_chain

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

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
for f in ["index.html", "dashboard.html", "app-1.js", "app-2.js", "app-3.js", "app-4.js",
          "app-5.js", "style.css", "signals.json", "prices.json",
          "charts_extra.json", "long_history.json", "stocks.json",
          "overnight.json", "news.json", "signals_history.json",
          "plotly-cartesian-2.35.2.min.js"]:
    p = WEB_DIR / f
    check(p.exists() and p.stat().st_size > 100, f"{f} 存在且非空")

# 首屏体积守门：signals.json 发布版只含近两年（P1-3），别让它再胖回去
check((WEB_DIR / "signals.json").stat().st_size < 800_000,
      f"signals.json < 800KB（当前 {(WEB_DIR / 'signals.json').stat().st_size//1024}KB）")

# 1b. 拆分后的前端脚本语法守门：每个 app-*.js 过 node --check
#     （app.js 拆成 5 个有序经典脚本后，一处语法错会整站白屏 → 上线前拦住）
import shutil, subprocess
_node = shutil.which("node")
if _node:
    for jf in sorted(WEB_DIR.glob("app-*.js")):
        r = subprocess.run([_node, "--check", str(jf)],
                           capture_output=True, text=True)
        check(r.returncode == 0,
              f"{jf.name} 语法合法" + ("" if r.returncode == 0
                                      else f"（{r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'parse error'}）"))
else:
    print("  · 跳过 app-*.js 语法检查（环境无 node）")

# 1c. 全部 web JSON 必须是"浏览器级"严格 JSON。
#     注意：Python json.load 默认放行 NaN/Infinity（它们是非法 JSON），
#     而浏览器 JSON.parse 会拒绝整个文件——曾导致 charts_extra.json 5 张图全空。
def _reject_const(c):
    raise ValueError(f"非法 JSON 常量 {c}（浏览器无法解析）")

for jf in sorted(WEB_DIR.glob("*.json")):
    try:
        with open(jf, encoding="utf-8") as fh:
            json.load(fh, parse_constant=_reject_const)
        check(True, f"{jf.name} 严格 JSON")
    except Exception as e:
        check(False, f"{jf.name} 严格 JSON —— {e}")

# 2. signals.json 严格合法 + 结构完整 + 无周末数据 + 不过期
try:
    with open(WEB_DIR / "signals.json", encoding="utf-8") as fh:
        sig = json.load(fh)   # 注：NaN 检查由上方 1c 节统一负责（json.load 默认放行 NaN）
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

# 3b. 关键数据列完整性（yfinance 部分失败会静默掉列 → 残缺站点）
try:
    import pandas as pd
    cp = pd.read_csv(PROC_DIR.parent / "raw" / "combined_prices.csv",
                     index_col="Date", parse_dates=True)
    KEY_COLS = ["NASDAQ", "SP500", "VIX", "VIX3M", "BTC", "DXY", "HY_SPREAD"]
    missing_cols = [c for c in KEY_COLS if c not in cp.columns]
    check(not missing_cols, f"关键列齐全（缺失：{missing_cols or '无'}）")
    if not missing_cols:
        stale = [c for c in KEY_COLS if cp[c].dropna().empty
                 or (US_TODAY - cp[c].dropna().index[-1].date()).days > 6]
        check(not stale, f"关键列近期有值（疑似过期/全空：{stale or '无'}）")
except Exception as e:
    errors.append(f"列完整性检查失败: {e}")
    print(f"  ✗ 列完整性检查失败: {e}")

# 3c. 保形预测产物形状（方法E：每期限有区间且 lower<upper；存在才查，缺失不致命）
try:
    cf_path = WEB_DIR / "conformal.json"
    if cf_path.exists():
        with open(cf_path, encoding="utf-8") as fh:
            cf = json.load(fh)
        hs = cf.get("horizons", [])
        bad = [h.get("horizon_days") for h in hs for b in h.get("bands", [])
               if b.get("lower_pct") is None or b["lower_pct"] >= b["upper_pct"]]
        check(len(hs) > 0 and not bad, f"conformal.json 形状正常（坏区间：{bad or '无'}）")
except Exception as e:
    errors.append(f"conformal 形状检查失败: {e}")
    print(f"  ✗ conformal 形状检查失败: {e}")

# 3d. 周期检验产物形状（方法F：status ok 时 p_global 合法、具名周期齐全；存在才查，缺失不致命）
try:
    cy_path = WEB_DIR / "cycles.json"
    if cy_path.exists():
        with open(cy_path, encoding="utf-8") as fh:
            cy = json.load(fh)
        res = cy.get("result", {})
        if res.get("status") == "ok":
            p = res.get("p_global")
            ok_p = isinstance(p, (int, float)) and 0.0 <= p <= 1.0
            nnamed = len(res.get("named_cycles", []))
            check(ok_p and nnamed >= 1,
                  f"cycles.json 形状正常（p_global={p}，具名周期 {nnamed} 条）")
except Exception as e:
    errors.append(f"cycles 形状检查失败: {e}")
    print(f"  ✗ cycles 形状检查失败: {e}")

# 3e. 跨检验族 FDR 形状（#5：BY 存活 ≤ BH 存活 是头条不变式；claims 非空。存在才查，缺失不致命）
try:
    fx_path = WEB_DIR / "fdr_crossfamily.json"
    if fx_path.exists():
        with open(fx_path, encoding="utf-8") as fh:
            fx = json.load(fh)
        by10, bh10 = fx.get("n_survive_by_10"), fx.get("n_survive_bh_10")
        ok = (isinstance(by10, int) and isinstance(bh10, int) and by10 <= bh10
              and len(fx.get("claims", [])) >= 1)
        check(ok, f"fdr_crossfamily.json 形状正常（BY {by10} ≤ BH {bh10}，{len(fx.get('claims', []))} 项）")
except Exception as e:
    errors.append(f"fdr_crossfamily 形状检查失败: {e}")
    print(f"  ✗ fdr_crossfamily 形状检查失败: {e}")

# 3f. 新闻 curated 条目须遵守自动下架（防"停在旧日期"回归 → CI 自动抓，不靠人工发现）
try:
    nj = WEB_DIR / "news.json"
    if nj.exists():
        with open(nj, encoding="utf-8") as fh:
            nd = json.load(fh)
        stale_cur = []
        for it in nd.get("items", []):
            if it.get("kind", "curated") == "curated":
                ds = (it.get("time") or "")[:10]
                try:
                    if (US_TODAY - datetime.date.fromisoformat(ds)).days > 3:
                        stale_cur.append(ds)
                except Exception:
                    pass
        check(not stale_cur, f"新闻无滞留的旧 curated 条目（发现 {stale_cur or '无'}）")
except Exception as e:
    errors.append(f"新闻 curated 新鲜度检查失败: {e}")
    print(f"  ✗ 新闻 curated 新鲜度检查失败: {e}")

# 3g. CPCV 过拟合概率 PBO 形状（方法G：pbo∈[0,1]、n_combos>0。存在才查，缺失不致命）
try:
    cv_path = WEB_DIR / "cpcv.json"
    if cv_path.exists():
        with open(cv_path, encoding="utf-8") as fh:
            cv = json.load(fh)
        r = cv.get("result", {})
        pbo_v = r.get("pbo")
        ok = (isinstance(pbo_v, (int, float)) and 0.0 <= pbo_v <= 1.0
              and int(r.get("n_combos", 0)) > 0)
        check(ok, f"cpcv.json 形状正常（PBO={pbo_v}，n_combos={r.get('n_combos')}）")
except Exception as e:
    errors.append(f"cpcv 形状检查失败: {e}")
    print(f"  ✗ cpcv 形状检查失败: {e}")

# 3h. 校准漂移形状（#3：嵌在 signals.json；verdict 合法、每折 gap 有界。存在才查，缺失不致命）
try:
    with open(WEB_DIR / "signals.json", encoding="utf-8") as fh:
        _sig = json.load(fh)
    cd = _sig.get("calibration_drift")
    if cd and cd.get("status") == "ok":
        ok = (cd.get("verdict") in {"stable", "drifting", "inconclusive"}
              and isinstance(cd.get("folds"), list) and len(cd["folds"]) >= 2
              and all(abs(f.get("gap", 9)) <= 1.0 for f in cd["folds"]))
        check(ok, f"signals.json calibration_drift 形状正常（{cd.get('verdict')}，{cd.get('n_folds')} 折）")
except Exception as e:
    errors.append(f"calibration_drift 形状检查失败: {e}")
    print(f"  ✗ calibration_drift 形状检查失败: {e}")

# 3i. 个股诚实体检形状（块0：tickers 非空、ok 票 vol 有界且回撤≤0。存在才查、缺失不致命）
try:
    sc_path = WEB_DIR / "stock_checkup.json"
    if sc_path.exists():
        with open(sc_path, encoding="utf-8") as fh:
            sc = json.load(fh)
        tks = sc.get("tickers", {})
        oks = [v for v in tks.values() if v.get("status") == "ok"]
        ok = (len(tks) > 0 and all(
            0 < v.get("ann_vol_pct", 0) < 500 and v.get("max_drawdown_pct", 1) <= 0 for v in oks))
        check(ok, f"stock_checkup.json 形状正常（{len(tks)} 票，{len(oks)} 个 ok）")
except Exception as e:
    errors.append(f"stock_checkup 形状检查失败: {e}")
    print(f"  ✗ stock_checkup 形状检查失败: {e}")

# 3i-2. 数据源健康形状（实时/缓存/过期透明度；存在才查，缺失不致命）
try:
    dh_path = WEB_DIR / "data_health.json"
    if dh_path.exists():
        with open(dh_path, encoding="utf-8") as fh:
            dh = json.load(fh)
        sm = dh.get("summary", {})
        src = dh.get("sources", {})
        ok = (isinstance(src, dict) and len(src) >= 20
              and sm.get("total") == len(src)
              and sm.get("freshness") in {"ok", "degraded", "incomplete"})
        check(ok, f"data_health.json 形状正常（{len(src)} 源，freshness={sm.get('freshness')}）")
except Exception as e:
    errors.append(f"data_health 形状检查失败: {e}")
    print(f"  ✗ data_health 形状检查失败: {e}")

# 3l. R3 短期反转形状(full 有 p_value/diff_pct、verdict 合法。存在才查、缺失不致命)
try:
    ov_path = WEB_DIR / "overreaction.json"
    if ov_path.exists():
        with open(ov_path, encoding="utf-8") as fh:
            ov = json.load(fh)
        if ov.get("status") == "ok":
            f = ov.get("full", {})
            ok = ("p_value" in f and "diff_pct" in f
                  and ov.get("verdict") in {"real", "faded", "real_recent_untested", "rejected", "inconclusive"})
            check(ok, f"overreaction.json 形状正常（verdict={ov.get('verdict')}）")
except Exception as e:
    errors.append(f"overreaction 形状检查失败: {e}")
    print(f"  ✗ overreaction 形状检查失败: {e}")

# 3j. 方法论完整性护栏(automation-first):个股"真规律"(三关全过)必须先经人工审视,
#     不得自动发布——若 patterns_fdr_real=True 进了已发布 JSON,说明人工停下被绕过 → 拦住发布。
try:
    sc_path = WEB_DIR / "stock_checkup.json"
    if sc_path.exists():
        with open(sc_path, encoding="utf-8") as fh:
            _sc = json.load(fh)
        check(_sc.get("patterns_fdr_real") is not True,
              "方法论护栏:无未经人工审视的个股'真规律'(patterns_fdr_real≠True)")
except Exception as e:
    errors.append(f"方法论完整性护栏失败: {e}")
    print(f"  ✗ 方法论完整性护栏失败: {e}")

# 3k. R1 市场风险体制形状（components 非空、有 composite。存在才查、缺失不致命）
try:
    mr_path = WEB_DIR / "market_regime.json"
    if mr_path.exists():
        with open(mr_path, encoding="utf-8") as fh:
            mr = json.load(fh)
        ok = (mr.get("status") == "ok" and isinstance(mr.get("components"), list)
              and len(mr["components"]) >= 2 and bool(mr.get("composite")))
        check(ok, f"market_regime.json 形状正常（{len(mr.get('components', []))} 指标）")
except Exception as e:
    errors.append(f"market_regime 形状检查失败: {e}")
    print(f"  ✗ market_regime 形状检查失败: {e}")

# 4. 账本完整性（append-only 数据的硬约束）
try:
    import csv
    ledger_specs = [
        ("paper_ledger.csv", ("date", "strategy"),
         ["date", "strategy", "action", "holdings", "cash", "equity", "note", "logged_at"]),
        ("prediction_log.csv", ("signal_date", "index", "model_version"),
         ["logged_at", "signal_date", "index", "model_version", "prob", "tier", "ret_1d", "ret_5d", "ret_20d"]),
    ]
    for fname, keys, hash_fields in ledger_specs:
        p = PROC_DIR / fname
        if p.exists():
            with open(p, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            seen = [tuple(str(r[k]) for k in keys) for r in rows]
            dup = len(seen) - len(set(seen))
            check(dup == 0, f"{fname} 无重复键（发现 {dup} 条重复）")
            import pandas as pd
            h_errors = verify_hash_chain(pd.DataFrame(rows), hash_fields)
            check(not h_errors, f"{fname} hash chain 完整（{h_errors or 'ok'}）")
except Exception as e:
    errors.append(f"账本检查失败: {e}")

if errors:
    print(f"\n[FAIL] {len(errors)} 项检查未通过，拒绝发布")
    sys.exit(1)
print("\n[OK] 全部自检通过，可以发布")
