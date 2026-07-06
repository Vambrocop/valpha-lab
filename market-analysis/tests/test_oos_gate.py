"""test_oos_gate.py — 自生长 P-A/P-C 单测：门4 OOS 三态/滞回/floor 语义/边缘守卫 + 知识库晋升降级单调。

实盘今日全候选锚=注册日 → 锚后空 → 全 pending（测不到 confirmed/overturned）。故这里**合成锚在过去 +
锚后数据成立/翻盘/不足**的场景，把每条裁决路径真正跑出来断言。命门复用项目生产模块、不复制逻辑。
"""
import numpy as np
import pandas as pd
import pytest

import oos_gate as og
import knowledge_base as kb


# ════════════════════════════════════════════════════════════════════════════
# 1. _classify 纯逻辑：三态 + 滞回 + 无方向(omnibus) + pending
# ════════════════════════════════════════════════════════════════════════════
def test_classify_directional_branches():
    # 同向 + p<0.10 → confirmed
    assert og._classify(+1, +1, 0.04) == og.CONFIRMED
    # 方向反号 → overturned（不论 p）
    assert og._classify(+1, -1, 0.001) == og.OVERTURNED
    assert og._classify(-1, +1, 0.30) == og.OVERTURNED
    # 同向但 p>0.20（已淡）→ overturned
    assert og._classify(+1, +1, 0.42) == og.OVERTURNED
    # 同向 0.10–0.20（持中）→ neutral，滞回带,不动
    assert og._classify(+1, +1, 0.15) == og.NEUTRAL


def test_classify_omnibus_and_pending():
    # 无方向(omnibus)只看 p
    assert og._classify(None, None, 0.04) == og.CONFIRMED
    assert og._classify(None, None, 0.42) == og.OVERTURNED
    assert og._classify(None, None, 0.15) == og.NEUTRAL
    # p 缺失 → pending（未到可判，绝不凑结论）
    assert og._classify(+1, +1, None) == og.PENDING


def test_sign():
    assert og._sign(0.5) == 1 and og._sign(-0.3) == -1
    assert og._sign(0.0) == 0 and og._sign(1e-15) == 0 and og._sign(None) == 0


# ════════════════════════════════════════════════════════════════════════════
# 2. _diff_oos（反弹/体制族）：只 floor (sel,y) 到锚后、不重算阈值/均线；方向取锚后
# ════════════════════════════════════════════════════════════════════════════
def _cand(fam="rebound", cid="reb_test01"):
    return {"candidate_id": cid, "key": f"{fam}_test", "family": fam, "params": {}}


def _arr(n_pre, n_post, *, sel_every=4, pre_up=1.0, post_up=1.0, base_up=0.5):
    """造 (idx, sel, y)：前 n_pre 行锚前、后 n_post 行锚后；sel 每 sel_every 取 1。
    sel 日上涨率 pre 段=pre_up、post 段=post_up；非 sel 日上涨率≈base_up（确定性交替）。"""
    n = n_pre + n_post
    idx = pd.date_range("2000-01-03", periods=n, freq="B")
    sel = (np.arange(n) % sel_every == 0)
    y = np.zeros(n)
    # 非 sel：按**序**交替 0/1 → 上涨率干净的 0.5（不能用全局 index%2,删掉 4 的倍数后会偏奇→2/3）
    nonsel = np.where(~sel)[0]
    y[nonsel] = (np.arange(len(nonsel)) % 2)
    pre = np.arange(n) < n_pre
    for seg_mask, up in ((pre, pre_up), (~pre, post_up)):
        m = sel & seg_mask
        k = int(m.sum())
        yy = np.zeros(k)
        yy[: int(round(up * k))] = 1.0          # 前 up 比例置 1 → 该段 sel 上涨率≈up
        y[np.where(m)[0]] = yy
    anchor = idx[n_pre - 1].date().isoformat()  # 锚=最后一个锚前日 → 锚后=后 n_post 行
    return (idx, sel, y), anchor


def test_diff_oos_confirmed_post_anchor_strong():
    arr, anchor = _arr(1200, 800, pre_up=1.0, post_up=1.0)   # sel 恒涨、非 sel 0.5
    v = og._diff_oos(_cand(), anchor, arr, block=5)
    assert v["oos_status"] == og.CONFIRMED
    assert v["full_sign"] == 1 and v["oos_sign"] == 1
    assert v["oos_n"] == int(arr[1][np.asarray(arr[0] > pd.Timestamp(anchor))].sum())


def test_diff_oos_overturned_signflip():
    # 全样本 sel 偏涨(full_sign +1)，但锚后 sel 全跌 → oos_sign -1 → 反号 → overturned
    arr, anchor = _arr(1500, 600, pre_up=1.0, post_up=0.0)
    v = og._diff_oos(_cand(), anchor, arr, block=5)
    assert v["full_sign"] == 1 and v["oos_sign"] == -1
    assert v["oos_status"] == og.OVERTURNED


def test_diff_oos_pending_insufficient_post():
    # 锚后 sel 触发组 < MIN_OOS_N → 未到可判
    arr, anchor = _arr(1500, 60, sel_every=4)               # 锚后 sel ≈ 15 < 30
    v = og._diff_oos(_cand(), anchor, arr, block=5)
    assert v["oos_status"] == og.PENDING
    assert v["oos_n"] < og.MIN_OOS_N


def test_diff_oos_overturned_faded_same_sign_high_p():
    # 锚后同向(+)但效应极弱 → p>0.20 → overturned(已淡,非反号)。守 _classify 的 faded 分支端到端。
    arr, anchor = _arr(1500, 400, post_up=0.52)             # 锚后 sel 上涨率≈0.52 vs 0.5,差极小
    v = og._diff_oos(_cand(), anchor, arr, block=5)
    assert v["full_sign"] == 1 and v["oos_sign"] == 1       # 同向(不是反号)
    assert v["oos_p"] > og.OVERTURN_P                       # p 大 → 已淡
    assert v["oos_status"] == og.OVERTURNED


def test_diff_oos_floor_only_masks_not_recompute():
    """floor 语义：_diff_oos 收到的是**全样本** sel/y，只按日期掩码取锚后，绝不重算触发规则。
    断言锚后用到的 (sel,y) 正是全样本切片，而非按锚后重新定义。"""
    arr, anchor = _arr(1000, 1000)
    idx, sel, y = arr
    mask = np.asarray(idx > pd.Timestamp(anchor))
    v = og._diff_oos(_cand(), anchor, arr, block=5)
    # oos_n 必须等于"全样本 sel 在锚后的计数"，不等于任何锚后重算的触发数
    assert v["oos_n"] == int(sel[mask].sum())


# ════════════════════════════════════════════════════════════════════════════
# 3. 日历族 OOS：floor **输入** ret（月/年频无边界泄漏）+ perm_test 真跑出 confirmed
# ════════════════════════════════════════════════════════════════════════════
def _september_series(start="2006-01-02", end="2020-12-31", sep_mu=-0.004, base_mu=0.0006):
    idx = pd.date_range(start, end, freq="B")
    r = np.where(idx.month == 9, sep_mu, base_mu).astype(float)  # 九月弱、其余强（确定性，无噪声）
    return pd.Series(r, index=idx)


def test_calendar_floor_filters_input(monkeypatch):
    """floor=anchor 时，抽取前先把输入 ret 滤到 > anchor → 返回的 vals 长度=锚后业务日数。"""
    import autodiscovery as ad
    s = _september_series()
    monkeypatch.setattr(ad, "_daily", lambda index: s)
    anchor = "2013-01-01"
    arr = ad._calendar_arrays("september", "sp500", floor=anchor)
    assert arr is not None
    vals = arr[0]
    assert len(vals) == int((s.index > pd.Timestamp(anchor)).sum())   # 严格只含锚后


def test_calendar_floor_no_leak_resampled_month(monkeypatch):
    """B1/trap-1 的真考验:月频效应。floor 必须滤**输入** ret → 锚后月 bar 不含锚前任何一天。
    造'锚前每天 +1%、锚后每天 -1%' → 若 floor 输入正确,锚后全部月收益必为负(纯锚后)；
    若错成'先重采样再按月末过滤'(输出掩码),跨锚那个月会混入锚前 +1% → 可能转正。"""
    import autodiscovery as ad
    idx = pd.date_range("2008-01-02", "2016-12-31", freq="B")
    anchor = pd.Timestamp("2011-06-15")
    r = np.where(idx <= anchor, 0.01, -0.01).astype(float)
    monkeypatch.setattr(ad, "_daily", lambda index: pd.Series(r, index=idx))
    arr = ad._calendar_arrays("month", "sp500", floor="2011-06-15")
    vals = np.asarray(arr[0])
    assert (vals < 0).all()                                 # 每个锚后月都是纯 -1% → 全负 = 零泄漏


def test_monthof_is_omnibus_in_oos_not_directional(monkeypatch):
    """B1 修复守卫:机器逐月扫 monthof_ 两侧打分、无方向先验 → OOS 必须 omnibus(full_sign=None),
    绝不从数据读方向再'确认'它(循环=不诚实)。"""
    import autodiscovery as ad
    idx = pd.date_range("2006-01-02", "2020-12-31", freq="B")
    r = np.where(idx.month == 3, 0.005, 0.0003).astype(float)   # 三月明显异常(两侧可测)
    monkeypatch.setattr(ad, "_daily", lambda index: pd.Series(r, index=idx))
    cand = {"candidate_id": "cal_m3_test", "key": "monthof_3_sp500", "family": "calendar",
            "params": {"effect": "monthof_3", "index": "sp500"}}
    v = og._calendar_oos(cand, "2013-01-01")
    assert v["full_sign"] is None and v["oos_sign"] is None     # omnibus:无方向
    assert v["oos_status"] == og.CONFIRMED                      # 仍可凭两侧 p<0.10 确认"该月异常持续"


def test_calendar_oos_confirmed_september(monkeypatch):
    import autodiscovery as ad
    s = _september_series()
    monkeypatch.setattr(ad, "_daily", lambda index: s)
    cand = {"candidate_id": "cal_sep_test", "key": "september_sp500", "family": "calendar",
            "params": {"effect": "september", "index": "sp500"}}
    v = og._calendar_oos(cand, "2013-01-01")
    assert v["oos_status"] == og.CONFIRMED
    assert v["full_sign"] == 1 and v["oos_sign"] == 1      # 非九月 > 九月 → +1
    assert v["oos_p"] is not None and v["oos_p"] < og.CONFIRM_P


def test_calendar_oos_pending_when_anchor_recent(monkeypatch):
    import autodiscovery as ad
    s = _september_series()
    monkeypatch.setattr(ad, "_daily", lambda index: s)
    cand = {"candidate_id": "cal_sep_test", "key": "september_sp500", "family": "calendar",
            "params": {"effect": "september", "index": "sp500"}}
    # 锚太晚 → 锚后 < 1000 日 → 未到可判
    v = og._calendar_oos(cand, "2019-06-01")
    assert v["oos_status"] == og.PENDING


def test_calendar_oos_pre_fomc_structural_pending(monkeypatch):
    # S3:pre_fomc 锚点晚于 fomc_dates 表末 → 锚后永远无会议 → 结构性 pending(需扩表),
    #     note 必须能与"引擎刚起步样本少"区分（明说 fomc_dates 止于…），否则永久 pending 被误读为卡住。
    #     注入"止于过去"的会议表 → 不依赖真实表末日期(以后扩到 2027+ 也不破此测)。
    import autodiscovery as ad
    import fomc_dates
    s = _september_series()                                 # 2006-2020·>=1000 日,保证全样本可抽取
    monkeypatch.setattr(ad, "_daily", lambda index: s)
    monkeypatch.setattr(fomc_dates, "load_fomc_dates",
                        lambda: [pd.Timestamp("2010-06-01"), pd.Timestamp("2015-06-01")])
    cand = {"candidate_id": "cal_prefomc_test", "key": "pre_fomc_sp500", "family": "calendar",
            "params": {"effect": "pre_fomc", "index": "sp500"}}
    v = og._calendar_oos(cand, "2018-01-01")                # 锚 > 注入表末(2015) → 结构性
    assert v["oos_status"] == og.PENDING
    assert "fomc_dates 止于" in v["note"]                    # 结构性饥饿提示(区别于"锚后样本不足")


def test_oos_verdict_unregistered_is_pending():
    v = og.oos_verdict(_cand(fam="factor"), anchor=None)
    assert v["oos_status"] == og.PENDING


# ════════════════════════════════════════════════════════════════════════════
# 3b. 仓位族(COT)/期权情绪族(P/C) OOS — #7 2026-07-04：H-1 反退化(显式路由,note 绝不落"因子族待接")
# ════════════════════════════════════════════════════════════════════════════
def _synth_cot_reports(n=300, start="2000-01-04", seed=0):
    idx = pd.date_range(start, periods=n, freq="7D")
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"report_date": idx, "usable_from": idx + pd.Timedelta(days=6),
                         "value": rng.normal(0, 1, n)})


def _synth_price(start="1998-01-01", end="2012-12-31", seed=1):
    idx = pd.date_range(start, end, freq="B")
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.cumprod(1 + rng.normal(0.0003, 0.01, len(idx))), index=idx)


def test_positioning_oos_dispatch_no_silent_factor_note(monkeypatch):
    """H-1 BLOCKER 守门:positioning 必须显式路由到 _diff_oos(放大块)，绝不落 else→"因子族待接"错误 pending。"""
    import autodiscovery as ad
    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: _synth_cot_reports())
    monkeypatch.setattr(ad, "_daily_price", lambda index: _synth_price())
    cand = {"candidate_id": "pos_oos_t", "key": "k", "family": "positioning",
            "params": {"market": "sp500", "series": "legacy_noncomm_pct_oi", "extreme": "hi", "hold": 20}}
    v = og.oos_verdict(cand, "2008-01-01")
    assert "因子族" not in v["note"]                      # 绝不误落 factor 分支
    assert v["oos_status"] in (og.CONFIRMED, og.OVERTURNED, og.NEUTRAL) or (
        v["oos_status"] == og.PENDING and v["note"] in ("锚后触发组样本不足", "锚后自助不可算"))
    assert v["full_sign"] is not None                     # _diff_oos 真跑了(全样本方向已算)


def test_optsent_oos_dispatch_no_silent_factor_note(monkeypatch):
    import autodiscovery as ad
    idx_all = pd.date_range("2006-11-01", periods=1600, freq="B")
    rng = np.random.default_rng(7)
    vals = rng.normal(0.9, 0.15, len(idx_all))
    vals[300:1500:25] = 2.5                              # 过去段尖峰→hi 极端日足量(>30·过检验力守卫)
    monkeypatch.setattr(ad, "_putcall_daily",
                        lambda: pd.DataFrame({"total_pc": vals, "equity_pc": vals}, index=idx_all))
    monkeypatch.setattr(ad, "_daily_price", lambda index: _synth_price(start="2006-01-01", end="2015-12-31"))
    cand = {"candidate_id": "opt_oos_t", "key": "k", "family": "options_sentiment",
            "params": {"series": "total_pc", "extreme": "hi", "hold": 10}}
    v = og.oos_verdict(cand, "2009-06-01")
    assert "因子族" not in v["note"]
    assert v["full_sign"] is not None


def test_oos_verdict_unrouted_family_raises():
    """H-1 反退化的防御端：未知 family 必须炸，不许静默 pending（防未来再漏接一族）。"""
    with pytest.raises(ValueError):
        og.oos_verdict(_cand(fam="totally_unknown"), anchor="2020-01-01")


def test_positioning_oos_block_matches_discovery():
    """§10 定稿:discovery 与 OOS 的 positioning block 必须同一放大公式(hold+episode p90)，两处不一致=
    同一效应两套显著性口径。锚定实测常数:hold20→71、hold60→111（改 POSITIONING_BLOCK_EXTRA 必须重跑
    块敏感性并过审,不许只改一处）。"""
    import autodiscovery as ad
    assert ad._positioning_block(20) == 20 + ad.POSITIONING_BLOCK_EXTRA == 71
    assert ad._positioning_block(60) == 60 + ad.POSITIONING_BLOCK_EXTRA == 111


# ════════════════════════════════════════════════════════════════════════════
# 4. knowledge_base：晋升门 / 降级 / 单调 / append-only 回放
# ════════════════════════════════════════════════════════════════════════════
def _v(cid, status, full_sign=1, oos_sign=1, key=None):
    return {"candidate_id": cid, "key": key or cid, "family": "calendar", "anchor_date": "2020-01-01",
            "oos_status": status, "oos_n": 99, "oos_p": 0.03, "oos_sign": oos_sign, "full_sign": full_sign}


def test_decide_promote_requires_survive_and_confirmed():
    verdicts = [
        _v("A", og.CONFIRMED), _v("B", og.CONFIRMED), _v("C", og.CONFIRMED), _v("D", og.NEUTRAL),
    ]
    vmap = {"A": "survive", "B": "faded", "C": "dead", "D": "survive"}
    rows = kb.decide(verdicts, vmap, members=set(), today="2026-07-01")
    promoted = {r["candidate_id"] for r in rows if r["action"] == kb.PROMOTE}
    assert promoted == {"A"}                  # 只有 survive ∧ confirmed 才晋升


def test_decide_no_double_promote_when_already_member():
    verdicts = [_v("A", og.CONFIRMED)]
    rows = kb.decide(verdicts, {"A": "survive"}, members={"A"}, today="2026-07-01")
    assert rows == []                          # 已在库 + confirmed → 不重复晋升（单调）


def test_decide_demote_only_member_overturned():
    verdicts = [_v("A", og.OVERTURNED), _v("B", og.OVERTURNED)]
    vmap = {"A": "survive", "B": "survive"}
    rows = kb.decide(verdicts, vmap, members={"A"}, today="2026-07-01")
    actions = {(r["candidate_id"], r["action"]) for r in rows}
    assert actions == {("A", kb.DEMOTE)}       # 在库 A 翻盘→降级；不在库 B 翻盘→无操作


def test_decide_noop_on_pending_neutral():
    verdicts = [_v("A", og.PENDING), _v("B", og.NEUTRAL)]
    rows = kb.decide(verdicts, {"A": "survive", "B": "survive"}, members=set(), today="2026-07-01")
    assert rows == []


def test_replay_members_append_only(tmp_path):
    p = tmp_path / "kb.csv"
    kb._append([kb._row("2026-07-01", _v("A", og.CONFIRMED), kb.PROMOTE, "t"),
                kb._row("2026-07-01", _v("B", og.CONFIRMED), kb.PROMOTE, "t")], p)
    assert kb.replay_members(p) == {"A", "B"}
    # A 翻盘降级（append 一行，不改历史）
    kb._append([kb._row("2026-08-01", _v("A", og.OVERTURNED), kb.DEMOTE, "t")], p)
    assert kb.replay_members(p) == {"B"}
    # 历史行仍在（append-only）：3 行
    with open(p, encoding="utf-8") as f:
        assert sum(1 for _ in f) == 1 + 3      # header + 3 data


def test_replay_repromote_after_demote(tmp_path):
    # docstring 承诺:曾 overturn 降级、日后又 confirmed 可再 promote(新证据周期,每次转换都留行)。
    p = tmp_path / "kb.csv"
    kb._append([kb._row("2026-07-01", _v("A", og.CONFIRMED), kb.PROMOTE, "t")], p)
    assert kb.replay_members(p) == {"A"}
    kb._append([kb._row("2026-08-01", _v("A", og.OVERTURNED), kb.DEMOTE, "t")], p)
    assert kb.replay_members(p) == set()
    kb._append([kb._row("2026-10-01", _v("A", og.CONFIRMED), kb.PROMOTE, "t")], p)
    assert kb.replay_members(p) == {"A"}        # 最后一次 action=promote → 在库
    with open(p, encoding="utf-8") as f:
        assert sum(1 for _ in f) == 1 + 3       # header + 3 行(全留,append-only)


def test_step_dry_does_not_write(tmp_path):
    p = tmp_path / "kb.csv"
    verdicts = [_v("A", og.CONFIRMED)]
    results = [{"candidate_id": "A", "verdict": "survive"}]
    rows = kb.step(verdicts=verdicts, results=results, today="2026-07-01", path=p, write=False)
    assert len(rows) == 1 and rows[0]["action"] == kb.PROMOTE
    assert not p.exists()                       # write=False 绝不落盘


# ── P-D 前端导出 knowledge_base.json 形状 ──
def test_export_json_shape_queue_and_summary(tmp_path):
    p = tmp_path / "kb.csv"                      # 空账本(无在库/无史)
    verdicts = [_v("A", og.PENDING, key="september_sp500"),   # survive 但 pending → 进 queue
                _v("B", og.PENDING, key="x"), _v("C", og.CONFIRMED, key="y")]
    verdicts[0]["family"] = "calendar"
    results = [{"candidate_id": "A", "verdict": "survive", "family": "calendar", "key": "september_sp500"},
               {"candidate_id": "B", "verdict": "dead", "family": "rebound", "key": "x"},
               {"candidate_id": "C", "verdict": "survive", "family": "calendar", "key": "y"}]
    out = kb.export_json(verdicts, results, members=set(), today="2026-06-29", write=False, path=p)
    assert set(out) >= {"summary", "members", "queue", "movements", "history", "anchor_common", "days_since_anchor", "caveat"}
    # queue = verdict=='survive' ∧ 未在库（与 oos_status 无关）→ A 和 C；B 是 dead 不进
    assert {q["key"] for q in out["queue"]} == {"september_sp500", "y"}
    assert out["summary"]["queue"] == 2 and out["summary"]["in_kb"] == 0
    assert out["summary"]["confirmed"] == 1      # C 的 oos_status=confirmed → movements/summary 计 1
    assert {m["key"] for m in out["movements"]} == {"y"}   # 只有非 pending 的进 movements
    assert "未到可判" in out["caveat"] and "非荐股" in out["caveat"]
    assert out["anchor_common"] == "2020-01-01" and out["days_since_anchor"] > 0


def test_export_json_members_and_history(tmp_path):
    p = tmp_path / "kb.csv"
    kb._append([kb._row("2026-07-01", _v("A", og.CONFIRMED, key="golden_cross_sp500"), kb.PROMOTE, "t")], p)
    verdicts = [_v("A", og.NEUTRAL, key="golden_cross_sp500")]
    results = [{"candidate_id": "A", "verdict": "survive", "family": "regime", "key": "golden_cross_sp500"}]
    out = kb.export_json(verdicts, results, members={"A"}, today="2026-08-01", write=False, path=p)
    assert out["summary"]["in_kb"] == 1
    assert [m["key"] for m in out["members"]] == ["golden_cross_sp500"]
    assert out["members"][0]["since"] == "2026-07-01"     # 取最后一次 promote 日
    assert len(out["history"]) == 1 and out["history"][0]["action"] == kb.PROMOTE
