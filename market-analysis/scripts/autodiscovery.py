"""autodiscovery.py — v1.5 自生长 Phase 1b：把候选路由到真统计算 p，喂裁决引擎，产出 autodiscovery.json。

状态(2026-06-22)：种子稳定(hashlib)、_daily 缓存、每候选带多时间窗(完整/2000后/2021后/近1年)
   实际上涨率 vs 基率。**内建校验通过**：SP500 日历 p 值与 placebo_tests.json 一致。
   N_DECLARED=80 候选(日历51 含九月/元月/月末月初/机器逐月扫24/预FOMC漂移2/期权到期周·季末两侧4 + 反弹12 + 价格体制2金叉 + 因子15；
   2026-06-30 期权到期周/季末 append-only 扩声明)：约 12 跨族存活、7 已淡、其余死/检验力不足——诚实。
   门4 OOS(oos_gate.py) 与晋升/降级(knowledge_base.py) 已建+审，待接 run_all 写 kb_ledger。
   2026-07-04 append-only 扩声明(#7·Opus 审规格定稿)：N_DECLARED 80→104，新增仓位族 positioning(COT·16)
   + 期权情绪族 options_sentiment(P/C·8)。两族均为"状态型 sel"(最近一份 usable 报告/滚动z 落极端区)，
   走同一 _diff_windows + block_bootstrap_diff 机器；positioning 因状态多周持续 → block 放大(见
   POSITIONING_BLOCK_EXTRA)，optsent 尖峰短 block=hold 不变。


复用现有原语（不重写统计）：
  · 日历族 → placebo_test 的 perm_test + make_ssb_stat / make_dir_diff_stat（SP500/纳指 日收益）
  · 反弹族 → walk_forward.block_bootstrap_diff（跌破第 N 百分位日后持有 M 日的前向收益 vs 基率）
  · 因子族 → factor_pruning._segment_lens（全段 full_p + 现代段 recent_p，同口径）
  · 仓位族(COT)/期权情绪族(P/C) → 同 walk_forward.block_bootstrap_diff（状态型 sel：最近一份 usable 报告/
    滚动z 落极端区 vs 基率），数据源 data/cot.csv / data/cboe_putcall.csv（fetch_cot.py / fetch_putcall.py）。
每候选 → {p(全段), recent_p(现代段), recent_powered}；交 quality_gate.adjudicate（双栏 BY-FDR + 三态）。
固定种子、**全部候选进分母（禁预筛）** = 防 p-hacking。Phase 1b 不接门4 OOS（留后续）、不进账本。
"""
import csv
import json
import hashlib
import datetime
import numpy as np
import pandas as pd
from pathlib import Path

import placebo_test as pb
from walk_forward import build_feature_df, block_bootstrap_diff
import factor_pruning as fp
import candidate_space as cs
from quality_gate import adjudicate, summarize

SCRIPTS = Path(__file__).parent
RAW_DIR = SCRIPTS.parent / "data" / "raw"
WEB_DIR = SCRIPTS.parent / "web"
PROC_DIR = SCRIPTS.parent / "data" / "processed"
DOCS_DIR = SCRIPTS.parent.parent / "docs"
RECENT_CUT = pd.Timestamp("2000-01-01")   # 现代段口径，与 placebo 一致
LOG = SCRIPTS.parent / "data" / "autodiscovery_log.csv"   # append-only 裁决账本(被 CI 提交持久化;Phase4 衰减/建议器自升级的前向史)


def _seed_for(cid):
    # 稳定哈希(hashlib)——内置 hash() 跨进程随机(PYTHONHASHSEED)会让"固定种子"失效、p 值不可复现
    return [pb.SEED, int(hashlib.sha1(cid.encode()).hexdigest()[:8], 16)]


_DAILY_CACHE = {}


def _daily(index):
    if index in _DAILY_CACHE:                 # 缓存：22 个候选别重读 22 次 CSV
        return _DAILY_CACHE[index]
    if index == "sp500":
        s = pb.load_sp500_daily()
    else:
        s = pd.read_csv(RAW_DIR / "NASDAQ_COMP_long.csv", index_col=0, parse_dates=True).squeeze()
        s = pd.to_numeric(s, errors="coerce").dropna()
        s = s[s > 0].sort_index().pct_change().dropna()
    _DAILY_CACHE[index] = s
    return s


# ── 多时间窗：完整 / 2000后 / 2021后 / 近1年（用户要"结果具体·概率·多时间窗"）──
WINS = [("完整", None), ("2000后", pd.Timestamp("2000-01-01")),
        ("2021后", pd.Timestamp("2021-01-01")), ("近1年", "y1")]

# 二元方向型日历效应（label==1=先验更高组，单边置换才有意义）→ 给"触发组上涨率 vs 基率"
_DIR_EFFECTS = ("pre_holiday", "santa", "sell_in_may", "world_cup_year", "term_year3",
                "september", "january", "turn_of_month", "pre_fomc")


def _wmask(idx, w):
    idx = pd.DatetimeIndex(idx)
    if w is None:
        return np.ones(len(idx), dtype=bool)
    if w == "y1":
        return np.asarray(idx >= (idx.max() - pd.Timedelta(days=365)))
    return np.asarray(idx >= w)


def _decade_rows(idx, trig, up):
    """逐十年：触发组上涨率 vs 该十年基率（看规律哪些年代对、哪些年代死了）。trig=触发布尔，up=上涨布尔。"""
    idx = pd.DatetimeIndex(idx)
    dec = (idx.year // 10) * 10
    trig = np.asarray(trig)
    up = np.asarray(up, dtype=float)
    out = []
    for d in sorted(set(int(x) for x in dec)):
        m = (dec == d)
        tm = m & trig
        if int(m.sum()) < 30 or int(tm.sum()) < 5:     # 该十年样本太少 → 不下结论(略过)
            continue
        ut, ub = float(up[tm].mean()), float(up[m].mean())
        out.append({"decade": f"{d}s", "up_pct": round(ut * 100), "base_pct": round(ub * 100),
                    "diff_pp": round((ut - ub) * 100, 1), "n": int(tm.sum())})
    return out


def _diff_windows(idx, sel, y, block):
    """触发条件 sel 下 y 的上涨率 vs 基率，逐时间窗（反弹/因子通用·有清晰"概率"）。"""
    out = []
    for lab, w in WINS:
        mk = _wmask(idx, w)
        s, yy = sel[mk], y[mk]
        if int(s.sum()) >= 10 and int((~s).sum()) >= 10:
            bb = block_bootstrap_diff(s, yy, block=block)
            out.append({"label": lab, "p": (round(float(bb["p_boot"]), 3) if bb else None),
                        "up_pct": round(float(yy[s].mean() * 100)), "base_pct": round(float(yy.mean() * 100)),
                        "diff_pp": round(float((yy[s].mean() - yy.mean()) * 100), 1), "n": int(s.sum())})
        else:
            out.append({"label": lab, "p": None, "up_pct": None, "n": int(s.sum())})
    return out


def _cal_windows(idx, vals, lab, stat, cid, eff):
    """日历效应逐时间窗 p；方向型(节前/圣诞)附触发组上涨率；class 型(周几/月份)omnibus·无单一概率。"""
    out = []
    for wi, (wlab, w) in enumerate(WINS):
        mk = _wmask(idx, w)
        v, l = vals[mk], lab[mk]
        cnts = np.unique(l, return_counts=True)[1] if len(l) else np.array([0])
        if len(v) >= 60 and len(set(l.tolist())) >= 2 and cnts.min() >= 8:
            pw = pb.perm_test(v, l, stat, np.random.default_rng(_seed_for(cid) + [3000 + wi]))["p_value"]
            row = {"label": wlab, "p": (None if np.isnan(pw) else round(float(pw), 3)), "n": int(len(v))}
            if eff in _DIR_EFFECTS or eff.startswith("monthof_"):
                row["up_pct"] = round(float((v[l == 1] > 0).mean() * 100)) if (l == 1).any() else None
                row["base_pct"] = round(float((v[l == 0] > 0).mean() * 100)) if (l == 0).any() else None
            out.append(row)
        else:
            out.append({"label": wlab, "p": None, "n": int(len(v))})
    return out


# ── 日历族：复用 placebo 的统计量与口径，逐候选算 全段 p + 现代段 recent_p ──
def _calendar_arrays(eff, index, floor=None):
    """提取日历效应的 (vals, lab, idx, stat, directional)；全样本、不算 p。
    命门：门4 OOS(oos_gate.py) 与 _calendar 共用这一份定义 → OOS 与裁决永不漂移。
    directional=True 仅限有方向先验的效应(见返回处说明)；机器逐月扫 monthof_ 为两侧 omnibus → False。
    floor(§10·日历族 OOS)：先把**输入** ret 滤到 `> floor` 再抽取/重采样 → 月/年频效应不会有
       '锚点当期 bar 含锚前数据'的边界泄漏（日历无前看依赖，floor 输入是对的）。floor=None=全样本。"""
    ret = _daily(index)
    if ret is None or len(ret) < 1000:
        return None
    if floor is not None:
        ret = ret[ret.index > pd.Timestamp(floor)]
        if len(ret) < 1000:          # 锚后数据不足 → None → 上游 oos_gate 记"未到可判"
            return None
    if eff == "dow":
        d = ret[ret.index >= pb.DOW_START]; lab = d.index.weekday.values; m = lab <= 4
        vals, lab, idx = d.values[m], lab[m], d.index[m]; stat = pb.make_ssb_stat(5)
    elif eff == "month":
        mo = (1 + ret).resample("ME").prod(min_count=1).dropna() - 1
        vals, lab, idx = mo.values, (mo.index.month - 1).values, mo.index; stat = pb.make_ssb_stat(12)
    elif eff == "decade_digit":
        an = (1 + ret).resample("YE").prod(min_count=1).dropna() - 1
        an = an[an.index.year < pd.Timestamp.today().year]
        vals, lab, idx = an.values, (an.index.year % 10).values, an.index; stat = pb.make_ssb_stat(10)
    elif eff == "presidential_cycle":
        an = (1 + ret).resample("YE").prod(min_count=1).dropna() - 1
        an = an[an.index.year < pd.Timestamp.today().year]
        vals, lab, idx = an.values, (an.index.year % 4).values, an.index; stat = pb.make_ssb_stat(4)
    elif eff == "pre_holiday":
        h = ret[ret.index >= pb.HOLIDAY_START]; pre = pb.holiday_pre_mask(h.index)
        vals, lab, idx = h.values, pre.astype(int), h.index; stat = pb.make_dir_diff_stat()
    elif eff == "santa":
        santa = (((ret.index.month == 12) & (ret.index.day >= 26)) |
                 ((ret.index.month == 1) & (ret.index.day <= 3))).astype(int)
        vals, lab, idx = ret.values, santa, ret.index; stat = pb.make_dir_diff_stat()
    elif eff == "sell_in_may":
        # Sell-in-May/万圣节先验：冬季(11-4月)强 > 夏季(5-10月)。label==1=冬季(先验更高组)→单边
        winter = (~ret.index.month.isin([5, 6, 7, 8, 9, 10])).astype(int)
        vals, lab, idx = ret.values, winter, ret.index; stat = pb.make_dir_diff_stat()
    elif eff == "world_cup_year":
        # 世界杯分心先验：限夏季(6-8月)，常规夏季 > 世界杯年夏季。label==1=非杯年夏季(先验更高组)
        from seasonality import WORLD_CUP_YEARS                      # 单一来源，避免年份表漂移
        jja = ret[ret.index.month.isin([6, 7, 8])]
        nonwc = (~jja.index.year.isin(WORLD_CUP_YEARS)).astype(int)
        vals, lab, idx = jja.values, nonwc, jja.index; stat = pb.make_dir_diff_stat()
    elif eff == "september":
        # 九月效应先验：九月历史最弱月。label==1=非九月(先验更高组)→单边(非九月 > 九月)
        nonsep = (ret.index.month != 9).astype(int)
        vals, lab, idx = ret.values, nonsep, ret.index; stat = pb.make_dir_diff_stat()
    elif eff == "january":
        # 元月效应先验：一月历史偏强(尤小盘)。label==1=一月(先验更高组)→单边(一月 > 其余)
        jan = (ret.index.month == 1).astype(int)
        vals, lab, idx = ret.values, jan, ret.index; stat = pb.make_dir_diff_stat()
    elif eff == "turn_of_month":
        # 月末月初效应先验(Ariel 1987)：收益集中在每月最后1个交易日 + 月初前3个交易日。
        # label==1=turn 窗(先验更高组)→单边(月界 > 月中)
        per = ret.index.to_period("M")
        s = pd.Series(ret.values, index=ret.index)
        dom = s.groupby(per).cumcount().values                 # 0-based 月内交易日序
        msize = s.groupby(per).transform("size").values        # 该月交易日数
        tom = ((dom < 3) | (dom == msize - 1)).astype(int)     # 前3日 或 最后1日
        vals, lab, idx = ret.values, tom, ret.index; stat = pb.make_dir_diff_stat()
    elif eff == "pre_fomc":
        # 预 FOMC 漂移先验(Lucca-Moench 2015)：计划 FOMC 公告前 1 个交易日偏强。
        # label==1=会前日(先验更高组)→单边(会前 > 其余)，测**平均收益**差。会议日表/标签定义见 fomc_dates.py。
        from fomc_dates import pre_fomc_mask                # 单一定义,与 fomc_study 同标签不漂移
        pre, _ = pre_fomc_mask(ret.index, 1)               # pre_window 固定 1（改了=新候选/新锚,见 registry 纪律）
        vals, lab, idx = ret.values, pre.astype(int), ret.index; stat = pb.make_dir_diff_stat()
    elif eff == "opex_week":
        # 期权到期周先验(Stoll-Whaley 等)：每月第3个周五(day in [15,21])那个日历周(周一到周五)活跃度异常。
        # 无方向共识 → 两侧 make_ssb_stat(2)，不进 _DIR_EFFECTS。
        import datetime as _dt
        lab = np.zeros(len(ret), dtype=int)
        for i, d in enumerate(ret.index):
            yr, mo = d.year, d.month
            # 找第3个周五：day_of_month 在 [15,21] 且 weekday==4(周五)
            third_fri = None
            for day in range(15, 22):
                if _dt.date(yr, mo, day).weekday() == 4:
                    third_fri = _dt.date(yr, mo, day)
                    break
            if third_fri is not None:
                # 整个日历周(周一..周五)：third_fri - 4天(周一) .. third_fri
                week_mon = third_fri - _dt.timedelta(days=4)
                d_date = d.date() if hasattr(d, 'date') else _dt.date(d.year, d.month, d.day)
                if week_mon <= d_date <= third_fri:
                    lab[i] = 1
        vals, lab, idx = ret.values, lab, ret.index; stat = pb.make_ssb_stat(2)
    elif eff == "quarter_end":
        # 季末窗口先验(窗口粉饰/再平衡)：3/6/9/12月最后3个交易日异常。
        # 无方向共识 → 两侧 make_ssb_stat(2)，不进 _DIR_EFFECTS。
        # 注：与 turn_of_month 有意重叠(均预声明·均进 FDR 分母，相关但非 p-hacking)。
        per = ret.index.to_period("M")
        s = pd.Series(ret.values, index=ret.index)
        msize = s.groupby(per).transform("size").values        # 该月交易日数
        dom = s.groupby(per).cumcount().values                 # 0-based 月内交易日序
        quarter_months = ret.index.month.isin([3, 6, 9, 12])
        last3 = (dom >= msize - 3)                             # 最后3个交易日(0-based末尾3)
        lab = (quarter_months & last3).astype(int)
        vals, lab, idx = ret.values, lab, ret.index; stat = pb.make_ssb_stat(2)
    elif eff.startswith("monthof_"):
        # 机器枚举·逐月：该月 vs 其余是否异常。无方向先验 → 两侧(SS_between，方向无关)，谁异常谁自己冒出来。
        M = int(eff.split("_")[1])
        m1 = (ret.index.month == M).astype(int)
        vals, lab, idx = ret.values, m1, ret.index; stat = pb.make_ssb_stat(2)
    elif eff == "term_year3":
        # Hirsch 总统周期：任期第3年(大选前一年)历史最强。年频，label==1=第3年(先验更高组)
        an = (1 + ret).resample("YE").prod(min_count=1).dropna() - 1
        an = an[an.index.year < pd.Timestamp.today().year]
        y3 = (an.index.year % 4 == 3).astype(int)
        vals, lab, idx = an.values, y3, an.index; stat = pb.make_dir_diff_stat()
    else:
        return None
    # directional：仅**有方向先验**(label==1=先验更高组,单边 make_dir_diff_stat)才置 True → 门4 才比'方向'。
    # monthof_ 是机器逐月扫、两侧 make_ssb_stat(2)、**无方向先验**(不能从数据里读出方向再'确认'它,那是循环) →
    # OOS 视作 omnibus(只看 p)。注:_calendar 显示层的 showup/decades 另算(eff.startswith monthof_),不受此影响。
    directional = eff in _DIR_EFFECTS
    return vals, lab, idx, stat, directional


def _calendar(eff, index, cid):
    arr = _calendar_arrays(eff, index)
    if arr is None:
        return None
    vals, lab, idx, stat, _directional = arr
    p = pb.perm_test(vals, lab, stat, np.random.default_rng(_seed_for(cid)))["p_value"]
    # 现代段(post-2000)：够样本才测；年频(decade/presidential)样本太疏 → 不测 → inconclusive
    rmask = np.asarray(idx >= RECENT_CUT)
    recent_p, powered = None, False
    if eff not in ("decade_digit", "presidential_cycle", "term_year3") and int(rmask.sum()) >= 200:
        rp = pb.perm_test(vals[rmask], lab[rmask], stat,
                          np.random.default_rng(_seed_for(cid) + [2000]))["p_value"]
        if not np.isnan(rp):                       # P2-a 守卫:现代段单标签组→NaN→留 None/False(防 allow_nan=False 崩盘)
            rmin = int(np.unique(lab[rmask], return_counts=True)[1].min())
            recent_p, powered = rp, rmin >= pb.MIN_GROUP_N
    dirf = eff in _DIR_EFFECTS
    showup = dirf or eff.startswith("monthof_")    # 月扫虽两侧,仍亮"该月上涨率"便于看方向
    return {"p": float(p), "recent_p": (None if recent_p is None else float(recent_p)),
            "recent_powered": bool(powered),
            "windows": _cal_windows(idx, vals, lab, stat, cid, eff),
            "decades": (_decade_rows(idx, lab == 1, vals > 0) if showup else []),
            "effect": ("该月上涨率 vs 基率(两侧·机器枚举)" if eff.startswith("monthof_")
                       else "触发组上涨率 vs 基率" if dirf else "组间差异(omnibus·无单一概率)")}


# ── 反弹族：跌破第 pctl 百分位日后，持有 hold 日的前向收益 up 率 vs 基率（块自助） ──
def _rebound_arrays(pctl, hold, index):
    """提取反弹族 (idx, sel, y)；全样本、阈值=全样本百分位、不算 p。
    命门(§10)：阈值定义于全数据 → 门4 OOS 只把 (sel,y) 滤到锚后，**绝不**在锚后重算阈值。"""
    ret = _daily(index)
    if ret is None or len(ret) < 1000:
        return None
    # 向量化前向 hold 日收益：cumsum(log1p) 差分，替掉慢的 rolling().apply(逐窗 Python 调用，单候选 ~100s)
    r = ret.values
    C = np.log1p(r).cumsum()
    fwd = np.full(len(r), np.nan)
    m = len(r) - hold
    fwd[:m] = np.expm1(C[hold:hold + m] - C[:m])   # fwd[t]=prod(1+r[t+1..t+hold])-1
    df = pd.DataFrame({"ret": r, "fwd": fwd}, index=ret.index).dropna()
    thr = np.percentile(df["ret"].values, pctl)
    sel = (df["ret"].values <= thr)
    y = (df["fwd"].values > 0).astype(float)
    if sel.sum() < 30:
        return None
    return df.index, sel, y


def _rebound(pctl, hold, index, cid):
    arr = _rebound_arrays(pctl, hold, index)
    if arr is None:
        return None
    idx, sel, y = arr
    bb = block_bootstrap_diff(sel, y, block=hold)
    if bb is None:
        return None
    rmask = np.asarray(idx >= RECENT_CUT)
    recent_p, powered = None, False
    rsel = sel & rmask
    if int(rsel.sum()) >= 30 and int((~sel & rmask).sum()) >= 30:
        rbb = block_bootstrap_diff(sel[rmask], y[rmask], block=hold)
        if rbb is not None:
            recent_p, powered = rbb["p_boot"], True
    return {"p": float(bb["p_boot"]), "recent_p": (None if recent_p is None else float(recent_p)),
            "recent_powered": bool(powered),
            "windows": _diff_windows(idx, sel, y, hold),
            "decades": _decade_rows(idx, sel, y > 0),
            "effect": "触发日后持有期上涨率 vs 基率"}


# ── 价格体制族：金叉等"价格条件成立时未来 hold 日上涨率 vs 基率"（标普不在 factor 管线，单列）──
def _daily_price(index):
    f = {"sp500": "SP500_long.csv", "nasdaq": "NASDAQ_COMP_long.csv"}.get(index)
    if not f or not (RAW_DIR / f).exists():
        return None
    s = pd.read_csv(RAW_DIR / f, index_col=0, parse_dates=True)
    s = pd.to_numeric(s.iloc[:, 0], errors="coerce").dropna()
    return s[s > 0].sort_index()


def _regime_arrays(signal, index, hold=20):
    """提取价格体制族 (idx, sel, y)；全样本、均线用全 px、不算 p。
    命门(§10)：均线(50/200)定义于全数据 → 门4 OOS 只把 (cond,fwd) 滤到锚后，**绝不**在锚后重启均线。"""
    px = _daily_price(index)
    if px is None or len(px) < 300:
        return None
    if signal == "golden_cross":                       # 50 日均线 > 200 日均线（先验：趋势向上）
        ma50, ma200 = px.rolling(50).mean(), px.rolling(200).mean()
        # 暖机段(前199天)均线未定义:必须是 NaN 被 dropna 剔除,不是 False 混进基率(H-2 同款纪律)
        cond = (ma50 > ma200).astype(float).where(ma200.notna())
    else:
        return None
    fwd = px.shift(-hold) / px - 1
    # 审④同款修(T1·2026-07-07):fwd(float 含 NaN)先进 df 再 dropna,之后才派生 y——
    # 先 (fwd>0) 转 float 会把尾部"前向窗未实现"的日子捏造成 y=0(下跌),且 dropna 删不掉
    df = pd.DataFrame({"sel": cond, "fwd": fwd}).dropna()
    sel = df["sel"].values == 1
    y = (df["fwd"].values > 0).astype(float)
    if int(sel.sum()) < 100 or int((~sel).sum()) < 100:
        return None
    return df.index, sel, y


def _regime(signal, index, cid, hold=20):
    arr = _regime_arrays(signal, index, hold)
    if arr is None:
        return None
    idx, sel, y = arr
    bb = block_bootstrap_diff(sel, y, block=hold)
    if bb is None:
        return None
    rmask = np.asarray(idx >= RECENT_CUT)
    recent_p, powered = None, False
    if int((sel & rmask).sum()) >= 100 and int((~sel & rmask).sum()) >= 100:
        rbb = block_bootstrap_diff(sel[rmask], y[rmask], block=hold)
        if rbb is not None:
            recent_p, powered = rbb["p_boot"], True
    return {"p": float(bb["p_boot"]), "recent_p": (None if recent_p is None else float(recent_p)),
            "recent_powered": bool(powered),
            "windows": _diff_windows(idx, sel, y, hold),
            "decades": _decade_rows(idx, sel, y > 0),
            "effect": "信号成立时未来20日上涨率 vs 基率"}


# ══════════════════════════════════════════════════════════════════════════
# ── 仓位族 positioning（2026-07-04·#7·CFTC COT 期货持仓·状态型 sel）──
#   命门(H-2)：merge_asof 是 direction="backward"，早于该 series/market 首份 usable 报告(以及暖机段，
#   见下 _rolling_pctrank)的交易日一律 NaN → dropna 整段剔除 = "数组裁到该 series 首个 usable 报告日"，
#   绝不把"无报告可用"悄悄当成"不极端"(False)，否则会拿现代极端日对未纳入 COT 覆盖前的年代基率作差
#   （年代错配污染 discovery p）。
# ══════════════════════════════════════════════════════════════════════════
COT_CSV = SCRIPTS.parent / "data" / "cot.csv"
_POS_WINDOW = 156        # 3 年周频报告(命门:156份"周频报告"滚动分位，绝非156个日历天)

# H-3(块敏感性·2026-07-04 建造者实测)：positioning 是多周状态，block=hold 会漏掉状态持续段(重叠序列相关
# 被低估) → p 系统性偏低。实测 8 个(market×series×extreme)sel 状态的"连续极端段"长度分布：
#   sp500/legacy   hi p90=43.0d lo p90=50.6d ；sp500/tff    hi p90=42.2d lo p90=49.8d
#   nasdaq100/legacy hi p90=33.0d lo p90=37.4d；nasdaq100/tff hi p90=31.5d lo p90=33.0d
# 取全族**最保守**(最大)值 ceil(50.6)=51，discovery 与 OOS 两处同用(§10 定稿要求)，不按候选各自调参
# (否则"挑对自己有利的 block"本身就是新的researcher-degree-of-freedom)。
POSITIONING_BLOCK_EXTRA = 51
_COT_CACHE = {}


def _positioning_block(hold):
    return hold + POSITIONING_BLOCK_EXTRA


def _cot_reports(market, series):
    """加载+过滤 COT 报告级数据 → 单一 (report_date, usable_from, value) DataFrame，report_date 升序。
    series="legacy_noncomm_pct_oi"：source=legacy，用已算好的 noncomm_net_pct_oi。
    series="tff_lev_net_pct_oi"：source=tff，载入时算 lev_funds_net/open_interest*100(scale-free 跨年代可比)。
    """
    key = (market, series)
    if key in _COT_CACHE:
        return _COT_CACHE[key]
    if not COT_CSV.exists():
        _COT_CACHE[key] = None
        return None
    df = pd.read_csv(COT_CSV, parse_dates=["report_date", "usable_from"])
    df = df[df["market"] == market].copy()
    if series == "legacy_noncomm_pct_oi":
        df = df[df["source"] == "legacy"].copy()
        df["value"] = pd.to_numeric(df["noncomm_net_pct_oi"], errors="coerce")
    elif series == "tff_lev_net_pct_oi":
        df = df[df["source"] == "tff"].copy()
        oi = pd.to_numeric(df["open_interest"], errors="coerce")
        lev = pd.to_numeric(df["lev_funds_net"], errors="coerce")
        df["value"] = np.where(oi > 0, 100.0 * lev / oi, np.nan)
    else:
        _COT_CACHE[key] = None
        return None
    df = df.dropna(subset=["value", "usable_from"]).sort_values("report_date").reset_index(drop=True)
    out = df[["report_date", "usable_from", "value"]] if len(df) else None
    _COT_CACHE[key] = out
    return out


def _rolling_pctrank(vals, window=_POS_WINDOW):
    """纯回看滚动分位(含当期报告)：窗口内 <= 当前值 的比例*100。暖机不足(< window 份报告)→NaN
    （命门:window 单位是**报告篇数**，不是日历天——156 份周频报告≈3年，与日频族的 252 日z窗不是同一时间刻度）。
    """
    vals = np.asarray(vals, dtype=float)
    n = len(vals)
    out = np.full(n, np.nan)
    for i in range(window - 1, n):
        w = vals[i - window + 1: i + 1]
        out[i] = 100.0 * np.sum(w <= w[-1]) / window
    return out


def _positioning_arrays(market, series, extreme, hold):
    """提取仓位族 (idx, sel, y)：156 份周频报告滚动分位(纯回看)判极端状态 → merge_asof backward 把
    状态铺到每个交易日(状态持续到下一份报告生效，照 regime 金叉先例的"状态型" sel) → 前向严格
    t+1..t+hold 上涨率。market="nasdaq100" 时前向目标映射到 "nasdaq"（NASDAQ_COMP，声明为代理）。
    命门(H-2)：merge_asof 前先把暖机段/无报告段的 state 置 NaN，随后 dropna → 数组裁到该 series
    首个"可判定"状态生效的交易日，绝不拿早年（COT 未覆盖或滚动窗未暖机）当"不极端"凑基率。
    """
    rep = _cot_reports(market, series)
    if rep is None or len(rep) < _POS_WINDOW:
        return None
    rep = rep.copy()
    rep["pctrank"] = _rolling_pctrank(rep["value"].values)
    if extreme == "hi":
        state = rep["pctrank"] >= 90
    elif extreme == "lo":
        state = rep["pctrank"] <= 10
    else:
        return None
    state = state.where(rep["pctrank"].notna())     # 暖机段(pctrank NaN)→ state 也 NaN(未定义,非 False)

    price_idx = {"sp500": "sp500", "nasdaq100": "nasdaq"}.get(market)   # 命门:market 映射 nasdaq100→"nasdaq"
    px = _daily_price(price_idx)
    if px is None or len(px) < 300:
        return None
    daily = pd.DataFrame({"date": pd.DatetimeIndex(px.index)}).sort_values("date")
    rep_asof = pd.DataFrame({"date": rep["usable_from"], "state": state}).sort_values("date")
    merged = pd.merge_asof(daily, rep_asof, on="date", direction="backward")   # 点时间铁律:只准用 usable_from
    merged = merged.dropna(subset=["state"])         # H-2:早于首个可判定状态的交易日整段剔除(不当 False)
    if len(merged) < 300:
        return None
    keep_dates = pd.DatetimeIndex(merged["date"])
    px2 = px.reindex(keep_dates)
    fwd = px2.shift(-hold) / px2 - 1                 # 严格 t+1..t+hold（收盘 t 到收盘 t+hold 的realize收益）
    sel = merged["state"].astype(bool).values
    # 审④阻断修:必须在 (>0) 强转**之前**从 fwd 取 valid——(NaN>0)→False 会把尾部"无已实现前向窗"
    # 的日子捏造成 y=0(下跌),系统性压制"当前正处极端态"的活信号(修正即翻转 legacy_lo_h60_nasdaq100 头条)。
    valid = ~np.isnan(fwd.values)
    keep_dates, sel = keep_dates[valid], sel[valid]
    y = (fwd.values[valid] > 0).astype(float)
    if int(sel.sum()) < 30 or int((~sel).sum()) < 30:
        return None
    return keep_dates, sel, y


def _positioning(market, series, extreme, hold, cid):
    arr = _positioning_arrays(market, series, extreme, hold)
    if arr is None:
        return None
    idx, sel, y = arr
    block = _positioning_block(hold)                  # H-3:状态多周持续 → block 放大(hold+episode p90)
    bb = block_bootstrap_diff(sel, y, block=block)
    if bb is None:
        return None
    rmask = np.asarray(idx >= RECENT_CUT)
    recent_p, powered = None, False
    if int((sel & rmask).sum()) >= 30 and int((~sel & rmask).sum()) >= 30:
        rbb = block_bootstrap_diff(sel[rmask], y[rmask], block=block)
        if rbb is not None:
            recent_p, powered = rbb["p_boot"], True
    return {"p": float(bb["p_boot"]), "recent_p": (None if recent_p is None else float(recent_p)),
            "recent_powered": bool(powered),
            "windows": _diff_windows(idx, sel, y, block),
            "decades": _decade_rows(idx, sel, y > 0),
            "effect": "仓位极端状态下未来持有期上涨率 vs 基率"}


# ══════════════════════════════════════════════════════════════════════════
# ── 期权情绪族 options_sentiment（2026-07-04·#7·CBOE Put/Call 比·状态型 sel）──
#   命门：滚动252日z(纯回看含当日t)判极端；口径纪律绝不用绝对阈值(2012-06 CBOE 口径变更+市占漂移，
#   滚动z天然吸收)；block=hold 保留(尖峰型 sel，持续中位仅1天，不像 positioning 需要放大块)。
# ══════════════════════════════════════════════════════════════════════════
PUTCALL_CSV = SCRIPTS.parent / "data" / "cboe_putcall.csv"
_OPT_ZWIN = 252          # 日频滚动z窗(含当日t，与 positioning 的156"份报告"不是同一时间刻度)
_PUTCALL_CACHE = None


def _putcall_daily():
    global _PUTCALL_CACHE
    if _PUTCALL_CACHE is None:
        if not PUTCALL_CSV.exists():
            _PUTCALL_CACHE = False
        else:
            df = pd.read_csv(PUTCALL_CSV, parse_dates=["date"]).sort_values("date").set_index("date")
            _PUTCALL_CACHE = df
    return _PUTCALL_CACHE if _PUTCALL_CACHE is not False else None


def _optsent_arrays(series, extreme, hold):
    """提取期权情绪族 (idx, sel, y)：滚动252日z(纯回看窗含当日t·收盘已知，暖机不足252日不判)判极端 →
    与 SP500 daily 对齐(inner join 同交易日) → 前向严格 t+1..t+hold 上涨率。目标固定 SP500_long
    (P/C 是全市场情绪·标普为市场代理·声明)。"""
    df = _putcall_daily()
    if df is None or series not in df.columns:
        return None
    s = pd.to_numeric(df[series], errors="coerce").dropna()
    if len(s) < _OPT_ZWIN:
        return None
    roll_mean = s.rolling(_OPT_ZWIN, min_periods=_OPT_ZWIN).mean()
    roll_std = s.rolling(_OPT_ZWIN, min_periods=_OPT_ZWIN).std(ddof=0)
    z = (s - roll_mean) / roll_std
    z = z.replace([np.inf, -np.inf], np.nan).dropna()
    if extreme == "hi":
        sel_s = z > 2.0
    elif extreme == "lo":
        sel_s = z < -2.0
    else:
        return None
    px = _daily_price("sp500")
    if px is None or len(px) < 300:
        return None
    common = sel_s.index.intersection(px.index)
    if len(common) < 300:
        return None
    common = pd.DatetimeIndex(sorted(common))
    sel_s = sel_s.reindex(common)
    px2 = px.reindex(common)
    fwd = px2.shift(-hold) / px2 - 1                  # 严格 t+1..t+hold
    # 审④阻断修:fwd(float 含 NaN)先进 df 再 dropna,之后才派生 y——先 (fwd>0) 转 bool 会把尾部
    # NaN 变 False、dropna 形同虚设(同 positioning 侧同款 bug·捏造 y=0)。
    df2 = pd.DataFrame({"sel": sel_s, "fwd": fwd}).dropna()
    sel = df2["sel"].values.astype(bool)
    y = (df2["fwd"].values > 0).astype(float)
    if int(sel.sum()) < 30 or int((~sel).sum()) < 30:
        return None
    return df2.index, sel, y


def _optsent(series, extreme, hold, cid):
    arr = _optsent_arrays(series, extreme, hold)
    if arr is None:
        return None
    idx, sel, y = arr
    bb = block_bootstrap_diff(sel, y, block=hold)      # 尖峰型 sel → block=hold 不放大(与 positioning 不同)
    if bb is None:
        return None
    rmask = np.asarray(idx >= RECENT_CUT)
    recent_p, powered = None, False
    if int((sel & rmask).sum()) >= 30 and int((~sel & rmask).sum()) >= 30:
        rbb = block_bootstrap_diff(sel[rmask], y[rmask], block=hold)
        if rbb is not None:
            recent_p, powered = rbb["p_boot"], True
    return {"p": float(bb["p_boot"]), "recent_p": (None if recent_p is None else float(recent_p)),
            "recent_powered": bool(powered),
            "windows": _diff_windows(idx, sel, y, hold),
            "decades": _decade_rows(idx, sel, y > 0),
            "effect": "期权情绪极端状态下未来持有期上涨率 vs 基率"}


# ── 因子族：复用 _segment_lens 的 全段 full_p + 现代段 recent_p ──
def _factor_map(factor_cands):
    if not factor_cands:        # 无因子候选不碰特征数据集(CI 干净检出无 data/raw/,#104 连挂根因)
        return {}
    df = build_feature_df()
    cutoff = df["date"].max() - pd.DateOffset(years=fp.RECENT_YEARS)
    out = {}
    for c in factor_cands:
        col = c["params"]["factor"]
        seg = fp._segment_lens(df, col, fp.ASSUMED_DIR.get(col, +1), cutoff)
        wins = (_diff_windows(df["date"], (df[col] == 1).values, df["fwd_up_20d"].values.astype(float), fp.HORIZON)
                if col in df.columns else [])
        if seg is None:
            out[c["candidate_id"]] = {"p": 1.0, "recent_p": None, "recent_powered": False,
                                      "windows": wins, "effect": "因子为真时20日上涨率 vs 基率"}
        else:
            out[c["candidate_id"]] = {
                "p": float(seg["full_p"]),
                "recent_p": (None if seg["recent_p"] is None else float(seg["recent_p"])),
                "recent_powered": seg["status"] != "现代检验力不足",
                "windows": wins, "effect": "因子为真时20日上涨率 vs 基率"}
    return out


def compute_results(candidates):
    """每候选路由到真统计 → {candidate_id, family, key, p, recent_p, recent_powered}。"""
    fac = _factor_map([c for c in candidates if c["family"] == "factor"])
    results = []
    for c in candidates:
        fam = c["family"]
        if fam == "calendar":
            r = _calendar(c["params"]["effect"], c["params"]["index"], c["candidate_id"])
        elif fam == "rebound":
            r = _rebound(c["params"]["pctl"], c["params"]["hold"], c["params"]["index"], c["candidate_id"])
        elif fam == "regime":
            r = _regime(c["params"]["signal"], c["params"]["index"], c["candidate_id"])
        elif fam == "positioning":                       # H-1 BLOCKER:必须显式路由，绝不落 else→p=1.0
            p = c["params"]
            r = _positioning(p["market"], p["series"], p["extreme"], p["hold"], c["candidate_id"])
        elif fam == "options_sentiment":                  # H-1 BLOCKER:同上
            p = c["params"]
            r = _optsent(p["series"], p["extreme"], p["hold"], c["candidate_id"])
        elif fam == "factor":
            r = fac.get(c["candidate_id"])
        else:
            raise ValueError(f"compute_results: 未路由的 family={fam!r}"
                              "(H-1 反退化:新族必须显式接线，不许静默落 p=1.0)")
        if r is None:                       # 数据不足 → 进分母但永不存活(检验力不足)
            r = {"p": 1.0, "recent_p": None, "recent_powered": False}
        results.append({"candidate_id": c["candidate_id"], "family": fam, "key": c["key"], **r})
    return results


# ── Phase 2：append-only 裁决账本（每交易日一快照=N 行，幂等：盘前+盘后同日不重复）──
def _append_log(results, path=LOG):
    from util_io import append_daily_log
    today = datetime.date.today().isoformat()
    header = ["date", "candidate_id", "key", "family", "verdict", "p", "recent_p"]
    rows = [[today, r["candidate_id"], r["key"], r["family"], r.get("verdict", ""),
             "" if r.get("p") is None else round(float(r["p"]), 6),
             "" if r.get("recent_p") is None else round(float(r["recent_p"]), 6)]
            for r in sorted(results, key=lambda x: x["candidate_id"])]
    return append_daily_log(path, header, rows, date=today)


def _log_days(path=LOG):
    """账本里已记录的不同交易日数（前端显示「已追踪 N 天」）。"""
    if not path.exists():
        return 0
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return len({r[0] for r in rows[1:]}) if len(rows) > 1 else 0


def run_all(write=True, q=0.10):
    cands = cs.enumerate_candidates()
    results = compute_results(cands)
    adjudicate(results, q=q, expect_n=cs.N_DECLARED)   # 断言分母完整 = 全部候选都算了
    s = summarize(results)
    if write:
        _append_log(results)               # 每交易日 append 裁决快照，攒衰减/自升级前向史
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": ("自动发现 Phase 1b：预注册有限候选(日历/反弹/因子)各路由到真统计算 p，"
                   "经 quality_gate 双栏 BY-FDR(族内+跨族)+三态裁决。全部候选进分母、禁预筛、固定种子。"),
        "caveat": "存活≠未来重演≠可交易；现代已淡=全段过FDR但现代测不到(疑被套利)；"
                  "检验力不足=样本太小不下结论。因子族 FDR 为**无向双侧**(只问'有无可测边际'、不含方向判断，"
                  "与 factor_pruning 的方向门控透镜口径不同)。门4样本外待接入。探索性，非预测、非荐股。",
        "q": q, "n_declared": cs.N_DECLARED, "days_tracked": _log_days(), "summary": s,
        "candidates": sorted(results, key=lambda r: r["p"]),
    }
    if write:
        from util_io import write_json
        write_json("autodiscovery.json", out, proc=True, allow_nan=False)
        print(f"[OK] autodiscovery.json — 测 {s['m_total']} / 跨族存活 {s['n_survive_cross']} "
              f"(族内 {s['n_survive_family']}) / 已淡 {s['n_faded']} / 检验力不足 {s['n_inconclusive']}")
    return out


if __name__ == "__main__":
    run_all()
