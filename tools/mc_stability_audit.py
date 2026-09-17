"""mc_stability_audit.py — 真换种子重跑 compute_results，量裁决的实际不稳定度。

## 为什么需要它（以及为什么它不能进 CI）

`quality_gate.change_probabilities`（进流水线的那个）是**模型化**的近似：
从已存下的 MC 计数按 `θ*~Beta(X+½,n−X+½)`、`X*~Binom(n,θ*)` 重抽，重跑 `adjudicate`。
纯算术、K=2000 约 1.2s —— 所以它能天天算、能进 CI 守门。

**但它假设了一个噪声模型。** 本工具不假设：它真的换随机种子、真的重跑
`compute_results`（全部自助/置换重算），直接数有多少条裁决变了。
两者若显著不一致 → **说明那个模型错了**，这才是本工具的用处。

代价：每个种子约 2 分钟（148 候选全量重算）。N=5 → 约 10 分钟。
**所以它是离线工具，绝不进 CI。**

## ⚠ 这条工具的前身是个假绿

SPEC_MC_RESOLUTION R1 把它写成「按 N 个种子重跑 `adjudicate`」——
而 `adjudicate` **没有种子参数、也不算 p**，它只消费算好的 p。
按字面实现会 N 次得到同一个答案、**恒报 0 条改判**，然后"修复后显著下降"看起来完美达成。
独立审规格（B8）抓出了这一点。教训同 CLAUDE.md 的 `fe8af0a`：
**「我跑了一次是绿的」≠ 验证过，还得问它到底在测什么。**

## 用法

    $env:PYTHONUTF8='1'; py tools/mc_stability_audit.py [--seeds 5]

输出：每个种子的改判条数 + 逐条改判频率 + 与模型化估计的对照。
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
from quality_gate import adjudicate, change_probabilities   # noqa: E402


def _patch_seeds(offset):
    """把两个估计器的种子整体挪 offset。

    生产代码里自助的种子是 `block_bootstrap_diff` 的默认参数（永远 42）、
    置换的种子来自 `autodiscovery._seed_for(cid)`。两者都要挪，否则只换了一半。
    """
    orig_bbd, orig_seed_for = wf.block_bootstrap_diff, ad._seed_for

    def bbd(sel, y, block=20, B=None, seed=42):
        return orig_bbd(sel, y, block=block, B=B, seed=seed + offset)

    def seed_for(cid):
        return [x + offset for x in orig_seed_for(cid)]

    wf.block_bootstrap_diff = bbd
    ad.block_bootstrap_diff = bbd          # autodiscovery 是 from-import，要单独打
    import factor_pruning as fp
    fp.block_bootstrap_diff = bbd
    ad._seed_for = seed_for
    return lambda: (setattr(wf, "block_bootstrap_diff", orig_bbd),
                    setattr(ad, "block_bootstrap_diff", orig_bbd),
                    setattr(fp, "block_bootstrap_diff", orig_bbd),
                    setattr(ad, "_seed_for", orig_seed_for))


def run(n_seeds=5, q=0.10):
    cands = cs.enumerate_candidates()
    print(f"[基准] 生产种子跑一遍（{len(cands)} 候选）…")
    t = time.time()
    base_rows = ad.compute_results(cands)
    adjudicate(base_rows, q=q, expect_n=cs.N_DECLARED)
    per_run = time.time() - t
    base = {r["key"]: r["verdict"] for r in base_rows}
    model_probs, model_sum = change_probabilities(base_rows, q=q)
    print(f"[基准] 耗时 {per_run:.0f}s；模型化估计：平均改判 {model_sum['mean_changes']} 条"
          f"、名单原样复现 {model_sum['published_set_prob']:.1%}")
    print(f"[计划] 再跑 {n_seeds} 个种子 ≈ {per_run * n_seeds / 60:.0f} 分钟\n")

    flips = collections.Counter()
    counts = []
    for k in range(1, n_seeds + 1):
        undo = _patch_seeds(offset=k * 1000)
        t = time.time()
        rows = ad.compute_results(cands)
        adjudicate(rows, q=q, expect_n=cs.N_DECLARED)
        undo()
        v = {r["key"]: r["verdict"] for r in rows}
        chg = [key for key in base if base[key] != v[key]]
        for key in chg:
            flips[key] += 1
        counts.append(len(chg))
        print(f"  种子 +{k*1000}: 改判 {len(chg)} 条 ({time.time()-t:.0f}s)"
              + (f" → {chg[:5]}" if chg else ""))

    print(f"\n=== 实测（真换种子、真重跑）===")
    print(f"改判条数: 均值 {sum(counts)/len(counts):.2f} / 最大 {max(counts)} / 各次 {counts}")
    print(f"模型化估计的均值: {model_sum['mean_changes']}")
    gap = abs(sum(counts) / len(counts) - model_sum["mean_changes"])
    print(f"差距 {gap:.2f} 条 —— "
          + ("模型与实测一致，快守门可信" if gap <= 1.5 else
             "⚠ **模型与实测差得多**：change_probabilities 的噪声模型可能不对，先查它再信守门"))
    if flips:
        print(f"\n逐条改判频率（{n_seeds} 个种子）：")
        for key, n in flips.most_common(15):
            mp = (model_probs.get(key) or {}).get("change_prob")
            print(f"    {key[:40]:40s} 实测 {n}/{n_seeds}"
                  + (f"  模型 {mp:.0%}" if mp is not None else ""))
    else:
        print("\n没有任何裁决随种子变化 —— 若这是加算上线之后，说明修复生效了。")
    return counts, flips


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="真换种子重跑，量裁决的实际不稳定度（离线，勿进 CI）")
    ap.add_argument("--seeds", type=int, default=5, help="换几个种子（每个约 2 分钟）")
    a = ap.parse_args()
    run(n_seeds=a.seeds)
