"""signal_model.py — 生产与验证共享的模型核心（ROADMAP P0-1）

build_signals.py（生产打分）与 walk_forward.py（滚动验证）必须 import 本模块，
禁止各自复制实现——验证跑的必须是部署的同一套逻辑。

注意：日历因子目前仍是两套（生产用硬编码长历史表，walk_forward 用各折学习值），
统一计划在 ROADMAP P2-1，本模块先收编全部共享原语。
"""
import calendar
import numpy as np
from datetime import date, timedelta

# ── 技术因子阈值（生产与验证唯一来源）─────────────────────────────
BTC_MOM_THRESH = 0.05   # BTC 20日动量 ±5% 触发
DXY_TREND_THRESH = 0.01  # 美元 20日趋势 ±1% 触发
VOL_HIGH = 0.25          # 年化波动 >25% = 高波动
VOL_LOW = 0.15           # 年化波动 <15% = 低波动
RSI_OVERBOUGHT = 75
RSI_OVERSOLD = 35

# ── 收缩估计 ──────────────────────────────────────────────────────
SHRINK_N = 200  # 收缩强度：样本 n 越小，LR 越向 1（无信息）收缩


def shrink_lr(lr, n, k=SHRINK_N):
    """经验 LR 的样本量收缩：n=0 → 1.0（无信息），n→∞ → 原值"""
    return 1 + (lr - 1) * n / (n + k)


# ── 档位 ──────────────────────────────────────────────────────────
def tier(prob):
    if prob >= 0.80: return 5
    if prob >= 0.60: return 4
    if prob >= 0.40: return 3
    if prob >= 0.20: return 2
    return 1


# ── 贝叶斯概率融合 ────────────────────────────────────────────────
def bayesian_update(prior, likelihoods):
    """log-odds 空间累乘 LR 后压回 (0,1)。

    已知方法论局限（ROADMAP P2-2）：传入的 LR 是胜率比而非胜算比，
    且因子间相关性未建模——本函数只保证生产与验证算的是同一个数。
    """
    prior = float(np.clip(prior, 0.02, 0.98))
    log_odds = np.log(prior / (1 - prior))
    for lr in likelihoods:
        log_odds += np.log(max(lr, 0.01))
    prob = 1 / (1 + np.exp(-log_odds))
    return float(np.clip(prob, 0.02, 0.98))


# ── 日历原语 ──────────────────────────────────────────────────────
def week_of_month(ts):
    first_dow = ts.replace(day=1).weekday()
    return (ts.day + first_dow - 1) // 7 + 1


# ── 技术指标 ──────────────────────────────────────────────────────
def rsi(returns, period=14):
    gain = returns.clip(lower=0).rolling(period).mean()
    loss = (-returns.clip(upper=0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / (loss + 1e-10))


# ── 美股假日日历 ──────────────────────────────────────────────────
def _easter(year):
    a = year % 19; b = year // 100; c = year % 100
    d = b // 4; e = b % 4; f = (b + 8) // 25
    g = (b - f + 1) // 3; h = (19*a + b - d - g + 15) % 30
    i = c // 4; k = c % 4; l = (32 + 2*e + 2*i - h - k) % 7
    m = (a + 11*h + 22*l) // 451
    month = (h + l - 7*m + 114) // 31
    day = ((h + l - 7*m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday(year, month, weekday, n):
    d = date(year, month, 1); count = 0
    while True:
        if d.weekday() == weekday:
            count += 1
            if count == n: return d
        d += timedelta(days=1)


def _last_weekday(year, month, weekday):
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _adjust_weekend(d):
    if d.weekday() == 5: return d - timedelta(days=1)
    if d.weekday() == 6: return d + timedelta(days=1)
    return d


def us_holidays(year):
    easter = _easter(year)
    holidays = {
        _adjust_weekend(date(year, 1, 1)),       # New Year
        _nth_weekday(year, 1, 0, 3),             # MLK Day
        _nth_weekday(year, 2, 0, 3),             # Presidents Day
        easter - timedelta(days=2),               # Good Friday
        _last_weekday(year, 5, 0),               # Memorial Day
        _adjust_weekend(date(year, 7, 4)),        # Independence Day
        _nth_weekday(year, 9, 0, 1),             # Labor Day
        _nth_weekday(year, 11, 3, 4),            # Thanksgiving
        _adjust_weekend(date(year, 12, 25)),      # Christmas
    }
    # Juneteenth：NYSE 自 2022 年起 6 月 19 日休市
    if year >= 2022:
        holidays.add(_adjust_weekend(date(year, 6, 19)))
    return holidays


# 预生成 1990-2030 年假日集合
HOLIDAY_SET = set()
THANKSGIVING_DATES = set()
for _yr in range(1990, 2031):
    HOLIDAY_SET |= us_holidays(_yr)
    THANKSGIVING_DATES.add(_nth_weekday(_yr, 11, 3, 4))
