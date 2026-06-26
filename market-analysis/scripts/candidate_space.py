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
#   元月效应（一月历史偏强，尤小盘·January effect）。方向先验固定：以"先验更强组"为 label==1，配单边置换。
_CAL_DUAL3 = ("september", "january")                      # × 2 指数 = 4
_CAL_ANNUAL = ("decade_digit", "presidential_cycle", "term_year3")  # 年频，标普 only = 3（+任期第3年先验·Hirsch 大选前一年最强）

# ── 超跌反弹族（预声明）：阈值 × 持有 × 指数 ──
_REB_PCTL = (1, 5, 10)        # 触发 = 跌破第 N 百分位
_REB_HOLD = (1, 5)            # 持有日

# ── 因子族：BINARY_FEATURES（单一来源，晚 import）。每因子 1 个候选，
#    全段 p 与现代段 recent_p 是同一候选的两个字段(由 _segment_lens 给)，不拆成两个候选 ──


def _cid(family, params):
    """稳定 candidate_id：family + 排序后 params 的短哈希（可复现、可作账本主键）。"""
    raw = family + "|" + "|".join(f"{k}={params[k]}" for k in sorted(params))
    return family[:3] + "_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _cand(family, key, **params):
    return {"family": family, "key": key, "params": params, "candidate_id": _cid(family, params)}


def calendar_candidates():
    out = [_cand("calendar", f"{eff}_{idx}", effect=eff, index=idx)
           for eff in _CAL_DUAL + _CAL_DUAL2 + _CAL_DUAL3 for idx in INDICES]
    out += [_cand("calendar", f"{eff}_sp500", effect=eff, index="sp500") for eff in _CAL_ANNUAL]
    return out


def rebound_candidates():
    return [_cand("rebound", f"p{p}_h{h}_{idx}", pctl=p, hold=h, index=idx)
            for p in _REB_PCTL for h in _REB_HOLD for idx in INDICES]


def factor_candidates():
    from walk_forward import BINARY_FEATURES   # 单一来源，避免与生产因子集漂移
    return [_cand("factor", col, factor=col) for col, _name in BINARY_FEATURES]


def enumerate_candidates():
    """全部预注册候选（无序拼接）。Phase 1 全部进 FDR 分母，禁预筛。"""
    return calendar_candidates() + rebound_candidates() + factor_candidates()


# 预声明总数（写死；test 对账，漂移即失败 → 强制有意识更新分母）
N_CALENDAR = (len(_CAL_DUAL) + len(_CAL_DUAL2) + len(_CAL_DUAL3)) * len(INDICES) + len(_CAL_ANNUAL)  # 19
N_REBOUND = len(_REB_PCTL) * len(_REB_HOLD) * len(INDICES)           # 12
N_FACTOR = 15                                                        # = len(BINARY_FEATURES)，test 核对(每因子1候选)
N_DECLARED = N_CALENDAR + N_REBOUND + N_FACTOR                       # 42


if __name__ == "__main__":
    cs = enumerate_candidates()
    print(f"候选空间 N_DECLARED={N_DECLARED}：日历{N_CALENDAR} + 反弹{N_REBOUND} + 因子{N_FACTOR}")
    print(f"实枚举 {len(cs)}；唯一 candidate_id {len({c['candidate_id'] for c in cs})}")
    for fam in ("calendar", "rebound", "factor"):
        print(f"  {fam}: {sum(c['family'] == fam for c in cs)}")
