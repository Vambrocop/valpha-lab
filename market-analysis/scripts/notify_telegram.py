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
import urllib.request

API = "https://api.telegram.org/bot{token}/sendMessage"


def send(text, parse_mode=None):
    """发一条 Telegram 消息。返回 True/False；未配置或失败均不抛异常（流水线不被拖垮）。"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
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
            return ok
    except Exception as e:
        print(f"[Telegram] 推送失败（非致命）: {e}")
        return False


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) or "Valpha Lab Telegram 推送自测 ✅"
    if not send(msg):
        print("未发送：检查 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 是否已设。")
