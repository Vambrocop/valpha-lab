"""candidate_space.py — v1.5 自生长 Phase 0：预注册、有限、可枚举的候选空间（纯枚举，不算统计）。

铁律（防 p-hacking 的命门）：候选空间必须**预先声明、可枚举、有限**。禁止无界钓鱼
（"试遍所有阈值直到显著"= forking paths）。阈值/持有期只允许**预声明的离散集**。

每个候选 = {family, key, params, candidate_id}。candidate_id 由 family+params 决定（稳定哈希）
→ 增删候选互不影响、逐项可复现、可作 append-only 账本主键。

N_DECLARED 写死。Phase 1 的 quality_gate 将断言 len(enumerate_candidates())==N_DECLARED，
并把**全部** N 个候选喂进 FDR 分母（**禁止显著性预筛**）。扩 N 必须改这里 + append-only 记录
（日期/原因），代码评审锁定（改空间=改 spec 走双审）。

Phase 0 只做枚举，**不接任何统计原语**（placebo/FDR/walk-forward 在 Phase 1）。
未来族（计划中、未启用）：smart-money / 内部人(SEC Form 4) 诚实检验——届时作新 family
加入并 bump N_DECLARED（单独红线-例外页，2026-06-20 用户授权；不做跟单，只做"是否有 OOS edge"检验）。
"""
import hashlib

INDICES = ("nasdaq", "sp500")

# ── 日历族（预声明）──
_CAL_DUAL = ("dow", "month", "pre_holiday", "santa")        # × 2 指数 = 8
# 2026-06-22 扩声明（append-only）：民俗/学术先验日历效应——非事后挑(HARKing)，是早于本数据已存在的
#   既有假说，正式接进 FDR 引擎出裁决（方向先验固定：以"先验更强组"为 label==1，配单边置换）。
#   sell_in_may=万圣节/夏歇先验(冬强夏弱)；world_cup_year=世界杯分心先验(Edmans 等·限夏季 非杯年 vs 杯年)
_CAL_DUAL2 = ("sell_in_may", "world_cup_year")              # × 2 指数 = 4
# 2026-06-26 扩声明（append-only·prior 先于数据，非事后挑）：九月效应（九月历史最弱月·经典 Sept effect）、
#   元月效应（一月历史偏强，尤小盘·January effect）、月末月初效应（收益集中月界·Ariel 1987 turn-of-month）。
#   方向先验固定：以"先验更强组"为 label==1，配单边置换。
_CAL_DUAL3 = ("september", "january", "turn_of_month")     # × 2 指数 = 6
# 2026-06-29 扩声明（append-only·prior 先于数据，非事后挑）：预 FOMC 漂移（Lucca-Moench 2015·JF：
#   美股在计划 FOMC 公告前的交易日历史偏强）。方向先验固定：label==1=会前日(先验更高组)，单边 make_dir_diff_stat
#   测**平均收益**差（与 fomc_study.py 那张"上涨率"卡同一标签、不同统计量，刻意如此）。会议日表见 fomc_dates.py。
_CAL_FOMC = ("pre_fomc",)                                   # × 2 指数 = 2
# 2026-06-30 扩声明（append-only·prior 先于数据）：期权到期周(每月第3个周五那周·Stoll-Whaley 等·活跃度异常)、
#   季末(3/6/9/12月最后3个交易日·窗口粉饰/再平衡)。二者**无方向共识**→两侧 make_ssb_stat(2)、不进 _DIR_EFFECTS。
#   quarter_end 与 turn_of_month 有意重叠(均预声明·均进 FDR 分母,相关但非 p-hacking)。
_CAL_TWOSIDE = ("opex_week", "quarter_end")          # × 2 指数 = 4
_CAL_ANNUAL = ("decade_digit", "presidential_cycle", "term_year3")  # 年频，标普 only = 3（+任期第3年先验·Hirsch 大选前一年最强）
# ── 机器枚举：逐月扫（2026-06-26）。无方向先验 → 两侧检验(make_ssb_stat(2))"该月 vs 其余是否异常"，
#    全 12 月 × 2 指数 = 24 全进 FDR、谁异常谁自己冒出来（这才是"机器主动发现"，非我手挑某月）。
_CAL_MONTHSWEEP = tuple(f"monthof_{m}" for m in range(1, 13))      # × 2 指数 = 24

# ── 超跌反弹族（预声明）：阈值 × 持有 × 指数 ──
_REB_PCTL = (1, 5, 10)        # 触发 = 跌破第 N 百分位
_REB_HOLD = (1, 5)            # 持有日

# ── 价格体制族（2026-06-26 扩声明·prior 先于数据）：金叉(50日均线>200日线·经典趋势信号·TradingAgents 等都用)
#    → 信号成立时未来 20 日上涨率 vs 基率。标普不在 factor 管线(只 NASDAQ/BTC/DXY)，故单列价格体制族测两指数。
_REGIME = ("golden_cross",)   # × 2 指数 = 2

# ── 因子族：BINARY_FEATURES（单一来源，晚 import）。每因子 1 个候选，
#    全段 p 与现代段 recent_p 是同一候选的两个字段(由 _segment_lens 给)，不拆成两个候选 ──

# ── 仓位族 positioning（2026-07-04 扩声明·#7·先验先于数据·Opus 审规格定稿）：CFTC COT 期货持仓。
#   网格：{market: sp500, nasdaq100} × {series: legacy 非商业净头寸/OI, TFF 杠杆基金净头寸/OI}
#         × {extreme: 高(>90分位)/低(<10分位)，纯回看滚动156份周频报告} × {hold: 20, 60 交易日} = 16。
#   先验(Wang 2003·Sanders et al. COT 文献)：大投机者/杠杆基金净头寸极端偏多→未来偏弱；极端偏空→未来偏强
#   (反向)。方向只作解释性先验，p 按 diff 族既有标准=双侧块自助(block 见 autodiscovery.py，因状态多周持续，
#   实测放大 block=hold+episode p90，非单纯 hold)。
#   ⚠ 诚实关联：本族与 rebound 族同属"极端分位→反转"母假设(极端回归)，FDR 跨族栏会自然处理相关性，
#   但在此明记(JP6·Opus 审规格·2026-07-04)。
_POS_MARKET = ("sp500", "nasdaq100")
_POS_SERIES = ("legacy_noncomm_pct_oi", "tff_lev_net_pct_oi")
_POS_EXTREME = ("hi", "lo")
_POS_HOLD = (20, 60)

# ── 期权情绪族 options_sentiment（2026-07-04 扩声明·#7·同上定稿）：CBOE Put/Call 比。
#   网格：{series: total_pc 全市场, equity_pc 个股} × {extreme: z>+2 恐慌 / z<-2 自满，纯回看滚动252日z}
#         × {hold: 10, 20 交易日} = 8。目标固定 SP500_long(P/C 是全市场情绪·标普为市场代理·声明)。
#   先验(期权情绪经典文献)：P/C 极高=恐慌对冲极值→反向偏多；极低=自满→偏弱。方向只作解释性先验，p 双侧。
#   口径纪律：绝不用绝对阈值(2012-06 CBOE 口径变更+市占漂移)——只用滚动 z。
#   ⚠ 诚实关联：与 positioning 族同属"极端→反转"母假设(见上)。
_OPTSENT_SERIES = ("total_pc", "equity_pc")
_OPTSENT_EXTREME = ("hi", "lo")
_OPTSENT_HOLD = (10, 20)

# ── 连跌族 streak（2026-07-10 用户原案·Fable 军师定规格 SPEC_STREAK_FAMILY.md·Opus 审规格通过）：
#   streak_down=连跌事件日(runlen==N 严格)，streak_break=连跌后首个上涨日(确认式反转)。
#   先验(§2·文献先于数据)：streak_down=短期反转(Lehmann 1990/Jegadeesh 1990；De Bondt-Thaler 过度反应
#   的日频形式)，连跌后偏反弹(up>base)，预期现代段衰减(被套利，同日历族命运)。streak_break=从业者启发式
#   "等首根阳线"，文献支撑弱于 streak_down，先验方向弱偏正、置信低——明写此子族更可能被打回，打回也是
#   有价值的公开答案。**p 值双侧，方向先验仅作解释性，不许事后按结果挑边**。
#   ⚠ 诚实关联：与 rebound 族、trailing_extreme 族同属"极端回归"母假设(尾部收益 vs 连跌是同一过度反应
#   现象的不同跨度切面)——跨族 FDR 栏自然处理相关性，此处明记(SPEC_STREAK_FAMILY.md §0/§2)。
#   口径命门(§1 S2)："跌"写死 down = ret < 0(严格小于零；平盘/零收益断连跌，不算跌也不续)——
#   建造期已用实际数据核对触发计数与规格预注册数字(纳指758/363/190·标普1423/646/307，
#   break纳指756/189·标普1402/304)逐一相符，无口径漂移。
_STREAK_DOWN_N = (3, 4, 5)
_STREAK_BREAK_N = (3, 5)
_STREAK_HOLD = (1, 5, 20)

# ── 长跨度对称反转/延续族 trailing_extreme（2026-07-10 用户扩范围·同一规格 §5）：
#   trailing-N 累计收益处于历史极端分位(PIT expanding 分位，见 autodiscovery._TRAILING_WARMUP)，
#   low(跌了好久)/high(涨了好久) 对称双向。**方向绝不预设为"涨久必跌"**——按跨度分段先验(§5.2)：
#   中跨度(63/126/252d)先验=动量/延续(Jegadeesh-Titman 1993)，长跨度(504d)先验=弱反转
#   (De Bondt-Thaler 1985，置信低、大概率 inconclusive，预注册接受的诚实结果)。p 双侧，先验仅解释性。
#   网格纪律(§5.3)：hold 与 lookback 一一匹配(去 hold 维·最大且最可辩护的裁剪)；504d 只枚举 sp500
#   (纳指史短、2年成形+持有的不重叠周期天然稀少·S4 设计取舍)；756d 3年成形期永不枚举(同理·文献常识)。
#   stage2 先枚举占位(_trailing_extreme() 恒返回 None→p=1.0，H-1 已就绪的显式路由，不是静默 else)，
#   2026-07-11 stage4 补真统计(PIT expanding 分位 + block=hold+TRAILING_BLOCK_EXTRA 状态族放大，
#   见 autodiscovery.py 声明注释)。数据仍不足的候选(如暖机后有效样本太少)照旧返回 None→p=1.0。
#   ⚠ 诚实关联：与 streak 族、rebound 族同属"极端回归"母假设，此处明记(SPEC_STREAK_FAMILY.md §0/§5.2)。
_TRAILING_GRID = (                       # (lookback N, 匹配 hold, 覆盖指数)
    (63, 21, INDICES),
    (126, 63, INDICES),
    (252, 126, INDICES),
    (504, 126, ("sp500",)),              # S4:504d 不设 nasdaq(成形+持有周期在纳指史里天然稀少)
)
_TRAILING_SIDES = ("low", "high")


def _cid(family, params):
    """稳定 candidate_id：family + 排序后 params 的短哈希（可复现、可作账本主键）。"""
    raw = family + "|" + "|".join(f"{k}={params[k]}" for k in sorted(params))
    return family[:3] + "_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _cand(family, key, **params):
    return {"family": family, "key": key, "params": params, "candidate_id": _cid(family, params)}


def calendar_candidates():
    out = [_cand("calendar", f"{eff}_{idx}", effect=eff, index=idx)
           for eff in _CAL_DUAL + _CAL_DUAL2 + _CAL_DUAL3 + _CAL_FOMC + _CAL_TWOSIDE + _CAL_MONTHSWEEP for idx in INDICES]
    out += [_cand("calendar", f"{eff}_sp500", effect=eff, index="sp500") for eff in _CAL_ANNUAL]
    return out


def rebound_candidates():
    return [_cand("rebound", f"p{p}_h{h}_{idx}", pctl=p, hold=h, index=idx)
            for p in _REB_PCTL for h in _REB_HOLD for idx in INDICES]


def regime_candidates():
    return [_cand("regime", f"{sig}_{idx}", signal=sig, index=idx)
            for sig in _REGIME for idx in INDICES]


def factor_candidates():
    from walk_forward import BINARY_FEATURES   # 单一来源，避免与生产因子集漂移
    return [_cand("factor", col, factor=col) for col, _name in BINARY_FEATURES]


def positioning_candidates():
    return [_cand("positioning", f"{series}_{extreme}_h{hold}_{market}",
                  market=market, series=series, extreme=extreme, hold=hold)
            for market in _POS_MARKET for series in _POS_SERIES
            for extreme in _POS_EXTREME for hold in _POS_HOLD]


def optsent_candidates():
    return [_cand("options_sentiment", f"{series}_{extreme}_h{hold}",
                  series=series, extreme=extreme, hold=hold)
            for series in _OPTSENT_SERIES for extreme in _OPTSENT_EXTREME for hold in _OPTSENT_HOLD]


def streak_candidates():
    down = [_cand("streak_down", f"down{n}_h{h}_{idx}", n=n, hold=h, index=idx)
            for n in _STREAK_DOWN_N for h in _STREAK_HOLD for idx in INDICES]
    brk = [_cand("streak_break", f"break{n}_h{h}_{idx}", n=n, hold=h, index=idx)
           for n in _STREAK_BREAK_N for h in _STREAK_HOLD for idx in INDICES]
    return down + brk


def trailing_extreme_candidates():
    return [_cand("trailing_extreme", f"n{n}_h{hold}_{side}_{idx}", n=n, hold=hold, side=side, index=idx)
            for n, hold, idxs in _TRAILING_GRID for side in _TRAILING_SIDES for idx in idxs]


def enumerate_candidates():
    """全部预注册候选（无序拼接）。Phase 1 全部进 FDR 分母，禁预筛。
    2026-07-10 扩声明(SPEC_STREAK_FAMILY.md·B2)：streak(30)与 trailing_extreme(14)
    **同批**加入枚举——trailing 的真统计留 stage4 才建，但候选必须 stage2 就一次性声明进 148 分母
    (不许分阶段扩分母，否则 BY 阈值随分母变化=违反 §0 预注册锁定)。"""
    return (calendar_candidates() + rebound_candidates() + regime_candidates() + factor_candidates()
            + positioning_candidates() + optsent_candidates()
            + streak_candidates() + trailing_extreme_candidates())


# 预声明总数（写死；test 对账，漂移即失败 → 强制有意识更新分母）
N_CALENDAR = ((len(_CAL_DUAL) + len(_CAL_DUAL2) + len(_CAL_DUAL3) + len(_CAL_FOMC) + len(_CAL_TWOSIDE) + len(_CAL_MONTHSWEEP))
              * len(INDICES) + len(_CAL_ANNUAL))                     # (4+2+3+1+2+12)*2 + 3 = 48+3 = 51
N_REBOUND = len(_REB_PCTL) * len(_REB_HOLD) * len(INDICES)           # 3*2*2 = 12
N_REGIME = len(_REGIME) * len(INDICES)                               # 1*2 = 2（金叉 × 2 指数）
N_FACTOR = 15                                                        # = len(BINARY_FEATURES)，test 核对(每因子1候选)
# 2026-07-04 扩声明（append-only·#7·Opus 审规格定稿）：仓位族(COT) + 期权情绪族(P/C) 两新族进 FDR 池。
N_POSITIONING = len(_POS_MARKET) * len(_POS_SERIES) * len(_POS_EXTREME) * len(_POS_HOLD)   # 2*2*2*2 = 16
N_OPTSENT = len(_OPTSENT_SERIES) * len(_OPTSENT_EXTREME) * len(_OPTSENT_HOLD)              # 2*2*2 = 8
_N_BASELINE = (N_CALENDAR + N_REBOUND + N_REGIME + N_FACTOR + N_POSITIONING + N_OPTSENT)   # 原基线 104
# 2026-07-10 扩声明(SPEC_STREAK_FAMILY.md·B2·§3·§6)：streak(18+12=30) + trailing_extreme(14)，
# 一步到 148(不经 134 中转)——子算术常量 + 对账护栏(N3)，写成显式相加，不填魔数。
N_STREAK = (len(_STREAK_DOWN_N) * len(_STREAK_HOLD) * len(INDICES)                         # 3*3*2 = 18
            + len(_STREAK_BREAK_N) * len(_STREAK_HOLD) * len(INDICES))                     # 2*3*2 = 12 → 30
N_TRAILING = sum(len(idxs) for _n, _h, idxs in _TRAILING_GRID) * len(_TRAILING_SIDES)       # (2+2+2+1)*2 = 14
N_DECLARED = _N_BASELINE + N_STREAK + N_TRAILING                                            # 104+30+14 = 148


if __name__ == "__main__":
    cs = enumerate_candidates()
    print(f"N_DECLARED={N_DECLARED} 候选空间：日历{N_CALENDAR} + 反弹{N_REBOUND} + 体制{N_REGIME} + "
          f"因子{N_FACTOR} + 仓位{N_POSITIONING} + 期权情绪{N_OPTSENT} + "
          f"连跌{N_STREAK} + 长跨度反转{N_TRAILING}")
    print(f"实枚举 {len(cs)}；唯一 candidate_id {len({c['candidate_id'] for c in cs})}")
    for fam in ("calendar", "rebound", "regime", "factor", "positioning", "options_sentiment",
                "streak_down", "streak_break", "trailing_extreme"):
        print(f"  {fam}: {sum(c['family'] == fam for c in cs)}")
