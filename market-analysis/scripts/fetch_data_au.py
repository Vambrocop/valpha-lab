"""
fetch_data_au.py — 澳洲市场数据抓取（B1 产品化，2026-07-12，HANDOVER.md §命题B）

沿用 B0 探针（fetch_data_au.py 原版）验证过的抓取管线，产品化为**一次运行、两份输出**：
  1. `au_probe.json`  — 数据体检（史深/近期缺口/可回测性），供人工/B2·B3 判断门槛用，不接前端。
  2. `au_market.json` — 展示数据（^AXJO/^AORD 概览 + AUDUSD + ASX50 涨跌榜近期动量），供 `au.html` 读取。

独立平行区：不碰美股任何脚本/数据/账本/基准；只读写 raw/au/ 与本文件两个 web/ JSON。

数据卫生（B0 结论，HANDOVER.md 已记档）：
  - **剔 NCM**（Newcrest 已退市并入 Newmont）——不进抓取池，只在 au_market.json.excluded 里留痕。
  - **COL 标短史**（7.6y·2018 从 Wesfarmers 分拆）——short_history=true，B3 固定窗口回测须单独处理。
  - **基准/主指数用 ^AXJO**（33.6y，覆盖 2008/2000 完整周期；^AORD 41.9y 作全市场对照，不可直接交易）。
  - **FMG 留痕不拦**：一类买壳身份连续性问题（1988-2002 是壳公司稀疏数据，2003 起才是真 Fortescue）是
    **B3 回测门**要处理的；B1 纯描述、只读近期动量，不受影响——但仍打 identity_note 留痕，别装看不见。

fail-soft：单票失败不阻断，静默跳过，仅记入 au_probe.json 的 fetch_failed 列表。

运行：
  $env:PYTHONUTF8='1'; py market-analysis/scripts/fetch_data_au.py
"""

import json
import time
import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date, datetime, timezone

BASE = Path(__file__).parent.parent
RAW_DIR = BASE / "data" / "raw" / "au"
WEB_DIRS = [BASE / "web", BASE.parent / "docs"]
RAW_DIR.mkdir(parents=True, exist_ok=True)
for d in WEB_DIRS:
    d.mkdir(parents=True, exist_ok=True)

OK_YEARS = 10           # ≥10年 视为 ok_for_backtest（au_probe.json 诊断口径，沿用 B0）
STALE_DAYS = 14          # 距今超过此天数视为"近期有缺口"（ASX假期与美股不同，留余量）

# ── 指数 / 汇率 / 股票池 ──────────────────────────────────────────
INDEX_TICKERS = {
    "AXJO": ("^AXJO", "ASX200"),   # 基准（不可直接交易，33.6年史，覆盖完整周期）
    "AORD": ("^AORD", "All Ordinaries"),  # 全市场对照（41.9年史）
}
FX_TICKERS = {
    "AUDUSD": ("AUDUSD=X", "AUD/USD"),
}
ETF_TICKERS = {
    "VAS_AX": ("VAS.AX", "Vanguard AU Shares ETF"),
    "STW_AX": ("STW.AX", "SPDR ASX200 ETF"),
}

# ASX 大盘票（ASX50 常识挑选，NCM 已剔除——见 EXCLUDED）
STOCK_TICKERS = {
    "BHP": "BHP.AX", "CBA": "CBA.AX", "CSL": "CSL.AX", "NAB": "NAB.AX",
    "WBC": "WBC.AX", "ANZ": "ANZ.AX", "WES": "WES.AX", "MQG": "MQG.AX",
    "GMG": "GMG.AX", "WOW": "WOW.AX", "TLS": "TLS.AX", "RIO": "RIO.AX",
    "FMG": "FMG.AX", "TCL": "TCL.AX", "COL": "COL.AX", "WDS": "WDS.AX",
    "QBE": "QBE.AX", "STO": "STO.AX", "REA": "REA.AX", "ALL": "ALL.AX",
    "PME": "PME.AX", "XRO": "XRO.AX", "WTC": "WTC.AX", "JHX": "JHX.AX",
    "SHL": "SHL.AX", "COH": "COH.AX", "AMC": "AMC.AX", "SUN": "SUN.AX",
}

# 显式剔除（不抓，只留痕说明原因——诚实标注"为什么这票不在榜上"，不是默默漏掉）
EXCLUDED = {
    "NCM": {
        "ticker": "NCM.AX",
        "reason_zh": "Newcrest Mining 已于 2023 年退市，被 Newmont 并购吸收，ticker 不再存在。",
        "reason_en": "Newcrest Mining delisted 2023, merged into Newmont — ticker no longer exists.",
    },
}

# 短史标注（B3 固定窗口回测须单独处理；B1 展示层如实标注，不隐藏）
SHORT_HISTORY_NOTES = {
    "COL": {
        "years_history": 7.6,
        "note_zh": "2018 年从 Wesfarmers 分拆上市，仅 7.6 年史（COL 上市前无独立股价，非缺口）。",
        "note_en": "Spun off from Wesfarmers in 2018 — only 7.6y of history (no standalone price before listing, not a data gap).",
    },
}

# 公司身份连续性留痕（B3 回测门要用；B1 纯描述不受影响，但留痕不装看不见）
IDENTITY_NOTES = {
    "FMG": {
        "note_zh": "1988–2002 为壳公司稀疏数据（$0.0006 极低价，非真实 Fortescue 股价），"
                   "2003 年起才是真正 Fortescue Metals 的连续交易史。长窗口回测前需身份连续性校验（B3 待办）；"
                   "本页仅展示近期动量，不受影响。",
        "note_en": "1988–2002 is thinly-traded shell-company data ($0.0006, not real Fortescue price) — "
                   "continuous Fortescue Metals history only starts 2003. Long-window backtests need an identity-"
                   "continuity check first (B3 TODO); this page only shows recent momentum, unaffected.",
    },
}


def _yf_fetch_max(ticker):
    """period='max' 全史抓取，带退避重试；失败回退 Ticker.history(period='max')。
    永不抛异常：全部失败返回 (None, error_str)。"""
    last_err = None
    for attempt in range(3):
        try:
            df = yf.download(ticker, period="max", auto_adjust=True, progress=False)
            if not df.empty:
                col = df["Close"]
                if isinstance(col, pd.DataFrame):
                    col = col.iloc[:, 0]
                col = col.dropna()
                col.index = pd.to_datetime(col.index)
                try:
                    col.index = col.index.tz_localize(None)
                except Exception:
                    pass
                return col.rename(ticker), None
        except Exception as e:
            last_err = e
        time.sleep(1.0 * (attempt + 1))  # 1s, 2s, 3s 退避

    try:
        hist = yf.Ticker(ticker).history(period="max", auto_adjust=True)
        if not hist.empty:
            col = hist["Close"].dropna()
            col.index = pd.to_datetime(col.index)
            try:
                col.index = col.index.tz_localize(None)
            except Exception:
                pass
            return col.rename(ticker), None
    except Exception as e:
        last_err = e

    return None, str(last_err)[:300] if last_err else "empty"


def _diag(series):
    """B0 诊断口径：史深/近期缺口/是否够回测。"""
    start = series.index.min()
    last = series.index.max()
    n_rows = int(len(series))
    years = round((last - start).days / 365.25, 1)
    age_days = (date.today() - last.date()).days
    return {
        "start_date": start.strftime("%Y-%m-%d"),
        "last_date": last.strftime("%Y-%m-%d"),
        "n_rows": n_rows,
        "years": years,
        "age_days": age_days,
        "recent_gap": age_days > STALE_DAYS,
        "ok_for_backtest": years >= OK_YEARS,
    }


def _market_metrics(p, price_round=2):
    """近期动量指标——与 build_valpha150.py 的 compute_metrics 同一套口径（d1/w1/m1/c6/c1/v/fh），
    刻意复用同一公式，让 au.html 的排序/展示代码能照抄 valpha150.html 的骨架，不造新范式。"""
    p = p.dropna()
    if len(p) < 2:
        return None
    ret = p.pct_change()
    last = float(p.iloc[-1])

    def chg(n):
        return round((last / p.iloc[-(n + 1)] - 1) * 100, 2) if len(p) > n else None

    d1 = chg(1)
    w1 = chg(5)
    m1 = chg(21)
    c6 = round((last / p.iloc[-126] - 1) * 100, 1) if len(p) > 126 else None
    c1 = round((last / p.iloc[-252] - 1) * 100, 1) if len(p) > 252 else None
    tail20 = ret.tail(20).dropna()
    vol = round(float(tail20.std() * np.sqrt(252) * 100), 1) if len(tail20) > 5 else None
    fh = round((last / p.tail(252).max() - 1) * 100, 1) if len(p) >= 20 else None
    return {"p": round(last, price_round), "d1": d1, "w1": w1, "m1": m1, "c6": c6, "c1": c1, "v": vol, "fh": fh}


def _fetch_one(name, ticker, price_round=2):
    """抓一票→(series, diag, metrics)；失败返回 (None, diag_failed, None)，永不抛异常。"""
    print(f"  抓 {name} ({ticker})...")
    series, err = _yf_fetch_max(ticker)
    if series is None or series.empty:
        print(f"    x 失败：{err}")
        return None, {
            "status": "fetch_failed", "error": err, "start_date": None, "last_date": None,
            "n_rows": 0, "years": None, "age_days": None, "recent_gap": None, "ok_for_backtest": False,
        }, None
    series.to_csv(RAW_DIR / f"{name}.csv")
    diag = _diag(series)
    diag["status"] = "ok"
    diag["error"] = None
    m = _market_metrics(series, price_round=price_round)
    print(f"    -> {diag['n_rows']} 行，{diag['start_date']} ~ {diag['last_date']}（{diag['years']} 年）"
          f"{'  [近期缺口]' if diag['recent_gap'] else ''}")
    return series, diag, m


def run():
    generated = datetime.now(timezone.utc).isoformat()
    probe_results = []
    market = {
        "generated": generated,
        "note_tz": {
            "zh": "ASX 本地日 = 交易日（与美股「本地日期比美东快一天」的注释方向相反——阿德莱德本地日就是当天 ASX 交易日）。",
            "en": "ASX local date = trading date (opposite of the US-stock 'local date is a day ahead of ET' note — Adelaide's local date IS the ASX trading day).",
        },
        "index": {},
        "audusd": None,
        "stocks": [],
        "excluded": [
            {"name": k, "ticker": v["ticker"], "reason_zh": v["reason_zh"], "reason_en": v["reason_en"]}
            for k, v in EXCLUDED.items()
        ],
    }

    print("=== 指数（基准 ^AXJO）===")
    for name, (ticker, label) in INDEX_TICKERS.items():
        series, diag, m = _fetch_one(name, ticker, price_round=1)
        probe_results.append({"group": "index", "name": name, "ticker": ticker, **diag})
        if m is not None:
            market["index"][name] = {
                "ticker": ticker, "label": label, "as_of": diag["last_date"],
                "years_history": diag["years"], **m,
            }

    print("\n=== 汇率 ===")
    for name, (ticker, label) in FX_TICKERS.items():
        series, diag, m = _fetch_one(name, ticker, price_round=4)
        probe_results.append({"group": "fx", "name": name, "ticker": ticker, **diag})
        if m is not None:
            market["audusd"] = {
                "ticker": ticker, "label": label, "as_of": diag["last_date"],
                "years_history": diag["years"], **m,
            }

    print("\n=== 可交易ETF对照（诊断用，不上榜）===")
    for name, (ticker, label) in ETF_TICKERS.items():
        series, diag, m = _fetch_one(name, ticker, price_round=2)
        probe_results.append({"group": "etf", "name": name, "ticker": ticker, **diag})

    print("\n=== ASX50 大盘票 ===")
    for name, ticker in STOCK_TICKERS.items():
        series, diag, m = _fetch_one(name, ticker, price_round=2)
        probe_results.append({"group": "stock", "name": name, "ticker": ticker, **diag})
        if m is None:
            continue
        row = {"t": ticker, "n": name, "as_of": diag["last_date"], "years_history": diag["years"], **m}
        if name in SHORT_HISTORY_NOTES:
            sh = SHORT_HISTORY_NOTES[name]
            row["short_history"] = True
            row["short_history_note"] = {"zh": sh["note_zh"], "en": sh["note_en"]}
        else:
            row["short_history"] = False
        if name in IDENTITY_NOTES:
            idn = IDENTITY_NOTES[name]
            row["identity_note"] = {"zh": idn["note_zh"], "en": idn["note_en"]}
        else:
            row["identity_note"] = None
        market["stocks"].append(row)

    market["n_stocks"] = len(market["stocks"])
    market["n_excluded"] = len(market["excluded"])
    # 顶层 as_of：以 ^AXJO（基准）的最新交易日为准；股票/AUDUSD 各自也带独立 as_of（不同数据源可能不同步）
    market["as_of"] = market["index"].get("AXJO", {}).get("as_of")

    # ── au_probe.json（B0 诊断，供人工/B2·B3 判断门槛，保持原有结构不破坏既有读者）──
    ok_results = [r for r in probe_results if r["status"] == "ok"]
    failed = [r for r in probe_results if r["status"] == "fetch_failed"]
    stocks_ok = [r for r in ok_results if r["group"] == "stock"]
    n_ok_10y = sum(1 for r in ok_results if r["ok_for_backtest"])
    n_short = sum(1 for r in ok_results if not r["ok_for_backtest"])
    n_stock_ok_10y = sum(1 for r in stocks_ok if r["ok_for_backtest"])
    n_stock_short = sum(1 for r in stocks_ok if not r["ok_for_backtest"])
    axjo = next((r for r in probe_results if r["name"] == "AXJO"), None)
    aord = next((r for r in probe_results if r["name"] == "AORD"), None)
    vas = next((r for r in probe_results if r["name"] == "VAS_AX"), None)
    stw = next((r for r in probe_results if r["name"] == "STW_AX"), None)
    probe_out = {
        "summary": {
            "generated": generated,
            "n_total": len(probe_results),
            "n_fetch_failed": len(failed),
            "n_ok_10y": n_ok_10y,
            "n_short": n_short,
            "stock_pool": {
                "n_total": len(STOCK_TICKERS),
                "n_fetched_ok": len(stocks_ok),
                "n_ok_10y": n_stock_ok_10y,
                "n_short": n_stock_short,
                "n_fetch_failed": len(STOCK_TICKERS) - len(stocks_ok),
            },
            "index_vs_etf": {
                "AXJO_years": axjo.get("years") if axjo else None,
                "AORD_years": aord.get("years") if aord else None,
                "VAS_AX_years": vas.get("years") if vas else None,
                "STW_AX_years": stw.get("years") if stw else None,
            },
            "excluded_from_pool": list(EXCLUDED.keys()),
        },
        "tickers": probe_results,
    }

    for d in WEB_DIRS:
        (d / "au_probe.json").write_text(
            json.dumps(probe_out, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        (d / "au_market.json").write_text(
            json.dumps(market, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")

    print(f"\n=== 汇总 ===")
    print(f"指数 {len(market['index'])}/{len(INDEX_TICKERS)}，AUDUSD {'ok' if market['audusd'] else 'FAILED'}，"
          f"股票 {market['n_stocks']}/{len(STOCK_TICKERS)}（剔除 {market['n_excluded']}：{list(EXCLUDED.keys())}）")
    if failed:
        print("失败票（fail-soft，未阻断）：")
        for r in failed:
            print(f"  {r['name']} ({r['ticker']}): {r['error']}")
    print(f"写出 → au_market.json / au_probe.json → {[str(d) for d in WEB_DIRS]}")
    print(f"写出 → {RAW_DIR} (逐票 CSV，gitignored)")

    return market, probe_out


if __name__ == "__main__":
    run()
