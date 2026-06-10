"""
track_predictions.py — 实盘预测追踪（模型的"成绩单"）

与回测的区别：回测是事后用历史重算，这里是「当时的模型在当时说了什么」
的append-only日志，之后用真实行情回填，永远无法事后美化。

每次运行：
  1. 把 signals.json 最新一天的预测（prob/tier/模型版本）按指数追加到
     data/processed/prediction_log.csv（同日同指数同版本不重复）
  2. 用最新价格回填历史记录的真实 1d/5d/20d 前向收益
  3. 汇总写入 prediction_log_summary.json（build_signals.py 嵌入 signals.json）

运行顺序：在 build_signals 第一遍之后、第二遍之前（见 run_all.py）
"""
import pandas as pd
import json
from pathlib import Path

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"
LOG_PATH = PROC_DIR / "prediction_log.csv"

COLS = ["logged_at", "signal_date", "index", "model_version", "prob", "tier",
        "ret_1d", "ret_5d", "ret_20d"]


def load_log():
    if LOG_PATH.exists():
        df = pd.read_csv(LOG_PATH)
        return df.reindex(columns=COLS)
    return pd.DataFrame(columns=COLS)


def main():
    with open(WEB_DIR / "signals.json", encoding="utf-8") as f:
        sig = json.load(f)
    version = str(sig.get("model_version", "1.0"))
    log = load_log()

    streams = {"NASDAQ": sig["daily_signals"]}
    if "daily_signals_sp500" in sig:
        streams["SP500"] = sig["daily_signals_sp500"]

    # ── 1. 追加最新预测 ───────────────────────────────────────────
    new_rows = []
    for idx, daily in streams.items():
        d = list(daily)[-1]
        s = daily[d]
        # 注意 astype(str)：CSV 读回后 "2.0" 会变成浮点，直接比较永远 False
        dup = bool(len(log) and ((log["signal_date"].astype(str) == d) &
                                 (log["index"] == idx) &
                                 (log["model_version"].astype(str) == version)).any())
        if not dup:
            new_rows.append({
                "logged_at":     pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                "signal_date":   d,
                "index":         idx,
                "model_version": version,
                "prob":          s["prob"],
                "tier":          s["tier"],
                "ret_1d": None, "ret_5d": None, "ret_20d": None,
            })
            print(f"  + 记录 {idx} {d}: prob={s['prob']} tier={s['tier']} (v{version})")
    if new_rows:
        log = pd.concat([log, pd.DataFrame(new_rows)], ignore_index=True)
    # 防御性去重（同日同指数同版本只留最后一条）
    log["model_version"] = log["model_version"].astype(str)
    log = log.drop_duplicates(subset=["signal_date", "index", "model_version"],
                              keep="last").reset_index(drop=True)

    # ── 2. 回填真实前向收益 ───────────────────────────────────────
    prices = pd.read_csv(RAW_DIR / "combined_prices.csv",
                         index_col="Date", parse_dates=True)
    n_filled = 0
    for idx in streams:
        s = prices[idx].dropna()
        pos = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(s.index)}
        for i, r in log.iterrows():
            if r["index"] != idx:
                continue
            p = pos.get(str(r["signal_date"]))
            if p is None:
                continue
            for h, col in [(1, "ret_1d"), (5, "ret_5d"), (20, "ret_20d")]:
                if pd.isna(r[col]) and p + h < len(s):
                    log.at[i, col] = round(float(s.iloc[p + h] / s.iloc[p] - 1) * 100, 3)
                    n_filled += 1
    if n_filled:
        print(f"  回填 {n_filled} 个前向收益")

    log.to_csv(LOG_PATH, index=False)

    # ── 3. 汇总（嵌入前端）────────────────────────────────────────
    def _summary(df):
        out = {"n": int(len(df))}
        f5 = df.dropna(subset=["ret_5d"])
        if len(f5):
            hit = (f5["prob"].astype(float) > 0.5) == (f5["ret_5d"].astype(float) > 0)
            out["n_scored_5d"]  = int(len(f5))
            out["hit_rate_5d"]  = round(float(hit.mean() * 100), 1)
            out["avg_ret_5d"]   = round(float(f5["ret_5d"].astype(float).mean()), 3)
        f1 = df.dropna(subset=["ret_1d"])
        if len(f1):
            hit1 = (f1["prob"].astype(float) > 0.5) == (f1["ret_1d"].astype(float) > 0)
            out["n_scored_1d"] = int(len(f1))
            out["hit_rate_1d"] = round(float(hit1.mean() * 100), 1)
        return out

    summary = {
        "since":    str(log["signal_date"].min()) if len(log) else None,
        "n_logged": int(len(log)),
        "by_index": {idx: _summary(log[log["index"] == idx]) for idx in streams},
        "by_version": {v: _summary(log[log["model_version"] == v])
                       for v in sorted(log["model_version"].astype(str).unique())} if len(log) else {},
        # 最近30条明细（前端表格）
        "recent": json.loads(
            log.sort_values("signal_date").tail(30).to_json(orient="records")),
    }
    out = PROC_DIR / "prediction_log_summary.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[OK] 预测日志 {len(log)} 条 → {LOG_PATH.name}；汇总 → {out.name}")


if __name__ == "__main__":
    main()
