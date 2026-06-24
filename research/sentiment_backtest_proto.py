"""
sentiment_backtest_proto.py
============================
RESEARCH SPIKE — Valpha Lab v2.0  (2026-06-24)

PURPOSE
-------
Prototype harness for an honest backtest of a Reddit ticker-mention-count
signal. Uses SYNTHETIC data only — no live network calls. Comments show
exactly where real data would be substituted.

WHAT THIS TESTS
---------------
1. Z-scored log-mention-count signal vs next-5-day excess return
2. Hit-rate vs 50% baseline
3. Spearman IC (information coefficient) — pooled across all ticker-dates
4. Binomial p-value on directional calls
5. Shuffle-placebo comparison (label permutation)
6. Unrelated-ticker placebo
7. Benjamini-Hochberg FDR correction across ticker x horizon p-values

VERDICT THRESHOLDS (from sentiment_spike.md §2G)
-------------------------------------------------
OOS IC > 0.05 AND placebo IC < 10% of real IC AND BH-FDR passes  → GO
OOS IC 0.02-0.05 AND placebo IC < 20% of real IC AND BH-FDR passes → CONDITIONAL
Otherwise                                                           → NO-GO

HOW TO USE WITH REAL DATA
--------------------------
Replace the block marked # === SYNTHETIC DATA GENERATION === below with:

    import pandas as pd
    df = pd.read_csv("path/to/wsb_mentions.csv", parse_dates=["date"])
    # columns: date, ticker, mention_count
    prices = pd.read_csv("path/to/prices.csv", parse_dates=["date"])
    # columns: date, ticker, close_price
    # (SPY close price also needed for excess-return calculation)

Then run:  py research/sentiment_backtest_proto.py

DEPENDENCIES
------------
numpy, pandas, scipy — all present in market-analysis/requirements.txt
"""

import sys
import random
import numpy as np
import pandas as pd
from scipy import stats

SEED = 42
np.random.seed(SEED)
random.seed(SEED)

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────
SIGNAL_WINDOW = 20        # rolling window for z-scoring (trading days)
FORWARD_DAYS = 5          # prediction horizon
IC_GO_THRESHOLD = 0.05    # OOS IC needed for GO
IC_COND_THRESHOLD = 0.02  # OOS IC needed for CONDITIONAL
PLACEBO_RATIO_GO = 0.10   # placebo IC must be < 10% of real IC for GO
PLACEBO_RATIO_COND = 0.20 # placebo IC must be < 20% for CONDITIONAL
BH_ALPHA = 0.05           # Benjamini-Hochberg FDR level
N_PLACEBO_SHUFFLES = 500  # permutations for Monte-Carlo placebo baseline


# ─────────────────────────────────────────────────────────────
# === SYNTHETIC DATA GENERATION ===
# Replace this entire block with real CSV/parquet loads for live use.
# ─────────────────────────────────────────────────────────────

def generate_synthetic_data(
    n_tickers: int = 20,
    n_days: int = 1000,
    signal_strength: float = 0.04,   # planted IC in the signal (weak but detectable)
    seed: int = SEED
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
        mentions_df: (date, ticker, mention_count)
        prices_df:   (date, ticker, close_price, spy_close)
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-01", periods=n_days)  # business days
    tickers = [f"TICK{i:02d}" for i in range(n_tickers)]

    rows_mentions = []
    rows_prices = []

    # SPY: random walk base
    spy_log_ret = rng.normal(0.0003, 0.012, n_days)
    spy_close = 300.0 * np.exp(np.cumsum(spy_log_ret))

    for ticker in tickers:
        # Each ticker has a latent daily factor
        latent = rng.normal(0, 1, n_days)

        # Mention count: log-normal with noise + small latent component
        mention_base = rng.poisson(lam=20, size=n_days)  # baseline ~20 mentions/day
        mention_count = np.maximum(0, mention_base + (latent * 5).astype(int))

        # Price: random walk + tiny predictive component from latent
        # planted signal: next-5d return is slightly correlated with mention_count anomaly
        idio_ret = rng.normal(0, 0.018, n_days) + signal_strength * latent
        price = 50.0 * np.exp(np.cumsum(idio_ret))

        for i, d in enumerate(dates):
            rows_mentions.append({"date": d, "ticker": ticker, "mention_count": int(mention_count[i])})
            rows_prices.append({"date": d, "ticker": ticker, "close_price": price[i], "spy_close": spy_close[i]})

    mentions_df = pd.DataFrame(rows_mentions)
    prices_df = pd.DataFrame(rows_prices)
    return mentions_df, prices_df


# ─────────────────────────────────────────────────────────────
# SIGNAL COMPUTATION
# ─────────────────────────────────────────────────────────────

def compute_signal(mentions_df: pd.DataFrame, window: int = SIGNAL_WINDOW) -> pd.DataFrame:
    """
    signal = log(mention_count + 1) - rolling_mean(log(mention_count + 1), window)
    i.e. z-score using rolling mean and std.
    """
    df = mentions_df.copy().sort_values(["ticker", "date"])
    df["log_count"] = np.log1p(df["mention_count"])

    grp = df.groupby("ticker")["log_count"]
    df["rolling_mean"] = grp.transform(lambda x: x.rolling(window, min_periods=max(1, window//2)).mean())
    df["rolling_std"] = grp.transform(lambda x: x.rolling(window, min_periods=max(1, window//2)).std().fillna(1.0))
    df["signal"] = (df["log_count"] - df["rolling_mean"]) / df["rolling_std"].clip(lower=1e-8)
    return df[["date", "ticker", "signal"]]


# ─────────────────────────────────────────────────────────────
# FORWARD RETURN COMPUTATION
# ─────────────────────────────────────────────────────────────

def compute_forward_returns(prices_df: pd.DataFrame, horizon: int = FORWARD_DAYS) -> pd.DataFrame:
    """
    next-{horizon}d excess return = r(t+1:t+horizon, ticker) - r(t+1:t+horizon, SPY)
    """
    df = prices_df.copy().sort_values(["ticker", "date"])
    df["fwd_price"] = df.groupby("ticker")["close_price"].shift(-horizon)
    df["fwd_spy"] = df.groupby("ticker")["spy_close"].shift(-horizon)
    df["ret_stock"] = df["fwd_price"] / df["close_price"] - 1.0
    df["ret_spy"] = df["fwd_spy"] / df["spy_close"] - 1.0
    df["excess_return"] = df["ret_stock"] - df["ret_spy"]
    return df[["date", "ticker", "excess_return"]].dropna()


# ─────────────────────────────────────────────────────────────
# CORE EVALUATION: IC + HIT RATE + BINOMIAL P-VALUE
# ─────────────────────────────────────────────────────────────

def evaluate(signal_df: pd.DataFrame, returns_df: pd.DataFrame) -> dict:
    """
    Join signal with returns and compute aggregate metrics.
    Returns dict with IC, hit_rate, n_obs, p_value_ic, p_value_binomial.
    """
    merged = pd.merge(signal_df, returns_df, on=["date", "ticker"], how="inner").dropna()
    if len(merged) < 30:
        return {"IC": np.nan, "hit_rate": np.nan, "n_obs": len(merged),
                "p_value_ic": 1.0, "p_value_binomial": 1.0}

    # Spearman IC across all ticker-date pairs
    ic, p_ic = stats.spearmanr(merged["signal"], merged["excess_return"])

    # Hit rate: fraction of obs where sign(signal) == sign(excess_return)
    correct = ((merged["signal"] > 0) == (merged["excess_return"] > 0)).sum()
    n = len(merged)
    hit_rate = correct / n

    # Binomial p-value (one-sided: is hit_rate > 0.5?)
    # scipy >= 1.7: use binomtest; older: binom_test (deprecated/removed)
    try:
        p_binom = stats.binomtest(int(correct), int(n), p=0.5, alternative="greater").pvalue
    except AttributeError:
        p_binom = stats.binom_test(int(correct), int(n), p=0.5, alternative="greater")  # type: ignore[attr-defined]

    return {
        "IC": ic,
        "hit_rate": hit_rate,
        "n_obs": n,
        "p_value_ic": p_ic,
        "p_value_binomial": p_binom,
    }


# ─────────────────────────────────────────────────────────────
# PER-TICKER EVALUATION (for BH-FDR correction)
# ─────────────────────────────────────────────────────────────

def evaluate_per_ticker(signal_df: pd.DataFrame, returns_df: pd.DataFrame) -> pd.DataFrame:
    merged = pd.merge(signal_df, returns_df, on=["date", "ticker"], how="inner").dropna()
    rows = []
    for ticker, grp in merged.groupby("ticker"):
        if len(grp) < 20:
            continue
        ic, p_ic = stats.spearmanr(grp["signal"], grp["excess_return"])
        n = len(grp)
        correct = ((grp["signal"] > 0) == (grp["excess_return"] > 0)).sum()
        try:
            p_binom = stats.binomtest(int(correct), int(n), p=0.5, alternative="greater").pvalue
        except AttributeError:
            p_binom = stats.binom_test(int(correct), int(n), p=0.5, alternative="greater")  # type: ignore[attr-defined]
        rows.append({"ticker": ticker, "IC": ic, "n_obs": n,
                     "p_value_ic": p_ic, "p_value_binomial": p_binom})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# BENJAMINI-HOCHBERG FDR CORRECTION
# ─────────────────────────────────────────────────────────────

def bh_correction(p_values: np.ndarray, alpha: float = BH_ALPHA) -> np.ndarray:
    """Returns boolean array: True if hypothesis rejects after BH correction."""
    n = len(p_values)
    if n == 0:
        return np.array([], dtype=bool)
    order = np.argsort(p_values)
    sorted_p = p_values[order]
    thresholds = (np.arange(1, n + 1) / n) * alpha
    below = sorted_p <= thresholds
    # find largest k where all p[1..k] <= threshold[1..k]
    if not below.any():
        reject = np.zeros(n, dtype=bool)
    else:
        max_k = np.where(below)[0].max()
        reject_sorted = np.zeros(n, dtype=bool)
        reject_sorted[:max_k + 1] = True
        reject = np.empty(n, dtype=bool)
        reject[order] = reject_sorted
    return reject


# ─────────────────────────────────────────────────────────────
# PLACEBO TESTS
# ─────────────────────────────────────────────────────────────

def placebo_shuffle(signal_df: pd.DataFrame, returns_df: pd.DataFrame,
                    n_shuffles: int = N_PLACEBO_SHUFFLES) -> dict:
    """
    Shuffle-label placebo: for each ticker, randomly permute the signal
    time series. Compute IC distribution across shuffles.
    Returns mean IC and std IC of the placebo distribution.
    """
    merged = pd.merge(signal_df, returns_df, on=["date", "ticker"], how="inner").dropna()
    ics = []
    for _ in range(n_shuffles):
        shuffled = merged.copy()
        # permute signal within each ticker independently
        shuffled["signal"] = (
            shuffled.groupby("ticker")["signal"]
            .transform(lambda x: x.sample(frac=1, random_state=None).values)
        )
        if len(shuffled) > 10:
            ic, _ = stats.spearmanr(shuffled["signal"], shuffled["excess_return"])
            ics.append(ic)
    ics = np.array(ics)
    return {"mean_placebo_IC": float(np.mean(ics)), "std_placebo_IC": float(np.std(ics)),
            "p95_placebo_IC": float(np.percentile(np.abs(ics), 95))}


def placebo_unrelated_ticker(signal_df: pd.DataFrame, returns_df: pd.DataFrame) -> dict:
    """
    Unrelated-ticker placebo: replace each (date, ticker) signal with the
    signal of a different randomly-selected ticker on the same date.
    If this also predicts returns, the signal captures market-wide date effects.
    """
    merged = pd.merge(signal_df, returns_df, on=["date", "ticker"], how="inner").dropna()
    tickers = merged["ticker"].unique().tolist()
    if len(tickers) < 2:
        return {"unrelated_IC": np.nan}

    rng = np.random.default_rng(SEED + 99)

    def scramble_ticker(grp):
        ticker = grp.name
        alternatives = [t for t in tickers if t != ticker]
        alt = rng.choice(alternatives)
        # get the signal series for alt ticker on the same dates
        alt_signal = merged.loc[merged["ticker"] == alt, ["date", "signal"]].rename(
            columns={"signal": "alt_signal"}
        )
        result = grp.merge(alt_signal, on="date", how="inner")
        return result

    parts = []
    for ticker, grp in merged.groupby("ticker"):
        parts.append(scramble_ticker(grp))

    if not parts:
        return {"unrelated_IC": np.nan}

    unrel = pd.concat(parts, ignore_index=True).dropna(subset=["alt_signal", "excess_return"])
    if len(unrel) < 20:
        return {"unrelated_IC": np.nan}

    ic, _ = stats.spearmanr(unrel["alt_signal"], unrel["excess_return"])
    return {"unrelated_IC": float(ic)}


# ─────────────────────────────────────────────────────────────
# VERDICT
# ─────────────────────────────────────────────────────────────

def compute_verdict(real_ic: float, placebo: dict, bh_n_rejected: int) -> str:
    if np.isnan(real_ic):
        return "NO-GO (insufficient data)"
    mean_plac = abs(placebo["mean_placebo_IC"])
    plac_ratio = mean_plac / max(abs(real_ic), 1e-9)
    bh_pass = bh_n_rejected > 0

    if abs(real_ic) < IC_COND_THRESHOLD:
        return f"NO-GO  (IC={real_ic:.4f} < threshold {IC_COND_THRESHOLD})"
    if not bh_pass:
        return f"NO-GO  (IC={real_ic:.4f} but no ticker survives BH-FDR)"
    if abs(real_ic) >= IC_GO_THRESHOLD and plac_ratio < PLACEBO_RATIO_GO:
        return f"GO     (IC={real_ic:.4f} >= {IC_GO_THRESHOLD}; placebo ratio={plac_ratio:.2f} < {PLACEBO_RATIO_GO})"
    if abs(real_ic) >= IC_COND_THRESHOLD and plac_ratio < PLACEBO_RATIO_COND:
        return f"CONDITIONAL  (IC={real_ic:.4f}; placebo ratio={plac_ratio:.2f})"
    return f"NO-GO  (IC={real_ic:.4f}; placebo too similar, ratio={plac_ratio:.2f})"


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("Valpha Lab — Sentiment Backtest Prototype (SYNTHETIC DATA)")
    print("=" * 65)
    print()
    print("NOTE: All data below is synthetic. No network calls were made.")
    print("Replace the data generation block to run on real Reddit data.")
    print()

    # 1. Generate synthetic data
    print("Generating synthetic data (20 tickers, 1000 trading days)...")
    mentions_df, prices_df = generate_synthetic_data(
        n_tickers=20, n_days=1000, signal_strength=0.04
    )

    # 2. Split into in-sample and OOS
    split_date = pd.Timestamp("2022-01-01")
    mentions_is = mentions_df[mentions_df["date"] < split_date]
    prices_is   = prices_df[prices_df["date"] < split_date]
    mentions_oos = mentions_df[mentions_df["date"] >= split_date]
    prices_oos   = prices_df[prices_df["date"] >= split_date]

    print(f"In-sample rows:  mentions={len(mentions_is):,}  prices={len(prices_is):,}")
    print(f"OOS rows:        mentions={len(mentions_oos):,}  prices={len(prices_oos):,}")
    print()

    # 3. Compute signals
    # Note: use full history for rolling window (don't leak future into IS window)
    signal_full = compute_signal(mentions_df, window=SIGNAL_WINDOW)
    signal_oos = signal_full[signal_full["date"] >= split_date]

    # 4. Compute forward returns
    returns_full = compute_forward_returns(prices_df, horizon=FORWARD_DAYS)
    returns_oos  = returns_full[returns_full["date"] >= split_date]

    # 5. Aggregate evaluation
    print(f"── Aggregate OOS evaluation (horizon={FORWARD_DAYS}d) ──────────────")
    result = evaluate(signal_oos, returns_oos)
    print(f"  IC (Spearman):   {result['IC']:+.4f}")
    print(f"  Hit rate:        {result['hit_rate']:.3f}  (baseline: 0.500)")
    print(f"  N observations:  {result['n_obs']:,}")
    print(f"  p-value (IC):    {result['p_value_ic']:.4f}")
    print(f"  p-value (binom): {result['p_value_binomial']:.4f}")
    print()

    # 6. Per-ticker evaluation + BH-FDR
    print("── Per-ticker BH-FDR correction ────────────────────────────")
    per_ticker = evaluate_per_ticker(signal_oos, returns_oos)
    if len(per_ticker) > 0:
        p_vals = per_ticker["p_value_binomial"].values
        per_ticker["bh_reject"] = bh_correction(p_vals, alpha=BH_ALPHA)
        n_reject = per_ticker["bh_reject"].sum()
        print(f"  Tickers tested:        {len(per_ticker)}")
        print(f"  BH-FDR rejects (q=.05): {n_reject} / {len(per_ticker)}")
        if n_reject > 0:
            top = per_ticker[per_ticker["bh_reject"]].sort_values("IC", ascending=False)
            print(f"  Surviving tickers: {', '.join(top['ticker'].tolist())}")
    else:
        n_reject = 0
    print()

    # 7. Shuffle-placebo
    print(f"── Shuffle-placebo ({N_PLACEBO_SHUFFLES} permutations) ──────────────────")
    placebo = placebo_shuffle(signal_oos, returns_oos, n_shuffles=N_PLACEBO_SHUFFLES)
    print(f"  Placebo mean IC:    {placebo['mean_placebo_IC']:+.4f}")
    print(f"  Placebo std IC:     {placebo['std_placebo_IC']:.4f}")
    print(f"  Placebo |IC| p95:   {placebo['p95_placebo_IC']:.4f}")
    real_abs_ic = abs(result["IC"]) if not np.isnan(result["IC"]) else 0.0
    placebo_ratio = abs(placebo["mean_placebo_IC"]) / max(real_abs_ic, 1e-9)
    print(f"  Placebo/Real ratio: {placebo_ratio:.3f}  (want < {PLACEBO_RATIO_COND} for CONDITIONAL, < {PLACEBO_RATIO_GO} for GO)")
    print()

    # 8. Unrelated-ticker placebo
    print("── Unrelated-ticker placebo ─────────────────────────────────")
    unrel = placebo_unrelated_ticker(signal_oos, returns_oos)
    print(f"  Unrelated-ticker IC: {unrel['unrelated_IC']:+.4f}  (want ≈ 0.00)")
    print()

    # 9. Final verdict
    print("── VERDICT ──────────────────────────────────────────────────")
    verdict = compute_verdict(result["IC"], placebo, n_reject)
    print(f"  {verdict}")
    print()
    print("Thresholds from sentiment_spike.md §2G:")
    print(f"  GO:          OOS IC > {IC_GO_THRESHOLD}, placebo ratio < {PLACEBO_RATIO_GO}, BH-FDR passes")
    print(f"  CONDITIONAL: OOS IC > {IC_COND_THRESHOLD}, placebo ratio < {PLACEBO_RATIO_COND}, BH-FDR passes")
    print(f"  NO-GO:       anything else")
    print()
    print("IMPORTANT: This prototype ran on SYNTHETIC data with a planted")
    print("signal_strength=0.04. Replace with real WSB data before")
    print("drawing any conclusion about the actual signal.")
    print("=" * 65)

    # Return non-zero exit code if the harness itself crashed
    # (not based on GO/NO-GO — that's a research decision, not a code failure)
    return 0


if __name__ == "__main__":
    sys.exit(main())
