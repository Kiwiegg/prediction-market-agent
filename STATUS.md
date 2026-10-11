# Project status

Updated: 2026-10-11. Read this file at task start. The specification and milestone document preserve the original research requirements; this file records the authorized scope and actual completion.

## Current handoff

The user authorized historical Bitcoin data collection, including daily/weekly/monthly hit events, and removal of the runtime Codex discovery experiment. `collect_history.py` is implemented using standard-library Python and JSON. Live collection evidence and remaining limitations are in [history validation](docs/history-validation.md). The review dataset is `data/history/20261010T125801Z-478e8721/`: 39 events (32 daily, 5 weekly, 2 monthly), 704 markets, and complete collection for that selection after separate retries. Start with its `report.md`. No analysis/backtest, forecasting claim or pricing eligibility is implemented.

Day 1 implementation remains closed at the user's direction with its original acceptance gaps retained. The broader labeling benchmark, proof, pricing and replay milestones remain deferred/incomplete. Do not start those solely because they appear in the original milestone document.

| Work | State | Evidence / gaps |
| --- | --- | --- |
| Day 1 ingestion | Implementation complete; acceptance gaps retained | [Day 1 validation](docs/day1-validation.md); commit `ab90223` |
| Historical catalog and collection | Implemented; live pilot collected | [History validation](docs/history-validation.md); inspect coverage before using data |
| Historical signal analysis | Not started | Price definitions, rule-version review, freshness/gap gates and chronological evaluation remain open |
| Original LLM benchmark, proof, pricing and replay | Deferred/incomplete | Original milestone acceptance checks are not satisfied by historical collection |

## What exists

- `collect_history.py`: closed-event discovery with date/tag filters and pagination; explicit slugs or saved Gamma input; bounded concurrency; independent local runs. Data API v2 YES price histories and resolution records, and Binance BTC/USDT one-minute candles. No signing credentials or model calls.
- `bitcoin_history_templates.json`: inspected exact daily, weekly and monthly hit templates. The collector also supports the inspected noon-Eastern terminal-close template. Unknown or changed rules abstain. Calendar windows and creation-based windows remain distinct; creation boundaries require review.
- JSON artifacts: catalog and coverage at run level; per-event market definitions, price series, source candles, labels and coverage. Source hashes, receipt times, token mappings and input references are retained. Coarse and finer price series remain separate. Settlement records are separate from underlying prices.
- `ingest.py`: the existing read-only current-market Gamma/CLOB collector, actual YES/NO books and fee inputs. Schema 6, bounded request concurrency, no verified fee or venue adapter. It remains available for later work.
- 30 offline checks pass (17 ingestion, 13 historical); saved-data replay generated 3,906 cutoff records. The pilot has 651 supported templates and granular history for 650 markets. All 704 settlement records carry rule-update flags; 53 contracts have unsupported rule variants. Analysis eligibility remains false.
- Offline ingestion and historical-collection checks. The earlier `discover.py`, its dedicated tests/fixtures, prompt, schema and guide/validation docs were removed at the user's request; Git history preserves that experiment.

## Decisions to preserve

Keep standard-library scripts and JSON files. No database, services, raw-byte archive, blob deduplication, manifest or request log. Do not collect historical order books, wallet profiles, balances or positions for this study. Runtime data and credentials stay out of Git. Small reviewed rule-template texts can be checked in; collected datasets cannot.

Use Data API `/v2` routes, but do not append `/v2` to Gamma/CLOB. Public reads need no API key. No Codex CLI or OpenAI subscription is required for collection. Preserve source denomination BTC/USDT and source rules rather than substituting BTC/USD.

“Hit” means a path condition under inspected rules; a noon close is a terminal condition. Full-period and creation-based windows differ even within one event. Daily/weekly/monthly series titles do not prove compatible semantics. Separate windows cannot imply one another merely because they concern Bitcoin.

Prices are historical research observations, not executable quotes. Bucket ends must precede forecast cutoffs. Resolved zero-width points are conservatively quarantined; this can also exclude genuine ticks. Missing history is not zero activity. A source NO outcome needs the complete measurement window. All analysis/pricing eligibility remains false.

## Open checks

- Establish what historical price points represent and handle synthetic settlement values more precisely before probability/forecast interpretation.
- Review historical rule-version flags and creation-minute boundaries. Current rule text is not proof of the original historical rule version; quarantine unresolved cases.
- Qualify observations by freshness, actual resolution, completeness and coverage; cutoff candidates alone are not analysis-ready rows.
- Verify trade pagination and trade-level reconstruction only if finer history is needed. Trade/activity collection is not implemented and no wallet data is needed.
- Freeze a chronological evaluation design that groups correlated thresholds and overlapping windows. Compare against spot/volatility before claiming added predictive information. No backtest exists.
- Retain original venue, collateral, payout-unit, fee-rounding, live failure-path and human pricing-review gates before any pricing work. Day 1 negative-risk mechanics remain unsupported.

## Resume protocol

1. Read repository instructions, this file, specification, milestones, research plan and history validation; inspect Git status before changes.
2. Inspect the latest pilot's catalog, coverage and representative records. Next resolve data-quality/semantic gaps and select usable observations before implementing analysis. Do not reinstall a runtime LLM pipeline by inference.
3. Run `python3 -m unittest discover -s tests -v`. Live checks are opt-in and separate from offline evidence; see README commands.
4. Update this handoff and detailed validation in the same semantic commit as work. Record failed checks explicitly. Runtime data is local and ignored; another checkout must recollect it.
