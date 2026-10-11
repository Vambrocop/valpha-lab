"""block_calibration.py —— 量一量「循环块自助」这把尺子本身准不准（离线，绝不进 CI）。

## 为什么要有它

`walk_forward.block_bootstrap_diff` 是全站最通吃的统计核（8 个模块在用），
但在 2026-09-21 之前**从没有人量过它的实际水平** —— 名义 α=0.10 的检验，
真实拒真率是多少？没人知道，也没有工具能问。

于是发生了两件事：
  · `block >= n` 时它**恒定输出最显著的值**（拒真率 100%），没有任何守门发现；
  · F2 想给状态型 sel 补块放大 —— 但"放大多少才够"只能靠拍脑袋。

这个工具把两件事都变成可测的。

## 方法：循环旋转 null（rotation null）

把 `y` 相对 `sel` 做随机循环平移。两条序列**各自的边际分布与自相关结构分毫不动**，
只有二者之间的关联被打断 → H0「sel 对 y 无信息」成立。
于是 `p < α` 的经验比例 = 这个检验在**这段真实样本上**的实际水平。

合成模式（`--synthetic`）用的是独立生成的 sel/y，同一个道理、答案更干净。

## 先验量具（控制组）

`--controls` 跑一组**答案已知**的配置。量具坏了当场看得出来 ——
不先验量具就拿它去撤公开结论，是本项目犯过的错（a2872a3：我上一次"矫枉"过了头，
把本该显著的 SP500 Tier≥4 撤成 p=.209，后来实测证实是我错的）。

## 用法

    py tools/block_calibration.py --controls          # 验量具（答案已知）
    py tools/block_calibration.py --sweep             # 拒真率 vs 块数 曲线
    py tools/block_calibration.py --sweep --R 2000    # 更窄的误差棒（慢）

成本约生产点估计的 R 倍（R×B 次重采样/配置）→ **离线量一次、把结论写进规格**，
生产只读常量。同 SPEC_MC_RESOLUTION 对加算成本的处理。
"""
import argparse
import math
import sys
from pathlib import Path

import pathlib

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "market-analysis" / "scripts"))
import walk_forward as wf                                     # noqa: E402

# 只用来决定**先给哪些行花算力测尾巴**（排序/预算），不决定任何裁决。
# ⚠ 我原来写的理由（"阈值必须高于估计器自己的本底"）**是错的** ——
# 那 0.11–0.135 是块自助的真实水平、不是旋转 null 的偏差；审查者验过估计器本身
# （真值 0.093 vs 旋转 0.070，1 SE 内）。详见 scripts/block_levels.py 的 docstring。
MAX_LEVEL_RATIO = 2.0


def _rate(n, block, R, B, alpha, seed0, *, sel_ac=0, y_ac=0, force=False):
    """跑 R 次 H0 为真的数据，返回 p<alpha 的比例（= 实际水平）。

    `sel_ac` / `y_ac`：>0 时给 sel / y 注入持续性（游程长度 / 重叠窗口），
    用来造出"两边都有结构"的难例 —— 那才是真实数据的形状。
    `force`：绕过 MIN_BLOCKS 门，用于**演示门存在的理由**（量退化本身）。
    """
    hits = ran = 0
    for s in range(R):
        g = np.random.default_rng(seed0 + s)
        if sel_ac > 0:                       # 长段 sel：游程长度 ~ sel_ac 的状态型
            runs, out = [], 0
            while out < n:
                ln = max(1, int(g.exponential(sel_ac)))
                runs.append(np.full(ln, g.random() < 0.5))
                out += ln
            sel = np.concatenate(runs)[:n]
        else:
            sel = g.random(n) < 0.35
        if y_ac > 0:                         # 重叠前向窗：y 天然序列相关
            raw = g.standard_normal(n + y_ac)
            y = np.convolve(raw, np.ones(y_ac) / y_ac, mode="valid")[:n]
        else:
            y = g.standard_normal(n)
        if int(sel.sum()) < 10 or int((~sel).sum()) < 10:
            continue
        r = _call(sel, y, block, B, s, force=force)
        if r is None:
            continue
        ran += 1
        if r["p_boot"] < alpha:
            hits += 1
    return (hits / ran if ran else float("nan")), ran


def _call(sel, y, block, B, seed, *, force=False):
    if not force:
        return wf.block_bootstrap_diff(sel, y, block=block, B=B, seed=seed)
    old = wf.MIN_BLOCKS
    wf.MIN_BLOCKS = 1                       # 只在本工具内、只为演示退化
    try:
        return wf.block_bootstrap_diff(sel, y, block=block, B=B, seed=seed)
    finally:
        wf.MIN_BLOCKS = old


def _line(label, rate, ran, R, alpha, extra=""):
    se = math.sqrt(rate * (1 - rate) / ran) if ran else float("nan")
    flag = "✓" if rate <= alpha + 2 * se else ("✗✗" if rate > 3 * alpha else "✗")
    skipped = f"  (跳过 {R - ran})" if ran < R else ""
    print(f"  {label:<38} {rate:>6.3f} ±{se:.3f}  {flag}{extra}{skipped}")


def controls(R, B, alpha):
    """答案已知的控制组 —— 量具自检。"""
    print(f"\n=== 控制组（答案已知；名义 α={alpha}）R={R} B={B} ===")
    print("  量具本底：i.i.d. 数据下这个检验应当就在名义值附近。")
    r, n_ = _rate(3000, 20, R, B, alpha, 1000);                _line("(a) sel i.i.d. + y i.i.d.", r, n_, R, alpha)
    r, n_ = _rate(3000, 20, R, B, alpha, 2000, sel_ac=140);    _line("(b) sel 长段(140) + y i.i.d.", r, n_, R, alpha)
    r, n_ = _rate(3000, 20, R, B, alpha, 3000, y_ac=20);       _line("(c) sel i.i.d. + y 20日重叠", r, n_, R, alpha)
    print("  难例：两边都有结构 —— 真实数据的形状。block=20 应当反保守。")
    for blk in (20, 164, 320):
        r, n_ = _rate(3000, blk, R, B, alpha, 4000, sel_ac=140, y_ac=20)
        _line(f"(d) 两边都有结构 n=3000 block={blk}", r, n_, R, alpha)
    print("  同样的持续性，样本放长 4 倍 —— 放大块长这时才修得好。")
    for blk in (20, 164, 320):
        r, n_ = _rate(12000, blk, R, B, alpha, 5000, sel_ac=140, y_ac=20)
        _line(f"(e) 同 (d) 但 n=12000 block={blk}", r, n_, R, alpha)


def sweep(R, B, alpha, block=64):
    """拒真率 vs 块数 —— MIN_BLOCKS 的依据。"""
    print(f"\n=== 拒真率 vs 块数（block={block} 固定，只变 n）R={R} B={B} α={alpha} ===")
    print("  纯 i.i.d. 噪声 = **最好情况**；真实数据带自相关只会更差。")
    print(f"  {'块数':>5} {'n':>7}   拒真率")
    for nb in (1, 2, 3, 4, 6, 8, 10, 15, 20, 30, 50):
        n = nb * block
        r, ran = _rate(n, block, R, B, alpha, 90000, force=True)
        mark = "  ← MIN_BLOCKS" if nb == wf.MIN_BLOCKS else ""
        bad = "   ⚠ 恒定输出最显著" if nb == 1 else ""
        _line(f"{nb:>5} 块  n={n:<6}", r, ran, R, alpha, extra=f"{mark}{bad}")
    print(f"\n  当前 walk_forward.MIN_BLOCKS = {wf.MIN_BLOCKS}")
    print("  注:1 块时 (start+arange(block))%n 的前 n 个是整条序列的**循环平移**,")
    print("     而 sel 与 y 共用同一 idx → 每次重采样原样复现观测统计量 → 方差为 0。")


# ── 段长测量：EXTRA 常量的来源 ──────────────────────────────────────────────
# 纪律（抄 TRAILING_BLOCK_EXTRA 的建造顺序）：**只看 sel 的状态持续，绝不看前向收益**。
# 目的是让"挑一个对自己有利的 block"在物理上做不到 —— 测量根本碰不到 y。

def _runs(arr):
    a = np.asarray(arr, dtype=bool)
    if a.sum() == 0:
        return np.array([], dtype=int)
    ch = np.diff(np.concatenate(([0], a.astype(int), [0])))
    return np.where(ch == -1)[0] - np.where(ch == 1)[0]


def _family_arrays():
    """对每个候选取它的 sel（不取 y）→ {family: [run_lengths...]}。"""
    import candidate_space as cs
    import autodiscovery as ad
    import factor_pruning as fp
    out, dfs = {}, {}
    for c in cs.enumerate_candidates():
        fam, pr = c["family"], c["params"]
        try:
            if fam == "regime":
                arr = ad._regime_arrays(pr["signal"], pr["index"], 20)
            elif fam == "rebound":
                arr = ad._rebound_arrays(pr["pctl"], pr["hold"], pr["index"])
            elif fam == "positioning":
                arr = ad._positioning_arrays(pr["market"], pr["series"], pr["extreme"], pr["hold"])
            elif fam == "options_sentiment":
                arr = ad._optsent_arrays(pr["series"], pr["extreme"], pr["hold"])
            elif fam == "trailing_extreme":
                arr = ad._trailing_extreme_arrays(pr["n"], pr["hold"], pr["index"], pr["side"])
            elif fam in ("streak_down", "streak_break"):
                arr = ad._streak_arrays(fam, pr["n"], pr["hold"], pr["index"])
            elif fam == "factor":
                if "df" not in dfs:
                    dfs["df"] = wf.build_feature_df()
                arr = fp.factor_arrays(dfs["df"], pr["col"] if "col" in pr else pr.get("factor"))
            else:
                continue
        except Exception:
            continue
        if arr is None:
            continue
        r = _runs(arr[1])
        if len(r):
            out.setdefault(fam, []).append((c["key"], r))
    return out


def runlengths():
    """逐族报 sel 连续段长的 p90 —— EXTRA 常量就取全族 p90 的最大值 ceil。"""
    import autodiscovery as ad
    print()
    print("=== 各族 sel 连续段长（只测状态持续，**绝不看前向收益**）===")
    known = {"positioning": ad.POSITIONING_BLOCK_EXTRA,
             "trailing_extreme": ad.TRAILING_BLOCK_EXTRA}
    fams = _family_arrays()
    print(f"  {'族':<20} {'候选':>4} {'p90最大':>8} {'最长段':>7} {'→EXTRA':>8}  {'对照已有常量'}")
    for fam in sorted(fams):
        rows = fams[fam]
        p90s = [float(np.percentile(r, 90)) for _, r in rows]
        top = max(p90s)
        extra = math.ceil(top)
        chk = ""
        if fam in known:
            chk = ("✓ 复现 " if extra == known[fam] else "✗ 不符！已有=")+str(known[fam])
        print(f"  {fam:<20} {len(rows):>4} {top:>8.1f} "
              f"{max(int(r.max()) for _, r in rows):>7} {extra:>8}  {chk}")
    print()
    print("  读法：带 ✓ 的两行是**控制组** —— 这套测法先复现了项目自己写死的两个常量，")
    print("       所以不是我另起了一套口径。不符就说明测法有问题，先别信新常量。")


# ── 真候选的旋转 null：这个检验在**这段真实样本**上实际会错判多少 ──────────────
# 把 y 相对 sel 做随机循环平移：两条序列各自的边际分布与自相关结构分毫不动，
# 只有二者之间的关联被打断 → H0「sel 对 y 无信息」成立。
# 于是 p<α 的经验比例 = 这个检验在这段样本上的**实际水平**。
# 名义 0.10、实测 0.30，意思就是每 3 条"显著"里有 1 条是块长不够编出来的。

# 候选标识**绝不手写**：手写过一次就踩到了 —— 我把体制族的 index 写成 "nasdaq100"，
# 而 `_daily_price` 只认 {"sp500","nasdaq"} → `.get()` 返回 None → arrays 为 None →
# 那一行被**静默跳过**，测量表里少一条却没人报警。改为一律从 `candidate_space`
# 枚举真候选、用它们自己的 params，标识与生产同源。
# 全部走**块自助**的族。日历族(51 条)走置换检验、是另一台机器，不在这张表里
# （置换对"月份标签"的可交换性有它自己的问题 —— 同类问题、不同机器，另案）。
#
# ⚠ 纪律：**别只测你预期有问题的那几族**。只量 factor/regime 就下架它们的结论、
# 却不量 positioning/trailing，那是选择性测量 —— 公开名单会因此变得不一致。
BOOTSTRAP_FAMILIES = ("factor", "regime", "rebound", "positioning",
                      "options_sentiment", "trailing_extreme",
                      "streak_down", "streak_break")
_MEASURED_FAMILIES = BOOTSTRAP_FAMILIES


def _arrays_for(c, ad, fp, df_box):
    """按族取 (arr, block) —— block 一律走生产自己的公式，绝不在这里另算。"""
    fam, pr = c["family"], c["params"]
    if fam == "regime":
        return ad._regime_arrays(pr["signal"], pr["index"], 20), ad._regime_block(20)
    if fam == "rebound":
        return (ad._rebound_arrays(pr["pctl"], pr["hold"], pr["index"]),
                ad._rebound_block(pr["hold"]))
    if fam == "positioning":
        return (ad._positioning_arrays(pr["market"], pr["series"], pr["extreme"], pr["hold"]),
                ad._positioning_block(pr["hold"]))
    if fam == "options_sentiment":
        return (ad._optsent_arrays(pr["series"], pr["extreme"], pr["hold"]), pr["hold"])
    if fam == "trailing_extreme":
        return (ad._trailing_extreme_arrays(pr["n"], pr["hold"], pr["index"], pr["side"]),
                ad._trailing_extreme_block(pr["hold"]))
    if fam in ("streak_down", "streak_break"):
        return ad._streak_arrays(fam, pr["n"], pr["hold"], pr["index"]), pr["hold"]
    if fam == "factor":
        if df_box["df"] is None:
            df_box["df"] = wf.build_feature_df()
        return fp.factor_arrays(df_box["df"], pr["factor"]), fp.factor_block()
    return None, None


def _target_arrays(only=None):
    """(key, family, 窗口, sel, y, block) —— 标识与 block 全部与生产同源。"""
    import candidate_space as cs
    import autodiscovery as ad
    import factor_pruning as fp
    import pandas as pd
    df = None
    # 两族的"现代段"**不是一个东西**（规格 §6 登记过这个口径差）：
    #   regime/rebound → ad.RECENT_CUT = 2000-01-01（=2000 年起的全部样本）
    #   factor         → df.date.max() - RECENT_YEARS（滚动的"最近 N 年"）
    # 早先这里两族都用 ad.RECENT_CUT → 因子族的"现代段"与"全段"变成同一个窗、
    # 表里出现两行一模一样的数字。量 recent_p 的校准就必须用 recent_p 自己的窗。
    cut_regime = pd.Timestamp(ad.RECENT_CUT)
    cut_factor = None
    out, skipped = [], []
    box = {"df": None}
    for c in cs.enumerate_candidates():
        fam, key = c["family"], c["key"]
        if fam not in (only or _MEASURED_FAMILIES):
            continue
        arr, block = _arrays_for(c, ad, fp, box)
        if box["df"] is not None and cut_factor is None:
            cut_factor = box["df"]["date"].max() - pd.DateOffset(years=fp.RECENT_YEARS)
        if arr is None:
            skipped.append(key)
            continue
        idx, sel, y = arr
        idx = pd.DatetimeIndex(idx)
        sel, y = np.asarray(sel), np.asarray(y, float)
        # 因子族的"现代段"是滚动的最近 8 年；其余块自助族用 RECENT_CUT(2000-01-01)。
        cut = cut_factor if fam == "factor" else cut_regime
        for win, m in (("全段", np.ones(len(y), bool)), ("现代段", np.asarray(idx >= cut))):
            if m.sum() < 300 or sel[m].sum() < 10 or (~sel[m]).sum() < 10:
                continue
            out.append((key, fam, win, sel[m], y[m], int(block)))
    if skipped:
        print(f"  [本机数据不足,跳过 {len(skipped)} 条]: {', '.join(skipped)}")
        print("   ⚠ 本机 VIX3M 历史已丢(见 CLAUDE.md) → vix_backwardation 在本机必然掉出;")
        print("     **以 CI 产物为准**,别把本机测出的表当完整表提交。")
    return out


def _rotation_nulls(sel, y, block, R, B, seed0):
    """旋转 null 下算出的 **每一个 p**。

    原先这里只数 `p < alpha` 的个数、把 p 本身扔掉了 —— 那只够回答
    "名义 0.10 处实际会错多少"。但判定并不发生在 0.10：跨族 BY 的临界值
    c₁..c₁₄ 落在 **0.000121–0.001696**（F1 实测），而存活者的 p 常在 0.001 量级。
    **量错了位置，就不能拿来撤结论**（规格 §9）。

    把 p 全留下来，就免费得到 null 下 p 的整条经验分布，于是能算**校准后的 p**
    （`#{null p <= p_obs} / R`）—— 那才是与判定同处一个位置的统计量。
    """
    n = len(y)
    g = np.random.default_rng(seed0)
    out = []
    for _ in range(R):
        k = int(g.integers(1, n))                # 绝不取 0：那就是原始配对
        yr = np.roll(y, k)
        r = wf.block_bootstrap_diff(sel, yr, block=block, B=B, seed=int(g.integers(1 << 30)))
        if r is not None:
            out.append(float(r["p_boot"]))
    return np.asarray(out, dtype=float)


def _rotation_level(sel, y, block, R, B, alpha, seed0):
    """旋转 null 下 p<alpha 的比例。返回 (水平, 有效次数, 块数)。"""
    nulls = _rotation_nulls(sel, y, block, R, B, seed0)
    n, ran = len(y), len(nulls)
    lv = (float((nulls < alpha).sum()) / ran) if ran else float("nan")
    return lv, ran, math.ceil(n / block)


def _merge_write(out_path, rows, alpha, R, B):
    """**合并**而不是覆盖：允许分族/分次增量测量。

    覆盖写的后果很恶劣 —— "表里没有 = 不拦"，所以第二批把第一批冲掉，
    等于**悄悄取消了一批门**，而且产物看着完全正常。
    表头（阈值等）每次按当前模块常量重写，避免代码改了、表还挂着旧阈值。
    """
    import json
    fp_out = pathlib.Path(out_path)
    prev = {}
    if fp_out.exists():
        try:
            prev = json.loads(fp_out.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    # **逐字段**合并，不是逐行替换（独立审查 Important 5，已复现）：
    # `real()` 造的新 rec 只含 family/window/n/block/n_blocks/ran/level/se，
    # 整行替换会把 `null_p_q` / `null_B` / `null_p_floor` / `refined` / `R` 全抹掉 ——
    # 于是一次基线 R 的重测就能**静默**把一行的尾巴数据和"曾经是边界行"的记录删掉，
    # 而 `test_every_tail_row_carries_the_B_it_was_measured_at` 不会红（两个字段都没了）。
    # 另外拒绝把一行的精度**调低**：R=1600 测过的行不该被 R=400 的重测覆盖掉，
    # 除非显式重测到同等精度。
    merged = {k: dict(v) for k, v in (prev.get("rows") or {}).items()}
    for k, rec in rows.items():
        cur = merged.setdefault(k, {})
        old_r = int(cur.get("R") or cur.get("ran") or 0)
        new_r = int(rec.get("R") or rec.get("ran") or 0)
        if old_r > new_r and cur.get("level") is not None:
            print(f"    [保留高精度行] {k}: 已有 R={old_r} > 本次 R={new_r} → 不降级")
            continue
        cur.update(rec)
    payload = {"nominal_alpha": alpha, "max_level_ratio": MAX_LEVEL_RATIO,
               # R/B 是**本次**写入用的；每行自己的 ran/se 才是那一行的真实精度
               # (分族增量测量时各批的 R 可以不同,边界带还会被 --refine 加算)。
               "R": R, "B": B, "measured": __import__("datetime").date.today().isoformat(),
               "how": "tools/block_calibration.py --real --write",
               # 这张表覆盖的是**走块自助**的族。日历族(51 条)走置换检验,是另一台机器,
               # 本工具的旋转 null 量不了它 —— 这是**已知缺口**,不是漏测:
               # verify_output 只对"本该测却没测"的族告警,前端则对日历族照实写
               # 「这条的检验还没做过校准测量」。要补它得另建置换检验的 null。
               "families_covered": list(BOOTSTRAP_FAMILIES),
               "note": ("旋转 null 实测的**实际水平**。生产(scripts/block_levels.py)读它:"
                        "超过 max_level_ratio×nominal_alpha 的候选记不可判。"
                        "表里没有的候选不拦,但 verify_output 会醒目告警(不硬红)。"),
               "rows": merged}
    fp_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(merged)


def real(R, B, alpha, out_path=None, only=None):
    """逐 (候选 × 窗口) 量放大后 block 下的实际水平；可写出冻结表。"""
    import json
    print()
    print(f"=== 真候选的实际水平（旋转 null，R={R} B={B}，名义 α={alpha}）===")
    print("  读法：这一列是「这个检验在这段样本上，H0 为真时会有多大比例报显著」。")
    print("        名义 0.10 而实测 0.30 = 每 3 条『显著』里有 1 条是块长不够编出来的。")
    print("  旋转 null 把真关联**按构造**破坏 → 该测量不可能被『这条候选好不好看』影响。")
    rows, thr = {}, alpha * MAX_LEVEL_RATIO
    print(f"  {'候选':<24} {'族':<7} {'窗口':<7} {'n':>6} {'块':>5} {'水平':>7} {'SE':>6}  判断")
    for key, fam, win, sel, y, block in _target_arrays(only):
        lv, ran, nb = _rotation_level(sel, y, block, R, B, alpha, 4242)
        rec = {"family": fam, "window": win, "n": int(len(y)), "block": block,
               "n_blocks": nb, "ran": ran,
               "level": (None if ran == 0 else round(lv, 4)),
               "se": (None if ran == 0 else round(math.sqrt(lv * (1 - lv) / ran), 4))}
        rows[f"{key}|{win}"] = rec
        if ran == 0:
            txt, se, mark = "   拒绝", "      ", "块数不足→不给 p"
        else:
            txt, se = f"{lv:>7.3f}", f"{rec['se']:>6.3f}"
            mark = "✓ 可用" if lv <= thr else f"✗ 超 {MAX_LEVEL_RATIO}×名义 → 应记不可判"
        print(f"  {key:<24} {fam:<7} {win:<7} {len(y):>6} {nb:>5} {txt} {se}  {mark}")
        if out_path:
            # **每行都落盘**。全量跑要一个多小时，只在末尾写一次的话，
            # 中途 Ctrl-C / 掉电 = 前面几十条全白测。增量写是这类长测量的起码要求。
            _merge_write(out_path, rows, alpha, R, B)
    bad = sorted((k for k, v in rows.items() if v["level"] and v["level"] > thr),
                 key=lambda k: -rows[k]["level"])
    print()
    print(f"  实际水平 > {MAX_LEVEL_RATIO}×名义({thr:.2f}) 的 {len(bad)} 条 —— 这些的 p 不该被当结论：")
    for k in bad:
        v = rows[k]
        print(f"    {k:<34} {v['level']:.3f} (±{v['se']:.3f})  n={v['n']} 块={v['n_blocks']}")
    if out_path:
        n = _merge_write(out_path, rows, alpha, R, B)
        print(f"  （合并写入：本次 {len(rows)} 行 → 表共 {n} 行）")
        print()
        print(f"  写出冻结表 → {out_path}")
    return rows


def refine(path, R, B, alpha, factor=4):
    """边界带自适应加算 —— 抄 SPEC_MC_RESOLUTION Part B 的同一做法。

    基线 R 给出的 SE≈0.018，而判据是一条线：落在线附近 ±3SE 的行，
    分类基本是掷硬币（实测同一配置两次给出 0.132 与 0.095）。
    对**只有这些行**把 R 放大 `factor` 倍，其余保持基线 —— 把精度花在刀口上。
    """
    import json
    fp_out = pathlib.Path(path)
    tbl = json.loads(fp_out.read_text(encoding="utf-8"))
    # 表头按**当前**模块常量刷新：阈值改了代码却没重跑测量的话，表会挂着旧阈值，
    # 而 gate() 优先用表里的值 → 等于代码改了但门没改。有守门测试钉住两者一致。
    if tbl.get("max_level_ratio") != MAX_LEVEL_RATIO:
        print(f"  表头阈值 {tbl.get('max_level_ratio')} → {MAX_LEVEL_RATIO}（按当前模块常量刷新）")
        tbl["max_level_ratio"] = MAX_LEVEL_RATIO
    tbl.setdefault("families_covered", list(BOOTSTRAP_FAMILIES))
    thr = alpha * float(tbl.get("max_level_ratio", MAX_LEVEL_RATIO))
    band = []
    for k, v in (tbl.get("rows") or {}).items():
        if v.get("level") is None or v.get("se") is None:
            continue
        if abs(v["level"] - thr) < 3 * v["se"]:
            band.append(k)
    print()
    print(f"=== 边界带加算（阈值 {thr:.2f}，带宽 ±3SE，R {R}→{R * factor}）===")
    if not band:
        print("  边界带为空 —— 没有哪一行的分类卡在噪声里，不必加算。")
        fp_out.write_text(json.dumps(tbl, ensure_ascii=False, indent=2), encoding="utf-8")
        return tbl
    print(f"  {len(band)} 行落在边界带：{', '.join(sorted(band))}")
    want = {k.split("|")[0] for k in band}
    by_key = {}
    for key, fam, win, sel, y, block in _target_arrays():
        if f"{key}|{win}" in band:
            by_key[f"{key}|{win}"] = (sel, y, block)
    for k in sorted(band):
        if k not in by_key:
            print(f"  [取不到 arrays,保留基线] {k}")
            continue
        sel, y, block = by_key[k]
        lv, ran, nb = _rotation_level(sel, y, block, R * factor, B, alpha, 4242)
        old_lv = tbl["rows"][k]["level"]
        se = math.sqrt(lv * (1 - lv) / ran) if ran else None
        tbl["rows"][k].update(level=round(lv, 4), se=round(se, 4), ran=ran,
                              R=R * factor, refined=True)
        moved = "分类改变 →" if (old_lv > thr) != (lv > thr) else "分类不变"
        print(f"  {k:<34} {old_lv:.3f} → {lv:.3f} (±{se:.3f})  {moved}"
              f" {'不可判' if lv > thr else '可用'}")
    tbl["refined_R"] = R * factor
    fp_out.write_text(json.dumps(tbl, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  写回 → {path}")
    return tbl


# null p 分布要存哪些分位：覆盖 BY 临界值的量级（0.0001~0.002）直到 α。
# 存分位而不是存 1600 个 p：表要进仓库、要能读，194 行 ×1600 个浮点不现实。
_NULL_Q = (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50)


def _production_B(artifact="docs/autodiscovery.json"):
    """每条候选×窗口，生产**实际用的** B（= mc_n）。

    为什么必须按行取而不是全局给一个 B：F1 的边界带自适应加算会把选中的候选
    放大 10 倍（`BTC_mom20_pos` 的 mc_n 是 **20000**，而基线是 2000）。
    而 p 是离散格点、下限 = 2/(B+1) —— null 侧若用比生产更小的 B，
    下尾就被截断在比 p_obs 更粗的刻度上，整条尾巴不可比。
    （实测踩到：null 用 B=300 → 下限 0.0066，而 p_obs=0.0007。）
    """
    import json
    out = {}
    try:
        d = json.loads(pathlib.Path(artifact).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [读不到 {artifact}：{e}] → 退回命令行给的 B")
        return out
    for c in d.get("candidates") or []:
        for win, fld, pf in (("全段", "mc", "p"), ("现代段", "mc_recent", "recent_p")):
            mc = c.get(fld) or {}
            if mc.get("mc_n"):
                out[f"{c['key']}|{win}"] = (int(mc["mc_n"]), c.get(pf))
    return out


def calibrated(path, R, B, alpha, factor=4):
    """对**水平超标**的行补算 null p 的下尾分位（判定真正发生的位置）。

    水平门只是**筛子**：它说"这条的 p 尺度在 0.10 附近不可信"。
    但一条 p=0.001 的候选，即使尺度被压缩，仍可能远在 null 分布的极端尾部。
    所以筛出来的行要再问一句：**它的 p 在 null 下有多罕见**。
    筛完再裁，跟 F1 的边界带加算是同一个套路。
    """
    import json
    fp_out = pathlib.Path(path)
    tbl = json.loads(fp_out.read_text(encoding="utf-8"))
    thr = alpha * float(tbl.get("max_level_ratio", MAX_LEVEL_RATIO))
    need = sorted(k for k, v in (tbl.get("rows") or {}).items()
                  if v.get("level") is not None and v["level"] > thr)
    print()
    print(f"=== 补算 null p 下尾分位（水平 > {thr:.2f} 的 {len(need)} 行，R={R * factor}）===")
    if not need:
        print("  没有超标行，无需补算。")
        return tbl
    prodB = _production_B()
    todo = {f"{key}|{win}": (sel, y, block)
            for key, fam, win, sel, y, block in _target_arrays()
            if f"{key}|{win}" in need}
    for k in need:
        if k not in todo:
            print(f"  [取不到 arrays,跳过] {k}")
            continue
        sel, y, block = todo[k]
        # null 侧的 B 只在**这一行真的需要那个分辨率**时才抬到生产的 B。
        # 判据：这一行自己的 p_obs 是否低于基线 B 的格点下限 2/(B+1)。
        #   · p_obs=0.35 → 基线 B=300(下限 0.0066)完全够用，问题是"P(null p<=0.35)>0.10 吗"，
        #     不需要 0.001 的刻度；抬到 B=2000 只是白烧 7 倍算力。
        #   · p_obs=0.0007 → 基线下限比它粗 9 倍，尾巴被截断 → **必须**抬到生产的 B(20000)。
        # 不这么分的话 16 行全按生产 B 跑要 2~3 小时，而其中 15 行的结论根本不会变。
        pb_n, p_obs = prodB.get(k, (0, None))
        base_floor = 2.0 / (int(B) + 1)
        if p_obs is not None and float(p_obs) < base_floor:
            b_row = max(int(B), int(pb_n))
            r_row = max(400, int(R * factor * int(B) / b_row))
            print(f"    ({k}: p_obs={p_obs} 低于基线下限 {base_floor:.4f} → "
                  f"null 侧 B 抬到生产的 {b_row}，旋转 {r_row} 次)")
        else:
            b_row, r_row = int(B), R * factor
        nulls = _rotation_nulls(sel, y, block, r_row, b_row, 4242)
        B_used = b_row
        if not len(nulls):
            continue
        qs = {str(q): round(float(np.quantile(nulls, q)), 6) for q in _NULL_Q}
        # **必须记下 null 侧用的 B**：p 是离散格点，下限 = 2/(B+1)。
        # B=300 时下限 0.0066 —— 比生产(B=2000,下限 0.001)粗 6.6 倍，
        # 于是 null 的下尾被**截断**在 0.0066。拿这样一条尾巴去判断一个
        # p=0.0007 的候选，会把"我这把尺子量不到那么细"误读成"它比所有 null 都极端"。
        # 生产侧 `calibrated_p` 据此拒绝使用分辨不到的尾巴（见 block_levels.py）。
        tbl["rows"][k].update(null_p_q=qs, null_p_min=round(float(nulls.min()), 6),
                              null_R=int(len(nulls)), null_B=int(B_used),
                              null_p_floor=round(2.0 / (B_used + 1), 8))
        print(f"  {k:<36} null p 下尾：" +
              "  ".join(f"q{q}={qs[str(q)]:.4f}" for q in (0.01, 0.05, 0.10)) +
              f"   最小 {nulls.min():.4f}")
    tbl["null_q_levels"] = list(_NULL_Q)
    fp_out.write_text(json.dumps(tbl, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  写回 → {path}")
    return tbl


def main():
    ap = argparse.ArgumentParser(description="量块自助这把尺子本身的实际水平（离线）")
    ap.add_argument("--controls", action="store_true", help="跑答案已知的控制组（先验量具）")
    ap.add_argument("--sweep", action="store_true", help="跑 拒真率 vs 块数 曲线")
    ap.add_argument("--real", action="store_true",
                    help="对真候选跑旋转 null，量放大后 block 下的**实际水平**（最重要的一条）")
    ap.add_argument("--calibrated", metavar="PATH", default=None,
                    help="对水平超标的行补算 null p 下尾分位（判定真正发生的位置）")
    ap.add_argument("--refine", metavar="PATH", default=None,
                    help="对冻结表里落在判据边界 ±3SE 的行加算 R（抄 F1 的边界带自适应加算）")
    ap.add_argument("--only", metavar="FAM", nargs="+", default=None,
                    help="只测这几族（分批跑；--write 是合并写入，不会冲掉上一批）")
    ap.add_argument("--write", metavar="PATH", default=None,
                    help="把 --real 的结果写成冻结表（生产读它）")
    ap.add_argument("--runlengths", action="store_true",
                    help="逐族量 sel 连续段长 p90（EXTRA 常量的来源；含复现已有两个常量的控制组）")
    ap.add_argument("--R", type=int, default=600, help="每个配置重复多少次（默认 600）")
    ap.add_argument("--B", type=int, default=400, help="每次自助多少轮（默认 400）")
    ap.add_argument("--alpha", type=float, default=0.10, help="名义水平（默认 0.10）")
    a = ap.parse_args()
    if not (a.controls or a.sweep or a.runlengths or a.real or a.refine or a.calibrated):
        ap.error("至少选一个：--controls / --sweep / --runlengths / --real / --refine / --calibrated")
    if a.runlengths:
        runlengths()
    if a.real:
        real(a.R, a.B, a.alpha, out_path=a.write, only=a.only)
    if a.refine:
        refine(a.refine, a.R, a.B, a.alpha)
    if a.calibrated:
        calibrated(a.calibrated, a.R, a.B, a.alpha)
    if a.controls:
        controls(a.R, a.B, a.alpha)
    if a.sweep:
        sweep(a.R, a.B, a.alpha)
    print("\n✓ 读法：✓=与名义同量级；✗=反保守；✗✗=拒真率超名义 3 倍（不可用）")


if __name__ == "__main__":
    main()
