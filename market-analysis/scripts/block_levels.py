"""生产读「块自助实际水平」的冻结表 —— 量具没校准的候选，记不可判、不给结论。

## 这是什么

`tools/block_calibration.py --real` 用**旋转 null**量出每个 (候选 × 窗口) 上
块自助检验的**实际水平**：把 y 相对 sel 随机循环平移 → 两条序列各自的边际分布与
自相关结构分毫不动、只有二者之间的关联被破坏 → H0「sel 对 y 无信息」按构造成立 →
`p < α` 的经验比例就是这个检验在这段样本上真正的犯错率。

名义 0.10 而实测 0.33，意思是**每 3 条"显著"里有 1 条是块长不够编出来的**。

## 为什么要有这道门（F2 的 P2）

F2 给状态型 sel 补上 block 放大之后，校准**普遍改善但并不够**：

  · `BTC_above_ma200` 放大后仍 **0.332** —— 2859 个观测配 143 天的依赖长度，
    这条因子在现有样本上根本不可检验，换任何块长都不行；
  · `BTC_mom20_pos` **0.176** —— 而它是**已经发布的存活者**；
  · `BTC_mom20_neg` **0.160** —— 而放大恰好把它推过了存活线。

只做放大 = 一边说"我们把检验做准了"，一边发布一条自己有证据反对的"发现"。

## `MAX_LEVEL_RATIO` 现在只是**花算力的取舍**，不是门

⚠ **我原来给这个阈值写的理由是错的**（独立审查 Important 4，2026-10-09）。

原话是：「`--controls` 在答案已知的合成数据上测出这个估计器的本底是 0.11–0.135，
所以阈值必须高于本底」。**这是把"被测量"当成了"测量误差"。**
那 0.11–0.135 就是块自助在那些配置上的**真实水平**，不是旋转 null 估计器的偏差。
审查者直接验了估计器本身（同一合成生成器、H0 按构造成立，n=2000、sel 游程~140、
y 20 日重叠、block=164）：

    (i)  300 份新数据上的**真实**水平        0.093 ± 0.017
    (ii) 一份已实现的 H0 数据上的旋转 null    0.070 ± 0.015

估计器在 ~1 SE 内追上了真值。所以**不存在一个"尺子自己的噪声底"要去跨过** ——
「阈值必须高于本底」这条原则是无效的，照它推下去会随着检验越来越差而无限抬阈值。

真话是我早就登记过的那句：**整个块自助族的实际水平是 0.12–0.19，
所以 q=0.10 的存活线实际更接近 0.15。**

### 那 2.0 这个数现在算什么

**只算一件事：先给哪些行花算力去测尾巴。** 它不再决定任何裁决（见
`autodiscovery.apply_calibration_gate`：现在只披露、不裁决）。

而且必须诚实记上：**2.0 是在看到 1.5 会撤掉两条已发布存活者之后才定的**，
这个数与结果相关，不是先验推出来的。审查把这一点挑明了，我接受。
R=400 时 SE≈0.018、0.15 附近分辨不开，这个说法成立；但它只支持
「边界附近要加算」（`--refine` 的 ±3SE 带就是干这个的），**不支持把线往上挪**。

## 不止拦，还要**全部公开**

比二元的"拦/不拦"更诚实的是：**每一条候选的实测水平都写进产物**，
前端照实写「这条规律的检验实测约 N 次里错 1 次」。
这样即使没被拦下的（0.15 附近那些）读者也看得见证据有多硬，
而不是靠一个卡在噪声里的阈值替他们决定。

## 它不会被"这条好不好看"影响

旋转 null 把真关联**按构造**破坏掉。测量过程根本碰不到真实的关联强度 ——
它量的是尺子，不是被测物。这也是为什么这张表可以冻结在仓库里而不算 researcher-DoF。

## 缺测怎么办

表里没有的候选 → **不拦**（这道门只会让我们说得更少，不会让我们说得更多），
但产物里记 `calib_unmeasured`，`verify_output` 会对「**存活却没测过**」的候选报红
—— 缺一次测量绝不能变成悄悄放行一条公开结论。

⚠ 本机 VIX3M 历史已丢（CLAUDE.md）→ 本机测出的表必然缺 `vix_backwardation`。
**以 CI 产物为准。**
"""
import json
from pathlib import Path

BASE = Path(__file__).parent.parent
LEVELS_PATH = BASE / "data" / "block_levels.json"

# 只用来决定**先给哪些行花算力测尾巴**，不再决定任何裁决（见上方 docstring）。
# 2.0 这个数与结果相关（是在看到 1.5 会撤两条已发布存活者之后定的），已如实记下。
MAX_LEVEL_RATIO = 2.0

_CACHE = {}


def load(path=None):
    """读冻结表；文件不存在 → 空表（= 谁都不拦，但全部记为未测）。"""
    p = Path(path) if path else LEVELS_PATH
    key = str(p)
    if key not in _CACHE:
        try:
            _CACHE[key] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _CACHE[key] = {"nominal_alpha": 0.10, "rows": {}, "missing_file": True}
    return _CACHE[key]


def clear_cache():
    _CACHE.clear()


def calibrated_p(row, p_obs, n_obs=None):   # n_obs 保留供诊断/将来用，不再当硬条件
    """这条候选**观测到的** p，在 null 分布里有多罕见？

    这是与判定**同处一个位置**的统计量。实测水平说的是「名义 0.10 处会错多少」，
    而跨族 BY 的临界值在 0.000121–0.001696、存活者的 p 常在 0.001 量级 ——
    在 0.10 处量出的数字不能拿来撤一条 p=0.001 的结论（规格 §9）。

    返回 P(null p <= p_obs) 的**保守上界**（取跨过 p_obs 的那个分位档），
    没有分位数据时返回 None。
    """
    if p_obs is None:
        return None
    qs = row.get("null_p_q")
    if not qs:
        return None
    p_obs = float(p_obs)
    # **分辨率守门**：null 侧的 p 是离散格点，下限 = 2/(null_B+1)。
    # 若 p_obs 比这个下限还小，这条尾巴根本**量不到**那么细 ——
    # 此时 `p_obs < 所有 null p` 不是"它极端"，而是"我的尺子刻度不够密"。
    # 实测踩到过：null 侧用 B=300（下限 0.0066）、生产用 B=2000（下限 0.001），
    # 而 `BTC_mom20_pos` 的 recent_p = 0.0007。误用就会把一条已发布的存活者
    # 凭一个截断的尾巴**错误放行**（或在反向写法里错误撤下）。
    # **真正的判据只有一条：p_obs 必须落在 null 这把尺子量得到的区间里**，
    # 即 p_obs >= null_p_floor（= 2/(null_B+1)，null 侧 p 的格点下限）。
    #
    # 我一开始还加了「null_B >= n_obs」—— **那条是错的，已删**：
    # null 比 p_obs 粗并不妨碍定位，只要 p_obs 远在下限之上。
    # null 的经验 CDF 是阶梯函数，取"跨过 p_obs 的那一档分位"本身就是**上界**，
    # 粗一点只会让上界更松（保守），不会把不显著的说成显著。
    # 而那条规则会把 15 行 p 在 0.09~0.998 的候选全判成「无从校准」——
    # 结论虽然同样是拦下，理由却从"校准后 0.5、不够显著"退化成"量不了"，
    # 把能说清的话说糊了；对将来 p 中等的候选还会**错拦**。
    #
    # 真正要挡的是 p_obs **低于** null 下限那种情形：那时
    # 「p_obs 比所有 null p 都小」只是"我的刻度不够密"，不是"它极端"。
    floor = row.get("null_p_floor")
    if floor is not None and p_obs < float(floor):
        return None                         # 不可比 → 交回上层按"无从校准"保守处理
    pairs = sorted((float(q), float(v)) for q, v in qs.items())
    # **严格小于**，不是 `<=`（独立审查 BLOCKER 2，2026-10-09）：
    # 若 `p_obs == v_q` 而该值处有原子（null p 是离散格点，下限处常堆着一坨），
    # 按分位定义只有 `F(v_q) >= q`，F 可以远高于 q —— 此时返回**最小**的并列 q
    # 就变成了**下界**，低估幅度等于整个原子的宽度。
    # 实测：下限原子占 8% 时，p_obs 恰好落在原子上 → 真值 0.08、旧写法返回 0.001（低估 80 倍）。
    # 表里 16 行有尾巴的行里 **12 行** 的 q0.001~q0.05 全部并列，正是会踩中的形状。
    # 改成严格小于 → 跳过所有并列档、落到下一档，重新成为真正的上界。
    # （这是本仓库第三次栽在"低于估计器下限不等于极显著"上 —— F1 修的是生产的 p，
    #   上一条修的是 null 侧的 B，这条是**印给用户看的那个校准后数字**。）
    for q, v in pairs:
        if p_obs < v:
            return q
    return 1.0                              # 比最大分位还大 → 一点都不罕见


def gate(key, p=None, recent_p=None, p_n=None, recent_n=None, table=None):
    """这条候选的检验校准到能下结论吗？

    两道：
      ① **筛子**：某个窗口的实测水平 > 阈值 → 那个窗口的 p 尺度在名义 α 附近不可信；
      ② **裁**：被筛出来的窗口，再问**它自己那个 p** 在 null 下有多罕见
         （`calibrated_p`）。校准后仍 <= α 的，结论照样成立 ——
         尺度被压缩不等于一条 p=0.0004 的发现是噪声。

    **逐窗口判，不是只看最差的那个窗口**：`p`（全段）喂跨族 FDR → 决定 survive_cross；
    `recent_p`（现代段）决定 modern_status → survive 还是 faded。两者各自独立影响裁决，
    所以要各自对着**自己的** p 过这两道。任一窗口过不了 → 整条不下结论。

    返回 dict：measured / ok / level / window / threshold / cal_p
    （level/window/cal_p 报的是**导致判不可判的那个**窗口；全过则报最差窗口的水平。）
    """
    t = table if table is not None else load()
    alpha = float(t.get("nominal_alpha", 0.10))
    thr = alpha * float(t.get("max_level_ratio", MAX_LEVEL_RATIO))
    rows = {k: v for k, v in (t.get("rows") or {}).items()
            if k.split("|")[0] == key}
    scored = [(v["level"], v.get("window", k.split("|")[-1]), v)
              for k, v in rows.items() if v.get("level") is not None]
    if not scored:
        # 没测过，或每个窗口都被 MIN_BLOCKS 挡住（那种情况本来就没有 p）
        return {"measured": bool(rows), "ok": True, "level": None,
                "window": None, "threshold": round(thr, 4), "cal_p": None}

    fails, screened = [], []
    for lv, win, row in scored:
        if lv <= thr:
            continue                                  # 这个窗口的尺度可信
        modern = "现代" in str(win)
        p_obs = recent_p if modern else p
        n_obs = recent_n if modern else p_n          # 这个 p 自己是用多少次重采样算的
        cal = calibrated_p(row, p_obs, n_obs=n_obs)
        screened.append((lv, win, cal))
        if cal is None or cal > alpha:                # 校准后也不显著（或无从校准）
            fails.append((lv, win, cal))
    if fails:
        lv, win, cal = max(fails, key=lambda x: x[0])
        return {"measured": True, "ok": False, "level": round(lv, 4), "window": win,
                "threshold": round(thr, 4),
                "cal_p": (None if cal is None else round(cal, 6))}
    worst, win, _ = max(scored, key=lambda x: x[0])
    # 过了筛子的也报 cal_p：某条水平 0.22 却因为自己的 p 极罕见而放行时，
    # 只给读者看 0.22 会显得比实际更糟 —— 放行的**理由**也要摆出来。
    cal_pass = max((c for _, _, c in screened if c is not None), default=None)
    return {"measured": True, "ok": True, "level": round(worst, 4),
            "window": win, "threshold": round(thr, 4),
            "cal_p": (None if cal_pass is None else round(cal_pass, 6))}


def covers_family(family, table=None):
    """这张表覆不覆盖这一族？

    表里量的是**走块自助**的族。日历族（51 条）走置换检验、是另一台机器，
    旋转 null 量不了它 —— 那是**已知缺口**，不是"漏测"。
    两者必须分开：「本该测却没测」要吵，「这一族本来就不在覆盖范围内」只需如实标注。
    表里没有 `families_covered` 字段（旧表）→ 保守地当作"都覆盖"，宁可多吵一句。
    """
    t = table if table is not None else load()
    fams = t.get("families_covered")
    if fams is None:
        return True
    return family in fams


def reason(g):
    """给用户看的人话 —— 别只说"不可判"，要说清它会错多少。"""
    if g.get("level") is None:
        return "这条规律的检验没有做过校准测量,不下结论"
    n_in = max(int(round(1.0 / g["level"])), 2)
    base = (f"这条规律的检验在{g['window']}上实测会**{n_in} 次里错判 1 次**"
            f"(名义应为 10 次里 1 次)")
    if g.get("cal_p") is None:
        return base + " —— 量具本身没校准,所以不下结论"
    return (base + f"；把它自己的 p 放回同一把尺子上重算,校准后约 {g['cal_p']:.3g}"
                   ",仍不够显著 —— 所以不下结论")


def unmeasured_survivors(cands):
    """存活、却**本该量过校准但没量**的候选 —— `verify_output` 的守门用这个。

    抽成纯函数而不是写在 `verify_output` 里：F1 的 D9/B2 两条 BLOCKER 都是
    「内联的守门没做行为测试、审查随手造的违规写法全绿过」。内联就测不到。

    判据三条同时成立才算：
      · `verdict == "survive"`（只有已发布的结论才值得吵）；
      · `calib_measured` 为假（表里没它）；
      · `calib_family_covered` 为真 —— 日历族走置换检验、旋转 null 量不了它，
        那是**已知缺口**不是漏测；对它吵只会训练人忽略告警。
    缺字段（旧产物）一律视为"不报"，避免把陈旧产物判成违规（B1 的教训）。
    """
    out = []
    for c in cands or []:
        if c.get("verdict") != "survive":
            continue
        if "calib_measured" not in c:          # 旧产物：这道门还没上线过
            continue
        if c.get("calib_measured"):
            continue
        if not c.get("calib_family_covered", True):
            continue                           # 已知缺口，不算漏测
        out.append(c.get("key") or c.get("candidate_id"))
    return sorted(out)

