# Project status

Updated: 2026-10-10. This file is the current handoff and progress tracker. The specification defines the research requirements; the milestone document defines deliverables; this file records actual completion and evidence.

## Current handoff

Day 1 implementation is closed at the user's direction. Some acceptance checks remain incomplete; closing implementation does not certify venue mechanics or pricing eligibility. The active task is historical Bitcoin API probing and an action plan for review. The user now prioritizes recurring threshold and hit markets across days and other timeframes, using deterministic collection rather than an embedded Codex runtime. [API findings and proposed milestones](docs/historical-bitcoin-action-plan.md) record successful June probes and later HTTP 403 failures for the user's October hit example. Catalog coverage, actual hit rules, price-point semantics, full pagination and timeframe selection remain unverified. No historical collector or backtest is implemented; implementation awaits the user's direction on the plan.

| Milestone | State | Evidence / remaining work |
| --- | --- | --- |
| Day 1 — Market inputs | Implementation complete; acceptance gaps retained | [Validation](docs/day1-validation.md); ingestion commit `ab90223` |
| Days 2–3 — LLM labeling and benchmark | Pipeline implemented; milestone incomplete | [Pipeline validation](docs/pipeline-validation.md); real candidates, review, benchmark, frozen split, baseline, and general relation schema remain open |
| Day 4 — Proof and payoff | Not started | Threshold rules, state tables, counterexamples |
| Day 5 — Pricing | Not started | Depth, verified fees, exact decimals, freshness and size limits |
| Day 6 — Replay and report | Not started | Ledger, failed-leg handling, audit report |
| Day 7 — Validation and handoff | Not started | Demo, evaluation, runbook, limitations |

## What exists

- `ingest.py`: read-only Gamma discovery and CLOB metadata, actual YES/NO books, and token fee inputs. Bounded HTTP concurrency defaults to eight workers (maximum 16); discovery caps at 50 markets.
- Schema version 6: each run writes only `data/runs/<run_id>/markets.json`, an array of self-contained markets with `event_id`, exact supplied rules/hash, token mappings, books/fees, receipt timestamps, readable trading parameters, and issues.
- 40 offline tests with synthetic fixtures. Live Day 1 collection captured 50 markets, 100 books and 100 fee responses in 20.62 seconds. Ten markets took 30.75 seconds sequentially and 4.39 seconds with eight workers (single samples).
- `discover.py`: Codex CLI chooses bounded Gamma search/read actions; Python executes read-only requests, reusing ingestion. It also accepts saved markets and can validate/replay saved model output without inference. Schema v1 records closing thresholds, settlement time/source/price definition, exceptions, and exact evidence spans with source hashes and token mappings. Session files retain native CLI responses, prompt/schema versions, usage, latency, inputs, and errors.
- Real Codex CLI 0.161.0 / gpt-6.1-sol extraction on two synthetic markets succeeded using existing ChatGPT login in 33.48 seconds. Full live search remains unverified (HTTP 451). See the validation document; synthetic semantics do not establish real-market accuracy.
- Every record remains unreviewed, with pricing eligibility false. No distribution grouping/curves, forecasts, proof, pricing, orders, or replay ledger exists. Saved-response extraction validation is separate from execution replay.

## Decisions to preserve

Use standard-library Python and JSON files. No database, separate services, raw-byte archive, blob deduplication, manifest, or request log. Preserve separate runs; failures belong in each affected market's issues. Store one parent `event_id`, and group YES/NO outcomes under their market. Keep credentials and runtime data out of Git. User decisions about storage supersede older raw-snapshot/manifest language in the specification.

Default liquidity discovery is a smoke universe, not the research benchmark. Public Gamma/CLOB reads need no API key; the existing ingestion script does not call the Data API; historical probes used public Data API v2. Do not add `/v2` to these routes based on the separate Data API migration.

The user prioritized historical Bitcoin threshold and hit-market information over collecting rare relationship/arbitrage examples. The proposed new runtime uses deterministic scripts, not model inference. Start with available real threshold families rather than forcing 30–50 pairs. The user selected Codex CLI with ChatGPT sign-in to avoid metered API-key inference. No `.env` or OpenAI API key is required. Python executes market requests; inference has built-in tools/delegation disabled. Model calls consume plan allowance and can hit limits.

## Open acceptance checks and dependencies

- Select and collect a suitable numerical-threshold family; the current live sample spans unrelated liquid events.
- Complete live LLM discovery where Gamma search access is permitted; the endpoint returned HTTP 451 here. Do not bypass access denial. Existing saved-market extraction is available.
- Inspect real contract outputs and group compatible closing-price contracts for later distribution analysis. Record review/corrections against rule hashes; human approval remains required before pricing. The current schema/guide are initial development versions, not a frozen benchmark or calibrated accuracy result.
- Confirm supported position system, collateral, payout unit, and fee formula/rounding from actual metadata and official documentation before pricing. These are explicitly unverified; 49 of the 50 sampled markets have unsupported negative-risk mechanics.
- Missing-data failure paths passed offline fixtures; live missing-fee/failure behavior is not yet demonstrated. Live negative-risk status is demonstrated.
- Semantic interpretation and human approval remain mandatory before pricing. Books are separate timestamped responses, not an atomic snapshot; freshness/skew gates belong to pricing.

Repeated live runs and a real record trace are documented in [Day 1 validation](docs/day1-validation.md). Runtime evidence is ignored local data, so another checkout must recollect it; synthetic fixtures alone do not establish live success.

## Resume and update protocol

1. Read `AGENTS.md`, this file, the specification, and the milestone document; inspect Git status and relevant code before editing.
2. Review the historical action plan and, when authorized, implement its catalog/coverage pilot. Inspect hit-market windows and daily/weekly/monthly rule templates before selecting a primary family. Existing Codex discovery remains available as an earlier experiment; it is not required in the proposed collection runtime. Original benchmark/reference labels and arbitrage milestones remain deferred and incomplete.
3. Run offline checks with `python3 -m unittest discover -s tests -v`. See `README.md` for ingestion, Codex discovery, saved-input extraction, and no-network saved-response demo commands. Fixture checks, live model smoke, and live venue integration are separate evidence.
4. At each meaningful task handoff, update this file in the same semantic commit: milestone state, artifacts/checks, open gates, decisions, and next action. Put detailed evidence in `docs/` and link it here. Use Git history for the change log; avoid a second task database or duplicated chronological log.
