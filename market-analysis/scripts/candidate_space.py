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


def enumerate_candidates():
    """全部预注册候选（无序拼接）。Phase 1 全部进 FDR 分母，禁预筛。"""
    return (calendar_candidates() + rebound_candidates() + regime_candidates() + factor_candidates()
            + positioning_candidates() + optsent_candidates())


# 预声明总数（写死；test 对账，漂移即失败 → 强制有意识更新分母）
N_CALENDAR = ((len(_CAL_DUAL) + len(_CAL_DUAL2) + len(_CAL_DUAL3) + len(_CAL_FOMC) + len(_CAL_TWOSIDE) + len(_CAL_MONTHSWEEP))
              * len(INDICES) + len(_CAL_ANNUAL))                     # (4+2+3+1+2+12)*2 + 3 = 48+3 = 51
N_REBOUND = len(_REB_PCTL) * len(_REB_HOLD) * len(INDICES)           # 3*2*2 = 12
N_REGIME = len(_REGIME) * len(INDICES)                               # 1*2 = 2（金叉 × 2 指数）
N_FACTOR = 15                                                        # = len(BINARY_FEATURES)，test 核对(每因子1候选)
# 2026-07-04 扩声明（append-only·#7·Opus 审规格定稿）：仓位族(COT) + 期权情绪族(P/C) 两新族进 FDR 池。
N_POSITIONING = len(_POS_MARKET) * len(_POS_SERIES) * len(_POS_EXTREME) * len(_POS_HOLD)   # 2*2*2*2 = 16
N_OPTSENT = len(_OPTSENT_SERIES) * len(_OPTSENT_EXTREME) * len(_OPTSENT_HOLD)              # 2*2*2 = 8
N_DECLARED = N_CALENDAR + N_REBOUND + N_REGIME + N_FACTOR + N_POSITIONING + N_OPTSENT      # 51+12+2+15+16+8 = 104


if __name__ == "__main__":
    cs = enumerate_candidates()
    print(f"N_DECLARED={N_DECLARED} 候选空间：日历{N_CALENDAR} + 反弹{N_REBOUND} + 体制{N_REGIME} + "
          f"因子{N_FACTOR} + 仓位{N_POSITIONING} + 期权情绪{N_OPTSENT}")
    print(f"实枚举 {len(cs)}；唯一 candidate_id {len({c['candidate_id'] for c in cs})}")
    for fam in ("calendar", "rebound", "regime", "factor", "positioning", "options_sentiment"):
        print(f"  {fam}: {sum(c['family'] == fam for c in cs)}")
