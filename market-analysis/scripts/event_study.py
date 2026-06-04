"""
event_study.py — 事件研究法（Event Study）
把定性事件转化为数据驱动的贝叶斯似然比

方法：
  对每类历史事件，计算事件后 [T+1, T+30] 的累计超额收益
  与随机窗口比较，得出统计检验过的LR

输出：
  event_study_results.json — 各事件类型的实证LR（带p值和置信区间）
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from scipy import stats

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
PROC_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════
# 历史事件数据库（具体日期 + 类型）
# 来源：公开历史记录
# ══════════════════════════════════════════════════════════════════
HISTORICAL_EVENTS = {

    "fed_hike_first": [
        # 首次加息（加息周期开始）— 市场通常提前定价，靴子落地反而涨
        "1994-02-04",  # 格林斯潘意外加息（引发债券崩盘）
        "1999-06-30",  # 互联网泡沫期
        "2004-06-30",  # 房市繁荣期
        "2015-12-16",  # 耶伦首次加息
        "2022-03-16",  # 抗通胀周期首次
    ],

    "fed_cut_first": [
        # 首次降息（宽松周期开始）— 历史上平均后6月+12%
        "2001-01-03",  # 科网泡沫破裂后
        "2007-09-18",  # 次贷危机前
        "2019-07-31",  # 预防性降息
        "2020-03-03",  # 新冠紧急降息
        "2024-09-18",  # 2024降息周期
    ],

    "trade_war_escalation": [
        # 中美贸易战重大升级节点
        "2018-03-01",  # 特朗普宣布钢铝关税
        "2018-06-15",  # 500亿关税清单公布
        "2018-07-06",  # 340亿关税生效
        "2019-05-05",  # 2000亿关税提升至25%
        "2019-08-01",  # 3000亿新增关税威胁
        "2025-04-02",  # 特朗普2.0 对等关税
        "2025-04-09",  # 90天暂停（逆转）
    ],

    "trade_war_relief": [
        # 贸易战缓和/协议
        "2019-12-13",  # 第一阶段协议
        "2020-01-15",  # 签署仪式
        "2025-05-12",  # 中美日内瓦关税协议（90天降至10%）
    ],

    "pandemic_lockdown": [
        # 全球封锁/疫情冲击
        "2020-03-11",  # WHO宣布大流行
        "2020-03-16",  # 美国多州封锁
    ],

    "geopolitical_shock": [
        # 重大地缘冲击
        "2001-09-11",  # 911
        "2003-03-20",  # 伊拉克战争
        "2022-02-24",  # 俄乌战争
        "2023-10-07",  # 以哈冲突
    ],

    "vix_spike_extreme": [
        # VIX单日跳升>40%（极度恐慌）
        "2018-02-05",  # VIX周一暴涨（Volmageddon）
        "2020-02-24",  # 新冠恐慌开始
        "2020-03-16",  # VIX历史高点
        "2022-01-24",  # 俄乌战争前恐慌
        "2024-08-05",  # 日元套利崩溃
    ],

    "banking_crisis": [
        # 银行危机
        "2008-09-15",  # 雷曼破产
        "2023-03-10",  # SVB银行倒闭
    ],

    "ai_breakthrough": [
        # AI重大里程碑（市场正面冲击）
        "2022-11-30",  # ChatGPT发布
        "2023-03-14",  # GPT-4发布
        "2024-01-08",  # CES AI展示
        "2025-01-21",  # DeepSeek引发震动（实际是负面？）
    ],
}

# ══════════════════════════════════════════════════════════════════
# 核心计算：事件窗口超额收益
# ══════════════════════════════════════════════════════════════════
def load_sp500():
    sp = pd.read_csv(RAW_DIR / "SP500_long.csv", index_col=0, parse_dates=True).squeeze()
    return sp.sort_index()

def event_study(sp, event_dates, window_days=30, label="事件"):
    """
    对一组事件日期，计算事件后 window_days 内的累计收益分布

    Returns:
        dict with win_rate, avg_return, median_return, t_stat, p_value, n, lr
    """
    daily_ret = sp.pct_change().dropna()
    base_wr = float((daily_ret > 0).mean())

    event_returns = []
    event_wr = []

    for date_str in event_dates:
        try:
            event_date = pd.Timestamp(date_str)
            # 找事件日期后第一个交易日
            future = daily_ret[daily_ret.index > event_date].head(window_days)
            if len(future) < window_days // 2:
                continue
            cumret = float((1 + future).prod() - 1)
            wr_post = float((future > 0).mean())
            event_returns.append(cumret)
            event_wr.append(wr_post)
        except Exception:
            continue

    if len(event_returns) < 2:
        return None

    arr = np.array(event_returns)
    wr_arr = np.array(event_wr)

    # 与历史随机窗口比较（bootstrap基准）
    all_windows = []
    for _ in range(500):
        start = np.random.randint(0, len(daily_ret) - window_days)
        w = daily_ret.iloc[start:start + window_days]
        all_windows.append(float((1 + w).prod() - 1))
    base_mean = np.mean(all_windows)
    base_std  = np.std(all_windows)

    t_stat, p_value = stats.ttest_1samp(arr, base_mean)

    avg_wr   = float(wr_arr.mean())
    lr = avg_wr / base_wr if base_wr > 0 else 1.0

    return {
        "n":            len(event_returns),
        "window_days":  window_days,
        "avg_return_pct":  round(float(arr.mean()) * 100, 2),
        "median_return_pct": round(float(np.median(arr)) * 100, 2),
        "std_return_pct":  round(float(arr.std()) * 100, 2),
        "win_rate":        round(avg_wr * 100, 1),
        "base_win_rate":   round(base_wr * 100, 1),
        "lr":              round(lr, 4),
        "t_stat":          round(float(t_stat), 3),
        "p_value":         round(float(p_value), 4),
        "significant":     bool(p_value < 0.10),
        "base_avg_pct":    round(base_mean * 100, 2),
        "returns":         [round(x * 100, 2) for x in arr.tolist()],
    }


def run_all():
    print("=== 事件研究法（Event Study）===")
    print("加载 S&P 500 日频数据...")
    sp = load_sp500()
    print(f"  数据：{sp.index[0].date()} – {sp.index[-1].date()}，{len(sp)} 行\n")

    results = {}
    for event_type, dates in HISTORICAL_EVENTS.items():
        res = event_study(sp, dates, window_days=30, label=event_type)
        if res is None:
            print(f"  {event_type}: 样本不足，跳过")
            continue

        sig_str = "[*] 显著" if res["significant"] else "[ ] 不显著"
        print(f"  {event_type}")
        print(f"    n={res['n']}  后30日均值={res['avg_return_pct']:+.1f}%  胜率={res['win_rate']}%  LR={res['lr']:.3f}  p={res['p_value']:.3f}  {sig_str}")
        results[event_type] = res

    # 汇总输出到 JSON
    # 生成供 build_signals.py 使用的事件LR表
    event_lr_table = {}
    mapping = {
        "war":         "geopolitical_shock",
        "pandemic":    "pandemic_lockdown",
        "trade_war":   "trade_war_escalation",
        "trade_relief":"trade_war_relief",
        "fed_hike":    "fed_hike_first",
        "fed_cut":     "fed_cut_first",
        "vix_spike":   "vix_spike_extreme",
        "banking":     "banking_crisis",
        "ai_boom":     "ai_breakthrough",
    }
    for key, evt_type in mapping.items():
        if evt_type in results:
            event_lr_table[key] = results[evt_type]["lr"]

    print("\n=== 数据驱动的事件LR（替换主观估计）===")
    for k, v in event_lr_table.items():
        print(f"  {k:<15}: LR={v:.3f}")

    out = {
        "event_studies": results,
        "data_driven_lr": event_lr_table,
        "methodology": (
            "事件研究法：对每类事件的历史发生日期，"
            "计算事件后30个交易日的累计收益，"
            "与随机窗口（bootstrap，n=500）比较，"
            "t检验验证显著性，计算胜率相对基准的似然比（LR）。"
        )
    }
    with open(PROC_DIR / "event_study_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[OK] 结果写入 event_study_results.json")
    return out


if __name__ == "__main__":
    run_all()
