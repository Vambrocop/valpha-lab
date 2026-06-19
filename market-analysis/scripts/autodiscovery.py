"""autodiscovery.py — v1.5 自生长 Phase 1b：把候选路由到真统计算 p，喂裁决引擎，产出 autodiscovery.json。

⚠️ WIP(2026-06-19)：路由逻辑建好、种子已稳定(hashlib)、_daily 已缓存；**但未接 run_all、未端到端验证**——
   实测 run_all(write=False) >280s 太慢(瓶颈：日历 perm_test N=1000×10候选×2 + rebound 的
   rolling().apply 逐窗 Python 调用)。**下一步先优化性能**(rebound 向量化前向收益、calendar 复用/降N、
   或缓存零分布)再验证(含 SP500 日历 p 对 placebo 的内建校验)+ 独立审 + 接 run_all。暂不上线。


复用现有原语（不重写统计）：
  · 日历族 → placebo_test 的 perm_test + make_ssb_stat / make_dir_diff_stat（SP500/纳指 日收益）
  · 反弹族 → walk_forward.block_bootstrap_diff（跌破第 N 百分位日后持有 M 日的前向收益 vs 基率）
  · 因子族 → factor_pruning._segment_lens（全段 full_p + 现代段 recent_p，同口径）
每候选 → {p(全段), recent_p(现代段), recent_powered}；交 quality_gate.adjudicate（双栏 BY-FDR + 三态）。
固定种子、**全部候选进分母（禁预筛）** = 防 p-hacking。Phase 1b 不接门4 OOS（留后续）、不进账本。
"""
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
    else:
        return None

    p = pb.perm_test(vals, lab, stat, np.random.default_rng(_seed_for(cid)))["p_value"]
    # 现代段(post-2000)：够样本才测；年频(decade/presidential)样本太疏 → 不测 → inconclusive
    rmask = np.asarray(idx >= RECENT_CUT)
    recent_p, powered = None, False
    if eff not in ("decade_digit", "presidential_cycle") and int(rmask.sum()) >= 200:
        rp = pb.perm_test(vals[rmask], lab[rmask], stat,
                          np.random.default_rng(_seed_for(cid) + [2000]))["p_value"]
        rmin = int(np.unique(lab[rmask], return_counts=True)[1].min())
        recent_p, powered = rp, rmin >= pb.MIN_GROUP_N
    return {"p": float(p), "recent_p": (None if recent_p is None else float(recent_p)),
            "recent_powered": bool(powered)}


# ── 反弹族：跌破第 pctl 百分位日后，持有 hold 日的前向收益 up 率 vs 基率（块自助） ──
def _rebound(pctl, hold, index, cid):
    ret = _daily(index)
    if ret is None or len(ret) < 1000:
        return None
    fwd = (1 + ret).rolling(hold).apply(np.prod, raw=True).shift(-hold) - 1
    df = pd.DataFrame({"ret": ret, "fwd": fwd}).dropna()
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
            "recent_powered": bool(powered)}


# ── 因子族：复用 _segment_lens 的 全段 full_p + 现代段 recent_p ──
def _factor_map(factor_cands):
    df = build_feature_df()
    cutoff = df["date"].max() - pd.DateOffset(years=fp.RECENT_YEARS)
    out = {}
    for c in factor_cands:
        col = c["params"]["factor"]
        seg = fp._segment_lens(df, col, fp.ASSUMED_DIR.get(col, +1), cutoff)
        if seg is None:
            out[c["candidate_id"]] = {"p": 1.0, "recent_p": None, "recent_powered": False}
        else:
            out[c["candidate_id"]] = {
                "p": float(seg["full_p"]),
                "recent_p": (None if seg["recent_p"] is None else float(seg["recent_p"])),
                "recent_powered": seg["status"] != "现代检验力不足"}
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


def run_all(write=True, q=0.10):
    cands = cs.enumerate_candidates()
    results = compute_results(cands)
    adjudicate(results, q=q, expect_n=cs.N_DECLARED)   # 断言分母完整 = 全部候选都算了
    s = summarize(results)
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": ("自动发现 Phase 1b：预注册有限候选(日历/反弹/因子)各路由到真统计算 p，"
                   "经 quality_gate 双栏 BY-FDR(族内+跨族)+三态裁决。全部候选进分母、禁预筛、固定种子。"),
        "caveat": "存活≠未来重演≠可交易；现代已淡=全段过FDR但现代测不到(疑被套利)；"
                  "检验力不足=样本太小不下结论。门4样本外待接入。探索性，非预测、非荐股。",
        "q": q, "n_declared": cs.N_DECLARED, "summary": s,
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
