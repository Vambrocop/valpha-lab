"""
paper_trading.py — 虚拟模拟盘（跟随信号的纸面交易，检验模型的终极方式）

规则（机械执行，无人为干预）：
  - 起始资金 $10,000，标的 = 纳斯达克指数（按收盘价成交）
  - 当日信号 tier >= 4 → 全仓买入（当日收盘价）
  - 当日信号 tier == 3 → 保持现有仓位不动
  - 当日信号 tier <= 2 → 清仓（当日收盘价）
  - 信号的技术因子来自前一日收盘（无前视），日历因子当日已知 → 收盘前可执行

账本 data/processed/paper_ledger.csv 为 append-only 且入 git——无法事后修改。
基准：同期买入持有。输出 web/paper.json 供前端展示。
"""
import pandas as pd
import json
from pathlib import Path

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"
LEDGER   = PROC_DIR / "paper_ledger.csv"

START_DATE    = "2026-06-10"   # 模拟盘开始日（前向实验，绝不回填历史）
START_CAPITAL = 10000.0

COLS = ["date", "action", "price", "units", "cash", "equity", "tier", "prob",
        "model_version", "logged_at"]


def load_ledger():
    if LEDGER.exists():
        return pd.read_csv(LEDGER)
    return pd.DataFrame(columns=COLS)


def main():
    with open(WEB_DIR / "signals.json", encoding="utf-8") as f:
        sig = json.load(f)
    daily = sig["daily_signals"]
    version = str(sig.get("model_version", "?"))
    prices = pd.read_csv(RAW_DIR / "combined_prices.csv",
                         index_col="Date", parse_dates=True)["NASDAQ"].dropna()

    ledger = load_ledger()
    done = set(ledger["date"].astype(str)) if len(ledger) else set()

    # 当前状态（从账本重放）
    cash, units = START_CAPITAL, 0.0
    if len(ledger):
        last = ledger.iloc[-1]
        cash, units = float(last["cash"]), float(last["units"])

    # 按日期处理 START_DATE 之后所有未处理的信号日
    new_rows = []
    for d in sorted(k for k in daily if k >= START_DATE and k not in done):
        ts = pd.Timestamp(d)
        if ts not in prices.index:
            continue
        px = float(prices.loc[ts])
        s = daily[d]
        tier = int(s["tier"])
        action = "HOLD"
        if tier >= 4 and units == 0:
            units = cash / px
            cash = 0.0
            action = "BUY"
        elif tier <= 2 and units > 0:
            cash = units * px
            units = 0.0
            action = "SELL"
        equity = cash + units * px
        new_rows.append({
            "date": d, "action": action, "price": round(px, 2),
            "units": round(units, 6), "cash": round(cash, 2),
            "equity": round(equity, 2), "tier": tier, "prob": s["prob"],
            "model_version": version,
            "logged_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        })
        print(f"  {d} tier{tier} {action:<4} 价格={px:.0f} 净值=${equity:,.0f}")

    if new_rows:
        ledger = pd.concat([ledger, pd.DataFrame(new_rows)], ignore_index=True)
        ledger.to_csv(LEDGER, index=False)

    # ── 输出前端 JSON ──────────────────────────────────────────────
    if not len(ledger):
        print("[OK] 模拟盘尚无记录（等待首个信号日）")
        return
    last = ledger.iloc[-1]
    px_now = float(prices.iloc[-1])
    equity_now = float(last["cash"]) + float(last["units"]) * px_now
    # 基准：开始日收盘全仓买入持有
    p0 = float(prices[prices.index >= START_DATE].iloc[0])
    bench_now = START_CAPITAL * px_now / p0

    bench_curve, eq_curve, dates = [], [], []
    for _, r in ledger.iterrows():
        dates.append(str(r["date"]))
        eq_curve.append(float(r["equity"]))
        bench_curve.append(round(START_CAPITAL * float(r["price"]) / p0, 2))

    trades = ledger[ledger["action"] != "HOLD"]
    out = {
        "start_date": START_DATE,
        "start_capital": START_CAPITAL,
        "current": {
            "equity": round(equity_now, 2),
            "ret_pct": round((equity_now / START_CAPITAL - 1) * 100, 2),
            "position": "满仓" if float(last["units"]) > 0 else "空仓（现金）",
            "as_of": str(last["date"]),
        },
        "benchmark": {
            "equity": round(bench_now, 2),
            "ret_pct": round((bench_now / START_CAPITAL - 1) * 100, 2),
            "note": "同期买入持有纳指",
        },
        "n_trades": int(len(trades)),
        "trades": json.loads(trades.tail(20).to_json(orient="records")),
        "curve": {"dates": dates, "equity": eq_curve, "benchmark": bench_curve},
        "rule": "tier≥4全仓买入 / tier=3持仓不动 / tier≤2清仓（收盘价成交，账本不可篡改）",
    }
    with open(WEB_DIR / "paper.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"[OK] 模拟盘净值 ${equity_now:,.0f}（{out['current']['ret_pct']:+.2f}%）"
          f" vs 基准 {out['benchmark']['ret_pct']:+.2f}% → paper.json")


if __name__ == "__main__":
    main()
