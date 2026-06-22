"""autodiscovery.py — v1.5 自生长 Phase 1b：把候选路由到真统计算 p，喂裁决引擎，产出 autodiscovery.json。

状态(2026-06-22)：种子稳定(hashlib)、_daily 缓存、每候选带多时间窗(完整/2000后/2021后/近1年)
   实际上涨率 vs 基率。**内建校验通过**：SP500 日历 p 值与 placebo_tests.json 一致。
   42 候选(2026-06-22 扩声明：+Sell-in-May/世界杯年/任期第3年 民俗/学术先验日历，append-only)：
   9 跨族存活、8 已淡、其余死/检验力不足——诚实。任期第3年=79%上涨 vs 64%(p≈.05·样本疏判 inconclusive)。
   待独立审(判断密集)后接 run_all（现 JSON 仍手动重生成，见审计 B2/D1）。


复用现有原语（不重写统计）：
  · 日历族 → placebo_test 的 perm_test + make_ssb_stat / make_dir_diff_stat（SP500/纳指 日收益）
  · 反弹族 → walk_forward.block_bootstrap_diff（跌破第 N 百分位日后持有 M 日的前向收益 vs 基率）
  · 因子族 → factor_pruning._segment_lens（全段 full_p + 现代段 recent_p，同口径）
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
_DIR_EFFECTS = ("pre_holiday", "santa", "sell_in_may", "world_cup_year", "term_year3")


def _wmask(idx, w):
    idx = pd.DatetimeIndex(idx)
    if w is None:
        return np.ones(len(idx), dtype=bool)
    if w == "y1":
        return np.asarray(idx >= (idx.max() - pd.Timedelta(days=365)))
    return np.asarray(idx >= w)


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
            if eff in _DIR_EFFECTS:
                row["up_pct"] = round(float((v[l == 1] > 0).mean() * 100)) if (l == 1).any() else None
                row["base_pct"] = round(float((v[l == 0] > 0).mean() * 100)) if (l == 0).any() else None
            out.append(row)
        else:
            out.append({"label": wlab, "p": None, "n": int(len(v))})
    return out


# ── 日历族：复用 placebo 的统计量与口径，逐候选算 全段 p + 现代段 recent_p ──
def _calendar(eff, index, cid):
    ret = _daily(index)
    if ret is None or len(ret) < 1000:
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
    elif eff == "term_year3":
        # Hirsch 总统周期：任期第3年(大选前一年)历史最强。年频，label==1=第3年(先验更高组)
        an = (1 + ret).resample("YE").prod(min_count=1).dropna() - 1
        an = an[an.index.year < pd.Timestamp.today().year]
        y3 = (an.index.year % 4 == 3).astype(int)
        vals, lab, idx = an.values, y3, an.index; stat = pb.make_dir_diff_stat()
    else:
        return None

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
    return {"p": float(p), "recent_p": (None if recent_p is None else float(recent_p)),
            "recent_powered": bool(powered),
            "windows": _cal_windows(idx, vals, lab, stat, cid, eff),
            "effect": ("触发组上涨率 vs 基率" if dirf else "组间差异(omnibus·无单一概率)")}


# ── 反弹族：跌破第 pctl 百分位日后，持有 hold 日的前向收益 up 率 vs 基率（块自助） ──
def _rebound(pctl, hold, index, cid):
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
    bb = block_bootstrap_diff(sel, y, block=hold)
    if bb is None:
        return None
    rmask = np.asarray(df.index >= RECENT_CUT)
    recent_p, powered = None, False
    rsel = sel & rmask
    if int(rsel.sum()) >= 30 and int((~sel & rmask).sum()) >= 30:
        rbb = block_bootstrap_diff(sel[rmask], y[rmask], block=hold)
        if rbb is not None:
            recent_p, powered = rbb["p_boot"], True
    return {"p": float(bb["p_boot"]), "recent_p": (None if recent_p is None else float(recent_p)),
            "recent_powered": bool(powered),
            "windows": _diff_windows(df.index, sel, y, hold),
            "effect": "触发日后持有期上涨率 vs 基率"}


# ── 因子族：复用 _segment_lens 的 全段 full_p + 现代段 recent_p ──
def _factor_map(factor_cands):
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
        else:
            r = fac.get(c["candidate_id"])
        if r is None:                       # 数据不足 → 进分母但永不存活(检验力不足)
            r = {"p": 1.0, "recent_p": None, "recent_powered": False}
        results.append({"candidate_id": c["candidate_id"], "family": fam, "key": c["key"], **r})
    return results


# ── Phase 2：append-only 裁决账本（每交易日一快照=N 行，幂等：盘前+盘后同日不重复）──
def _append_log(results, path=LOG):
    today = datetime.date.today().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        rows = list(csv.reader(open(path, encoding="utf-8")))
        if len(rows) > 1 and rows[-1][0] == today:   # 同日已记 → 幂等返回(不改历史行)
            return False
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "candidate_id", "key", "family", "verdict", "p", "recent_p"])
        for r in sorted(results, key=lambda x: x["candidate_id"]):
            w.writerow([today, r["candidate_id"], r["key"], r["family"], r.get("verdict", ""),
                        "" if r.get("p") is None else round(float(r["p"]), 6),
                        "" if r.get("recent_p") is None else round(float(r["recent_p"]), 6)])
    return True


def _log_days(path=LOG):
    """账本里已记录的不同交易日数（前端显示「已追踪 N 天」）。"""
    if not path.exists():
        return 0
    rows = list(csv.reader(open(path, encoding="utf-8")))
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
    payload = json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False)
    if write:
        for d in (PROC_DIR, WEB_DIR, DOCS_DIR):
            if d.exists():
                (d / "autodiscovery.json").write_text(payload, encoding="utf-8")
        print(f"[OK] autodiscovery.json — 测 {s['m_total']} / 跨族存活 {s['n_survive_cross']} "
              f"(族内 {s['n_survive_family']}) / 已淡 {s['n_faded']} / 检验力不足 {s['n_inconclusive']}")
    return out


if __name__ == "__main__":
    run_all()
