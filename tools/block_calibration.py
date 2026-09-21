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

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "market-analysis" / "scripts"))
import walk_forward as wf                                     # noqa: E402


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


def main():
    ap = argparse.ArgumentParser(description="量块自助这把尺子本身的实际水平（离线）")
    ap.add_argument("--controls", action="store_true", help="跑答案已知的控制组（先验量具）")
    ap.add_argument("--sweep", action="store_true", help="跑 拒真率 vs 块数 曲线")
    ap.add_argument("--R", type=int, default=600, help="每个配置重复多少次（默认 600）")
    ap.add_argument("--B", type=int, default=400, help="每次自助多少轮（默认 400）")
    ap.add_argument("--alpha", type=float, default=0.10, help="名义水平（默认 0.10）")
    a = ap.parse_args()
    if not (a.controls or a.sweep):
        ap.error("至少选一个：--controls / --sweep")
    if a.controls:
        controls(a.R, a.B, a.alpha)
    if a.sweep:
        sweep(a.R, a.B, a.alpha)
    print("\n✓ 读法：✓=与名义同量级；✗=反保守；✗✗=拒真率超名义 3 倍（不可用）")


if __name__ == "__main__":
    main()
