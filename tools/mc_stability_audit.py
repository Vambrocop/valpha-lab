"""mc_stability_audit.py — 真换种子重跑，量裁决的**实际**不稳定度（离线，勿进 CI）。

## 它测什么，为什么需要它

`quality_gate.change_probabilities`（进流水线的那个）是**模型化**近似：
从已存下的 MC 计数按 `θ*~Beta(X+½,n−X+½)`、`X*~Binom(n,θ*)` 重抽、重跑 `adjudicate`。
纯算术、K=2000 约 1.2s —— 所以它能天天算、能进 CI 守门。

**但它假设了一个噪声模型，而且是在"加算集固定"的条件下算的。**
本工具不假设：真换随机种子、**真跑生产的两遍流程**（`autodiscovery.resolve_candidates`），
所以加算集自己也会随种子变 —— 这才是端到端的真实不稳定度。

两个用处：
  ① **交叉验证噪声模型**：实测与模型显著不一致 → 先查模型，再信 CI 里那道快守门；
  ② **修前修后对照**（规格 §9-4）：`--both` 一次跑出"未加算 vs 加算"两种口径。

## ⚠ 它的前两版都有问题，都是独立审查抓的

· **R1 规格**把它写成「按 N 个种子重跑 `adjudicate`」—— 而 `adjudicate` 没有种子参数、
  也不算 p。按字面实现会 N 次得到同一答案、**恒报 0 条改判**，
  然后"修复后显著下降"看起来完美达成（审规格 B8）。
· **第一版实现**只调 `compute_results`（未加算），所以它量的是**未加算管线**的
  种子敏感度，规格 §9-4 的对照根本做不出来，而结尾话术读起来像能（审实现 B3）。
  现已改为与生产**共用** `resolve_candidates`。

教训同 CLAUDE.md 的 `fe8af0a`：**「我跑了一次是绿的」≠ 验证过，还得问它到底在测什么。**

## 代价（所以离线）

每个种子：未加算口径 ≈ 1 遍 `compute_results`；加算口径 ≈ 2 遍。
本机实测单遍约 2 分钟（审查者机器上约 4 分钟，块自助对并发负载敏感）。
  `--seeds 3`（默认）加算口径 ≈ 12 分钟；`--both` ≈ 18 分钟。
**绝不进 CI。**

## 用法

    $env:PYTHONUTF8='1'
    py tools/mc_stability_audit.py                  # 加算口径（= 生产在跑的）
    py tools/mc_stability_audit.py --no-refine      # 未加算基线（修前）
    py tools/mc_stability_audit.py --both --seeds 3 # 修前修后对照（规格 §9-4）
"""
import argparse
import collections
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "market-analysis" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import autodiscovery as ad          # noqa: E402
import candidate_space as cs        # noqa: E402
import walk_forward as wf           # noqa: E402


def _patch_seeds(offset):
    """把两个估计器的种子整体挪 offset，返回撤销函数。

    生产里自助的种子是 `block_bootstrap_diff` 的默认参数（永远 42）、
    置换的来自 `autodiscovery._seed_for(cid)`。**两者都要挪**，否则只换了一半种子。
    替身用 `*a, **k` 转发 —— 写死签名的话，将来 `block_bootstrap_diff` 加参数
    这里会静默丢掉它（审查 N4）。
    """
    import factor_pruning as fp
    orig_bbd, orig_seed_for = wf.block_bootstrap_diff, ad._seed_for

    def bbd(*a, **k):
        k["seed"] = k.get("seed", 42) + offset
        return orig_bbd(*a, **k)

    def seed_for(cid):
        return [x + offset for x in orig_seed_for(cid)]

    wf.block_bootstrap_diff = bbd
    ad.block_bootstrap_diff = bbd          # from-import 的副本要单独打
    fp.block_bootstrap_diff = bbd
    ad._seed_for = seed_for

    def undo():
        wf.block_bootstrap_diff = orig_bbd
        ad.block_bootstrap_diff = orig_bbd
        fp.block_bootstrap_diff = orig_bbd
        ad._seed_for = orig_seed_for
    return undo


def _one_regime(cands, n_seeds, refine, q):
    """跑一种口径：基准 + n_seeds 个换种子的重跑。返回 (实测改判序列, 模型摘要, 逐条频率)。"""
    tag = "加算（= 生产在跑的）" if refine else "未加算（修前基线）"
    print(f"\n{'='*66}\n口径：{tag}\n{'='*66}")
    t = time.time()
    base_rows, base_refine, model_probs, model_sum = ad.resolve_candidates(cands, q=q, refine=refine)
    per = time.time() - t
    base = {r["key"]: r["verdict"] for r in base_rows}
    print(f"[基准] 耗时 {per:.0f}s（pass1 {model_sum['seconds_pass1']}s / "
          f"pass2 {model_sum['seconds_pass2']}s）；加算集 {len(base_refine)} 条")
    print(f"[基准] **模型化**估计：平均改判 {model_sum['mean_changes']} 条、"
          f"名单原样复现 {model_sum['published_set_prob']:.1%}")
    print(f"[计划] 再跑 {n_seeds} 个种子 ≈ {per*n_seeds/60:.0f} 分钟")

    flips, counts, refine_sizes = collections.Counter(), [], []
    for k in range(1, n_seeds + 1):
        undo = _patch_seeds(offset=k * 1000)
        t = time.time()
        try:
            rows, rids, _p, _s = ad.resolve_candidates(cands, q=q, refine=refine)
        finally:
            undo()
        v = {r["key"]: r["verdict"] for r in rows}
        chg = [key for key in base if base[key] != v[key]]
        for key in chg:
            flips[key] += 1
        counts.append(len(chg))
        refine_sizes.append(len(rids))
        print(f"  种子 +{k*1000}: 改判 {len(chg):2d} 条 · 加算集 {len(rids):2d} 条 "
              f"({time.time()-t:.0f}s)" + (f" → {chg[:4]}" if chg else ""))

    real = sum(counts) / len(counts)
    print(f"\n[{tag}] **实测**（真换种子、真重跑两遍）：")
    print(f"    改判条数 均值 {real:.2f} / 最大 {max(counts)} / 各次 {counts}")
    if refine:
        print(f"    加算集规模 各次 {refine_sizes}（随种子变 = 端到端的真实情形）")
    gap = abs(real - model_sum["mean_changes"])
    print(f"    模型化估计 {model_sum['mean_changes']} → 差距 {gap:.2f} 条 —— "
          + ("模型与实测一致，CI 里那道快守门可信"
             if gap <= 1.5 else
             "⚠ **模型与实测差得多**：change_probabilities 的噪声模型可能不对，先查它再信守门"))
    if flips:
        print(f"    逐条改判频率（{n_seeds} 个种子）：")
        for key, n in flips.most_common(12):
            mp = (model_probs.get(key) or {}).get("change_prob")
            print(f"      {key[:40]:40s} 实测 {n}/{n_seeds}"
                  + (f"  模型 {mp:.0%}" if mp is not None else ""))
    return counts, model_sum, flips


def run(n_seeds=3, q=0.10, both=False, refine=True):
    cands = cs.enumerate_candidates()
    print(f"候选 {len(cands)} 只；离线工具，**勿进 CI**")
    if both:
        c_off, s_off, _ = _one_regime(cands, n_seeds, refine=False, q=q)
        c_on, s_on, _ = _one_regime(cands, n_seeds, refine=True, q=q)
        print(f"\n{'='*66}\n修前 → 修后（规格 §9-4 要的那张对照）\n{'='*66}")
        print(f"  实测平均改判条数   {sum(c_off)/len(c_off):.2f}  →  {sum(c_on)/len(c_on):.2f}")
        print(f"  模型化平均改判     {s_off['mean_changes']}  →  {s_on['mean_changes']}")
        print(f"  名单原样复现       {s_off['published_set_prob']:.1%}  →  {s_on['published_set_prob']:.1%}")
        print("  **不下降就是没修对** —— 这是规格 §9-4 的验收判据。")
        return
    _one_regime(cands, n_seeds, refine=refine, q=q)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="真换种子重跑生产的两遍流程，量裁决的实际不稳定度（离线，勿进 CI）")
    ap.add_argument("--seeds", type=int, default=3, help="换几个种子（加算口径每个约 4 分钟）")
    ap.add_argument("--no-refine", action="store_true", help="只跑未加算基线（修前口径）")
    ap.add_argument("--both", action="store_true", help="修前+修后两种口径都跑（规格 §9-4）")
    a = ap.parse_args()
    run(n_seeds=a.seeds, both=a.both, refine=not a.no_refine)
