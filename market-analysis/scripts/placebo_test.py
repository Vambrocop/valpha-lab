"""
placebo_test.py — P4-1 置换/安慰剂检验（2026-06-13 立项；2026-06-13 经独立审查加固）

对现有"日历规律"做标签置换检验(permutation / placebo test)：随机打乱日期标签
N=1000 次生成零分布，看真实效应统计量在零分布里的分位（单边 p）。

诚实性三态判定（独立审查 BLOCKER 修复——绝不把"检验力不足"说成"已证伪"）：
  ✓ 真实    : p<0.05 且样本充足 —— 效应可与随机区分
  ✗ 未显现  : p≥0.05 且样本充足（每组 ≥ MIN_GROUP_N）—— 充分样本下仍测不到效应
  — 无定论  : 每组样本过小（< MIN_GROUP_N）—— 检验力不足，无权下任何结论
小样本的年尾数(每组~10年)/任期年(~24年)落入"无定论"，而非"打回"：absence of
evidence ≠ evidence of absence，这正是本站要避免的那种反向幻觉。

统计量（独立审查 SHOULD-FIX）：
  类别效应(星期/月份/年尾数/任期年)用组间平方和 SS_between = Σ nᵍ(meanᵍ-grand)²
  （= 置换 F 检验的等价量，按组样本量加权，比极差更稳/更有功效，且自动把
  "N 组里总有一个看着最好"的多重比较运气计入零分布）。
  方向断言(节前看涨/圣诞行情)用"该组均值-其余均值"的单边检验（方向是预注册的）。

数据口径（独立审查修正）：
  - 假日：用 signal_model 的**已验证**日历(知道 Juneteenth 自2022)，且限**1998+**
    现代 NYSE 口径（MLK 1998 起才休市，避免把早年的普通日误标成节前）。
  - 星期：限 **1952-09+** 五日交易制（1952 前周六开市，周五并非周末前最后一天）。
  - 年度：丢弃未走完的当年（避免不完整桶污染本就小的年度样本）。

输入：data/raw/SP500_long.csv（long_history.py 产出；缺失时回退 yfinance）
输出：placebo_tests.json（同时写 processed / web / docs，前端同源消费）
"""
import json
import datetime
import numpy as np
import pandas as pd
from pathlib import Path

SCRIPTS  = Path(__file__).parent
RAW_DIR  = SCRIPTS.parent / "data" / "raw"
PROC_DIR = SCRIPTS.parent / "data" / "processed"
WEB_DIR  = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"
PROC_DIR.mkdir(parents=True, exist_ok=True)

N_PERM        = 1000
SEED          = 20260613       # 固定种子 → 可复现（已发布统计结论的硬要求）
ALPHA         = 0.05
MIN_GROUP_N   = 30             # 每组 < 此值视为检验力不足 → "无定论"（启发式下限）
DOW_START     = "1952-09-01"   # 五日交易制起点
HOLIDAY_START = "1998-01-01"   # MLK 成为 NYSE 假日之后（现代口径）


# ══════════════════════════════════════════════════════════════════
# 数据：S&P500 日收益（与 long_history 各日历面板同源）
# ══════════════════════════════════════════════════════════════════
def load_sp500_daily():
    f = RAW_DIR / "SP500_long.csv"
    s = None
    if f.exists():
        raw = pd.read_csv(f, index_col=0, parse_dates=True)
        s = pd.to_numeric(raw.iloc[:, 0], errors="coerce").dropna()
    if s is None or len(s) < 1000:
        try:
            import yfinance as yf
            df = yf.download("^GSPC", start="1928-01-01",
                             end=(pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                             auto_adjust=True, progress=False)
            col = df["Close"]
            s = (col.iloc[:, 0] if isinstance(col, pd.DataFrame) else col).dropna()
            s.index = pd.to_datetime(s.index)
        except Exception as e:
            print(f"  ⚠ 无法获取 S&P500 数据：{e}")
            return None
    return s.sort_index().pct_change().dropna()


# ══════════════════════════════════════════════════════════════════
# 通用置换检验（每个效应独立 RNG 流 → 增删/改序互不影响，逐项可复现）
# ══════════════════════════════════════════════════════════════════
def perm_test(values, labels, stat_fn, rng, n_perm=N_PERM):
    values = np.asarray(values, float)
    labels = np.asarray(labels)
    real = float(stat_fn(values, labels))
    null = np.empty(n_perm)
    for i in range(n_perm):
        null[i] = stat_fn(values, rng.permutation(labels))
    # 单边：真实统计量越大越显著；+1 平滑避免 p=0；-eps 容忍浮点等值
    p = float((np.sum(null >= real - 1e-15) + 1) / (n_perm + 1))
    return {"real": round(real, 10), "p_value": round(p, 6),
            "null_p95": round(float(np.percentile(null, 100 * (1 - ALPHA))), 10)}


def _group_means(values, labels, k):
    cnt = np.bincount(labels, minlength=k).astype(float)
    tot = np.bincount(labels, weights=values, minlength=k)
    with np.errstate(invalid="ignore", divide="ignore"):
        gm = tot / cnt
    return gm, cnt


def make_ssb_stat(k):
    """组间平方和 SS_between = Σ nᵍ·(meanᵍ - grand)²（置换 F 的等价单调量）。"""
    def f(values, labels):
        gm, cnt = _group_means(values, labels, k)
        grand = values.mean()
        m = cnt > 0
        return float(np.sum(cnt[m] * (gm[m] - grand) ** 2))
    return f


def make_dir_diff_stat():
    """二元方向断言：mean(label==1) - mean(label==0)，单边。调用前保证两组非空。"""
    def f(values, labels):
        return values[labels == 1].mean() - values[labels == 0].mean()
    return f


def _verdict(p, min_group_n):
    """诚实三态。注意顺序：显著优先——置换检验在小样本下 type-I 仍受控，
    若真测到显著(p<α)那就是真实；只有"不显著"时才需区分'样本足够仍无效应'
    与'样本太小无权下结论'。反过来(先判样本)会把'小样本但显著'误判成无定论。"""
    if p < ALPHA:
        return "real", f"✓ 真实：通过 placebo (p={p:.3f})"
    if min_group_n < MIN_GROUP_N:
        return "inconclusive", f"— 无定论：每组样本仅 {min_group_n}，检验力不足 (p={p:.3f})"
    return "rejected", f"✗ 未显现：充分样本下仍不显著 (p={p:.3f})"


# ══════════════════════════════════════════════════════════════════
# 假日掩码：紧邻假日休市的最后一个交易日（用已验证的现代 NYSE 日历）
# ══════════════════════════════════════════════════════════════════
def holiday_pre_mask(ret_index):
    from signal_model import us_holidays   # 已验证日历（test_holidays.py 覆盖，知 Juneteenth 自 2022）
    yrs = range(int(ret_index.year.min()), int(ret_index.year.max()) + 1)
    hol = set()
    for y in yrs:
        try:
            hol.update(pd.Timestamp(d) for d in us_holidays(y))
        except Exception:
            pass
    idx = pd.DatetimeIndex(ret_index)
    pre = np.zeros(len(idx), bool)
    # 真实 ^GSPC 收盘里假日本身不是交易日，故 idx<h 干净排除假日，prev[-1] 即节前最后交易日。
    # 注：若最近的前一交易日距假日 >4 天（罕见的长休市，如 9/11），该假日不贡献节前日——已知的静默跳过。
    for h in hol:
        prev = idx[idx < h]
        if len(prev) and (h - prev[-1]).days <= 4:
            pre[idx.get_loc(prev[-1])] = True
    return pre


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
def run_all():
    ret = load_sp500_daily()
    if ret is None or len(ret) < 1000:
        print("⚠ S&P500 日收益不足，placebo 跳过")
        return None

    monthly = (1 + ret).resample("ME").prod(min_count=1).dropna() - 1
    annual  = (1 + ret).resample("YE").prod(min_count=1).dropna() - 1
    annual  = annual[annual.index.year < pd.Timestamp.today().year]   # 丢未走完的当年

    print(f"=== Placebo 置换检验 (N={N_PERM}, seed={SEED}, MIN_GROUP_N={MIN_GROUP_N}) ===")
    print(f"  S&P500 日收益 {ret.index[0].date()}–{ret.index[-1].date()}  n={len(ret)}")

    tests = []

    def add(idx_key, **kw):
        rng = np.random.default_rng([SEED, idx_key])      # 每项独立流
        r = perm_test(kw.pop("values"), kw.pop("labels"), kw.pop("stat_fn"), rng)
        status, verdict = _verdict(r["p_value"], kw["min_group_n"])
        tests.append({**kw, **r, "status": status,
                      "passed": bool(status == "real"), "verdict": verdict})

    # ── 1. 星期效应（日频，限五日交易制，SS_between）──────────────
    dret = ret[ret.index >= DOW_START]
    wlab = dret.index.weekday.values
    wmask = wlab <= 4
    wvals, wlab = dret.values[wmask], wlab[wmask]
    gm, cnt = _group_means(wvals, wlab, 5)
    names = ["周一", "周二", "周三", "周四", "周五"]
    add(1, values=wvals, labels=wlab, stat_fn=make_ssb_stat(5),
        key="dow", panel="星期效应", scope=f"日频 S&P500 {DOW_START[:4]}+",
        claim="某些交易日平均收益更高", stat="组间平方和(日均收益)",
        min_group_n=int(cnt.min()),
        detail=f"{names[int(np.argmax(gm))]}最高 / {names[int(np.argmin(gm))]}最低")

    # ── 2. 月份效应（月频，全历史，SS_between）─────────────────────
    mlab = (monthly.index.month - 1).values
    gm, cnt = _group_means(monthly.values, mlab, 12)
    add(2, values=monthly.values, labels=mlab, stat_fn=make_ssb_stat(12),
        key="month", panel="月份效应(月度胜率)", scope="月频 S&P500 1928+",
        claim="某些月份系统性更强/更弱", stat="组间平方和(月均收益)",
        min_group_n=int(cnt.min()),
        detail=f"{int(np.argmax(gm))+1}月最高 / {int(np.argmin(gm))+1}月最低")

    # ── 3. 年份尾数（年频，10 组；小样本 → 预期无定论）────────────
    digit = (annual.index.year % 10).values
    _, cnt = _group_means(annual.values, digit, 10)
    add(3, values=annual.values, labels=digit, stat_fn=make_ssb_stat(10),
        key="decade_digit", panel="年份尾数", scope="年频 S&P500",
        claim="尾数为 X 的年份历史最强", stat="组间平方和(年均收益)",
        min_group_n=int(cnt.min()), detail=f"每组仅约 {len(annual)//10} 年")

    # ── 4. 总统任期年（年频，4 组；小样本）────────────────────────
    cyc = (annual.index.year % 4).values
    _, cnt = _group_means(annual.values, cyc, 4)
    add(4, values=annual.values, labels=cyc, stat_fn=make_ssb_stat(4),
        key="presidential_cycle", panel="总统任期年", scope="年频 S&P500",
        claim="任期第 3 年(选前)最强", stat="组间平方和(年均收益)",
        min_group_n=int(cnt.min()), detail=f"每组仅约 {len(annual)//4} 年")

    # ── 5. 假日效应：节前看涨（日频，现代口径，单边 diff）─────────
    hret = ret[ret.index >= HOLIDAY_START]
    pre = holiday_pre_mask(hret.index)
    add(5, values=hret.values, labels=pre.astype(int), stat_fn=make_dir_diff_stat(),
        key="pre_holiday", panel="假日效应(节前)", scope=f"日频 S&P500 {HOLIDAY_START[:4]}+",
        claim="节前最后一个交易日平均看涨", stat="节前均值 - 其余均值(单边)",
        min_group_n=int(pre.sum()), detail=f"节前交易日 n={int(pre.sum())}")

    # ── 6. 圣诞行情 Santa Claus Rally（Dec26–Jan3，纯日期，全历史）──
    santa = (((ret.index.month == 12) & (ret.index.day >= 26)) |
             ((ret.index.month == 1) & (ret.index.day <= 3))).astype(int)
    add(6, values=ret.values, labels=santa, stat_fn=make_dir_diff_stat(),
        key="santa_claus", panel="圣诞行情", scope="日频 S&P500 1928+",
        claim="Dec26–Jan3 区间平均看涨", stat="区间均值 - 其余均值(单边)",
        min_group_n=int(santa.sum()), detail=f"区间交易日 n={int(santa.sum())}")

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "标签置换检验(permutation)；三态：真实/未显现/无定论(检验力不足)",
        "n_perm": N_PERM, "seed": SEED, "alpha": ALPHA, "min_group_n": MIN_GROUP_N,
        "data": {"source": "S&P 500 (^GSPC)",
                 "start": str(ret.index[0].date()), "end": str(ret.index[-1].date()),
                 "n_daily": int(len(ret))},
        "tests": tests,
    }
    payload = json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False)
    for d in (PROC_DIR, WEB_DIR, DOCS_DIR):
        if d.exists():
            (d / "placebo_tests.json").write_text(payload, encoding="utf-8")

    icon = {"real": "✓ 真实", "rejected": "✗ 未显现", "inconclusive": "— 无定论"}
    print(f"\n  {'效应':<16}{'p值':>8}  {'最小组n':>7}  结论")
    for t in tests:
        print(f"  {t['panel']:<16}{t['p_value']:>8.3f}  {t['min_group_n']:>7}  {icon[t['status']]}")
    n_real = sum(t["status"] == "real" for t in tests)
    n_inc  = sum(t["status"] == "inconclusive" for t in tests)
    print(f"\n[OK] placebo_tests.json：{n_real} 真实 / {n_inc} 无定论 / "
          f"{len(tests)-n_real-n_inc} 未显现")
    return out


if __name__ == "__main__":
    run_all()
