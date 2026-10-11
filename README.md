# Prediction-Market Consistency Agent

See [project status and agent handoff](STATUS.md) for milestone progress, open checks, and the next task.

Historical collection uses plain Python 3.11+ and JSON files. No third-party dependencies, API keys, model subscription, database or service are required. See the [research plan](docs/historical-bitcoin-action-plan.md) and [collection validation](docs/history-validation.md).

## Collect Bitcoin history

Start with `data/README.md` for the current local dataset, or the [data guide](docs/data-guide.md) for the file shapes and real examples. The review dataset is `data/bitcoin/`; older runs and probes are under `data/archive/`.

```sh
python3 collect_history.py --start 2026-09-01T00:00:00Z --end 2026-10-10T00:00:00Z --limit 40 --workers 8
```

The completed pilot is documented in [collection validation](docs/history-validation.md), including its local review directory and remaining analysis gates.

The default discovers closed events under Gamma's Hit Price tag, filters for Bitcoin, and follows pages. It selects a bounded pilot across observed series, taking recent IDs within each series. `--limit` counts events, not markets. Date filters use venue end metadata, which can differ from the rule window when a hit resolves early. This is a disclosed discovery scope, not every Bitcoin event ever created. Use `--tag-id 102516` for Multi Strikes discovery.

To collect specific events instead of listing:

```sh
python3 collect_history.py --slug what-price-will-bitcoin-hit-on-october-9-2026 --slug what-price-will-bitcoin-hit-in-september-2026
```

A saved Gamma event or array can supply the catalog with `--events-file PATH`; history requests still use the network, and the original catalog receipt time remains unknown. Each run writes `data/collections/<run_id>/catalog.json`, `coverage.json`, `report.md`, and per-event directories containing `markets.json`, `prices.json`, `btc.json`, `labels.json`, `observations.json`, and `coverage.json`. Runtime data stays out of Git.

The collector retrieves YES history from Data API v2, paginates cursors, and preserves coarse lifetime and granular window series separately. It stores actual resolution widths, receipt times, source hashes, errors, and cutoff candidates at 24/6/1 hours before the rule window or noon candle. `observations.json` also contains candidates before a hit window ends, the last completed source candle, and whether the barrier was already reached at that time. A candidate's bucket must end before the cutoff. Candidates have an age but no freshness qualification yet. Resolved zero-width points are conservatively quarantined because they can be synthetic settlement values. Price aggregation semantics remain unverified.

`bitcoin_history_templates.json` contains inspected exact daily/weekly/monthly Binance hit-rule templates; a noon-close template is in the script. Unknown or changed rules retain their source text with unsupported semantics. Weekly/monthly creation-based windows retain exact creation times and require boundary review before labels are accepted. Binance one-minute candles include seven days of preceding data by default (`--lookback-days`). Incomplete future windows cannot establish a NO outcome. Rule-update flags quarantine labels, and venue outcomes remain separate from independently calculated source outcomes.

Exit 1 means a request failed, a pagination/selection cap truncated collection, or there were no selected events; available data and issues remain saved. Exit 0 only establishes completion of the requested collection. `analysis_ready` and `pricing_eligible` remain false until price definitions, historical rule versions and the relevant data-quality gates are verified. The report does not claim forecast performance. No order books, wallet data, trading or model calls are collected by this script. The earlier Codex discovery pipeline has been removed.

Rebuild derived cutoff records and aggregate coverage/report without network, preserving collected source files:

```sh
python3 collect_history.py --derive-run data/collections/YOUR_RUN
```

## Existing market ingestion

```sh
python3 ingest.py --limit 10
```

The default collects up to ten active, open markets ordered by reported liquidity. This is an ingestion smoke universe, not a verified threshold family. Manually seed a specific event or market for the research universe:

```sh
python3 ingest.py --event-slug YOUR_EVENT_SLUG --limit 50
python3 ingest.py --market-slug YOUR_MARKET_SLUG
```

Run from the repository root. Outputs default to `data/`; use `--output PATH` to change it. `--timeout 15` controls each HTTP attempt and `--retries 2` bounds retries. `--workers 8` (the default) permits eight concurrent HTTP requests; use `--workers 1` for sequential fetching or up to 16 for higher concurrency. A complete collection exits 0; a partial collection exits 1 and saves available market data with issues. Discovery failure prints an error to stderr, exits 1, and creates no dataset. No request log is written.

An event selector keeps one family together but does not establish its semantics. Event responses are capped at the selected limit, with no claim of exhaustive exchange discovery. Historical collection uses the separate command above; proofs and trading are not implemented.

## Saved records

Each run saves one file: `data/runs/<run_id>/markets.json`. It is a JSON list of self-contained market records. There is no manifest, request log, response archive, or deduplication.

Each record includes:

- `market_id`, `condition_id`, `question`, and `slug`.
- `event_id` identifies the parent event for grouping. An event selector supplies the parent ID directly. Missing or unexpectedly multiple parent entries produce an issue rather than a guessed ID.
- `rules`, exactly as supplied in the description, `rules_sha256`, and `resolution_source`.
- `end_date` and `fetched_at`. The end date is source metadata, not an inferred observation or settlement time.
- `outcomes.YES` and `outcomes.NO`, each containing `token_id`, the full parsed `book` and `fee`, and separate `book_fetched_at` / `fee_fetched_at` timestamps.
- `trading_parameters` with readable order-limit and fee fields, `neg_risk`, venue verification status, and `issues`.

Later steps can read a record directly: semantic extraction uses its question and rules, while pricing uses its outcome books and fees. Missing data remains null or empty and is flagged in `issues`. Quote requests run concurrently through a bounded standard-library thread pool. Each response retains its own receipt timestamp; parallel fetching does not make the books an atomic snapshot. Output market order remains the discovery order. JSON decimal numbers are parsed as strings to avoid binary floating-point rounding.

Old run files are left intact; new market records use schema version 6. Token mapping uses labels rather than assuming YES is first. Book identity, finite prices/sizes, tick/minimum-size fields, and crossed quotes are checked. Source depth order is preserved. Fee inputs and metadata are captured without asserting a verified formula or payout model.

`trading_parameters` maps CLOB `mos` to `min_order_size`, `mts` to `tick_size`, `mbf` / `tbf` to `maker_base_fee_bps` / `taker_base_fee_bps`, and `fd` to `fee_curve` with `rate`, `exponent`, and `takers_only`. It includes its own `fetched_at`. Missing values remain null. Base fees are expressed in basis points; the curve rate is a separate parameter, not interchangeable with a basis-point fee. Fee formulas remain unverified. Tokens are already stored under `outcomes` and cross-checked against CLOB. Rewards, unrelated feature flags, and undocumented abbreviations are omitted.

## Venue boundaries

A `complete` run means the requested data passed ingestion checks. It does **not** mean a market is pricing-eligible or that its rules are complete enough to trade.

All records start with `pricing_eligible: false`, no approved operations, and no semantic review. Negative-risk mechanics are explicitly unsupported. Position system, collateral, and binary payout model remain unverified unless actual adapter verification is added later; the script never substitutes a generic collateral or payout assumption. The source's denomination/version fields are retained only as metadata.

Gamma descriptions are retained as supplied rule text. The script does not fetch linked resolution websites, validate exception clauses, or establish an authoritative interpretation. Fees are captured as inputs, not executable cost calculations. Quote freshness and cross-leg skew must be evaluated at a later decision time.

## Check offline

```sh
python3 -m unittest discover -s tests -v
```

Offline inputs are synthetic except for the small inspected rule-template texts; fixture success does not establish live market coverage. Tests use temporary directories and no network. The test suite verifies self-contained per-run storage, event membership, rule changes, reversed outcome ordering, invalid mappings, unsupported mechanics, missing data, malformed/nonfinite books, and failed/retried requests.

## Live smoke check

```sh
python3 ingest.py --limit 1 --retries 0 --timeout 5
```

Inspect `markets.json` and its `issues` rather than only the exit code. Then run twice against a selected event to check its real rules, mapping, books, and fee metadata. Each run saves its own market records, whether or not they changed.

A live 50-market run on 2026-10-09 succeeded with eight workers, capturing 100 books and 100 token fee responses in 20.62 seconds. Network access required sandbox approval. Venue and fee-formula verification remain incomplete. See [Day 1 validation](docs/day1-validation.md).

## Authentication and API versions

`ingest.py` calls Gamma (`gamma-api.polymarket.com`) and CLOB (`clob.polymarket.com`) public read endpoints. Public market data does not require credentials. Private CLOB requests and order placement require authentication; this script does neither. Neither script makes LLM calls. See [official market API and authentication guidance](https://docs.polymarket.com/getting-started/api).

The [Data API v1-to-v2 migration](https://docs.polymarket.com/migrate/data-api-v1-to-v2) concerns the separate `data-api.polymarket.com` service. `collect_history.py` uses its `/v2/prices-history` and `/v2/resolutions` routes; do not append `/v2` to Gamma or CLOB routes by assumption.

## API references

The read-only routes and response fields were checked against the official documentation on 2026-10-09:

- [Market discovery](https://docs.polymarket.com/api-reference/markets/list-markets)
- [Order books](https://docs.polymarket.com/api-reference/market-data/get-order-book)
- [CLOB market metadata](https://docs.polymarket.com/api-reference/markets/get-clob-market-info)
- [Token fee inputs](https://docs.polymarket.com/api-reference/market-data/get-fee-rate)

Runtime data is ignored by Git. See [repository rules](CONTRIBUTING.md) for semantic commit boundaries.
