"""P2-9 sidecar 哈希链单测：建链 → 改历史行 → 校验应报篡改 → 还原。

红线验证点：封存/校验全程**只读账本**（账本文件字节不变），链只进 manifest。
"""
import csv

import ledger_sidecar as ls


# ── 造两类账本:纯 append(全字段身份) / forward_ledger 结算型(身份+结算列)──
PURE_SPEC = [("mini_log.csv", None)]
SETTLE_SPEC = [("mini_picks.csv", ["pick_date", "symbol", "view"])]


def _write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _pure_ledger(tmp_path, n=3):
    p = tmp_path / "mini_log.csv"
    _write_csv(p, ["date", "verdict"],
               [{"date": f"2026-06-{10 + i}", "verdict": "survive"} for i in range(n)])
    return p


def _settle_ledger(tmp_path):
    p = tmp_path / "mini_picks.csv"
    _write_csv(p, ["pick_date", "symbol", "view", "ret_pct", "hit", "settled"], [
        {"pick_date": "2026-06-10", "symbol": "AAA", "view": "看好",
         "ret_pct": "1.5", "hit": "True", "settled": "True"},
        {"pick_date": "2026-06-11", "symbol": "BBB", "view": "看淡",
         "ret_pct": "", "hit": "", "settled": "False"},
    ])
    return p


def _seal(tmp_path, specs, **kw):
    return ls.seal_all(data_dir=tmp_path, manifest=tmp_path / "chain.csv", specs=specs, **kw)


def _verify(tmp_path, specs):
    return ls.verify_all(data_dir=tmp_path, manifest=tmp_path / "chain.csv", specs=specs)


# ── 主线:建链 → 改历史行 → 应报篡改 → 还原 → 应通过 ─────────────────────
def test_tamper_history_row_detected_then_restore(tmp_path):
    p = _pure_ledger(tmp_path)
    original = p.read_bytes()
    n, refusals = _seal(tmp_path, PURE_SPEC)
    assert n == 1 and refusals == []
    assert p.read_bytes() == original            # 红线:封存零写入账本本体
    assert _verify(tmp_path, PURE_SPEC) == [("mini_log.csv", [])]

    # 外部手改历史行(survive→faded 粉饰裁决)
    tampered = original.replace(b"2026-06-11,survive", b"2026-06-11,faded")
    assert tampered != original
    p.write_bytes(tampered)
    [(fname, errs)] = _verify(tmp_path, PURE_SPEC)
    assert fname == "mini_log.csv" and errs      # 校验抓到
    _, refusals = _seal(tmp_path, PURE_SPEC)     # 重封也祝福不掉:身份前缀链拒绝
    assert refusals and "拒绝" in refusals[0]

    p.write_bytes(original)                      # 还原 → 全部恢复绿
    assert _verify(tmp_path, PURE_SPEC) == [("mini_log.csv", [])]
    _, refusals = _seal(tmp_path, PURE_SPEC)
    assert refusals == []


def test_truncation_detected(tmp_path):
    p = _pure_ledger(tmp_path, n=3)
    _seal(tmp_path, PURE_SPEC)
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    p.write_text("".join(lines[:-1]), encoding="utf-8")     # 截掉最后一行(in-file 前缀链抓不到的盲区)
    [(_, errs)] = _verify(tmp_path, PURE_SPEC)
    assert errs and "删" in errs[0]
    _, refusals = _seal(tmp_path, PURE_SPEC)
    assert refusals and "缩水" in refusals[0]


def test_append_after_seal_is_fine(tmp_path):
    p = _pure_ledger(tmp_path)
    _seal(tmp_path, PURE_SPEC)
    with open(p, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(["2026-06-13", "survive"])   # 合法 append
    assert _verify(tmp_path, PURE_SPEC) == [("mini_log.csv", [])]   # 前缀性质:新行不影响旧链
    n, refusals = _seal(tmp_path, PURE_SPEC)                # 重封收编新行
    assert n == 1 and refusals == []


# ── forward_ledger 结算型:合法填空 vs 身份篡改 ──────────────────────────
def test_settlement_fill_needs_reseal_but_core_holds(tmp_path):
    p = _settle_ledger(tmp_path)
    _seal(tmp_path, SETTLE_SPEC)

    # 合法结算:只填空(pending 行补 ret/hit/settled),身份列不碰 → 行序保持
    _write_csv(p, ["pick_date", "symbol", "view", "ret_pct", "hit", "settled"], [
        {"pick_date": "2026-06-10", "symbol": "AAA", "view": "看好",
         "ret_pct": "1.5", "hit": "True", "settled": "True"},
        {"pick_date": "2026-06-11", "symbol": "BBB", "view": "看淡",
         "ret_pct": "-0.8", "hit": "True", "settled": "True"},
    ])
    [(_, errs)] = _verify(tmp_path, SETTLE_SPEC)
    assert errs and "重封" in errs[0]            # 诚实边界:结算后须重封,校验先亮黄
    n, refusals = _seal(tmp_path, SETTLE_SPEC)   # 身份前缀链完好 → 重封放行
    assert n == 1 and refusals == []
    assert _verify(tmp_path, SETTLE_SPEC) == [("mini_picks.csv", [])]

    # 身份篡改:把历史"看淡"改成"看好"(事后改口) → 重封也拒绝
    text = p.read_text(encoding="utf-8").replace("BBB,看淡", "BBB,看好")
    p.write_text(text, encoding="utf-8")
    [(_, errs)] = _verify(tmp_path, SETTLE_SPEC)
    assert errs and "身份" in errs[0]
    _, refusals = _seal(tmp_path, SETTLE_SPEC)
    assert refusals and "身份" in refusals[0]


# ── manifest 自身 append-only + 防膨胀 + 留痕放行 ───────────────────────
def test_manifest_append_only_and_dedup(tmp_path):
    p = _pure_ledger(tmp_path)
    m = tmp_path / "chain.csv"
    _seal(tmp_path, PURE_SPEC)
    first = m.read_bytes()
    n, _ = _seal(tmp_path, PURE_SPEC)            # 无变化 → 不追加(CI 小时级防膨胀)
    assert n == 0 and m.read_bytes() == first
    with open(p, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(["2026-06-13", "faded"])
    _seal(tmp_path, PURE_SPEC)
    assert m.read_bytes().startswith(first)      # manifest 只追加,历史记录一字节不动
    assert len(ls.read_manifest(m)) == 2


def test_rebless_leaves_audit_trail(tmp_path):
    p = _pure_ledger(tmp_path)
    _seal(tmp_path, PURE_SPEC)
    text = p.read_text(encoding="utf-8").replace("2026-06-10,survive", "2026-06-10,faded")
    p.write_text(text, encoding="utf-8")
    _, refusals = _seal(tmp_path, PURE_SPEC)     # 默认拒绝
    assert refusals
    n, refusals = _seal(tmp_path, PURE_SPEC, rebless="mini_log.csv",
                        note="测试:人工核准的历史修正")
    assert n == 1 and refusals == []             # 放行但留痕
    recs = ls.read_manifest(tmp_path / "chain.csv")
    assert recs[-1]["note"] == "测试:人工核准的历史修正"
    assert _verify(tmp_path, PURE_SPEC) == [("mini_log.csv", [])]


def test_missing_ledger_or_record_skipped(tmp_path):
    # 账本不存在(如 kb_ledger 首批晋升前) → 封存/校验都静默跳过
    assert _seal(tmp_path, PURE_SPEC) == (0, [])
    assert _verify(tmp_path, PURE_SPEC) == []
    # 账本在、记录没有(bootstrap) → 校验跳过不误报
    _pure_ledger(tmp_path)
    assert _verify(tmp_path, PURE_SPEC) == []


def test_real_specs_core_fields_match_writers():
    """SPECS 里结算型账本的身份字段必须真是建行即定的列(与各写手 HEADER 前缀一致)。"""
    import insider_signal
    import llm_prediction
    import pick_ledger
    headers = {"llm_prediction_log.csv": llm_prediction.HEADER,
               "pick_ledger.csv": pick_ledger.HEADER,
               "insider_signal_log.csv": insider_signal.HEADER}
    for fname, core in ls.SPECS:
        if core is None:
            continue
        h = headers[fname]
        assert core == h[:len(core)], f"{fname} 身份字段应是 HEADER 前缀(建行即定列)"
        # 结算列(settle 会填)绝不能混进身份字段
        assert not (set(core) & {"entry_date", "entry_px", "exit_date", "exit_px",
                                 "ret_pct", "hit", "settled", "dropped"})
