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
import csv
import datetime
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).parent
WEB = SCRIPTS.parent / "web"
DOCS = SCRIPTS.parent.parent / "docs"
LOG = SCRIPTS.parent / "data" / "llm_read_log.csv"        # append-only 计分账本
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")   # 此 key 免费额度在 lite 上(2.0-flash 该项目 limit:0)
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

PROMPT = """你是给投资初学者讲解的助手。下面是今天系统【真实算出】的市场读数（综合多个诚实因子）：

数据质量：{quality}
倾向：{stance}（打分 {score}，范围 -1 极防御 ~ +1 极积极）
各因子（含真实数值）：
{factors}

请用 2-3 句【大白话中文】，向一个新手解释「今天数据在说什么、当前该偏防御还是偏积极、为什么」。
铁律：
1. 只用上面给出的数字/事实，绝不编造任何未给出的数据、新闻或事件；
2. 不点任何具体股票、不说"买入/卖出某某"；
3. 结尾加一句"（这是数据读数不是预测，会错，过去不代表未来）"；
4. 若上面「数据质量」为「有限」或「不足」：你【只能】给"弱/不确定"的倾向、不得给强方向判断，且必须先加一句"⚠️ 今日数据质量不充分，本读数可信度低"。
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


def _gemini(prompt, key):
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 400},
    }).encode("utf-8")
    req = urllib.request.Request(URL.format(model=MODEL, key=key), data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.load(r)
    # 防御式取值：候选/parts 结构异常时抛错由上层 try 兜住
    return out["candidates"][0]["content"]["parts"][0]["text"].strip()


# ── provider 无关：默认 Gemini；设 LLM_PROVIDER=openai 走 OpenAI 兼容(DeepSeek/OpenAI/Ollama 等) ──
def _provider():
    return os.environ.get("LLM_PROVIDER", "gemini").lower()


def _active_model():
    return MODEL if _provider() == "gemini" else os.environ.get("LLM_MODEL", "deepseek-chat")


def _llm_key():
    return os.environ.get("GEMINI_API_KEY") if _provider() == "gemini" else os.environ.get("LLM_API_KEY")


def _llm(prompt):
    """统一入口。Gemini 走 _gemini；其余走 OpenAI 兼容 /chat/completions（LLM_BASE_URL/API_KEY/MODEL）。"""
    if _provider() == "gemini":
        return _gemini(prompt, os.environ["GEMINI_API_KEY"])
    base = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
    body = json.dumps({"model": _active_model(),
                       "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.4, "max_tokens": 400}).encode("utf-8")
    req = urllib.request.Request(base + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {os.environ['LLM_API_KEY']}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.load(r)
    return out["choices"][0]["message"]["content"].strip()


def _append_log(today, stance, text):
    """append-only；同日只记一条。返回是否新写（用于 Telegram 一天只推一次）。"""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if LOG.exists():
        with open(LOG, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        if len(rows) > 1 and rows[-1][0] == today:
            return False
    new = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "stance", "text"])
        w.writerow([today, stance, (text or "").replace("\n", " ")])
    return True


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
    prompt = PROMPT.format(quality=quality, stance=cr.get("stance"), score=cr.get("score"), factors=factors)
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
    if wrote:                                            # 一天只推一次 Telegram
        try:
            import notify_telegram
            notify_telegram.send(f"🧠 Valpha Lab 今日读数（{cr.get('stance')}）\n\n{text}")
        except Exception:
            pass
    return out


if __name__ == "__main__":
    run()
