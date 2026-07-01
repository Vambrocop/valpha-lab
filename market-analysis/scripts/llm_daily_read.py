"""llm_daily_read.py — LLM 大白话日读（出格区·grounded·带计分）。

把当天【真实算出】的 composite_read.json（体制/信用/羊群/季节/方向 各因子 + 倾向）
喂给 Gemini，让它翻成一段初学者能懂的人话解读。铁律（CLAUDE.md「LLM 必须喂真数据、防瞎编」）：
只解释给定数字、不许编、不点具体买卖、带免责。写 llm_read.json + append llm_read_log.csv（可追责）。

读 GEMINI_API_KEY（GitHub Secrets / 本地 env）；未配置静默跳过（不阻断流水线）。
非预测、非荐股、出格区娱乐参考。本地自测：
    $env:GEMINI_API_KEY='AIza...'; py market-analysis/scripts/llm_daily_read.py
"""
import os
import json
import datetime
from pathlib import Path

# ── shared LLM helpers (provider-agnostic) ───────────────────────────────────
from llm_core import (  # noqa: F401  (re-exported for back-compat: tests may import these)
    MODEL, URL,
    _provider, _llm_key, _active_model,
    _gemini, _llm,
    _GLOSS, _plainify,
)

SCRIPTS = Path(__file__).parent
WEB = SCRIPTS.parent / "web"
DOCS = SCRIPTS.parent.parent / "docs"
LOG = SCRIPTS.parent / "data" / "llm_read_log.csv"        # append-only 计分账本
TG_PUSH_STATE = SCRIPTS.parent / "data" / "processed" / "tg_daily_push_state.json"  # dedup: last push date

PROMPT = """你是给【完全不懂金融的新手】讲解的助手。下面是今天系统【真实算出】的市场读数（综合多个诚实因子）：

数据质量：{quality}
倾向：{stance}（内部打分 {score}，范围 -1 极防御 ~ +1 极积极）
各因子（含真实数值）：
{factors}
{survivors}
请用 3-4 句【大白话中文】，向一个新手解释「今天数据在说什么、当前该偏防御还是偏积极、为什么」。
铁律：
1. 只用上面给出的数字/事实，绝不编造任何未给出的数据、新闻或事件；
2. 【说人话】凡用到专业词（如 VIX、收益率曲线、信用利差、相关性/共动、波动率），必须紧跟一个小括号、用最朴素的一句话解释它是什么，就像讲给一个从没买过股票的朋友听（例：「VIX（衡量市场恐慌程度的指标，越高越慌）」）；
3. 不要出现 "0.1""0.52" 这类内部打分数字；用"偏积极／偏防御／中性、强一点／弱一点"这种词来表达程度；
4. 不点任何具体股票、不说"买入/卖出某某"；
5. 结尾加一句"（这是数据读数不是预测，会错，过去不代表未来）"；
6. 若上面「数据质量」为「有限」或「不足」：你【只能】给"弱/不确定"的倾向、不得给强方向判断，且必须先加一句"⚠️ 今日数据质量不充分，本读数可信度低"。
7. 若给了「存活规律观察台」：**只有标【应期】的**才是今天成立的历史规律，可用最多一句话自然带过；标【休眠】或【未接入】的今天不成立/未监测，**绝不能**说成当前在起作用、看涨或看跌；提到某条时用它给出的组别原文(如"非九月"上涨率)，别把对照组的数字安到条件本身头上；这些都是描述性历史统计、非预测，"扛过检验"也不等于下次一定灵。不要逐条罗列。
只输出解读文字本身，不要标题、不要列表、不要重复上面的数字清单。"""


def _quality(cr, facs):
    """覆盖度 + 新鲜度 → 数据质量等级，喂进 prompt 强制降置信（吸收 daily_stock 的 ContextPack 思想）。"""
    n = len(facs)
    asof = cr.get("asof") or (cr.get("generated") or "")[:10]
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(asof)).days
    except Exception:
        age = 99
    lvl = "充分" if (n >= 5 and age <= 4) else ("有限" if n >= 3 else "不足")
    return f"{lvl}（覆盖 {n} 个因子，数据 {age} 天前）", lvl


def _nasdaq_plain(ic):
    """纳指方向 → 大白话 + 诚实标定：prob≈0.5 就直说掷硬币，绝不把 52% 装成「看涨」。"""
    if not ic or ic.get("prob") is None:
        return ""
    pct = round(ic["prob"] * 100)
    horizon = ic.get("horizon") or "短期"
    direction = "偏跌" if ic["prob"] < 0.5 else "偏涨"
    note = ("≈掷硬币，这个信号没有验证过的优势，别太当真"
            if abs(pct - 50) <= 4 else "短期方向谁都难测，仅供参考")
    return f"纳指{horizon}：约 {pct}% {direction}（{note}）"


def _survivors_block():
    """存活规律观察台 → prompt 文本；缺文件/空则返回空串（优雅降级，不改动其余读数）。"""
    try:
        sd = json.loads((WEB / "survivors_live.json").read_text(encoding="utf-8"))
    except Exception:
        return ""
    rows = sd.get("survivors") or []
    if not rows:
        return ""
    lines = []
    for s in rows:
        flag = "应期" if s.get("active") is True else ("休眠" if s.get("active") is False else "未接入")
        lines.append(f"- [{flag}] {s.get('name')}：{s.get('state')}。历史：{s.get('edge_plain')}")
    return ("存活规律观察台（扛过多重检验的历史规律，仅描述性；应期=今天成立、休眠=今天不成立勿当信号、"
            "未接入=当前态未监测只有历史）：\n" + "\n".join(lines) + "\n")


def _tg_already_pushed_today(today_str: str) -> bool:
    """Return True if we already pushed Telegram for today (dedup across CI retries)."""
    try:
        state = json.loads(TG_PUSH_STATE.read_text(encoding="utf-8"))
        return state.get("last") == today_str
    except Exception:
        return False


def _tg_mark_pushed(today_str: str) -> None:
    """Record today as the last pushed date."""
    try:
        TG_PUSH_STATE.write_text(
            json.dumps({"last": today_str}, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def _append_log(today, stance, text):
    """append-only；同日只记一条。返回是否新写（用于 Telegram 一天只推一次）。"""
    from util_io import append_daily_log
    return append_daily_log(LOG, ["date", "stance", "text"],
                            [[today, stance, (text or "").replace("\n", " ")]], date=today)


def run():
    if not _llm_key():
        print("[LLM日读] 未配置 LLM key（GEMINI_API_KEY 或 LLM_API_KEY），跳过")
        return None
    try:
        cr = json.loads((WEB / "composite_read.json").read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[LLM日读] 读 composite_read.json 失败，跳过: {e}")
        return None
    facs = cr.get("factors", [])
    factors = "\n".join(f"- {f.get('name')}：{f.get('reason')}" for f in facs)
    quality, qlevel = _quality(cr, facs)
    prompt = PROMPT.format(quality=quality, stance=cr.get("stance"), score=cr.get("score"),
                           factors=factors, survivors=_survivors_block())
    try:
        text = _llm(prompt)
    except Exception as e:
        print(f"[LLM日读] LLM 调用失败（非致命，不阻断流水线）: {e}")
        return None
    if not text:
        print("[LLM日读] 空返回，跳过")
        return None
    today = datetime.date.today().isoformat()
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": _active_model(), "date": today,
        "stance": cr.get("stance"), "score": cr.get("score"), "text": text, "coverage_level": qlevel,
        "caveat": "LLM 据当日真实因子生成的大白话解读；喂真数据防瞎编，但仍可能误读。"
                  "非预测、非荐股、会错，过去≠未来。每日 append 到 llm_read_log 公开计分。",
    }
    from util_io import write_json
    write_json("llm_read.json", out)
    wrote = _append_log(today, cr.get("stance"), text)
    print(f"[OK] llm_read.json — {cr.get('stance')} · {len(text)} 字" + ("" if wrote else "（今日已记，不重复）"))
    # Telegram push: only from post-close CI run (TG_DAILY_PUSH=true), once per day.
    # Decoupled from `wrote` so pre-open runs (which may append the log first) don't
    # fire the push on yesterday's data.  A tiny state file prevents double-push on
    # CI retries within the same post-close window.
    if os.environ.get("TG_DAILY_PUSH") == "true":
        if _tg_already_pushed_today(today):
            print("[LLM日读] Telegram 今日已推，跳过重复（dedup）")
        else:
            try:
                import notify_telegram
                try:
                    ic = (json.loads((WEB / "outlook.json").read_text(encoding="utf-8")).get("index_call") or {})
                except Exception:
                    ic = {}
                lines = [f"🧠 Valpha Lab 今日读数 · 数据截至 {cr.get('asof') or today}"]
                if cr.get("action"):
                    cf = cr.get("confidence_level")
                    lines.append(f"📊 今日结论：{cr['action']}" + (f"（把握：{cf}）" if cf else ""))
                np_line = _nasdaq_plain(ic)
                if np_line:
                    lines.append(f"📈 {np_line}")
                lines += ["", _plainify(text), ""] + notify_telegram.footer().splitlines()
                notify_telegram.send("\n".join(lines), tag="daily")
                _tg_mark_pushed(today)
            except Exception:
                pass
    return out


if __name__ == "__main__":
    run()
