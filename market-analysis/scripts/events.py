"""
events.py
重大事件数据库：黑天鹅 / 政治事件 / 大型IPO / BTC减半 / 美联储决策
"""

EVENTS = [
    # ── 黑天鹅 ──────────────────────────────────────────────────────
    {"date": "2015-08-24", "type": "black_swan",  "label": "中国A股熔断", "impact": -1},
    {"date": "2016-06-24", "type": "black_swan",  "label": "英国脱欧", "impact": -1},
    {"date": "2020-02-20", "type": "black_swan",  "label": "COVID崩盘开始", "impact": -1},
    {"date": "2020-03-23", "type": "black_swan",  "label": "COVID底部", "impact": 1},
    {"date": "2022-05-09", "type": "black_swan",  "label": "Luna/Terra崩溃", "impact": -1},
    {"date": "2022-11-11", "type": "black_swan",  "label": "FTX破产", "impact": -1},
    {"date": "2023-03-10", "type": "black_swan",  "label": "硅谷银行倒闭", "impact": -1},
    {"date": "2024-08-05", "type": "black_swan",  "label": "日元套利平仓崩盘", "impact": -1},
    {"date": "2025-04-04", "type": "black_swan",  "label": "特朗普对等关税冲击", "impact": -1},

    # ── 政治事件 ────────────────────────────────────────────────────
    {"date": "2016-11-08", "type": "political",   "label": "特朗普当选(1)", "impact": 1},
    {"date": "2020-11-03", "type": "political",   "label": "拜登当选", "impact": 0},
    {"date": "2021-01-06", "type": "political",   "label": "国会山事件", "impact": -1},
    {"date": "2024-11-05", "type": "political",   "label": "特朗普当选(2)", "impact": 1},
    {"date": "2025-01-20", "type": "political",   "label": "特朗普就职", "impact": 1},
    {"date": "2022-11-08", "type": "political",   "label": "2022中期选举", "impact": 0},
    {"date": "2026-11-03", "type": "political",   "label": "2026中期选举", "impact": 0},

    # ── 美联储重大决策 ───────────────────────────────────────────────
    {"date": "2022-03-16", "type": "fed",         "label": "开始加息周期", "impact": -1},
    {"date": "2023-07-26", "type": "fed",         "label": "加息至5.25%峰值", "impact": -1},
    {"date": "2024-09-18", "type": "fed",         "label": "首次降息", "impact": 1},
    {"date": "2025-01-29", "type": "fed",         "label": "暂停降息", "impact": -1},

    # ── BTC减半 ─────────────────────────────────────────────────────
    {"date": "2016-07-09", "type": "halving",     "label": "BTC第2次减半", "impact": 1},
    {"date": "2020-05-11", "type": "halving",     "label": "BTC第3次减半", "impact": 1},
    {"date": "2024-04-20", "type": "halving",     "label": "BTC第4次减半", "impact": 1},

    # ── 重大IPO ─────────────────────────────────────────────────────
    {"date": "2019-05-10", "type": "ipo",         "label": "Uber IPO", "impact": 0},
    {"date": "2020-09-16", "type": "ipo",         "label": "Snowflake IPO", "impact": 1},
    {"date": "2021-04-14", "type": "ipo",         "label": "Coinbase直接上市", "impact": 1},
    {"date": "2023-09-19", "type": "ipo",         "label": "ARM IPO", "impact": 1},
    {"date": "2024-03-22", "type": "ipo",         "label": "Reddit IPO", "impact": 0},
    {"date": "2024-05-14", "type": "ipo",         "label": "ASMB等AI概念潮", "impact": 1},

    # ── AI里程碑 ────────────────────────────────────────────────────
    {"date": "2022-11-30", "type": "ai",          "label": "ChatGPT发布", "impact": 1},
    {"date": "2023-01-23", "type": "ai",          "label": "MSFT $10B投资OpenAI", "impact": 1},
    {"date": "2024-06-10", "type": "ai",          "label": "Apple AI发布", "impact": 1},
    {"date": "2026-06-02", "type": "ai",          "label": "黄仁勋Computex演讲", "impact": 1},

    # ── 税务季（影响资金流动） ────────────────────────────────────
    # 美国：1/31 W-2截止 → 3/15 企业报税 → 4/15 个人报税截止（卖股缴税压力）
    # 澳洲：税务年度7/1开始，10/31报税截止（卖股锁定亏损抵税高峰）
    {"date": "2023-04-15", "type": "tax",         "label": "美国报税截止(个人)", "impact": -1},
    {"date": "2024-04-15", "type": "tax",         "label": "美国报税截止(个人)", "impact": -1},
    {"date": "2025-04-15", "type": "tax",         "label": "美国报税截止(个人)", "impact": -1},
    {"date": "2023-10-31", "type": "tax",         "label": "澳洲报税截止", "impact": -1},
    {"date": "2024-10-31", "type": "tax",         "label": "澳洲报税截止", "impact": -1},
    {"date": "2023-12-28", "type": "tax",         "label": "美国年末税损收割截止", "impact": -1},
    {"date": "2024-12-27", "type": "tax",         "label": "美国年末税损收割截止", "impact": -1},

    # ── 战争与地缘政治 ────────────────────────────────────────────
    {"date": "2022-02-24", "type": "geopolitical", "label": "俄乌战争爆发", "impact": -1},
    {"date": "2023-10-07", "type": "geopolitical", "label": "以哈战争爆发", "impact": -1},
    {"date": "2024-04-13", "type": "geopolitical", "label": "伊朗直接袭击以色列", "impact": -1},
    {"date": "2025-03-04", "type": "geopolitical", "label": "特朗普宣布全面关税", "impact": -1},

    # ── 贸易战 ────────────────────────────────────────────────────
    {"date": "2018-03-22", "type": "trade_war",   "label": "特朗普301关税(1.0)", "impact": -1},
    {"date": "2019-05-10", "type": "trade_war",   "label": "中美关税升级", "impact": -1},
    {"date": "2020-01-15", "type": "trade_war",   "label": "中美第一阶段贸易协议", "impact": 1},
    {"date": "2025-04-02", "type": "trade_war",   "label": "对等关税日(全球)", "impact": -1},
    {"date": "2025-05-12", "type": "trade_war",   "label": "中美90天关税暂停", "impact": 1},

    # ── 疫情 ──────────────────────────────────────────────────────
    {"date": "2020-01-21", "type": "pandemic",    "label": "美国首例新冠确认", "impact": -1},
    {"date": "2020-03-11", "type": "pandemic",    "label": "WHO宣布全球大流行", "impact": -1},
    {"date": "2020-11-09", "type": "pandemic",    "label": "辉瑞疫苗有效性公布", "impact": 1},
    {"date": "2021-12-01", "type": "pandemic",    "label": "奥密克戎变异株出现", "impact": -1},
]

EVENT_COLORS = {
    "black_swan":  "#e74c3c",
    "political":   "#3498db",
    "fed":         "#9b59b6",
    "halving":     "#f39c12",
    "ipo":         "#27ae60",
    "ai":          "#1abc9c",
    "tax":         "#95a5a6",
    "geopolitical":"#e67e22",
    "trade_war":   "#d35400",
    "pandemic":    "#c0392b",
}

EVENT_SYMBOLS = {
    "black_swan":  "✦",
    "political":   "★",
    "fed":         "◆",
    "halving":     "⬡",
    "ipo":         "▲",
    "ai":          "●",
    "tax":         "¥",
    "geopolitical":"⚔",
    "trade_war":   "⚡",
    "pandemic":    "☣",
}
