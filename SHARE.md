# 分享文案（直接复制可用）

> 角度：不是"我的信号很准"，而是"我诚实地分清了真规律 vs 幻觉"。
> 量化社区最吃这套，也最会挑刺——本项目的方法论扛得住。

---

## Show HN（英文，HN 用）

**Show HN: I built a stock-signal site, then proved most of my own signals have no edge**

Valpha Lab started as "daily entry signals for US indices (Nasdaq/S&P)." Then I did the
honest thing most signal projects skip: I rigorously tested whether the signals actually
work out-of-sample — walk-forward with **block bootstrap** (overlapping-window p-values are
optimistic), a **2024–2026 holdout that never touched training**, and a **benchmark
scorecard that pits every model against its honest baseline** (direction vs base rate, the
vol model vs just-read-VIX, the paper strategies vs buy-and-hold).

Result: the combined Bayesian direction signal **does not beat the base rate** out of sample
(Tier≥4 avg −0.3pp). A logistic-regression replacement did *worse*. I show this instead of
hiding it.

But the data is far from patternless — the site separates what's **real and usable**
(volatility is predictable, AUC≈0.67; the overnight anomaly, +11.2% vs −2.3% intraday;
correlation regimes; BTC momentum leading Nasdaq) from what's a **mirage** (short-term
direction, which an efficient market prices away).

Everything is static (GitHub Pages), data auto-refreshes via Actions, and there's an
append-only prediction log so I can't quietly rewrite history.

Live: https://vambrocop.github.io/valpha-lab/ · Code: https://github.com/Vambrocop/valpha-lab

---

## r/algotrading（英文）

**Title:** I built signals, then benchmarked every one against its honest baseline — most have no OOS edge, and I show it

**Body:**
Most signal projects stop at an in-sample backtest. I tried to do the opposite and would
genuinely welcome a teardown.

What I did:
- Walk-forward folds; **block bootstrap** instead of t-tests (overlapping 20-day forward
  windows make t p-values ~an order of magnitude too optimistic).
- A **2024–2026 holdout** that never entered any training fold.
- A **benchmark scorecard**: every model vs a *hard* baseline — direction vs the base rate
  (not 50%), the vol model vs simply ranking by today's VIX, paper strategies vs buy-and-hold.

Findings:
- Short-term **direction**: combined Bayesian signal AUC ≈ 0.45 OOS — no edge. Logistic
  regression was worse. Factor autopsy: of 15 factors, only BTC 20-day momentum survives
  OOS, and even that is regime-dependent (2017–2021 crypto bull).
- **Volatility** is genuinely predictable (AUC ≈ 0.67) — but a 12-feature GBM barely beats
  just reading VIX (+0.002), i.e. the market already prices it.
- Real, usable structure elsewhere: overnight anomaly, correlation regimes, mean reversion.

Honest negative results + the methodology to get them. Tear it apart:
https://github.com/Vambrocop/valpha-lab

---

## 中文（V2EX / 雪球 / 知乎 等）

**标题：我做了个美股信号站，然后用严格方法证明自己的信号样本外没用——并把它公开**

大多数信号项目止步于样本内回测。我反着来：用 walk-forward 块自助（重叠窗口的 t 检验 p 值
偏乐观约一个数量级）、2024–2026 从未参与训练的干净保留集、以及"每个模型 vs 硬基线"的
benchmark 记分卡，老实测了一遍。

结论：综合贝叶斯**方向**信号样本外打不赢基率（AUC≈0.45），换逻辑回归更差；15 个因子里只有
BTC 20 日动量站得住、还 regime 依赖。但**波动率确实可测**（AUC≈0.67，只是被 VIX 提前定价了）。
其余真规律（隔夜异象、相关性体制、均值回归）也都在。

诚实的负结果 + 拿到它的方法论。欢迎挑刺：
- 站点 https://vambrocop.github.io/valpha-lab/
- 代码 https://github.com/Vambrocop/valpha-lab

---

## 发帖小贴士

- **最佳时间**：HN/Reddit 用美东上午（你阿德莱德晚上）。
- **预期**：会有人质疑"那你这站还有什么用"——回答就是 README 的"真规律 vs 幻觉"：用来管风险、择波动窗口、理解结构，而不是预测短期涨跌。
- **扛得住**：每个结论都有块自助/保留集/基线对照，比多数能上 r/algotrading 的项目更经得起审。
