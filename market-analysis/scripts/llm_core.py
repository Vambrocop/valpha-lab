"""llm_core.py — provider-agnostic LLM helpers shared by llm_daily_read and llm_weekly_read.

Extracted to break the dependency-disorder anti-pattern where llm_weekly_read imported
private (_-prefixed) symbols from llm_daily_read.

Contains only:
  - Model/URL constants (Gemini default)
  - _provider() / _llm_key() / _active_model()  — env-driven provider selection
  - _gemini()                                     — raw Gemini HTTP call
  - _llm()                                        — unified entry point (Gemini or OpenAI-compat)
  - _GLOSS + _plainify()                          — jargon glossary + annotation helper

Does NOT import from llm_daily_read or llm_weekly_read (no circular dependency).
"""
import json
import os
import urllib.request

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

# ── provider selection ────────────────────────────────────────────────────────

def _provider():
    # ⚠️ Use `or`, not .get(default): CI passes unset secrets as empty strings.
    # .get("LLM_PROVIDER","gemini") returns "" when the var exists but is empty,
    # bypassing the default → provider="" falls through to LLM_API_KEY (also empty)
    # → skips push every run.  Empty string must fall back to "gemini".
    return (os.environ.get("LLM_PROVIDER") or "gemini").lower()


def _llm_key():
    return os.environ.get("GEMINI_API_KEY") if _provider() == "gemini" else os.environ.get("LLM_API_KEY")


def _active_model():
    return MODEL if _provider() == "gemini" else os.environ.get("LLM_MODEL", "deepseek-chat")


# ── Gemini HTTP call ──────────────────────────────────────────────────────────

def _gemini(prompt, key):
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 400},
    }).encode("utf-8")
    req = urllib.request.Request(URL.format(model=MODEL, key=key), data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.load(r)
    # Defensive extraction: raise on unexpected structure; caller's try/except handles it.
    return out["candidates"][0]["content"]["parts"][0]["text"].strip()


# ── unified LLM entry point ───────────────────────────────────────────────────

def _llm(prompt):
    """Unified entry point. Gemini via _gemini(); others via OpenAI-compat /chat/completions
    (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL env vars)."""
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


# ── jargon glossary + annotation helper ──────────────────────────────────────

_GLOSS = [
    ("VIX", "衡量市场恐慌情绪，越高越慌"),
    ("收益率曲线", "不同期限国债利率的高低对比，倒挂常被当衰退预警"),
    ("信用利差", "企业借钱比国债贵多少，越大=市场越担心违约"),
    ("相关性", "各只股票是不是一起涨跌，越高越像同涨同跌"),
    ("分散性", "不同股票走势分化的程度，分化大=分散投资更有效"),
]


def _plainify(text):
    """给 LLM 解读里的专业词，在【首次出现】且其后没有现成解释时补一句大白话括注。
    与新版 prompt 互补：prompt 让 LLM 自解释（其后接「（」就跳过，不重复）；此函数兜底旧文本。"""
    if not text:
        return text
    for term, exp in _GLOSS:
        i = text.find(term)
        if i < 0:
            continue
        if text[i + len(term): i + len(term) + 1] in ("（", "("):
            continue
        text = text[:i + len(term)] + f"（{exp}）" + text[i + len(term):]
    return text


# ── 大白话解读的英文版(2026-09-07·用户拍板"让 LLM 出英文版") ─────────────────
_EN_PROMPT = """Translate the following Chinese market commentary into natural, plain English.

Rules — these matter more than fluency:
1. **Translate, do not re-analyse.** Never add a view, a number, or a caveat that is not in the
   source. Never drop one either — especially the disclaimers.
2. Keep every number, percentage, date and ticker **exactly** as written.
3. Match the register: this is written for a complete beginner. Avoid jargon; where the Chinese
   explains a term, explain it the same way.
4. Output the translation only — no preamble, no notes, no markdown fences.

Chinese source:
{text}"""


def translate_read(text):
    """把已生成的中文解读翻成英文。**翻译,不是重新生成。**

    ## 为什么是翻译而不是"用同一份数据再生成一版英文"

    独立生成会让两个版本**说不一样的话** —— 英文读者看到的结论与中文不同。在一个双语的
    诚实计分站点上这是硬伤(同 market_regime/composite_read 档位表"中英同源"的道理:
    两套分支迟早漂移)。翻译则保证两边永远一致,顺带还便宜些(提示词短得多)。

    失败一律返回 None(缺 key / 调用失败 / 空返回)。**绝不编一句英文** ——
    前端 vpD() 在缺英文时回落中文,宁可显示中文,也不显示一段来路不明的英文。
    """
    if not text or not str(text).strip():
        return None
    if not _llm_key():
        return None
    try:
        en = _llm(_EN_PROMPT.format(text=text))
    except Exception as e:                      # 非致命:英文缺失只是少一份译文,不阻断流水线
        print(f"[LLM英文版] 调用失败(非致命,前端回落中文): {e}")
        return None
    en = (en or "").strip()
    return en or None
