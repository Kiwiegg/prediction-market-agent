# Prediction-Market Consistency Agent

Day 1 starts with a single read-only ingestion script. It uses Python's standard library and JSON files; no database, services, API keys, or dependencies are required. Python 3.10 or newer is recommended.

## Run

```sh
python3 ingest.py --limit 10
```

The default collects up to ten active, open markets ordered by reported liquidity. This is an ingestion smoke universe, not a verified threshold family. Manually seed a specific event or market for the research universe:

```sh
python3 ingest.py --event-slug YOUR_EVENT_SLUG --limit 50
python3 ingest.py --market-slug YOUR_MARKET_SLUG
```

Run from the repository root. Outputs default to `data/`; use `--output PATH` to change it. `--timeout 15` controls each HTTP attempt and `--retries 2` bounds retries. A complete collection exits 0; a partial or failed collection exits 1 and saves the failure manifest. Network/filesystem interruption can prevent manifest completion; do not treat a missing manifest as a successful run.

An event selector keeps one family together but does not establish its semantics. Event responses are capped at the selected limit, with no claim of exhaustive exchange discovery. No LLM extraction, proofs, or trading is implemented yet.

## Saved records

Each run gets its own folder:

```text
data/runs/<run_id>/
  manifest.json
  responses/
    000.json
    001.json
    ...
```

Responses contain the exact API response bytes, including error bodies. Files keep the `.json` extension even for malformed responses so the original input is retained. The manifest contains retrieval timestamps, URLs, response paths and hashes, normalized rules, token mappings, book/fee references, and issues. Rule text lives directly in the manifest with its hash. Nothing is deduplicated: every response is saved separately, including repeated requests and retries.

Read a market's `source_observation`, look up that index in `observations`, and open its `body_path` relative to the run folder. Book and fee records use the same mechanism. Requests are sequential; paired books are not simultaneous snapshots. `endDate` remains trading-end metadata and is never substituted for observation or resolution time.

Older runs using schema version 1 and `data/blobs/` are left intact. New schema version 2 runs use this folder layout; no migration is required for the ingestion command.

Token mapping uses outcome labels, not assumed array ordering. Both token books are fetched. Book identity, finite price/size values, tick/minimum-size fields, and crossed quotes are checked. Source depth order is preserved. Market-specific CLOB info and per-token fee responses are stored without asserting a verified fee formula.

## Venue boundaries

A `complete` run means the requested data passed ingestion checks. It does **not** mean a market is pricing-eligible or that its rules are complete enough to trade.

All records start with `pricing_eligible: false`, no approved operations, and no semantic review. Negative-risk mechanics are explicitly unsupported. Position system, collateral, and binary payout model remain unverified unless actual adapter verification is added later; the script never substitutes a generic collateral or payout assumption. The source's denomination/version fields are retained only as metadata.

Gamma descriptions are retained as supplied rule text. The script does not fetch linked resolution websites, validate exception clauses, or establish an authoritative interpretation. Fees are captured as inputs, not executable cost calculations. Quote freshness and cross-leg skew must be evaluated at a later decision time.

## Check offline

```sh
python3 -m unittest discover -s tests -v
```

Fixtures are explicitly synthetic, not live market evidence. Tests use temporary directories and no network. The test suite verifies independent per-run storage, source traceability, rule changes, reversed outcome ordering, invalid mappings, unsupported mechanics, missing data, malformed/nonfinite books, and failed/retried requests.

## Live smoke check

```sh
python3 ingest.py --limit 1 --retries 0 --timeout 5
```

Inspect the manifest rather than only the exit code. Then run twice against a selected event to check its real rules, mapping, books, and fee metadata. Each run saves its own responses, whether or not they changed.

The development environment's smoke attempt on 2026-10-09 failed DNS resolution. Live integration and venue verification remain incomplete. See [Day 1 validation](docs/day1-validation.md).

## Authentication and API versions

The script calls Gamma (`gamma-api.polymarket.com`) and CLOB (`clob.polymarket.com`) public read endpoints. Public market data does not require credentials. Private CLOB requests and order placement require authentication; this script does neither. It also makes no LLM calls, so no model-provider key is needed yet. See [official API and authentication guidance](https://docs.polymarket.com/getting-started/api).

The [Data API v1-to-v2 migration](https://docs.polymarket.com/migrate/data-api-v1-to-v2) concerns the separate `data-api.polymarket.com` service. We do not call that service. If positions, activity, or other Data API reads are added, use its `/v2` routes and documented response envelope; do not append `/v2` to Gamma or CLOB routes by assumption.

## API references

The read-only routes and response fields were checked against the official documentation on 2026-10-09:

- [Market discovery](https://docs.polymarket.com/api-reference/markets/list-markets)
- [Order books](https://docs.polymarket.com/api-reference/market-data/get-order-book)
- [CLOB market metadata](https://docs.polymarket.com/api-reference/markets/get-clob-market-info)
- [Token fee inputs](https://docs.polymarket.com/api-reference/market-data/get-fee-rate)

Runtime data is ignored by Git. See [repository rules](CONTRIBUTING.md) for semantic commit boundaries.
