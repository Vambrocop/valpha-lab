"""notify_telegram.py — Telegram 推送（可选渠道，无新依赖，纯 stdlib）。

读环境变量 TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID（GitHub Secrets / 本地 env）。
未配置则静默跳过（不报错、不阻断流水线）——供 alert_check 等调用，也可单独测试。

为什么纯 stdlib：流水线不引新依赖；api.telegram.org 一个 POST 就够（GitHub 服务器可达，
澳洲手机正常收）。token/chat_id 只走 Secrets，绝不进仓库。

本地自测（不会让我看到你的 token）：
    $env:TELEGRAM_BOT_TOKEN='123:abc'; $env:TELEGRAM_CHAT_ID='你的id'
    py market-analysis/scripts/notify_telegram.py "测试一下"
"""
import os
import sys
import json
import datetime
import urllib.request
from pathlib import Path

API = "https://api.telegram.org/bot{token}/sendMessage"


def _log_status(ok, tag, note=""):
    """把每次推送尝试留痕到 telegram_status.json(web+docs)——让「到底推没推/为啥没推」可查不靠猜。
    只记 时间/成败/标签/简短原因,不记消息正文(避免泄露 + 没必要)。"""
    try:
        rec = {"ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "ok": bool(ok), "tag": str(tag), "note": str(note)[:120]}
        base = Path(__file__).parent.parent
        for d in (base / "web", base.parent / "docs"):
            if not d.exists():
                continue
            p = d / "telegram_status.json"
            hist = []
            if p.exists():
                try:
                    hist = json.loads(p.read_text(encoding="utf-8")).get("recent", [])
                except Exception:
                    hist = []
            hist = ([rec] + hist)[:20]                  # 只留最近 20 条
            p.write_text(json.dumps({"updated": rec["ts"], "recent": hist},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def send(text, parse_mode=None, tag="msg"):
    """发一条 Telegram 消息。返回 True/False；未配置或失败均不抛异常（流水线不被拖垮）。
    每次尝试留痕到 telegram_status.json(tag 区分来源:daily/overreaction/alert…)。"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        _log_status(False, tag, "未配置 TELEGRAM_BOT_TOKEN/CHAT_ID")
        return False                                   # 未配置 → 静默跳过
    payload = {"chat_id": chat, "text": (text or "")[:4000],
               "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API.format(token=token), data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            ok = 200 <= r.status < 300
            print("[Telegram] 已推送" if ok else f"[Telegram] 响应 {r.status}")
            _log_status(ok, tag, "" if ok else f"HTTP {r.status}")
            return ok
    except Exception as e:
        print(f"[Telegram] 推送失败（非致命）: {e}")
        _log_status(False, tag, repr(e))               # 401=token被吊销 / 403=未/start / 400=chat_id错 一眼可辨
        return False


_FOOTER_LINK = "🔗 vambrocop.github.io/valpha-lab/"
_FOOTER_DISC = "（实验性·只读真实算出的数据·会错·已公开计分认账）"


def footer(extra: str = "") -> str:
    """返回标准消息尾巴：链接行 + 免责行（extra 非空时替换免责行）。
    调用方把 footer() 拆成两行插入消息列表：
        lines += footer().splitlines()
    或直接 append：
        lines += ["", _FOOTER_LINK, _FOOTER_DISC]
    """
    disc = extra if extra else _FOOTER_DISC
    return f"{_FOOTER_LINK}\n{disc}"


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) or "Valpha Lab Telegram 推送自测 ✅"
    if not send(msg):
        print("未发送：检查 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 是否已设。")
