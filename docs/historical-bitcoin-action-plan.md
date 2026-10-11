# Bitcoin market history: findings and action plan

Approved collection direction · 2026-10-10. Collection is implemented; analysis remains proposed. See [live validation](history-validation.md) for current evidence and limitations.

We can retrieve enough public data to start a historical study. The useful question is whether threshold prices tell us more about Bitcoin's future price path than its current price and recent volatility already do. Start by measuring coverage and settlement rules, then compare daily, weekly, and monthly markets. We do not yet have evidence that one timeframe is best or that these signals are tradable.

## What the API probes established

This table records the initial probes. Follow-up collection succeeded for daily, weekly and monthly hit markets, including the October 10 seed. Actual rules include full-period and creation-based windows. See [live validation](history-validation.md) for the newer evidence.

These were small live probes without signing credentials. They establish availability for the sampled requests, not complete historical coverage. Local responses are under ignored `data/archive/probes/`; another checkout must repeat the probes.

| Source | Observed result | What it gives us / limitation |
| --- | --- | --- |
| Gamma event-by-slug | June 30, 2026 Bitcoin above event: 11 closed markets, thresholds $52,000–$72,000 | Titles, rules, condition IDs, YES/NO token mappings and reported outcomes |
| Data API v2 prices-history | The $60,000 YES token returned 15 points for lifetime history; an explicit three-hour request also returned 15 | Historical prices are available, but points are sparse and requested resolution does not guarantee that cadence |
| Data API v2 prices-history | Five-minute history for that June window returned no points | Fine historical coverage cannot be assumed |
| Data API v2 trades | Five fills returned, with a next-page cursor | Trade-level prices, shares and times; full pagination and older coverage remain untested |
| Data API v2 resolutions | 11 records returned for the June event | Independent resolution status; oracle prices are outcome encodings, not Bitcoin prices |
| Binance BTC/USDT candles | The June 30 noon Eastern one-minute candle closed at 58,441.40 USDT | A price from the actual settlement source; consistent with the sampled $60,000 NO outcome |
| CLOB prices-history | 56 points for the same seven-day window at requested three-hour fidelity | Potential alternative, but it differs from Data v2 and must be compared before use |
| Gamma series | Series 45 returned 11 nested events, omitting the June event despite its membership | A series response is not a complete historical catalog |
| User's October 10 “hit” event and date-filtered event lists | Later requests returned HTTP 403 | Exact hit rules, other timeframe availability, and catalog pagination remain unverified |

Sources: [June event metadata](https://gamma-api.polymarket.com/events/slug/bitcoin-above-on-june-30-2026), [Gamma event-list documentation](https://docs.polymarket.com/api-reference/events/list-events), [Data API v2 schema](https://data-api.polymarket.com/v2/openapi.json), [CLOB schema](https://docs.polymarket.com/api-spec/clob-openapi.yaml), [Binance market-data documentation](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market).

The June contract uses Binance BTC/USDT's one-minute candle **close at noon Eastern**, with a strict “higher than” comparison. It is not a daily close or a BTC/USD contract. The rules refer to the title for the date and threshold, so extraction must preserve and interpret both. Noon Eastern is 16:00 UTC in summer and 17:00 UTC in winter; the candle closes almost a minute after its start.

Two historical-price traps need checking before analysis:

- Data v2 documents permanent three-hour/twelve-hour history and shorter retention for finer buckets. An empty fine-resolution response means unavailable coverage, not zero activity. Its price-point schema does not establish whether each price is a midpoint, last trade, or another aggregate.
- Resolved histories can append a synthetic settlement point. Our June three-hour response included a zero-resolution terminal price of zero at 15:00 UTC, before the contract's 16:00 UTC measurement candle. Using it as a historical forecast input would leak the outcome. Keep settlement values separate and identify these points explicitly; do not discard every zero-resolution observation because genuine ticks can have that resolution too.

## Which relationships are useful?

First classify the actual contract predicate: price at a moment, maximum reached during a window, or minimum reached during a window. The word “hit” in a title is insufficient. Inspect whether rules use candle highs/lows, trades, strict or inclusive thresholds, the exchange, timezone and exact window boundaries. The [October 10 example](https://polymarket.com/event/what-price-will-bitcoin-hit-on-october-10-2026) is the proposed seed; its rules are not yet verified here.

Within one compatible window, a higher upside barrier is harder to reach; a lower downside barrier is harder to reach. These ladders can describe expectations about the maximum and minimum. A high target and a low target can both be hit on the same day, so they are not exclusive outcomes. We cannot infer the order of those hits or a joint path distribution from their separate prices.

Across windows, distinguish logical relationships from statistical ones:

- If a daily window is entirely inside a weekly window, hitting the same upside barrier that day implies hitting it that week, provided the source and measurement rules agree. Analogous nesting applies to downside barriers.
- Monday and Tuesday alone do not imply one another. Their difference may reflect expected volatility, scheduled news, liquidity, or stale prices. Compare them at the same information time and account for different distances from spot and time remaining.
- A qualifying close above a barrier can imply a hit within a containing window only when the hit measurement actually includes that close. A hit does not imply a later close above the barrier.
- Where daily windows exactly partition a longer window, the longer-window hit is the union of daily hits. Its probability lies between the largest daily probability and the sum of daily probabilities capped at one. This is a conditional consistency check, not a way to recover dependence or a trading opportunity from historical price points.

These relationships motivate three research outputs: threshold curves within an event, a view of how barrier expectations change with horizon, and changes in those curves as Bitcoin moves or news arrives. A terminal-price ladder describes a different quantity from a maximum/minimum ladder; keep them separate.

## Choosing timeframes

Pilot daily, weekly and monthly events rather than selecting a winner now. Daily events offer more repeated outcomes; weekly/monthly events offer longer horizons and potentially more threshold coverage, but fewer independent examples. Longer windows also require more underlying candles to verify a hit.

For each family, report event count, threshold count, price coverage at forecast times, gaps, available activity, rule changes and settlement agreement. Begin with approximately 30 closed daily periods plus whatever comparable weekly/monthly periods are available over the same calendar range. Include a small older sample to test retention. This is a coverage pilot, not a sufficient sample for a strong forecasting claim.

Compare prices both at common timestamps and at matched time remaining. Neither comparison answers the other question. Initial candidate cutoffs are 24 hours, six hours and one hour before a window starts or a terminal measurement begins, where the market already exists. For in-window hit forecasts, use known running highs/lows and time remaining; once a barrier has already been reached, its eventual outcome is no longer a forecast of a new move.

## Work and deliverables

### 1. Build the catalog and prove coverage

Use Gamma event listing with Bitcoin tags, date ranges and pagination, then filter by inspected rule templates. Seed known slugs, but do not treat guessed slugs or series membership as a complete catalog. Retry inaccessible endpoints only through permitted access; retain the failure and stop claiming completeness when a page cannot be fetched.

Deliver `catalog.json` and a short coverage report. Each contract identifies its event, condition, actual token mappings, title/rule text and hashes, threshold, comparator, source, measurement kind, timezone and interval. Store fetch times and schema versions. Unknown templates remain unsupported. Current rules are not proof of original historical rules: retain update/dispute flags and quarantine unresolved version questions.

**Check:** Inspect real daily, weekly and monthly rules and show which are comparable. Follow pagination on both an event listing and trades. Report missing pages and unavailable timeframes. This is the first implementation milestone after plan review.

### 2. Collect histories and settlement evidence

Use one plain `collect_history.py` script, standard-library HTTP and bounded concurrency. Keep parsed JSON records in separate local runs; no database, raw-byte archive, deduplication store or embedded Codex session.

Per event, store `markets.json`, `prices.json`, `btc.json`, and `labels.json`. Add `activity.json` only if the pilot shows it helps; record coverage and failures in `coverage.json`. Derived records reference their input files/hashes and schema versions.

Collect YES price histories, actual source BTC candles and resolution records. NO token identities remain in metadata; collect NO histories only for a specific comparison. Start with price history and use trades where needed to check price semantics or reconstruct finer observations. Data v2 condition/event trade queries use their documented historical window and ignore start/end filters, so filter times locally and follow every cursor with unchanged query filters. Default taker-only results avoid counting maker rows twice. Do not assume the API includes every tiny fill or that a transaction hash identifies a unique fill.

Exclude old order books, wallet profiles, balances and positions. Do not use present-day lifetime volume as a historical feature. Optional activity must be computed solely from fills available before the cutoff. Oracle outcome encodings stay separate from underlying BTC values; missing or nonbinary settlement evidence stays unresolved.

**Check:** Match settlement labels against the source candle close or observed window high/low, according to the verified rules. Record discrepancies instead of overwriting them. Reject buckets extending past the forecast cutoff, synthetic terminal points, future fills, missing source data and overly old observations. No interpolation using later prices. Test DST, threshold equality, window boundaries, sparse data and pagination failures with saved fixtures.

### 3. Analyze what information the curves contain

Use a separate `analyze_history.py` script producing a readable report and plots. First show raw curves, timestamps and gaps; any monotonic fitting is a separate derived series so it cannot hide observed inconsistencies.

For terminal ladders, YES prices for strict above-threshold contracts approximate a survival curve; their complement corresponds to price at or below the threshold. For hit ladders, use separate maximum/minimum curves. Prices are noisy market signals, not established fair probabilities. Sparse thresholds cannot determine the tails, an expected Bitcoin price, or a full path distribution without additional assumptions.

Compare against a simple baseline using spot and trailing volatility known at the cutoff. Ask whether ladder shape, upward/downward asymmetry or changes in prices add predictive information. Evaluate threshold outcomes and calibration, and report coverage alongside scores. Keep all thresholds from an event together; use chronological holdouts and account for overlap between daily, weekly and monthly windows. Count independent periods, not correlated threshold markets, when discussing sample size.

**Check:** Resolve what historical price points represent before interpreting results, demonstrate a no-future-information trace, and compare the same supported observations against the baseline. If the pilot is too small or gaps dominate, expand collection before drawing conclusions. Forecast value alone does not establish executable profit; execution costs and current books belong to a later, separately scoped check.

## Review decision

The proposed next step is the catalog/coverage pilot across timeframes, with the user's “hit” example as a seed. Choose the main family only after inspecting actual rules and measuring available history. The collector is implemented; the analysis script remains proposed. The live validation document records actual collection and remaining gaps. Original arbitrage benchmark, pricing and replay gates remain deferred and incomplete.
