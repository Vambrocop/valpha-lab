"""F2·P2：量具没校准的候选，记「不可判」而不是给一个四位小数的 p。

## 为什么光放大 block 不够

F2 的 P1 给状态型 sel 补上了 block 放大。旋转 null 实测（R=400~500，SE≈0.02）说：
放大在**全段**上确实把校准修好了（`NASDAQ_above_ma200` .164→.120、
`NASDAQ_mom20_pos` .128→.100、`nasdaq_low_vol` .164→.120），
但在**现代段**（n≈2009）上，换哪个块长都救不回来：

    因子(现代段)            blk20   blk40   blk80  blk164
    BTC_mom20_pos           .235    .210    .203    .233
    BTC_above_ma200         .355    .315    .305    .302
    NASDAQ_above_ma200      .300    .268    .247    .265

名义 0.10。**两头都反保守**：块太短→低估序列相关；块数太少→重采样退化。
2009 个观测配 143 天的依赖长度，这两个条件同时满足不了 ——
这不是参数没调好，是这段样本里独立信息本来就只有十几段。

而**裁决用的正是现代段**（存活线 q=0.10 压在 `recent_p` 上）。
所以对这些候选，诚实的输出是「不可判」，不是一个 p。

## 判据不是拍的

`MAX_LEVEL_RATIO = 1.5`，与 `walk_forward.MIN_BLOCKS` **同一把尺子**
（那里也是取"最好情况拒真率首次回到 ≤1.5 倍名义"的位置）。

## 它为什么不算 researcher-DoF

旋转 null 把真关联**按构造**破坏掉 —— 测量过程根本碰不到真实的关联强度。
它量的是尺子，不是被测物。所以这张表可以冻结在仓库里。

hermetic：全部用构造的表，不读真产物、不联网。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import block_levels as bl              # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _table(**rows):
    return {"nominal_alpha": 0.10, "max_level_ratio": 1.5, "rows": rows}


def _row(level, window="现代段"):
    return {"level": level, "window": window, "family": "factor", "n": 2009}


# ── 门的行为 ────────────────────────────────────────────────────────────────

def test_level_above_threshold_is_not_ok():
    g = bl.gate("x", table=_table(**{"x|现代段": _row(0.186)}))
    assert g["measured"] and not g["ok"]
    assert g["level"] == 0.186 and g["window"] == "现代段"


def test_level_below_threshold_is_ok():
    g = bl.gate("x", table=_table(**{"x|现代段": _row(0.120)}))
    assert g["measured"] and g["ok"]


def test_threshold_boundary_is_inclusive():
    """恰好 1.5×名义 放行，超一点就拦 —— 边界别含糊。"""
    assert bl.gate("x", table=_table(**{"x|全段": _row(0.150, "全段")}))["ok"]
    assert not bl.gate("x", table=_table(**{"x|全段": _row(0.151, "全段")}))["ok"]


def test_the_worst_window_decides():
    """任一窗口不合格 → 整条不下结论。`golden_cross_sp500` 正是全段 .144 合格、
    现代段 .168 不合格 —— 只看全段会漏掉它。"""
    g = bl.gate("x", table=_table(**{"x|全段": _row(0.144, "全段"),
                               "x|现代段": _row(0.168)}))
    assert not g["ok"] and g["window"] == "现代段" and g["level"] == 0.168


def test_unmeasured_candidate_is_not_blocked_but_is_flagged():
    """表里没有 → **不拦**（这道门只该让我们说得更少），但必须记成"没测过"，
    好让 verify_output 对「存活却没测过」报红。"""
    g = bl.gate("never_seen", table=_table(**{"x|全段": _row(0.9, "全段")}))
    assert g["ok"] is True and g["measured"] is False


def test_key_prefix_match_is_exact_not_substring():
    """`BTC_mom20_pos` 不能被 `BTC_mom20_pos_extra` 的行误伤（反之亦然）。"""
    t = _table(**{"BTC_mom20_pos_extra|全段": _row(0.9, "全段")})
    assert bl.gate("BTC_mom20_pos", table=t)["measured"] is False
    assert bl.gate("BTC_mom20_pos_extra", table=t)["ok"] is False


def test_rows_refused_by_min_blocks_do_not_count_as_a_failure():
    """被 MIN_BLOCKS 挡住的窗口 level=None：那种窗口本来就没有 p，不该再算一次不合格。"""
    g = bl.gate("x", table=_table(**{"x|现代段": {"level": None, "window": "现代段"}}))
    assert g["ok"] and g["level"] is None


def test_missing_file_yields_an_empty_table_not_a_crash():
    bl.clear_cache()
    try:
        t = bl.load(ROOT / "data" / "__no_such_file__.json")
        assert t["rows"] == {} and t.get("missing_file")
    finally:
        bl.clear_cache()


# ── 人话理由：别只说"不可判"，要说清会错多少 ────────────────────────────────

def test_reason_states_the_error_rate_in_plain_language():
    g = bl.gate("x", table=_table(**{"x|现代段": _row(0.186)}))
    r = bl.reason(g)
    assert "5 次里错判 1 次" in r, r          # round(1/0.186) = 5
    assert "现代段" in r and "10 次里 1 次" in r


def test_reason_for_an_unmeasured_candidate_says_so():
    g = bl.gate("never", table=_table())
    assert "没有做过校准测量" in bl.reason(g)


# ── 冻结表本身：它在仓库里,得是自洽的 ────────────────────────────────────────

def test_the_committed_table_is_well_formed():
    bl.clear_cache()
    t = bl.load()
    assert not t.get("missing_file"), "冻结表不见了 —— 生产会退化成谁都不拦"
    assert t["rows"], "表是空的"
    assert 0 < float(t["nominal_alpha"]) < 1
    for k, v in t["rows"].items():
        assert "|" in k, f"行键要形如 候选|窗口，实为 {k}"
        if v.get("level") is not None:
            assert 0.0 <= v["level"] <= 1.0, f"{k} 的 level 越界: {v['level']}"
            assert v.get("n_blocks", 1) >= 1


def test_every_measured_candidate_key_is_a_real_candidate():
    """键**绝不手写**：我手写过一次 index="nasdaq100"，而 `_daily_price` 只认
    {"sp500","nasdaq"} → arrays 返回 None → 那一行被**静默跳过**、表里少一条没人报警。
    这条把"表里有个对不上任何候选的键"变成当场红。"""
    import candidate_space as cs
    real = {c["key"] for c in cs.enumerate_candidates()}
    bl.clear_cache()
    orphan = sorted({k.split("|")[0] for k in bl.load()["rows"]} - real)
    assert not orphan, f"表里这些键对不上任何真候选（拼错了？族改名了？）: {orphan}"


# ── 生产接线：门真的被用上了吗（行为测试，不是扫一眼代码）──────────────────

def _gated_table(key, level=0.30):
    return _table(**{f"{key}|现代段": _row(level)})


def test_gate_flips_recent_powered_off():
    import autodiscovery as ad
    r = {"p": 0.001, "recent_p": 0.002, "recent_powered": True}
    out = ad.apply_calibration_gate(r, "k", table=_gated_table("k"))
    assert out["recent_powered"] is False
    assert out["calib_level"] == 0.30 and out["calib_measured"] is True
    assert "3 次里错判 1 次" in out["calib_reason"]


def test_gate_leaves_a_calibrated_candidate_alone():
    import autodiscovery as ad
    r = {"p": 0.001, "recent_p": 0.002, "recent_powered": True}
    out = ad.apply_calibration_gate(r, "k", table=_gated_table("k", level=0.11))
    assert out["recent_powered"] is True
    assert "calib_reason" not in out
    assert out["calib_measured"] is True


def test_gate_never_touches_p_only_the_verdict_lever():
    """命门：绝不改 p、绝不把候选踢出分母 —— 动分母本身就是 p-hacking。"""
    import autodiscovery as ad
    r = {"p": 0.0008, "recent_p": 0.0022, "recent_powered": True, "mc": {"mc_x": 0}}
    out = ad.apply_calibration_gate(r, "k", table=_gated_table("k"))
    assert out["p"] == 0.0008 and out["recent_p"] == 0.0022
    assert out["mc"] == {"mc_x": 0}


def test_gate_does_not_mutate_its_input():
    import autodiscovery as ad
    r = {"p": 0.001, "recent_powered": True}
    ad.apply_calibration_gate(r, "k", table=_gated_table("k"))
    assert r["recent_powered"] is True, "原地改了调用方的 dict"


def test_unmeasured_candidate_keeps_its_verdict_but_is_marked():
    import autodiscovery as ad
    out = ad.apply_calibration_gate({"p": 0.001, "recent_powered": True}, "nope", table=_table())
    assert out["recent_powered"] is True and out["calib_measured"] is False


# ── adjudicate：两种「不可判」的理由必须分得开 ──────────────────────────────

def test_adjudicate_reports_the_calibration_reason_not_the_generic_one():
    from quality_gate import adjudicate
    res = [{"p": 0.001, "recent_p": 0.002, "recent_powered": False,
            "calib_reason": "量具没校准的具体说法", "family": "factor", "key": "a"},
           {"p": 0.5, "recent_p": None, "recent_powered": False, "family": "factor", "key": "b"}]
    adjudicate(res, q=0.10)
    assert res[0]["verdict"] == "inconclusive"
    assert res[0]["reason"] == "量具没校准的具体说法"
    assert res[1]["reason"] == "现代段检验力不足", "没有 calib_reason 的要保持原措辞"


def test_a_gated_candidate_cannot_survive():
    """终点断言：门开了之后，这条**不可能**出现在公开存活名单上。"""
    from quality_gate import adjudicate
    import autodiscovery as ad
    r = ad.apply_calibration_gate(
        {"p": 0.0001, "recent_p": 0.0001, "recent_powered": True}, "k",
        table=_gated_table("k"))
    r.update(family="factor", key="k")
    adjudicate([r], q=0.10)
    assert r["verdict"] == "inconclusive", (
        f"p 小到 0.0001 仍必须被拦下 —— 实为 {r['verdict']}")


def test_table_threshold_cannot_silently_diverge_from_the_module_constant():
    """`gate()` 优先用**表里**的 `max_level_ratio`（模块常量只是兜底）。

    这意味着改一下 JSON 就能悄悄把门放松 —— 而那个 JSON 是机器生成的、没人会逐行读。
    这条把"两者不一致"变成当场红：要放松判据，就得同时改代码常量，
    那是会被 review 看见的地方。
    """
    bl.clear_cache()
    t = bl.load()
    assert float(t["max_level_ratio"]) == bl.MAX_LEVEL_RATIO, (
        f"冻结表的 max_level_ratio={t['max_level_ratio']} 与 "
        f"block_levels.MAX_LEVEL_RATIO={bl.MAX_LEVEL_RATIO} 不一致 —— "
        "门被表单方面改松了？重新跑 tools/block_calibration.py --real --write")
    assert float(t["nominal_alpha"]) == 0.10, "名义水平变了,存活线 q 也要一起看"


# ── 第二道：校准后的 p（判定真正发生的位置）─────────────────────────────────
# 水平门只是**筛子**。实测水平说的是「名义 0.10 处会错多少」，而跨族 BY 的临界值
# 落在 0.000121–0.001696、存活者的 p 常在 0.001 量级 —— 在 0.10 处量出的数字
# **不能**拿来撤一条 p=0.0004 的结论（规格 §9）。所以筛出来的窗口要再问一句：
# 它自己那个 p 在 null 分布里有多罕见。

def _row_with_tail(level, window="现代段", null_B=20000, q=None):
    # 下限由 B 导出(2/(B+1))，与生产同一公式 —— 别反过来从下限猜 B
    # （我第一版那么写，差了 1，测试自己先红了）。
    return {"level": level, "window": window, "family": "factor", "n": 2009,
            "null_B": int(null_B), "null_p_floor": 2.0 / (int(null_B) + 1),
            "null_p_q": q or {"0.001": 0.0012, "0.01": 0.004,
                              "0.05": 0.02, "0.1": 0.04, "0.5": 0.3}}


def test_extreme_p_survives_a_failing_level():
    """命门：水平 0.2175 超标，但 recent_p=0.0007 在 null 下比 0.1% 分位还罕见
    → 尺度被压缩 ≠ 这条发现是噪声 → **不该**判不可判。

    这正是 `BTC_mom20_pos`（已发布的存活者）的处境。只看水平就会把它撤掉。
    """
    t = _table(**{"k|现代段": _row_with_tail(0.2175)})
    g = bl.gate("k", p=0.0004, recent_p=0.0007, table=t)
    assert g["ok"] is True, g
    # 过了筛子也要报 cal_p —— 水平 0.22 却放行时，放行的**理由**必须摆出来，
    # 否则读者只看到一个 0.22 会以为我们在无视它。
    assert g["cal_p"] == 0.001, g


def test_unremarkable_p_does_not_survive_a_failing_level():
    """反向：同样的水平，recent_p=0.30 在 null 下一点都不罕见 → 判不可判。"""
    t = _table(**{"k|现代段": _row_with_tail(0.2175)})
    g = bl.gate("k", p=0.0004, recent_p=0.30, table=t)
    assert g["ok"] is False and g["cal_p"] is not None and g["cal_p"] > 0.10


def test_each_window_is_judged_against_its_own_p():
    """`p` 喂跨族 FDR、`recent_p` 定 modern_status —— 两者各自影响裁决，
    所以要各自对着**自己的** p 过门，不能只看最差水平那个窗口。"""
    t = _table(**{"k|全段": _row_with_tail(0.25, "全段"),      # 坏窗口 ① 对 p
                  "k|现代段": _row_with_tail(0.21, "现代段")})   # 坏窗口 ② 对 recent_p
    # 全段的 p 很罕见、现代段的 recent_p 很普通 → 现代段应该把它拦下
    g = bl.gate("k", p=0.0005, recent_p=0.4, table=t)
    assert g["ok"] is False and g["window"] == "现代段", g
    # 反过来：现代段 p 罕见、全段 p 普通 → 全段拦下（且它水平更高，应被报出来）
    g2 = bl.gate("k", p=0.5, recent_p=0.0005, table=t)
    assert g2["ok"] is False and g2["window"] == "全段", g2
    # 两个窗口的 p 都极罕见 → 放行
    g3 = bl.gate("k", p=0.0005, recent_p=0.0005, table=t)
    assert g3["ok"] is True, g3


def test_a_censored_null_tail_is_refused():
    """**分辨率守门**：null 侧若用比生产更小的 B，下尾被截断在更粗的刻度上。

    实测踩到过：null 用 B=300（格点下限 2/301=0.0066），而生产用 B=20000
    报出 recent_p=0.0007。此时「p_obs 比所有 null p 都小」不是"它极端"，
    而是"我的尺子刻度不够密" —— 用它放行会凭一条截断的尾巴给出结论。
    """
    censored = _row_with_tail(0.2175, null_B=300,
                              q={"0.01": 0.0066, "0.05": 0.0133, "0.1": 0.0399})
    g = bl.gate("k", p=0.0004, recent_p=0.0007, table=_table(**{"k|现代段": censored}))
    assert g["ok"] is False, "截断的尾巴不该被用来放行"
    assert g["cal_p"] is None, "无从校准时应报 None，而不是编一个数"
    # 同一条尾巴对**够粗**的 p 是可用的
    assert bl.calibrated_p(censored, 0.35) is not None


def test_calibrated_p_is_a_conservative_upper_bound():
    row = _row_with_tail(0.3)
    assert bl.calibrated_p(row, 0.0012) == 0.001      # 正好落在 0.1% 分位
    assert bl.calibrated_p(row, 0.003) == 0.01        # 落在 0.1%~1% 之间 → 取上界 1%
    assert bl.calibrated_p(row, 0.9) == 1.0           # 比最大分位还大 → 一点不罕见
    assert bl.calibrated_p(row, None) is None


def test_reason_mentions_the_calibrated_p_when_there_is_one():
    t = _table(**{"k|现代段": _row_with_tail(0.2175)})
    g = bl.gate("k", p=0.0004, recent_p=0.30, table=t)
    r = bl.reason(g)
    assert "校准后" in r and "5 次里错判 1 次" in r, r


def test_a_coarser_null_is_fine_as_long_as_p_obs_is_above_its_floor():
    """判据只有一条：`p_obs >= null_p_floor`，**不是** `null_B >= n_obs`。

    我一开始加了后面那条，错的：null 比 p_obs 粗并不妨碍定位，只要 p_obs 远在
    下限之上 —— 经验 CDF 是阶梯，取"跨过 p_obs 的那一档"本身就是上界，
    粗一点只让上界更松（保守）。那条规则会把 15 行 p 在 0.09~0.998 的候选
    全判成「无从校准」，把能说清的话说糊了，将来还会错拦 p 中等的候选。
    """
    coarse = _row_with_tail(0.25, null_B=300,
                            q={"0.01": 0.0066, "0.05": 0.0133, "0.1": 0.0399, "0.5": 0.3})
    assert bl.calibrated_p(coarse, 0.35, n_obs=2000) == 1.0      # 粗尺子照样定位
    assert bl.calibrated_p(coarse, 0.02, n_obs=2000) == 0.1
    assert bl.calibrated_p(coarse, 0.0007, n_obs=2000) is None   # 真正该挡的

def test_gate_refuses_when_p_obs_is_below_the_null_floor():
    """生产用 B=20000 报出 recent_p=0.0007，而 null 只测到 B=2000（下限 0.001）
    → 0.0007 低于下限 → 不可比 → 保守拦下，而不是凭截断的尾巴放行。"""
    t = _table(**{"k|现代段": _row_with_tail(0.2175, null_B=2000)})
    g = bl.gate("k", p=0.0004, recent_p=0.0007, p_n=20000, recent_n=20000, table=t)
    assert g["ok"] is False and g["cal_p"] is None, g


def test_every_tail_row_carries_the_B_it_was_measured_at():
    """有 `null_p_q` 就必须有 `null_B` —— 否则分辨率守门**根本不会触发**。

    这条是被一次真实事故逼出来的（2026-10-08）：一个旧版本的测量进程在我加上
    `null_B` 字段之后才收尾，把一张**只有分位、没有 B** 的表写了回来。
    那种表里 `BTC_mom20_pos|现代段` 的尾巴截断在 0.0066（B=300），
    而它的 recent_p=0.0007 —— 守门拿不到 B 就不会拒绝，
    于是一条**截断的尾巴**会把这条已发布的存活者"校准通过"，
    理由是"它比所有 null 都极端"，而真相只是我的尺子刻度不够密。

    缺字段 = 静默地把一道门摘掉 → 必须当场红。
    """
    bl.clear_cache()
    rows = bl.load()["rows"]
    bad = sorted(k for k, v in rows.items()
                 if v.get("null_p_q") and not (v.get("null_B") and v.get("null_p_floor")))
    assert not bad, (
        f"这些行有 null 分位但没记测量用的 B：{bad}\n"
        "→ 分辨率守门会静默失效。重新跑 "
        "`py tools/block_calibration.py --calibrated market-analysis/data/block_levels.json`")


def test_tail_rows_resolve_at_least_as_fine_as_the_gate_needs():
    """表里每条有尾巴的行，其 null_p_floor 必须与 null_B 自洽（2/(B+1)）。"""
    bl.clear_cache()
    for k, v in bl.load()["rows"].items():
        if not v.get("null_B"):
            continue
        want = 2.0 / (int(v["null_B"]) + 1)
        got = float(v["null_p_floor"])
        # 表里存成 8 位小数 → 用相对容差，别拿比舍入还紧的绝对容差去卡自己
        assert abs(got - want) <= max(1e-8, want * 1e-3), (
            f"{k}: null_p_floor={got} 与 null_B={v['null_B']} 不自洽（应为 {want}）")


# ── verify_output 的守门判据（行为测试）─────────────────────────────────────

def _c(key, verdict="survive", **kw):
    return {"key": key, "verdict": verdict, **kw}


def test_unmeasured_survivor_is_reported():
    got = bl.unmeasured_survivors([_c("a", calib_measured=False,
                                      calib_family_covered=True)])
    assert got == ["a"]


def test_measured_survivor_is_not_reported():
    assert bl.unmeasured_survivors([_c("a", calib_measured=True,
                                       calib_family_covered=True)]) == []


def test_non_survivors_are_not_reported():
    """只有**已发布的结论**才值得吵；dead/inconclusive 没量过无所谓。"""
    rows = [_c("a", verdict="dead", calib_measured=False, calib_family_covered=True),
            _c("b", verdict="inconclusive", calib_measured=False, calib_family_covered=True)]
    assert bl.unmeasured_survivors(rows) == []


def test_uncovered_family_is_not_reported():
    """日历族走置换检验、旋转 null 量不了 —— 已知缺口，不是漏测。
    对它吵只会训练人忽略告警。"""
    rows = [_c("september_sp500", calib_measured=False, calib_family_covered=False)]
    assert bl.unmeasured_survivors(rows) == []


def test_old_artifacts_without_the_field_are_not_reported():
    """B1 的教训：守门只在产物**已经带**这些字段时才启用。

    否则旧产物（盘中 `--light` 读仓库里那份）会被判成违规 —— 那正是
    `fe8af0a` 把刷新干红两天的形状。
    """
    assert bl.unmeasured_survivors([_c("a")]) == []            # 根本没有 calib_* 字段
    assert bl.unmeasured_survivors([]) == []
    assert bl.unmeasured_survivors(None) == []


def test_reported_list_is_sorted_and_deduped_by_key():
    rows = [_c("z", calib_measured=False, calib_family_covered=True),
            _c("a", calib_measured=False, calib_family_covered=True)]
    assert bl.unmeasured_survivors(rows) == ["a", "z"]
