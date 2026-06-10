"""util_time.py — 美东交易日时间工具（全栈统一的"今天"定义）"""
import pandas as pd
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def us_now():
    return pd.Timestamp.now(tz=ET)


def us_today_str():
    return us_now().strftime("%Y-%m-%d")


def is_final_trading_day(date_str):
    """该日期的日线是否已是官方收盘价。

    盘中抓取的当日 bar 是临时价（fetch_data 的小时线兜底），
    模拟盘成交、预测回填等「不可篡改」操作只能用 final 数据。
    美东 16:05 之后当日才算 final。
    """
    now = us_now()
    today = now.strftime("%Y-%m-%d")
    if date_str < today:
        return True
    if date_str > today:
        return False
    return (now.hour, now.minute) >= (16, 5)
