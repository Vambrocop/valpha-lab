"""ticker_ondemand.py — D·C 点单深算：服务端按需算任意美股指标。

读 data/ticker_requests.txt（用户每行一个代码，# 注释）→ 批量抓价 →
复用 build_valpha150.compute_metrics（现价 + 6月/1年涨幅 + 20日年化波动 + 距52周高）
→ ticker_ondemand.json（web/ 与 docs/）。

为什么服务端：澳洲客户端被第三方源 CORS 拦 → 由 CI/本地抓好，前端只读自家 JSON 稳。
非荐股、非预测，纯描述性历史。盘后/手动单独跑（同 wildpool，不入 run_all）：
    py market-analysis/scripts/ticker_ondemand.py
"""
import json
import re
from pathlib import Path
from datetime import date

import pandas as pd
import yfinance as yf

from build_valpha150 import compute_metrics   # 复用纯函数，不重写指标逻辑

BASE = Path(__file__).parent.parent
REQ = BASE / "data" / "ticker_requests.txt"
MAX = 40                                       # 有界上限：防一次抓太多/滥用


def _read_requests():
    """解析点单文件：去注释/空行、大写、去重、校验代码字符、截到 MAX。"""
    if not REQ.exists():
        return []
    out = []
    for line in REQ.read_text(encoding="utf-8").splitlines():
        s = line.split("#", 1)[0].strip().upper()
        if s and re.fullmatch(r"[A-Z0-9.\-]{1,8}", s) and s not in out:
            out.append(s)
    return out[:MAX]


def build_all():
    reqs = _read_requests()
    rows, miss = [], []
    if not reqs:
        print("无点单（data/ticker_requests.txt 为空）；写空 JSON")
    else:
        print(f"点单 {len(reqs)} 只：{reqs}")
        px = yf.download(reqs, period="2y", interval="1d",
                         auto_adjust=True, progress=False)["Close"]
        for s in reqs:
            if isinstance(px, pd.Series):              # 单只时 ["Close"] 返回 Series
                col = px
            elif s in getattr(px, "columns", []):
                col = px[s]
            else:
                col = None
            if col is None or col.dropna().empty:
                miss.append(s)
                continue
            m = compute_metrics(col)
            if m is None:
                miss.append(s + "(史短)")
                continue
            rows.append({"t": s, **m})

    out = {"generated": date.today().isoformat(), "n": len(rows),
           "requested": reqs, "stocks": rows, "missing": miss}
    for d in [BASE / "web", BASE.parent / "docs"]:
        (d / "ticker_ondemand.json").write_text(
            json.dumps(out, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
    print(f"[OK] {len(rows)}/{len(reqs)} 只 → ticker_ondemand.json"
          + (f"；缺: {miss}" if miss else ""))


if __name__ == "__main__":
    build_all()
