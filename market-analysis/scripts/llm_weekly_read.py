"""llm_weekly_read.py — LLM「本周回顾」周报（grounded · 诚实 · 带计分）。

把本周【真实算出】的数据聚合成紧凑事实摘要，喂给 LLM 翻成初学者大白话回顾。
铁律（CLAUDE.md「LLM 必须喂真数据、防瞎编」）：
  - 只解释给定数字、不许编、不点具体买卖、带免责
  - LLM 只负责"翻译成人话"，不负责"算出数字"
  - 若数据不足（< 3 天）强制降置信，加不足警告

数据来源（均为真实算出，脚本写出 → 读入）：
  data/composite_log.csv         — 本周各日 stance/score 趋势
  web/market_regime.json         — VIX/收益率曲线/信用利差/体制标签
  web/scorecard.json             — 模型基准胜率（不是预测命中，是回测校准）
  web/valpha150.json             — 152 只股票近一周涨跌（chg_5d = w1 字段）

写 web/llm_weekly.json（via util_io.write_json）。
周级 append-only 账本 data/llm_weekly_log.csv（ISO-week 去重：YYYY-Www）。

本地自测（无 key → 静默跳过）：
    $env:GEMINI_API_KEY='AIza...'; py market-analysis/scripts/llm_weekly_read.py
"""
import csv
import datetime
import json
import sys
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────────────────────────────
SCRIPTS = Path(__file__).parent
BASE    = SCRIPTS.parent                             # market-analysis/
WEB     = BASE / "web"
DATA    = BASE / "data"
LOG     = DATA / "llm_weekly_log.csv"

# ── 复用日读的 provider 无关 LLM 路径（import 而非重写，保持 DRY）────────────
sys.path.insert(0, str(SCRIPTS))
from llm_daily_read import _llm, _llm_key, _active_model, _plainify  # noqa: E402

# ── 周报 Prompt ───────────────────────────────────────────────────────────────
WEEKLY_PROMPT = """你是给【完全不懂金融的新手】讲解的助手。下面是本周系统【真实算出】的市场读数摘要：

本周日期：{week_label}
本周综合倾向变化（每日真实加权读数）：
{stance_lines}
本周末市场环境（客观描述，非预测）：
{regime_lines}
追踪记录参考（历史回测，非 live 预测）：基准胜率 {base_rate_pct}%（样本 {n_total} 个）
{movers_block}

请用 4-6 句【大白话中文】，向一个新手解释「本周市场大环境发生了什么、倾向变化方向、有什么值得关注的结构信号」。
铁律：
1. 只用上面给出的数字/事实，绝不编造任何未给出的数据、新闻、事件或具体原因；
2. 【说人话】凡用到专业词（如 VIX、收益率曲线、信用利差、相关性/共动），必须紧跟一个小括号、用最朴素一句话解释（例：「VIX（衡量市场恐慌程度的指标，越高越慌）」）；
3. 不要出现内部打分数字（如 0.13、0.52）；用"偏积极／偏防御／中性、略有收紧／略有放松"这类词表达程度；
4. 不点任何具体股票名、不说"买入/卖出某某"；
5. 若股票涨跌数据中有极端表现，可提板块或范围，不点个股；
6. 结尾加一句"（这是数据读数不是预测，会错，过去不代表未来）"；
7. 若上面「数据天数」为「不足3天」：你【只能】给"弱/不确定"倾向，必须先加一句"⚠️ 本周数据不充分（{n_days}天），本读数可信度低"。
只输出解读文字本身，不要标题、不要列表、不要重复上面的数字清单。"""


# ── 聚合：composite_log → 本周条目 ───────────────────────────────────────────

def _iso_week(d: datetime.date) -> str:
    """返回 ISO-week 字符串 YYYY-Www，用作去重 key。"""
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def _week_label(d: datetime.date) -> str:
    """人类可读的周标签：起始-结束，例如 2026-06-22 ~ 2026-06-28。"""
    monday = d - datetime.timedelta(days=d.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return f"{monday.isoformat()} ~ {sunday.isoformat()}"


def _load_composite_week(today: datetime.date) -> list:
    """从 composite_log.csv 取本 ISO-week 的所有行（含今天）。
    若文件不存在返回空列表（防御性降级）。"""
    path = DATA / "composite_log.csv"
    if not path.exists():
        return []
    current_week = _iso_week(today)
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    d = datetime.date.fromisoformat(row["date"])
                except (KeyError, ValueError):
                    continue
                if _iso_week(d) == current_week:
                    rows.append({"date": row["date"],
                                 "stance": row.get("stance", ""),
                                 "score": row.get("score", "")})
    except Exception:
        return []
    return rows


def _format_stance_lines(rows: list) -> tuple:
    """把本周各日 stance 格式化为可喂进 prompt 的字符串，同时返回 stance 列表供 JSON 存储。
    score 转为程度词，不暴露原始数值。"""
    if not rows:
        return "（本周暂无综合读数数据）", []
    stances = []
    lines = []
    for r in rows:
        date_s = r["date"]
        stance = r["stance"] or "未知"
        stances.append(stance)
        # score → 程度词（不暴露原始浮点）
        try:
            sc = float(r["score"])
        except (ValueError, TypeError):
            sc = None
        if sc is None:
            degree = ""
        elif sc >= 0.4:
            degree = "（偏积极·较强）"
        elif sc >= 0.13:
            degree = "（偏积极·偏弱）"
        elif sc > -0.13:
            degree = "（中性）"
        elif sc > -0.4:
            degree = "（偏防御·偏弱）"
        else:
            degree = "（偏防御·较强）"
        lines.append(f"  {date_s}: {stance}{degree}")
    return "\n".join(lines), stances


def _load_regime() -> list:
    """从 market_regime.json 提取描述性体制标签行（不暴露内部分位数值）。
    返回人类可读字符串列表；若文件缺失返回空列表。"""
    path = WEB / "market_regime.json"
    if not path.exists():
        return []
    try:
        reg = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    lines = []
    for c in reg.get("components", []):
        name = c.get("name", "")
        label = c.get("label", "")
        val   = c.get("value")
        asof  = c.get("asof", "")
        # 包含真实测量值 + 标签（均为系统算出）
        if val is not None and label:
            lines.append(f"  {name}：{val}（标签：{label}，数据至 {asof}）")
        elif label:
            lines.append(f"  {name}：{label}（数据至 {asof}）")
    if reg.get("composite"):
        lines.append(f"  综合环境：{reg['composite']}")
    return lines


def _load_scorecard_summary() -> tuple:
    """返回 (base_rate_pct_str, n_total_str)；文件缺失返回 ('—', '—')。"""
    path = WEB / "scorecard.json"
    if not path.exists():
        return "—", "—"
    try:
        sc = json.loads(path.read_text(encoding="utf-8"))
        cal = sc.get("model_calibration", {})
        return str(cal.get("base_rate_pct", "—")), str(cal.get("n_total", "—"))
    except Exception:
        return "—", "—"


def _load_movers(top_n: int = 3) -> str:
    """从 valpha150.json 取近一周（w1 字段）涨/跌幅最大的各 top_n 只，
    只暴露涨跌幅+板块，不点股票名（prompt 约束）。
    若文件缺失或 w1 全为 null 返回空字符串。"""
    path = WEB / "valpha150.json"
    if not path.exists():
        return ""
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    stocks = v.get("stocks", [])
    valid = [s for s in stocks if s.get("w1") is not None]
    if not valid:
        return ""
    ranked = sorted(valid, key=lambda s: s.get("w1", 0))
    bottom = ranked[:top_n]   # 跌幅最大（最小 w1）
    top    = ranked[-top_n:][::-1]  # 涨幅最大

    def fmt(s_list, label):
        items = []
        for s in s_list:
            sec = s.get("sec", "未知板块")
            w1  = s.get("w1", 0)
            items.append(f"{sec}({'+' if w1 >= 0 else ''}{w1:.1f}%)")
        return f"{label}（板块·近一周）：{', '.join(items)}"

    lines = [
        fmt(top, "涨幅领先"),
        fmt(bottom, "跌幅靠前"),
    ]
    generated = v.get("generated", "")
    if generated:
        lines.append(f"（数据截至 {generated}，共 {len(stocks)} 只）")
    return "\n".join(lines)


# ── 数据质量覆盖判断 ──────────────────────────────────────────────────────────

def _coverage_label(n_days: int) -> str:
    if n_days >= 4:
        return "充分"
    elif n_days >= 3:
        return "有限"
    else:
        return f"不足3天（实际{n_days}天）"


# ── 主聚合入口（可在测试中独立调用）─────────────────────────────────────────

def build_weekly_summary(today=None):
    """聚合本周真实数据 → 返回 dict 供 prompt 使用和测试验证。
    所有数字来自磁盘文件，不由 LLM 推算。"""
    if today is None:
        today = datetime.date.today()

    rows = _load_composite_week(today)
    stance_text, stances = _format_stance_lines(rows)
    n_days = len(rows)

    regime_lines = _load_regime()
    regime_text  = "\n".join(regime_lines) if regime_lines else "（市场环境数据暂缺）"

    base_rate_pct, n_total = _load_scorecard_summary()

    movers_block = _load_movers()
    if movers_block:
        movers_block = "本周板块涨跌分布（真实价格数据，非预测）：\n" + movers_block

    coverage = _coverage_label(n_days)

    return {
        "week_of":       _iso_week(today),
        "week_label":    _week_label(today),
        "n_days":        n_days,
        "coverage":      coverage,
        "stance_trend":  stances,
        "stance_text":   stance_text,
        "regime_text":   regime_text,
        "base_rate_pct": base_rate_pct,
        "n_total":       n_total,
        "movers_block":  movers_block,
    }


# ── 日志追加（ISO-week 去重）─────────────────────────────────────────────────

def _append_log(week_key: str, stance_trend: list, text: str) -> bool:
    """append-only；同 ISO-week 只记一条。返回是否新写。"""
    from util_io import append_daily_log  # lazy import 与 llm_daily_read 一致
    trend_str = "→".join(stance_trend) if stance_trend else ""
    return append_daily_log(
        LOG,
        ["week", "stance_trend", "text"],
        [[week_key, trend_str, (text or "").replace("\n", " ")]],
        date=week_key,        # util_io 用 date 参数做去重
    )


# ── 主入口 ───────────────────────────────────────────────────────────────────

def run():
    if not _llm_key():
        print("[LLM周报] 未配置 LLM key（GEMINI_API_KEY 或 LLM_API_KEY），跳过")
        return None

    today = datetime.date.today()
    summary = build_weekly_summary(today)

    # 构建 prompt
    prompt = WEEKLY_PROMPT.format(
        week_label    = summary["week_label"],
        stance_lines  = summary["stance_text"],
        regime_lines  = summary["regime_text"],
        base_rate_pct = summary["base_rate_pct"],
        n_total       = summary["n_total"],
        movers_block  = summary["movers_block"] or "（近一周个股数据暂缺）",
        n_days        = summary["n_days"],
    )

    try:
        text = _llm(prompt)
    except Exception as e:
        print(f"[LLM周报] LLM 调用失败（非致命，不阻断流水线）: {e}")
        return None

    if not text:
        print("[LLM周报] 空返回，跳过")
        return None

    # 安全兜底：补充专业词大白话括注
    text = _plainify(text)

    week_key = summary["week_of"]
    out = {
        "generated":    datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model":        _active_model(),
        "week_of":      week_key,
        "week_label":   summary["week_label"],
        "n_days":       summary["n_days"],
        "coverage":     summary["coverage"],
        "stance_trend": summary["stance_trend"],
        "text":         text,
        "caveat": (
            "LLM 据本周真实算出因子生成的大白话回顾；喂真数据防瞎编，但仍可能误读。"
            "非预测、非荐股、会错，过去≠未来。每周 append 到 llm_weekly_log 公开计分。"
        ),
    }

    from util_io import write_json
    write_json("llm_weekly.json", out)

    wrote = _append_log(week_key, summary["stance_trend"], text)
    print(
        f"[OK] llm_weekly.json — {week_key} · {len(text)} 字"
        + ("" if wrote else "（本周已记，不重复）")
    )

    if wrote:
        try:
            import notify_telegram
            lines = [
                f"📅 Valpha Lab 本周回顾 · {summary['week_label']}",
                "",
                _plainify(text),
                "",
                "🔗 vambrocop.github.io/valpha-lab/",
                "（数据读数·会错·非预测·已公开计分认账）",
            ]
            notify_telegram.send("\n".join(lines), tag="weekly")
        except Exception:
            pass

    return out


if __name__ == "__main__":
    run()
