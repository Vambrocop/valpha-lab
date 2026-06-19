"""
export_fx.py
导出货币换算汇率给前端（CGT 计算器的"显示货币"切换用）。

输出：web/fx_rates.json  ——  {aud_usd, usd_cny, generated, source}
  · aud_usd  : 1 AUD = ? USD   （来自 Yahoo AUDUSD=X，约 0.70）
  · usd_cny  : 1 USD = ? CNY   （来自 Yahoo CNY=X，约 7.x）
run_all.py 末步会把 web/ 整体镜像到 docs/，无需在此手动拷贝。

⚠ 这只是"最新一日"的单点汇率，仅供前端把金额换个币种方便查看/估算；
   澳洲 CGT 法定按 AUD、且买入/卖出各按成交日汇率计税——单点汇率不能替代按成交日记账报税。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
WEB_DIR = Path(__file__).parent.parent / "web"
WEB_DIR.mkdir(exist_ok=True)

OUT = WEB_DIR / "fx_rates.json"


def _latest(series: pd.Series):
    """取一列最后一个有效（非 NaN、>0）值，连同其日期。"""
    s = pd.to_numeric(series, errors="coerce").dropna()
    s = s[s > 0]
    if s.empty:
        return None, None
    return float(s.iloc[-1]), str(s.index[-1].date())


def main():
    combined_path = RAW_DIR / "combined_prices.csv"
    aud_usd = usd_cny = None
    asof = None

    if combined_path.exists():
        df = pd.read_csv(combined_path, index_col=0, parse_dates=True)
        if "AUD" in df.columns:          # AUDUSD=X → 1 AUD = ? USD
            aud_usd, d1 = _latest(df["AUD"])
            asof = d1 or asof
        if "CNY" in df.columns:          # CNY=X → 1 USD = ? CNY
            usd_cny, d2 = _latest(df["CNY"])
            asof = d2 or asof
    else:
        print(f"  ! 缺 {combined_path}（先跑 fetch_data.py）")

    # 单列缺失时各自回退上次产物，不让整文件作废
    if (aud_usd is None or usd_cny is None) and OUT.exists():
        try:
            with open(OUT, encoding="utf-8") as f:
                old = json.load(f)
            aud_usd = aud_usd if aud_usd is not None else old.get("aud_usd")
            usd_cny = usd_cny if usd_cny is not None else old.get("usd_cny")
            print("  ⚠ 部分汇率缺失，沿用上次 fx_rates.json")
        except Exception:
            pass

    out = {
        "aud_usd": round(aud_usd, 6) if aud_usd else None,
        "usd_cny": round(usd_cny, 6) if usd_cny else None,
        "asof": asof,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Yahoo Finance (AUDUSD=X, CNY=X)",
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    print(f"  → {OUT.name}  1AUD≈US${out['aud_usd']} · 1USD≈¥{out['usd_cny']}（{asof}）")
    return out


if __name__ == "__main__":
    main()
