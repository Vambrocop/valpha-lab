"""
long_history.py
长历史统计分析（S&P 500 1928+，Dow 1914+）

输出：
  long_history_monthly.json  — 各时段月度胜率/均值
  long_history_annual.json   — 年度回报矩阵
  holiday_effects.json       — 节前/节后/圣诞行情/1月效应
  bear_markets.json          — 熊市目录
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
import warnings
from pathlib import Path
from datetime import date, timedelta

warnings.filterwarnings("ignore")

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROC_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════
# 1. 下载长历史数据
# ══════════════════════════════════════════════════════════════════
def download_long_history():
    print("=== 下载长历史数据 ===")
    tickers = {
        "SP500": "^GSPC",   # S&P 500，从1928年
        "DJIA":  "^DJI",    # 道琼斯，从1914年
        "NASDAQ_COMP": "^IXIC",  # 纳斯达克，从1971年
    }
    frames = {}
    for name, ticker in tickers.items():
        try:
            df = yf.download(ticker, start="1920-01-01", end="2026-06-05",
                             auto_adjust=True, progress=False)
            if df.empty:
                print(f"  ⚠ {name} 无数据"); continue
            col = df["Close"]
            if isinstance(col, pd.DataFrame):
                col = col.iloc[:, 0]
            col = col.rename(name)
            col.index = pd.to_datetime(col.index)
            frames[name] = col
            col.to_csv(RAW_DIR / f"{name}_long.csv")
            print(f"  {name}: {col.index[0].year}–{col.index[-1].year}  {len(col)} 行")
        except Exception as e:
            print(f"  ⚠ {name} 失败: {e}")
    return frames


# ══════════════════════════════════════════════════════════════════
# 2. 多时段月度统计
# ══════════════════════════════════════════════════════════════════
PERIODS = {
    "1928+": "1928-01-01",
    "1950+": "1950-01-01",
    "1980+": "1980-01-01",
    "2000+": "2000-01-01",
    "2010+": "2010-01-01",
    "2020+": "2020-01-01",
}

MONTH_CN = ["","1月","2月","3月","4月","5月","6月",
            "7月","8月","9月","10月","11月","12月"]

def monthly_stats_by_period(price_series):
    """对每个时段计算月度胜率和均值"""
    monthly = price_series.resample("ME").last()
    monthly_ret = monthly.pct_change().dropna()

    result = {}
    for label, start in PERIODS.items():
        sub = monthly_ret[monthly_ret.index >= start]
        if len(sub) < 12:
            continue
        rows = []
        for m in range(1, 13):
            mask = sub.index.month == m
            vals = sub[mask]
            if len(vals) == 0:
                continue
            rows.append({
                "month": m,
                "month_cn": MONTH_CN[m],
                "win_rate": round(float((vals > 0).mean() * 100), 1),
                "avg_return": round(float(vals.mean() * 100), 2),
                "n": int(len(vals)),
                "best": round(float(vals.max() * 100), 1),
                "worst": round(float(vals.min() * 100), 1),
            })
        result[label] = rows
        print(f"  {label}: {len(sub)} 月数据")
    return result


def annual_stats_by_period(price_series):
    """年度回报"""
    yearly = price_series.resample("YE").last()
    yearly_ret = yearly.pct_change().dropna()

    rows = []
    for yr, ret in yearly_ret.items():
        rows.append({
            "year": int(yr.year),
            "return_pct": round(float(ret * 100), 1),
            "positive": bool(ret > 0),
        })
    return rows


# ══════════════════════════════════════════════════════════════════
# 3. 假日效应计算
#    美国股市主要假日：New Year / MLK / Presidents / Memorial /
#    Independence / Labor / Thanksgiving / Christmas
# ══════════════════════════════════════════════════════════════════
def _easter(year):
    """计算复活节（西方），用于推算耶稣受难节（周五）"""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day   = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def us_market_holidays(year):
    """返回某年美国股市主要假日日期列表"""
    def nth_weekday(year, month, weekday, n):
        """第n个weekday（0=周一）"""
        d = date(year, month, 1)
        count = 0
        while True:
            if d.weekday() == weekday:
                count += 1
                if count == n:
                    return d
            d += timedelta(days=1)

    def last_weekday(year, month, weekday):
        d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
        while d.weekday() != weekday:
            d -= timedelta(days=1)
        return d

    def adjust_weekend(d):
        """若落在周末则调整到最近工作日"""
        if d.weekday() == 5: return d - timedelta(days=1)  # 周六→周五
        if d.weekday() == 6: return d + timedelta(days=1)  # 周日→周一
        return d

    easter = _easter(year)
    good_friday = easter - timedelta(days=2)

    holidays = {
        "New Year":        adjust_weekend(date(year, 1, 1)),
        "MLK Day":         nth_weekday(year, 1, 0, 3),
        "Presidents Day":  nth_weekday(year, 2, 0, 3),
        "Good Friday":     good_friday,
        "Memorial Day":    last_weekday(year, 5, 0),
        "Independence":    adjust_weekend(date(year, 7, 4)),
        "Labor Day":       nth_weekday(year, 9, 0, 1),
        "Thanksgiving":    nth_weekday(year, 11, 3, 4),
        "Christmas":       adjust_weekend(date(year, 12, 25)),
    }
    return holidays


def compute_holiday_effects(sp500_daily):
    """计算节前/节后/特殊窗口效应"""
    print("\n=== 假日效应计算 ===")
    df = sp500_daily.copy()
    df = df.sort_index()
    daily_ret = df.pct_change().dropna()

    # 生成所有假日日期集合
    holiday_dates = {}  # date → holiday_name
    for yr in range(1950, 2027):
        try:
            hols = us_market_holidays(yr)
            for name, d in hols.items():
                holiday_dates[d] = name
        except Exception:
            pass

    hol_set = set(holiday_dates.keys())
    trading_days = pd.Series(daily_ret.index.date)

    # 对每个交易日标注是否是节前/节后
    pre_holiday  = []  # 节前一个交易日
    post_holiday = []  # 节后第一个交易日

    for i, td in enumerate(daily_ret.index):
        d = td.date()
        # 找下一/上一个交易日
        next_days = [x for x in daily_ret.index[i+1:i+8] if x.date() in hol_set or (x - td).days <= 7]
        prev_days = [x for x in daily_ret.index[max(0,i-7):i] if x.date() in hol_set]

        # 节前：明天或后天是假日
        is_pre = any((x.date() - d).days <= 3 and x.date() in hol_set
                     for x in daily_ret.index[i+1:i+5])
        # 节后：前几天有假日
        is_post = any(d - x.date() >= timedelta(days=0) and x.date() in hol_set
                      and (d - x.date()).days <= 3
                      for x in [pd.Timestamp(hd) for hd in hol_set if hd < d][-10:])

        if is_pre:  pre_holiday.append(td)
        if is_post: post_holiday.append(td)

    pre_returns  = daily_ret.loc[daily_ret.index.isin(pre_holiday)]
    post_returns = daily_ret.loc[daily_ret.index.isin(post_holiday)]
    normal_ret   = daily_ret.loc[~daily_ret.index.isin(pre_holiday + post_holiday)]

    print(f"  节前交易日: n={len(pre_returns)}")
    print(f"  节后交易日: n={len(post_returns)}")

    # 各类窗口统计
    def stats(s, label):
        wr  = float((s > 0).mean() * 100)
        avg = float(s.mean() * 100)
        n   = len(s)
        print(f"  {label}: 胜率={wr:.1f}%  均值={avg:+.2f}%  n={n}")
        return {"win_rate": round(wr,1), "avg_return": round(avg,3), "n": n}

    result = {
        "pre_holiday":  stats(pre_returns,  "节前"),
        "post_holiday": stats(post_returns, "节后"),
        "normal":       stats(normal_ret,   "普通"),
    }

    # ── 圣诞行情 Santa Claus Rally (Dec 26 – Jan 2 区间) ──────────
    santa = daily_ret[(daily_ret.index.month == 12) & (daily_ret.index.day >= 26) |
                      (daily_ret.index.month == 1)  & (daily_ret.index.day <= 3)]
    result["santa_claus_rally"] = stats(santa, "圣诞行情(Dec26-Jan3)")

    # ── 1月效应 (前5个交易日) ──────────────────────────────────────
    jan = daily_ret[daily_ret.index.month == 1]
    jan_first5 = []
    for yr in jan.index.year.unique():
        sub = jan[jan.index.year == yr].head(5)
        jan_first5.append(sub)
    jan5 = pd.concat(jan_first5) if jan_first5 else pd.Series(dtype=float)
    result["january_effect"] = stats(jan5, "1月效应(前5交易日)")

    # ── 感恩节行情 ─────────────────────────────────────────────────
    # 感恩节前一天（周三）和感恩节后第一天（周五）
    thanksgiving_eves = []
    thanksgiving_fridays = []
    for yr in range(1950, 2027):
        try:
            hols = us_market_holidays(yr)
            tg = hols.get("Thanksgiving")
            if tg:
                tg_ts = pd.Timestamp(tg)
                eve = tg_ts - pd.Timedelta(days=1)
                fri = tg_ts + pd.Timedelta(days=1)
                if eve in daily_ret.index: thanksgiving_eves.append(eve)
                if fri in daily_ret.index: thanksgiving_fridays.append(fri)
        except Exception:
            pass
    if thanksgiving_eves:
        result["thanksgiving_eve"]    = stats(daily_ret.loc[thanksgiving_eves],    "感恩节前夕")
    if thanksgiving_fridays:
        result["thanksgiving_friday"] = stats(daily_ret.loc[thanksgiving_fridays], "黑色星期五")

    # ── 月初/月末效应（更细分）────────────────────────────────────
    def dom_stats(day_range, label):
        mask = daily_ret.index.day.isin(day_range)
        return stats(daily_ret[mask], label)

    result["dom"] = {
        "days_1_3":  dom_stats(range(1,4),   "月初1-3日"),
        "days_4_10": dom_stats(range(4,11),  "月初4-10日"),
        "days_11_20":dom_stats(range(11,21), "月中11-20日"),
        "days_21_25":dom_stats(range(21,26), "月末21-25日"),
        "days_26_31":dom_stats(range(26,32), "月末26-31日"),
    }

    # ── 星期效应（日频，更大样本）────────────────────────────────
    dow_stats = {}
    dow_names = {0:"周一",1:"周二",2:"周三",3:"周四",4:"周五"}
    for dow_i, dow_name in dow_names.items():
        s = daily_ret[daily_ret.index.weekday == dow_i]
        dow_stats[dow_name] = stats(s, f"日频{dow_name}")
    result["dow_daily"] = dow_stats

    return result


# ══════════════════════════════════════════════════════════════════
# 4. 熊市目录
# ══════════════════════════════════════════════════════════════════
BEAR_MARKETS = [
    {"name":"大萧条", "start":"1929-09", "end":"1932-06", "drawdown":-89.2, "cause":"银行系统崩溃、货币紧缩", "recovery_months":266},
    {"name":"二战前夕", "start":"1937-03", "end":"1938-04", "drawdown":-54.5, "cause":"财政紧缩过早", "recovery_months":49},
    {"name":"战后调整", "start":"1946-05", "end":"1949-06", "drawdown":-29.6, "cause":"战后通胀、去库存", "recovery_months":37},
    {"name":"闪崩1962", "start":"1961-12", "end":"1962-06", "drawdown":-27.1, "cause":"古巴导弹危机前夕", "recovery_months":14},
    {"name":"滞胀熊市", "start":"1973-01", "end":"1974-10", "drawdown":-48.2, "cause":"石油危机+尼克松水门", "recovery_months":69},
    {"name":"黑色星期一", "start":"1987-08", "end":"1987-12", "drawdown":-33.5, "cause":"程序化交易崩溃", "recovery_months":20},
    {"name":"互联网泡沫", "start":"2000-03", "end":"2002-10", "drawdown":-49.1, "cause":"科技股估值泡沫破裂", "recovery_months":56},
    {"name":"金融危机", "start":"2007-10", "end":"2009-03", "drawdown":-56.8, "cause":"次贷危机+雷曼兄弟", "recovery_months":49},
    {"name":"欧债危机", "start":"2011-04", "end":"2011-10", "drawdown":-19.4, "cause":"欧洲主权债务危机", "recovery_months":6},
    {"name":"新冠闪崩", "start":"2020-02", "end":"2020-03", "drawdown":-33.9, "cause":"COVID-19全球封锁", "recovery_months":5},
    {"name":"加息熊市", "start":"2022-01", "end":"2022-10", "drawdown":-27.5, "cause":"美联储40年最快加息周期", "recovery_months":20},
]


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
def run_all():
    frames = download_long_history()
    sp = frames.get("SP500")
    if sp is None:
        print("⚠ SP500数据缺失，退出"); return

    # 月度多时段统计
    print("\n=== 多时段月度胜率 ===")
    monthly_by_period = monthly_stats_by_period(sp)

    # 年度回报
    annual = annual_stats_by_period(sp)
    print(f"\n年度数据: {annual[0]['year']}–{annual[-1]['year']}, {len(annual)} 年")

    # 假日效应（日频）
    holiday_effects = compute_holiday_effects(sp)

    # 组合输出
    out = {
        "monthly_by_period": monthly_by_period,
        "annual_returns": annual,
        "holiday_effects": holiday_effects,
        "bear_markets": BEAR_MARKETS,
        "meta": {
            "sp500_start": str(sp.index[0].date()),
            "sp500_end":   str(sp.index[-1].date()),
            "n_years":     int((sp.index[-1] - sp.index[0]).days / 365),
        }
    }

    out_path = PROC_DIR / "long_history.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✓ long_history.json 写入完成  ({out_path.stat().st_size//1024} KB)")

    # 汇总打印
    print("\n=== 各时段9月胜率（最弱月对比）===")
    for period, rows in monthly_by_period.items():
        sep = next((r for r in rows if r["month"] == 9), None)
        if sep:
            print(f"  {period}: 9月胜率={sep['win_rate']}%  均值={sep['avg_return']}%  n={sep['n']}")

    print("\n=== 节前 vs 普通日 ===")
    for k in ["pre_holiday","post_holiday","normal","santa_claus_rally","january_effect"]:
        v = holiday_effects.get(k,{})
        print(f"  {k}: 胜率={v.get('win_rate','?')}%  均值={v.get('avg_return','?')}%  n={v.get('n','?')}")

    return out


if __name__ == "__main__":
    run_all()
