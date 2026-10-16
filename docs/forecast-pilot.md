# One-hour BTC forecast pilot

Approved scope · 2026-10-16. These rules are fixed before model fitting or inspection of test-period forecast errors. Visualization work stays closed.

## Question and scope

Can nearby threshold-market prices improve the prediction of the next 60-minute BTC/USDT return, compared with recent BTC price behavior alone?

Use the 32 saved daily calendar events only. Exclude weekly/monthly events, creation-based windows and unsupported rules. Do not change or recollect the source dataset. Do not use the full-history 0.05 filter. There is no LLM, trading strategy, settlement-outcome prediction or profit estimate.

## Price qualification

Reviewed on 2026-10-16: [official Data API v2 schema](https://data-api.polymarket.com/v2/openapi.json), `/v2/prices-history` and `PricePoint`. It specifies prices in 0–1, a bucket-start timestamp, and a per-point observation width. Aggregate observations lie within the stated window. Resolved series can append an on-chain payout with zero width. The schema does not state whether aggregates are last trades, midpoints or another calculation. The old human-readable history/migration URLs were unavailable during this check.

Use completed five-minute granular buckets only. Exclude zero-width, invalid, conflicting and incomplete-request points. Observe a bucket no earlier than its end; require age strictly below 300 seconds. Do not interpolate. Treat YES values as opaque historical numeric features, not verified probabilities or executable quotes. Retrospective receipts do not prove historical publication latency or absence of revisions. Historical rule versions remain unverified. An exploratory calculation is allowed, but `qualified_forecast` and `pricing_eligible` remain false until those checks pass.

## Rows and features

- One candidate per event per hour: window start + 1 hour through window end − 1 hour. The target can end at the window boundary.
- Target: `10,000 × (BTC close at t+60m / BTC close at t − 1)`, in basis points. A close at time t is from the minute ending immediately before t.
- Require exact, continuous one-minute BTC candles from t−6h through t+1h. Use only candles completed by t for features. The target interval is used only for labels and coverage checks.
- Use Decimal for prices, returns, distances and volatility calculation. Fit the statistical models with floating point. Keep exact derived inputs as JSON strings.
- BTC features: trailing 1h return, trailing 6h return, trailing 6h minute-return population standard deviation scaled by sqrt(60), and hours left in the window. Price-change and volatility features use basis points.
- At t, find the nearest unhit upward threshold above spot and nearest unhit downward threshold below spot, each within 5% of spot. Check the full source path from window start to t; exact threshold equality is a hit. Missing path data is not an unhit result. Break equal-distance ties by market ID.
- Choose the pair using only spot, source-path observations and metadata at t. Do not choose a different market because its price history is missing. Require actual YES token mapping and market creation no later than t−1h.
- For each selected market, require fresh buckets at t and t−1h. Use its YES price at t, signed distance toward the threshold (% of spot), and YES price change over that hour. Record token IDs, point times and ages.
- Both models use the same accepted rows. Record every rejected candidate and reason. Report counts before and after each date split. Do not accept venue settlement labels as forecast targets.

## Fixed model comparison

Use ridge linear regression with an unpenalized intercept. Standardize each input using fitting data only. Minimize mean squared training error plus `lambda × sum(coefficient²)` on standardized inputs. Use the fixed candidate values `0.01, 0.1, 1, 10`. Select lambda separately for each model using mean per-event validation MAE. On an exact tie, select the larger lambda. Do not search other features, horizons or models.

BTC model: four BTC features. Augmented model: the same four plus six market features. Also report a zero-return forecast for context. After lambda selection, fit once on training plus validation rows and evaluate the test rows once.

## Date split and evaluation

Split event windows in date order before row filtering. For the 32-event dataset, use 19 training events (September 7–25), six validation events (September 26–October 1), and seven test events (October 2–8), 2026. Never randomly split hourly rows. Reject overlapping event windows. Training target intervals must end no later than validation starts; validation target intervals must end no later than test starts. Within each event, hourly targets do not overlap.

Primary score: mean per-event MAE, giving each accepted event equal weight. Report pooled-row MAE and RMSE as additional checks. Define improvement as BTC-model error minus augmented-model error. Report test results for each event, day-win count, median daily improvement, and improvement with each test event omitted in turn. Do not treat hourly rows as independent trials or report statistical significance from them. An event with no accepted rows is a coverage failure, not a zero-error day.

The test set is used once by this fixed experiment. Re-running the same protocol is a reproducibility check, not new validation. Changes after test inspection require new untouched data. Seven test days cannot establish a general forecasting advantage.

## Deliverables and acceptance

One standard-library script, saved-fixture tests, exact derived rows, rejection records, input/protocol/code hashes, split assignments, validation choices, test predictions and a short Markdown report. Runtime outputs stay outside Git.

Acceptance requires no future feature inputs, no full-history selection filter, identical evaluation rows for both models, event/date separation, fitting-only standardization, explicit missing-data failures, a repeatable local-data run and honest qualification limits. A null or negative result is a valid result. Model results do not clear the price-definition, historical-publication, rule-version or pricing gates.
