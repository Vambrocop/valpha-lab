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
