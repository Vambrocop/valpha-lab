# Sentiment Signal Feasibility Spike — v2.0

**Date:** 2026-06-24  
**Author:** Claude Code (Sonnet 4.6) research spike  
**Scope:** Feasibility only. Nothing here is wired into the pipeline or website.  
**Verdict (TL;DR):** CONDITIONAL for Reddit WSB mention counts; NO-GO for Polymarket implied probs on individual stocks.

---

## 1. CANDIDATE SOURCES

### 1A. Reddit Ticker-Mention Counts (r/wallstreetbets, r/stocks)

#### What exists

| Source | History | Cost | Access from AU | Rate Limit | Notes |
|--------|---------|------|---------------|-----------|-------|
| Reddit Official API (OAuth) | ~30 days rolling search window; no historical endpoint for bulk time-series | Free for non-commercial | Yes | 60 req/min | Cannot retrieve posts from 2019 by date range; only recency-sorted listings |
| Arctic Shift (Pushshift successor) | ~2005 to present (community archive) | Free | Yes | Undocumented; polite crawl expected | https://arctic-shift.photon-reddit.com — JSON/zstd dump files indexed by subreddit+month; API available for search queries |
| Pushshift Academic Torrents (pre-2023) | 2005–2023 (monthly .zst dumps) | Free | Yes (torrent) | N/A (bulk download) | Pushshift's own API is dead; dumps exist on Academic Torrents / files.pushshift.io. Contains full comment + submission JSON for every subreddit |
| Kaggle: "Reddit r/wallstreetbets" dataset | 700k posts + 9.5M comments; approx 2012–2021 | Free | Yes | N/A (download) | Static snapshot only; not updated. Useful for a frozen backtest window |
| Quiver Quantitative API | Aug 2018 – present, daily frequency, 6,000 equities | Free tier (scope unclear); $30/mo for full API | Yes | Undocumented | Pre-parsed daily ticker-mention counts per stock from WSB daily discussion threads — most plug-and-play source |
| ApeWisdom API (apewisdom.io/api) | 24h window only — no documented historical depth | Free | Yes | Undocumented | Returns current-day mentions + 24h delta only. NOT suitable for backtesting |
| Tradestie reddit API | Current-day top-50 tickers only | Free | Uncertain (returned 403 in testing) | Undocumented | No historical depth; real-time use only |

#### Make-or-break question: how much history?

The honest answer depends on which access path is used:

**Path A — Pushshift dump files (Academic Torrents / Arctic Shift):**
The raw data exists going back to ~2005. r/wallstreetbets was created in 2012; r/stocks even earlier. The files are large compressed JSON dumps (tens of GB per month for active subreddits) that must be downloaded and parsed to extract ticker mentions. There is no pre-aggregated daily-count CSV. A parser must scan comment/submission bodies for `$TICKER` patterns.

- Estimated extractable history: ~2012–2023 for WSB; most signal research focuses on 2019–2023 because WSB was small before then.
- Practical data volume for a backtest: 2019–2023 (5 years, ~1,500 trading days × N tickers). Sufficient for an honest walk-forward split.
- Friction: high. Parsing multi-GB zstd files is a multi-day ETL project.

**Path B — Quiver Quantitative API:**
Pre-parsed daily mention counts from Aug 2018 onward. Free tier scope is unclear without registering; paid tier ($30/mo) provides clean CSV access. Lowest friction for a proper backtest.

**Path C — Kaggle snapshot datasets:**
Static snapshots; suitable only for a frozen historical analysis. Cannot be used for ongoing scoring.

**Conclusion on Reddit history:** Sufficient if using Pushshift dumps (free, high friction) or Quiver API (low friction, possibly $30/mo). Signal universe exists. Access from Australia is fine. Rate limits are non-blocking for batch historical work.

#### Known signal pitfalls (relevant to backtest design)

1. **Reverse causality is likely dominant.** Most mention spikes follow big price moves (earnings, news). The causal direction is ambiguous and likely mostly reactive (price → attention → mentions), not predictive.
2. **Survivorship skew.** WSB coverage is skewed toward a handful of names (GME, AMC, TSLA, NVDA). A signal that "works" on these may capitalise on momentum in highly volatile stocks, not sentiment per se.
3. **Regime shift.** WSB user base and posting behaviour changed dramatically post-Jan 2021 (GME squeeze). A signal calibrated pre-2021 may not transfer to 2022-present.
4. **Data-mining risk.** Testing mention → return correlations across a large universe without a multiple-comparison correction almost guarantees spurious significance on some tickers.

---

### 1B. Polymarket Implied Probabilities (macro/market events)

#### What exists

| Source | History | Cost | Access from AU | Notes |
|--------|---------|------|---------------|-------|
| Polymarket official CLOB API (`GET /prices-history`) | Live state only; `startTs`/`endTs` params exist but no documented historical depth | Free (60 req/min) | Yes | Endpoint: `https://clob.polymarket.com/prices-history?token_id=...` |
| pmxt.dev archive (v2) | **April 13, 2026 – present only** (~35 pages of hourly Parquet files) | Free (CC BY 4.0) | Yes | Far too short for any backtest |
| Kaggle: "Polymarket Prediction Markets" | Events snapshot Dec 3, 2025; covers events **July 2022 – Dec 2025** | Free | Yes | ~43,840 events; contains final resolution and market metadata but NOT continuous intra-market price time series |
| Telonex.io | Tick-level trades + order books; date range not independently verified | Paid (free samples) | Yes | Not confirmed reachable or complete |

#### The fundamental problem with Polymarket for stock signals

1. **Individual stocks are almost entirely absent.** Polymarket covers macro events (elections, Fed rate decisions, crypto prices, geopolitical events). Markets on individual company stocks (e.g., "Will Apple trade above $200 by Q2?") are sparse, illiquid, and short-lived. There is no systematic daily coverage of S&P 500 components.

2. **Platform launched June 2020.** Usable liquid-enough market history starts ~2022 for macro events. That is ~3.5 years maximum — marginal for an honest backtest.

3. **Macro markets don't map to individual stock signals.** A recession probability market gives one probability per quarter, not a daily per-ticker signal. Using it as a per-stock signal requires a factor model layer (each stock's beta to recession risk), multiplying uncertainty and model assumptions.

4. **pmxt.dev archive only starts April 2026.** This is the only confirmed free continuous price-series archive, and it covers only ~10 weeks. Completely unusable for backtesting.

5. **Kaggle dataset covers events but not price time series.** Knowing that a market resolved "Yes" on a certain date does not tell you what the probability was day-by-day during the market's lifetime.

**Conclusion on Polymarket:** NO-GO. Instrument design does not generate per-stock daily signals. History is insufficient for honest OOS testing under Valpha Lab's standards (5-year minimum preferred; 3 years in-sample + 2 years OOS). Recommend revisiting only if dedicated per-stock prediction markets with 5+ year continuous price history emerge.

---

## 2. BACKTEST DESIGN

This design applies to the Reddit WSB mention-count signal (the conditionally viable candidate). It is written concretely enough for an implementer to follow.

### 2A. Signal definition

```
signal(t, ticker) = log(mention_count(t, ticker) + 1)
                  - rolling_mean(log(mention_count + 1), window=20d)
```

Z-scored log-mention count relative to a 20-day trailing mean. This makes the signal stationary and prevents stocks with permanently-high mention counts from dominating.

Variants to test (secondary only; primary result is the one above):
- Raw mention count (not z-scored)
- Mention growth rate: `log(count_t / count_{t-1})`
- Attention spike: binary flag if z-score > 2.0 SD above rolling mean

### 2B. Target variable

Primary: **next-5-day excess return** = `r(t+1:t+5, ticker) - r(t+1:t+5, SPY)`

Secondary: `next-1d` and `next-20d` excess returns; `next-5d realised volatility`.

The excess return (vs SPY) removes market-wide moves so the test is about stock-specific predictability, not market timing.

### 2C. Baseline to beat

Three baselines in order of strength:
1. **Random (coin flip):** Does the signal predict direction better than 50%?
2. **Momentum persistence:** Does the signal add predictive power above the stock's own last-5d return as a predictor?
3. **Market regime:** Does the signal add above a VIX regime indicator (low/medium/high VIX tercile)?

The signal should beat all three. Beating only the coin flip is insufficient to claim a real signal.

### 2D. Walk-forward split

```
Data window: 2019-01-01 to 2023-12-31 (5 years)
Universe: ~100 most-mentioned tickers in WSB over the period (~1,500 trading days × 100 tickers)

In-sample (train): 2019-01-01 to 2021-12-31 (3 years)
  Use for: signal window tuning (e.g. rolling window length, z-score threshold)

Out-of-sample (OOS): 2022-01-01 to 2023-12-31 (2 years)
  HEADLINE STATISTICS COME FROM OOS ONLY.
  In-sample stats are for calibration reference, not the published finding.
```

The 2022–2023 OOS window spans a distinct regime (rate hikes, bear market), which is desirable: a signal that survives this regime change is more likely to be robust than one that only works in the 2020 bull market.

### 2E. Placebo / control tests (MANDATORY)

Neither result is publishable without both placebo tests passing:

**Placebo 1 — Shuffled time series:**
For each ticker, randomly permute the mention-count time series (keeping price series in place). Re-run the exact same backtest. The shuffled signal should produce:
- IC ≈ 0.00 (no directional prediction)
- Hit-rate ≈ 50%
- Binomial p-value >> 0.05

If the real signal IC is comparable to the shuffled IC, the result is noise.

**Placebo 2 — Unrelated-ticker signal:**
For each (date, ticker) pair, replace the mention count with the mention count of a randomly-chosen different ticker on the same date. If this placebo also predicts returns, the signal is driven by date-level market-wide variation (e.g., high-attention days tend to be up days) rather than stock-specific information.

### 2F. Multiple-comparison guard

Testing N tickers × M horizons × K signal variants implies many implicit hypothesis tests. Typical values: N=100, M=3, K=3 → ~900 comparisons.

Apply **Benjamini-Hochberg FDR correction at q=0.05** across all ticker × horizon × variant binomial p-values. Any result that does not survive BH adjustment is reported as inconclusive noise.

Primary headline statistic: **aggregate IC (information coefficient)** across all tickers and dates in the OOS window. This is ONE test (not 900) and is the primary publishable number. IC is computed as the Spearman correlation between signal(t, ticker) and next-5d-excess-return(t, ticker), pooled across all ticker-date pairs.

### 2G. Go/No-Go threshold

| OOS Aggregate IC | Placebo IC (shuffle) | BH-FDR | Decision |
|-----------------|---------------------|---------|---------|
| < 0.02 | any | any | NO-GO: signal is noise; publish as negative result |
| 0.02–0.05 | placebo IC > 50% of real IC | fails | NO-GO: can't distinguish from spurious |
| 0.02–0.05 | placebo IC < 20% of real IC | passes | CONDITIONAL: weak signal; further investigation before production |
| > 0.05 | placebo IC < 10% of real IC | passes | GO: signal is real; design production system |

---

## 3. PROTOTYPE

See: `research/sentiment_backtest_proto.py`

The prototype runs on synthetic data only (no network calls in committed code). It:
- Generates a synthetic (date, ticker, mention_count) series with a planted weak signal
- Computes z-scored log-mention signal
- Computes 5-day forward excess returns
- Calculates hit-rate, Spearman IC, and binomial p-value
- Runs the shuffle-placebo comparison
- Applies BH-FDR correction across a small synthetic universe of tickers
- Prints a structured result table showing real vs placebo vs threshold

---

## 4. RECOMMENDATION

### Reddit WSB Mention Counts: CONDITIONAL

**In favour:**
- Sufficient history exists (~5 years usable) if you obtain Pushshift dumps or Quiver API data
- Reachable from Australia via standard HTTPS/torrent
- Academic literature (ICE backtest paper) shows some quintile spread in professional-grade sentiment signals over 5 years

**Against:**
- Reverse causality is likely the dominant effect (prices drive mentions, not the other way)
- The Jan 2021 WSB regime shift makes pre/post 2021 data potentially non-stationary as a signal
- Raw mention counts (as opposed to NLP sentiment models) are a much noisier signal; academic results with raw counts are weaker
- Data access has real friction: Pushshift dumps require multi-GB ETL; Quiver API may require $30/mo

**Recommended next step (if user wants to pursue):**
1. Obtain a concrete data sample: download one Quiver Quantitative or Kaggle WSB dataset
2. Run `sentiment_backtest_proto.py` with real data substituted for synthetic data
3. If OOS IC > 0.05 and shuffle placebo IC < 20% of real IC → escalate to production design
4. If OOS IC < 0.05 or placebo IC is comparable → publish as an honest negative result and stop

Cost of the next step: ~2–4 hours of ETL work + computation time. Recommended budget: Sonnet-level agent, no Opus needed at this stage.

### Polymarket Implied Probabilities: NO-GO

**Evidence for NO-GO:**
- pmxt.dev archive starts April 2026 — only ~10 weeks of data, completely unusable for backtesting
- Kaggle snapshot contains event metadata but not continuous price time series
- Official API has no confirmed historical depth
- Individual stock markets essentially don't exist on Polymarket
- Even the best available macro-market history (~2022–2025, ~3.5 years) is insufficient by Valpha Lab's standards when combined with BH-FDR multiple-comparison correction

**Publish as:** "Investigated Polymarket implied probability signals (June 2026 spike). Verdict: NO-GO. Instrument design does not produce per-stock daily signals; available price-series history is too short for an honest walk-forward OOS test. Revisit if per-stock prediction markets with 5+ year continuous history emerge."

---

## 5. APPENDIX: KEY SOURCES CONSULTED

- Reddit Official API: https://www.reddit.com/dev/api
- Arctic Shift (Pushshift successor): https://github.com/ArthurHeitmann/arctic_shift
- Quiver Quantitative WSB API: https://api.quiverquant.com/
- ApeWisdom API: https://apewisdom.io/api/
- Polymarket CLOB docs: https://docs.polymarket.com/developers/CLOB/timeseries
- Polymarket API guide: https://pm.wiki/learn/polymarket-api
- pmxt.dev Polymarket archive (v2): https://archive.pmxt.dev/Polymarket/v2
- Kaggle: Polymarket Prediction Markets dataset (Dec 2025 snapshot)
- Kaggle: Reddit r/wallstreetbets dataset
- ICE sentiment backtesting research: https://www.ice.com/insights/backtesting-a-reddit-derived-strategy-using-ice-signals-and-sentiment-data
- arXiv 2507.03350: Backtesting Sentiment Signals for Trading

---

*This spike is a research artefact only. Nothing was added to market-analysis/web/, run_all.py, or any CI workflow. Do not push.*
