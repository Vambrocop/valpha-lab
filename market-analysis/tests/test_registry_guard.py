"""test_registry_guard.py — P2-10 registry 不可变门：check_registry_immutable 三态单测。

红线验证点：比**解析后的语义行**，不比字节——加列/换行漂移得放行，但历史行任何真实语义改动
（篡改锚点/删行/新行倒填/candidate_id 重复）都必须被抓。纯函数吃字符串，测试自造输入，
不依赖 git 状态/环境（门禁测试不得依赖外部状态）。
"""
import candidate_registry as reg

OLD = (
    "candidate_id,family,key,declared_date,reason,reviewer\n"
    "cal_a,calendar,dow_nasdaq,2026-06-26,首次进入候选空间,auto-sync\n"
    "cal_b,calendar,dow_sp500,2026-06-26,首次进入候选空间,auto-sync\n"
)


def test_normal_append_is_clean():
    new = OLD + "cal_c,calendar,month_nasdaq,2026-07-03,首次进入候选空间,auto-sync\n"
    assert reg.check_registry_immutable(OLD, new) == []


def test_tamper_historical_anchor_date_detected():
    new = OLD.replace("cal_a,calendar,dow_nasdaq,2026-06-26",
                       "cal_a,calendar,dow_nasdaq,2026-06-01")   # 倒填改早,企图伪造更长 OOS
    problems = reg.check_registry_immutable(OLD, new)
    assert problems
    assert any("cal_a" in p and "declared_date" in p for p in problems)


def test_tamper_historical_nondate_field_detected():
    new = OLD.replace("dow_sp500", "dow_faked")     # 改历史行任意字段(非日期)也要抓
    problems = reg.check_registry_immutable(OLD, new)
    assert problems
    assert any("cal_b" in p for p in problems)


def test_delete_historical_row_detected():
    lines = OLD.splitlines(keepends=True)
    new = "".join(lines[:2])                          # 删掉 cal_b 那一行
    problems = reg.check_registry_immutable(OLD, new)
    assert problems
    assert any("cal_b" in p and "消失" in p for p in problems)


def test_extra_column_and_crlf_drift_allowed():
    # 加一列(notes) + 全文 LF→CRLF 换行漂移：语义行不变 → 必须放行(免疫格式漂移 + 加列逃生口)
    new_lf = (
        "candidate_id,family,key,declared_date,reason,reviewer,notes\n"
        "cal_a,calendar,dow_nasdaq,2026-06-26,首次进入候选空间,auto-sync,备注A\n"
        "cal_b,calendar,dow_sp500,2026-06-26,首次进入候选空间,auto-sync,备注B\n"
    )
    new_crlf = new_lf.replace("\n", "\r\n")
    old_crlf = OLD.replace("\n", "\r\n")
    assert reg.check_registry_immutable(OLD, new_lf) == []
    assert reg.check_registry_immutable(old_crlf, new_crlf) == []
    assert reg.check_registry_immutable(OLD, new_crlf) == []   # 一边 LF 一边 CRLF 也不误报


def test_duplicate_candidate_id_reported():
    new = OLD + "cal_a,calendar,dow_nasdaq2,2026-07-03,重复注册,auto-sync\n"   # cal_a 在 new 里出现两次
    problems = reg.check_registry_immutable(OLD, new)
    assert problems
    assert any("重复" in p and "cal_a" in p for p in problems)


def test_new_row_backdated_reported():
    # 新行(cal_c 未在 old 出现)但 declared_date 早于 old 里最晚锚点 → 倒填造假长 OOS,必须报
    new = OLD + "cal_c,calendar,month_nasdaq,2026-01-01,补登旧候选,auto-sync\n"
    problems = reg.check_registry_immutable(OLD, new)
    assert problems
    assert any("cal_c" in p for p in problems)


def test_new_row_same_or_later_date_is_fine():
    same_date = OLD + "cal_c,calendar,month_nasdaq,2026-06-26,同日新增,auto-sync\n"
    assert reg.check_registry_immutable(OLD, same_date) == []   # ≥ 最晚锚点,允许(边界含等号)


def test_bootstrap_empty_old_has_no_row_constraints():
    new = "candidate_id,family,key,declared_date,reason,reviewer\ncal_a,calendar,dow_nasdaq,2026-06-26,首次登记,auto-sync\n"
    assert reg.check_registry_immutable("", new) == []


def test_bootstrap_empty_old_still_catches_duplicate_in_new():
    new = (
        "candidate_id,family,key,declared_date,reason,reviewer\n"
        "cal_a,calendar,dow_nasdaq,2026-06-26,首次登记,auto-sync\n"
        "cal_a,calendar,dow_nasdaq2,2026-06-26,首次登记,auto-sync\n"
    )
    problems = reg.check_registry_immutable("", new)
    assert problems and any("重复" in p for p in problems)


def test_new_row_backdated_nonpadded_still_reported():
    """Opus 审洞回归锁:非零填充日期 '2026-1-1' 字典序 > '2026-06-26' 但语义是 1 月(倒填)——
    修复前会绕过③;现在非规范 ISO 直接拒(sync 恒写 isoformat,非规范只可能来自手工篡改)。"""
    new = OLD + "cal_c,calendar,month_nasdaq,2026-1-1,伪装同年新增,auto-sync\n"
    problems = reg.check_registry_immutable(OLD, new)
    assert problems
    assert any("cal_c" in p and "非规范 ISO" in p for p in problems)


def test_rename_old_column_detected():
    """列改名回归锁(Opus 审确认行为正确·此测锁死):把 old 的 declared_date 列在 new 里改名移走
    → old 列集内取值坍成空串 ≠ old 非空值 → 必须报篡改,绝不静默放行。"""
    new = (
        "candidate_id,family,key,anchor_date,reason,reviewer\n"       # declared_date 改名 anchor_date
        "cal_a,calendar,dow_nasdaq,2026-06-26,首次登记,auto-sync\n"
        "cal_b,calendar,dow_sp500,2026-06-26,首次登记,auto-sync\n"
    )
    problems = reg.check_registry_immutable(OLD, new)
    assert problems
    assert any("declared_date" in p and "篡改" in p for p in problems)
