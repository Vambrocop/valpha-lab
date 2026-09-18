"""裁决的蒙特卡洛稳定性 —— 把"换个种子名单就变"变成可发布的数字（Part B/C · C4a）。

## 这个度量在回答什么

不是"p 还有效吗"，而是
  **「有限次重采样得到的这个裁决，和 B=∞ 的理想裁决一致吗？不一致的风险多大？」**
—— sequential Monte Carlo test 的标准口径（Besag & Clifford 1991；Gandy 2009 的
uniformly bounded resampling risk；多重检验版本 MMCTest）。

做法：只重抽**已经存下的** MC 计数、重跑 `adjudicate`，**不重跑任何自助/置换**。
所以它是纯算术、K=2000 约 1.2s —— 这才是它能天天算、能进 CI 守门的前提
（对比：真换种子重跑 `compute_results` 要 N×2 分钟，只能做离线工具）。

## 为什么不用「离阈值几个标准误」当判据（本文件的反例测试就守这个）

BY 是 **step-up**：一条被拒 ⟺ rank ≤ k，而 k 由**最大**的那个 i 决定 →
低 rank 候选的个体比较 `p_i vs c_i` 根本不是它的约束。而且：
  · 两个估计器在下限附近 SE ≈ p → 该判据在关键区间退化成恒真；
  · `c_i` 在并列组内由**枚举顺序**决定 → 会发布一个取决于候选顺序的数字；
  · 它会把 rank=1(最稳、实测 84% 仍在名单) 的候选永久标成"分辨不了" = 把证据说得比实际**弱**。
所以这里直接**模拟 step-up 本身**。下面 `test_probs_are_invariant_to_candidate_order`
就是针对第二条的回归守门。

hermetic：合成 results + 固定种子，不读 data/、不联网。
"""
import numpy as np
import pytest

import quality_gate as qg
import stats_util as su


def _row(key, fam, x, n, kind, rx=None, powered=True):
    """造一条带原始 MC 计数的候选。rx=None → recent_p 缺失。"""
    # 两族都用**带 +1 平滑**的公式（D6 之后自助也平滑）——
    # 合成 p 与估计器公式脱节的话，整个改判概率判据就在测一个不存在的世界
    _p = lambda k: (2 * (k + 1) / (n + 1)) if kind == "bootstrap" else ((k + 1) / (n + 1))
    p = _p(x)
    rp = None
    mcr = None
    if rx is not None:
        rp = _p(rx)
        mcr = su.mc_meta(rx, n, kind)
    return {"candidate_id": key, "key": key, "family": fam,
            "p": min(p, 1.0), "recent_p": rp, "recent_powered": powered,
            "mc": su.mc_meta(x, n, kind), "mc_recent": mcr}


def _pool(n_noise=40):
    """一个小池子：2 条强(已加算精度)、1 条贴边界、1 条中等、其余噪声。

    强候选刻意用 **n=20000**（= 加算后的精度）而不是 2000：
    D6 的 +1 平滑让最小可达 p 变成 `2/(n+1)`，而 44 条池子的 rank-1 BY 临界值
    `c₁ = q/(m·H_m) ≈ 0.0005` —— 若强候选只有 n=2000，它的下限 0.001 **高于**自己的临界值，
    连"完美"候选都清不过线，`test_a_rock_solid_candidate_has_low_change_prob` 就会假红
    （起草时真踩了：实测 0.38，而真实 148 条池子里 `p5_h1_nasdaq` 只有 15.6%）。
    顺带这样池子里**同时存在两种精度** —— 正是加算落地后的真实状态，比单一精度更有代表性。
    """
    rows = [
        _row("strong_a", "rebound", 0, 20000, "bootstrap", rx=0),
        _row("strong_b", "regime", 0, 20000, "bootstrap", rx=20),
        _row("edge", "calendar", 0, 1000, "permutation", rx=95),      # recent_p≈.096 贴 0.10
        _row("mid", "factor", 30, 2000, "bootstrap", rx=400),
    ]
    rows += [_row(f"noise{i}", "streak_down", 400 + i, 2000, "bootstrap", rx=900)
             for i in range(n_noise)]
    return rows


# ── 基本行为 ────────────────────────────────────────────────────────
def test_returns_probs_for_every_candidate():
    rows = _pool()
    qg.adjudicate(rows, q=0.10)
    probs, s = qg.change_probabilities(rows, q=0.10, K=200)
    assert set(probs) == {r["key"] for r in rows}
    for v in probs.values():
        assert 0.0 <= v["change_prob"] <= 1.0
        assert 0.0 <= v["survive_prob"] <= 1.0
        assert abs(sum(v["verdict_dist"].values()) - 1.0) < 1e-6


def test_summary_shape_and_bounds():
    rows = _pool()
    qg.adjudicate(rows, q=0.10)
    _p, s = qg.change_probabilities(rows, q=0.10, K=200)
    assert s["K"] == 200 and s["seed"] == qg._MC_SEED
    assert s["median_changes"] <= s["p90_changes"] <= s["max_changes"]
    assert 0.0 <= s["published_set_prob"] <= 1.0
    assert s["n_resampled"] == len(rows)


def test_deterministic_for_a_given_seed():
    """产物要可复现（规格 D4：固定种子，抖动靠报出来而不是随机化掩盖）。"""
    rows = _pool()
    qg.adjudicate(rows, q=0.10)
    a, sa = qg.change_probabilities(rows, q=0.10, K=150)
    b, sb = qg.change_probabilities(rows, q=0.10, K=150)
    assert a == b and sa == sb


def test_a_rock_solid_candidate_has_low_change_prob():
    """远离边界的强候选不该被报成"分辨不了" —— 否则就是把证据说得比实际弱。"""
    rows = _pool()
    qg.adjudicate(rows, q=0.10)
    probs, _ = qg.change_probabilities(rows, q=0.10, K=400)
    assert probs["strong_a"]["change_prob"] < 0.25, (
        "rank 最靠前的候选被报成高改判概率 —— 判据把最强的证据说弱了")


def test_a_boundary_candidate_has_high_change_prob():
    """贴着 recent_p 阈值(0.10)的那条必须被报出来 —— 否则度量没抓到该抓的。"""
    rows = _pool()
    qg.adjudicate(rows, q=0.10)
    probs, _ = qg.change_probabilities(rows, q=0.10, K=400)
    assert probs["edge"]["change_prob"] > probs["strong_a"]["change_prob"], (
        "边界候选的改判概率没高于最稳候选 —— 合成数据或判据有问题")


# ── 关键不变性：不许受枚举顺序影响（B2-② 的回归守门）────────────────
def test_probs_are_invariant_to_candidate_order():
    """打乱候选顺序，每条的改判概率必须基本不变。

    这是弃用 `z = |p − c_i| / SE` 判据的核心理由：`c_i = i·q/(m·H_m)` 里的 i 在并列组内
    由**稳定排序的原始下标**决定 → 那个判据会发布一个取决于枚举顺序的数字
    （实测打乱后某条的 c_i 变了一个数量级）。本判据直接模拟 step-up，故天然无此问题。
    """
    rows = _pool()
    qg.adjudicate(rows, q=0.10)
    a, _ = qg.change_probabilities(rows, q=0.10, K=600)

    shuffled = list(rows)
    np.random.default_rng(3).shuffle(shuffled)
    qg.adjudicate(shuffled, q=0.10)
    b, _ = qg.change_probabilities(shuffled, q=0.10, K=600)

    for k in ("strong_a", "strong_b", "edge", "mid"):
        assert abs(a[k]["change_prob"] - b[k]["change_prob"]) < 0.10, (
            f"{k} 的改判概率随枚举顺序变了({a[k]['change_prob']} → {b[k]['change_prob']}) "
            "—— 判据掺进了 rank/c_i")


# ── 退化情形：mc=None 不许被当成 X=0 ────────────────────────────────
def test_missing_counts_are_not_resampled_and_not_fabricated():
    """`mc=None` = 根本没跑过统计（如样本不足，p 硬编码 1.0）→ 不施噪、不编计数。

    若把它当 X=0 重抽，会给一条**从未测过**的候选编出"极显著"的后验，
    那正是 Part A/D10 要防的"把没测说成测了但极显著"。
    """
    rows = _pool(n_noise=10)
    rows.append({"candidate_id": "never_ran", "key": "never_ran", "family": "factor",
                 "p": 1.0, "recent_p": None, "recent_powered": False,
                 "mc": None, "mc_recent": None})
    qg.adjudicate(rows, q=0.10)
    probs, s = qg.change_probabilities(rows, q=0.10, K=200)
    assert s["n_resampled"] == len(rows) - 1, "mc=None 的候选被算进了重抽池"
    assert probs["never_ran"]["change_prob"] == 0.0, (
        "从未跑过统计的候选被施了噪声 —— 等于给'没测'编出一个后验")
    assert probs["never_ran"]["survive_prob"] == 0.0


def test_resample_p_respects_each_estimator_formula():
    """重抽必须按**该估计器自己的**公式重建 p（自助 2X/n、置换 (X+1)/(n+1)）。

    用错公式会让两族的噪声尺度系统性错配，而它们共用一个跨族 BY 池。
    """
    rng = np.random.default_rng(0)
    boots = [qg._resample_p(rng, su.mc_meta(0, 2000, "bootstrap")) for _ in range(400)]
    perms = [qg._resample_p(rng, su.mc_meta(0, 1000, "permutation")) for _ in range(400)]
    # D6 之后两族都带 +1 平滑 → 重抽也**绝不**出现"精确 0"。
    # 断言钉的是**生产的实际契约**：重抽与生产一样把 p 舍入（自助 4 位 / 置换 6 位），
    # 所以下界要用**舍入后**的下限比。拿未舍入的精确值比是拿理想值比生产 ——
    # `round(1/1001, 6) = 0.000999` 本就略低于 1/1001（起草时踩了，同 p_floor 那条）。
    assert min(boots) >= round(2 / 2001, 4) - 1e-12, f"自助重抽跌破了下限: {min(boots)}"
    assert min(perms) >= round(1 / 1001, 6) - 1e-12, f"置换重抽跌破了下限: {min(perms)}"
    assert min(boots) > 0 and min(perms) > 0, "又出现了「精确 0」"
    assert qg._resample_p(rng, None) is None


def test_x_zero_has_the_widest_posterior():
    """X=0（下限组）的后验必须是最宽的 —— 那正是"分辨不了"该有的不确定度。

    若用 SE=sqrt(2p/B) 判据，X=0 会给出 SE=0（"精确到 0"的假象），方向恰好相反。
    """
    rng = np.random.default_rng(1)
    at_floor = [qg._resample_p(rng, su.mc_meta(0, 2000, "bootstrap")) for _ in range(800)]
    away = [qg._resample_p(rng, su.mc_meta(400, 2000, "bootstrap")) for _ in range(800)]
    assert np.std(at_floor) > 0, "X=0 的重抽没有任何离散度 —— 又编出了'精确到 0'"
    # 相对不确定度：X=0 处应当远大于远离下限处
    assert np.std(at_floor) / (np.mean(at_floor) + 1e-9) > np.std(away) / np.mean(away)


# ── 接线：产物里必须有这些字段 ───────────────────────────────────────
def test_pipeline_emits_stability_fields():
    from pathlib import Path
    import autodiscovery as ad
    src = Path(ad.__file__).read_text(encoding="utf-8")
    assert "change_probabilities" in src, "run_all 没接稳定性度量"
    assert '"mc_change_prob"' in src and '"mc_survive_prob"' in src, "逐条概率没进产物"
    assert '"mc_stability": mc_sum' in src, "整体摘要没进产物"
    assert "mean_changes" in src


def test_caveat_discloses_the_boundary_uncertainty():
    """总括 caveat 必须说出"换个种子平均几条会变" —— 只在逐条字段里藏着不算披露。"""
    from pathlib import Path
    import autodiscovery as ad
    src = Path(ad.__file__).read_text(encoding="utf-8")
    i = src.index('"caveat"')
    body = src[i:i + 900]
    assert "边界不确定" in body
    assert "mean_changes" in body and "published_set_prob" in body, (
        "caveat 没把'平均几条会变/名单原样复现的概率'写进去")


# ── 观察台（公开面板）：概率必须逐条可见 ──────────────────────────────
def test_survivors_deck_carries_the_probability():
    """存活观察台是最面向用户的那张表 —— 概率必须带到行上，不能只留在 autodiscovery.json 里。"""
    from pathlib import Path
    import survivors_live as sl
    src = Path(sl.__file__).read_text(encoding="utf-8")
    assert '"mc_survive_prob": c.get("mc_survive_prob")' in src
    assert '"mc_change_prob": c.get("mc_change_prob")' in src


def test_low_probability_gets_a_plain_language_warning():
    """概率低的要有人话提示，而不是只给一个数字让读者自己判断"36% 算高还是低"。"""
    from pathlib import Path
    import survivors_live as sl
    src = Path(sl.__file__).read_text(encoding="utf-8")
    i = src.index("mc_survive_prob")
    body = src[i:i + 1200]
    assert "0.50" in body, "没有触发阈值 —— 要么人人喊狼，要么一条不报"
    assert "蒙特卡洛边界不稳" in body
    assert "别当成确定结论" in body, "提示里没有『该怎么看』，只报数字等于没解释"
    assert "更可能不在" in body, "只说'不稳'没说清严重程度;<50% 的含义是它更可能不在名单上"
    # 校准：阈值不许放宽到让多数存活者都挂警告（"警告滥发等于没有警告"）
    assert "0.70" not in body, "阈值又放宽了 —— 线上 7 条里会有 4 条挂警告"


def test_composite_deck_renders_the_probability_bilingually():
    """公开面板要中英双语（站点有境内访客 + 英文模式）。"""
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "web" / "composite.html").read_text(encoding="utf-8")
    assert "mc_survive_prob" in html, "观察台没渲染概率"
    i = html.index("s.mc_survive_prob==null")
    body = html[i:i + 700]
    assert "换个随机种子" in body and "chance this stays on the list" in body, "概率展示缺双语"
    assert "var(--amber)" in body, "低概率没有视觉区分 —— 全一个颜色等于没标"


def test_discoveries_page_never_prints_a_floor_p_as_exact():
    """`p = 0.0000` 这种写法必须消失：它把"低于分辨下限"说成了"极显著"。"""
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "web" / "discoveries.html").read_text(encoding="utf-8")
    assert "mc.p_at_floor" in html, "p 的格式化器没看 p_at_floor —— 下限仍会被显示成精确值"
    i = html.index("const pp=(v,mc)=>")
    body = html[i:i + 600]
    assert "p_floor" in body and "≤" in body, "下限没显示成 ≤ 形式"
    # 调用处必须把 mc 传进去,否则格式化器形同虚设
    assert "pp(c.p,c.mc)" in html and "pp(c.recent_p,c.mc_recent)" in html, (
        "格式化器加了参数但调用处没传 mc —— 等于没改")


def test_discoveries_new_i18n_keys_are_bilingual():
    """新增文案必须中英齐全 —— 英文模式下漏一条就是半个中文页面。"""
    import re
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "web" / "discoveries.html").read_text(encoding="utf-8")
    for key in ("dStab", "dStabSurv", "dStabChg", "dFloor"):
        m = re.search(key + r":\{zh:\"([^\"]+)\",en:\"([^\"]+)\"\}", html)
        assert m, f"{key} 不是 {{zh, en}} 两列（英文模式会露出中文或 undefined）"
        assert m.group(1) and m.group(2)
        assert not re.search(r"[一-龥]", m.group(2)), f"{key} 的英文里还有中文: {m.group(2)!r}"


def test_deck_caveat_also_states_the_list_level_uncertainty():
    """观察台自己的 caveat 也要说 —— 它和 autodiscovery.json 是两份 caveat，
    而页面显示的是**前者**。只在逐条提示里给概率，读者仍会把这张表当成一份确定的清单。"""
    from pathlib import Path
    import survivors_live as sl
    src = Path(sl.__file__).read_text(encoding="utf-8")
    i = src.index('"caveat"')
    body = src[i:i + 1400]
    assert "这张名单本身有边界不确定性" in body
    assert "mc_mean" in body and "mc_set" in body, "没把实测数字带进 caveat"
    assert "if mc_mean is not None" in body, "老产物缺字段时会崩 —— 要静默省略而不是阻断"


def test_deck_consumes_stability_without_recomputing():
    """观察台只**消费** autodiscovery 算好的摘要，绝不自己重算一遍（单一真相源）。"""
    from pathlib import Path
    import survivors_live as sl
    src = Path(sl.__file__).read_text(encoding="utf-8")
    assert 'ad.get("mc_stability")' in src
    assert "change_probabilities" not in src, (
        "观察台自己调了 change_probabilities —— 两处各算一次迟早漂移，应只读 autodiscovery 的结果")


# ── 加算（Part B pass-2）──────────────────────────────────────────────
def test_duplicate_keys_raise_instead_of_silently_dropping():
    """返回按 `key` 索引 → key 重复会**静默丢掉**一个候选，而它会拿到别人的改判概率。

    这种错不报、只让数字悄悄失真。今天 148 个 key 全不重复，这道断言是给将来的保险。
    """
    rows = [{"key": "dup", "candidate_id": "1", "family": "x", "p": 0.5},
            {"key": "dup", "candidate_id": "2", "family": "x", "p": 0.5}]
    with pytest.raises(ValueError, match="key 重复"):
        qg.change_probabilities(rows, K=2)


def test_boost_scales_the_estimator_n():
    """加算必须真的把 B / n_perm 放大 —— 否则"加算"只是改了个标签。"""
    import autodiscovery as ad
    import candidate_space as cs
    cands = cs.enumerate_candidates()
    one = [c for c in cands if c["key"] == "september_sp500"]
    assert one, "找不到基准候选，候选池变了?"
    base = ad.compute_results(one)[0]
    up = ad.compute_results(one, boosts={one[0]["candidate_id"]: ad.REFINE_FACTOR})[0]
    assert up["mc"]["mc_n"] == base["mc"]["mc_n"] * ad.REFINE_FACTOR, (
        f"boost 没放大 n：{base['mc']['mc_n']} → {up['mc']['mc_n']}")
    assert up["mc"]["p_floor"] < base["mc"]["p_floor"], "加算后分辨下限没变低"


def test_adopt_pass2_takes_the_worse_p_not_the_better():
    """**D9 的行为测试**：给 pass-2 一个更大(更不显著)的 p，必须采纳那个更大的。

    D9 是规格里标明"最容易被顺手优化掉"的一条。此前只有源码禁词扫描守它，而
    独立审实现（B2）实测出 **4 种**合理的违规写法全都骗过了文本匹配：
      · 海象算子取更显著者（保留 `by_id.get(`）
      · `sorted([pass2, pass1], key=p)[0]`
      · lambda 三元：pass-2 更差就丢掉
      · `min(r["p"], by_id.get(...)["p"])`  ← 禁词表只拦变量恰好叫 p/p1/p2 的写法
    所以撑住这条红线的必须是**行为**断言，文本扫描只能当第二道网。
    """
    import autodiscovery as ad
    p1 = [{"candidate_id": "x", "key": "k", "p": 0.001, "mc": {"mc_x": 1, "mc_n": 2000}}]
    p2 = [{"candidate_id": "x", "key": "k", "p": 0.400, "mc": {"mc_x": 400, "mc_n": 20000}}]
    got = ad.adopt_pass2(p1, p2)
    assert got[0]["p"] == 0.400, (
        f"采纳了 {got[0]['p']} 而不是 pass-2 的 0.400 —— 有人在取两次里更显著的那个（D9/S7 红线）")
    assert got[0]["mc"]["mc_n"] == 20000, "采纳的不是 pass-2 的计数"


def test_adopt_pass2_keeps_candidates_that_were_not_refined():
    import autodiscovery as ad
    p1 = [{"candidate_id": "a", "key": "ka", "p": 0.5, "mc": {"mc_x": 500, "mc_n": 2000}},
          {"candidate_id": "b", "key": "kb", "p": 0.001, "mc": {"mc_x": 1, "mc_n": 2000}}]
    p2 = [{"candidate_id": "b", "key": "kb", "p": 0.002, "mc": {"mc_x": 20, "mc_n": 20000}}]
    got = {r["candidate_id"]: r for r in ad.adopt_pass2(p1, p2)}
    assert got["a"]["p"] == 0.5 and got["b"]["p"] == 0.002


def test_adopt_pass2_refuses_a_degraded_pass2():
    """pass-1 有 MC 计数、pass-2 没有 → 无条件采纳会把一条好结果静默降级成 inconclusive。

    拒绝退化**不违反** D9（不是取更优的 p，是不接受更差的**数据**）。审查 S6。
    """
    import autodiscovery as ad
    p1 = [{"candidate_id": "x", "key": "k", "p": 0.001, "mc": {"mc_x": 1, "mc_n": 2000}}]
    degraded = [{"candidate_id": "x", "key": "k", "p": 1.0, "recent_powered": False, "mc": None}]
    with pytest.raises(ValueError, match="加算退化"):
        ad.adopt_pass2(p1, degraded)


def test_adopt_pass2_allows_both_missing_mc():
    """两边都没跑过统计 → 不算退化，照常采纳 pass-2。"""
    import autodiscovery as ad
    p1 = [{"candidate_id": "x", "key": "k", "p": 1.0, "mc": None}]
    p2 = [{"candidate_id": "x", "key": "k", "p": 1.0, "mc": None}]
    assert ad.adopt_pass2(p1, p2)[0]["p"] == 1.0


def test_two_pass_flow_uses_the_extracted_adopter():
    """就地写采纳逻辑就只能靠禁词扫描守 —— 那种守门实测挡不住任何合理的违规写法。

    采纳发生在共享的 `resolve_candidates` 里（B3 之后生产与离线工具共用它）。
    """
    import inspect
    import autodiscovery as ad
    src = inspect.getsource(ad.resolve_candidates)
    assert "adopt_pass2(results, boosted)" in src, (
        "两遍流程没走抽出来的 adopt_pass2 —— 那条红线就又只剩文本扫描了")
    # 且就地不许再出现比较式的采纳
    code = " ".join(ln.split("#", 1)[0] for ln in src.splitlines())
    for bad in ("min(", "max(", "sorted("):
        assert bad not in code, f"两遍流程里出现 {bad!r} —— 疑似取优（D9/S7 红线）"


def test_unresolved_reason_distinguishes_refined_from_not():
    """加算会挪动 FDR 阈值 → 一条**没被加算**的候选也可能变不稳。
    那时说"加算到 10× 后仍…"是假话，文案必须分开。"""
    from pathlib import Path
    import autodiscovery as ad
    src = Path(ad.__file__).read_text(encoding="utf-8")
    i = src.index("mc_unresolved_reason")
    body = src[i - 400:i + 1200]
    assert 'if r["mc_refined"]' in body, "reason 没按是否加算分支 —— 会对未加算的候选说假话"
    assert "未被加算" in body


def test_refine_selection_is_direction_blind():
    """D1/D2：加算的触发条件只看改判概率，**不看**结论方向、也不挑。"""
    from pathlib import Path
    import autodiscovery as ad
    src = Path(ad.__file__).read_text(encoding="utf-8")
    i = src.index("refine_ids = {")
    # 切片**必须带起始位置**：不带的话该串若将来出现在 `refine_ids = {` 之前，
    # 切片会变空、整条测试静默空过（审查 N1）。
    sel = src[i:src.index("if refine_ids:", i)]
    assert "change_prob" in sel
    for bad in ("survive", "verdict", "full_sign", "diff", "方向"):
        assert bad not in sel, f"选加算集时看了 {bad!r} —— 触发条件掺进结论方向 = 自动化 p-hacking"


# ── Part D：守门不变式 ────────────────────────────────────────────────
# 「每条裁决要么已分辨、要么已标注」。二者皆非 = 一个悄悄落在 MC 噪声里的裁决 ——
# 那正是本规格要消灭的东西。不变式逻辑在这里 hermetic 测；
# **真产物**的检查在 `verify_output.py` 里（pytest 拿不到真产物，要跑 3 分钟流水线）。
def _row_audit(key, *, powered=True, mc=True, cp=0.02, unres=False, reason="因为…"):
    return {"key": key, "recent_powered": powered,
            "mc": {"mc_x": 1, "mc_n": 2000} if mc else None,
            "mc_change_prob": cp, "mc_unresolved": unres,
            "mc_unresolved_reason": (reason if unres else None)}


def test_audit_passes_when_everything_is_resolved_or_labelled():
    rows = [_row_audit("ok_low", cp=0.02),
            _row_audit("ok_labelled", cp=0.40, unres=True)]
    assert qg.unresolved_audit(rows, 0.10) == []


def test_audit_catches_a_verdict_sitting_in_the_noise_unlabelled():
    """这条就是整个 Part D 存在的理由。"""
    rows = [_row_audit("sneaky", cp=0.30, unres=False)]
    bad = qg.unresolved_audit(rows, 0.10)
    assert len(bad) == 1 and bad[0][0] == "sneaky"
    assert "没标" in bad[0][2]


def test_audit_catches_missing_measurement():
    """度量没接上 = 守门形同虚设，必须报出来而不是当"通过"。"""
    rows = [_row_audit("nomeasure", cp=None)]
    bad = qg.unresolved_audit(rows, 0.10)
    assert len(bad) == 1 and "缺 mc_change_prob" in bad[0][2]


def test_audit_requires_a_human_readable_reason():
    """只给布尔不算披露 —— 读者需要知道"为什么分辨不了"。"""
    rows = [{"key": "nore", "recent_powered": True, "mc": {"mc_x": 1, "mc_n": 2000},
             "mc_change_prob": 0.4, "mc_unresolved": True, "mc_unresolved_reason": None}]
    bad = qg.unresolved_audit(rows, 0.10)
    assert len(bad) == 1 and "没给人话原因" in bad[0][2]


def test_audit_exempts_unpowered_candidates_by_the_right_field():
    """`recent_powered=False` 在 adjudicate 里短路成 inconclusive → 裁决不依赖 p，豁免。

    **不许用 `recent_p is None` 当代理**：线上实测两者解耦
    （6 条未 powered、其中 2 条 recent_p 非 None；另有 4 条 recent_p 为 None）。
    用错代理会让该豁免的没豁免、直接把守门顶到 S5。
    """
    # 未 powered 但 recent_p 有值 → 仍应豁免
    r = _row_audit("unpowered", powered=False, cp=0.9)
    r["recent_p"] = 0.03
    assert qg.unresolved_audit([r], 0.10) == []
    # powered 且 recent_p 为 None → **不**豁免（代理法会错放它过关）
    r2 = _row_audit("powered_no_recent", powered=True, cp=0.9)
    r2["recent_p"] = None
    assert len(qg.unresolved_audit([r2], 0.10)) == 1, (
        "用 recent_p is None 当豁免代理了? 那会放过真正落在噪声里的裁决")


def test_audit_exempts_candidates_that_never_ran_statistics():
    """`mc=None` = 根本没跑过统计（样本不足，p 硬编码 1.0）→ 无噪声可言。"""
    assert qg.unresolved_audit([_row_audit("neverran", mc=False, cp=None)], 0.10) == []


def test_verify_output_actually_calls_the_audit():
    """守门必须挂在**真产物**的检查里，否则它只是个没人调的函数。"""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "scripts" / "verify_output.py").read_text(encoding="utf-8")
    assert "unresolved_audit" in src, "verify_output 没调 MC 守门"
    assert "n_refined" in src and "n_unresolved" in src, "S2/S5 的计数没在流水线里亮出来"
    i = src.index("unresolved_audit")
    body = src[i - 900:i + 900]
    assert "旧产物" in body, "老产物缺字段时应优雅跳过而不是把流水线干红"


def test_refine_set_is_exactly_the_over_threshold_set():
    """D2：带内**全部**加算、一条不挑 —— 断言集合**相等**，不是子集。

    审查 S5 用内存变异实测：原先那条只用 `survive_prob` 挑会被抓到，但
    「只加算 p<0.01 的那半」「只加算前 5 条」「用 `reason==''` 当 survive 的代理」
    **三种挑法全部绿过**。所以必须钉住集合相等。
    """
    import autodiscovery as ad
    rows = _pool(n_noise=30)
    qg.adjudicate(rows, q=0.10)
    probs, _ = qg.change_probabilities(rows, q=0.10, K=400)
    expect = {r["candidate_id"] for r in rows
              if (probs[r["key"]]["change_prob"] or 0) > ad.P_REFINE}
    # 复刻 run_all 的选取表达式（同一份 probs → 必须得到同一个集合）
    got = {r["candidate_id"] for r in rows
           if (probs.get(r["key"], {}).get("change_prob") or 0) > ad.P_REFINE}
    assert got == expect, "选取不是「恰好等于超阈集合」"
    # 源码层面：选取表达式里只许出现 change_prob 这一个判据
    from pathlib import Path
    src = Path(ad.__file__).read_text(encoding="utf-8")
    k = src.index("refine_ids = {")
    sel = src[k:src.index("if refine_ids:", k)]          # 带起始位置，防切片空过(审查 N1)
    assert sel.count("change_prob") == 1 and ">" in sel
    for bad in ("survive", "verdict", "full_sign", "[:", "sorted("):
        assert bad not in sel, f"选取里出现了 {bad!r} —— 疑似挑选或排序后截取（违反 D2）"


# ── T13：Part C 的「分辨不了」必须有前端落点（审查 S4：此前零消费者）─────
def test_unresolved_has_frontend_consumers_on_the_dead_side():
    """规格 §10 明写 C2+C3 含 Part C（标注 + **对称披露**）同批发布，§8 T13 要求
    dead/faded 的 `mc_unresolved` 在前端有落点。

    审实现 S4 实测：`mc_unresolved` / `mc_unresolved_reason` 在 web/*.html 与
    survivors_live 里**零消费者**，唯一读它的是 verify_output 自己 ——
    也就是说这套方法**最值钱的那句输出**（"本质上分辨不了，不是算得不够多"）
    没有任何读者看得到。
    """
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "web" / "discoveries.html").read_text(encoding="utf-8")
    assert "mc_unresolved" in html, "坟场/弹窗没接 mc_unresolved"
    assert "mc_unresolved_reason" in html, "只标布尔、不给原因 = 只说不稳、不说为什么"
    assert "dUnres" in html and "dUnresHint" in html, "缺 i18n 键"


def test_unresolved_wording_says_it_is_inherent_not_under_computed():
    """措辞必须说清「不是算得不够多」—— 否则读者会以为再多跑几次就有结论了。"""
    import re
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "web" / "discoveries.html").read_text(encoding="utf-8")
    m = re.search(r'dUnresHint:\{zh:"([^"]+)",en:"([^"]+)"\}', html)
    assert m, "dUnresHint 不是 {zh,en} 两列"
    assert "本质上" in m.group(1) and "不是算得不够多" in m.group(1)
    assert not re.search(r"[一-龥]", m.group(2)), f"英文里有中文: {m.group(2)!r}"
    assert "inherently unresolvable" in m.group(2)


def test_survivors_deck_carries_unresolved_too():
    """对称披露：今天那 2 条都是 dead，但存活者将来也可能被标上。"""
    from pathlib import Path
    import survivors_live as sl
    src = Path(sl.__file__).read_text(encoding="utf-8")
    assert '"mc_unresolved": bool(c.get("mc_unresolved"))' in src
    assert "加算后仍分辨不了" in src, "存活一侧没有人话提示"
