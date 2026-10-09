# Project status

Updated: 2026-10-09. This file is the current handoff and progress tracker. The specification defines the research requirements; the milestone document defines deliverables; this file records actual completion and evidence.

## Current handoff

Day 1 implementation is closed at the user's direction. Ingestion works offline and live. Some original acceptance checks remain incomplete, listed below; closing implementation does not certify venue mechanics or pricing eligibility. Next planned milestone is the combined Days 2–3 block; implementation has not started. Do not start later milestones solely because they appear here.

| Milestone | State | Evidence / remaining work |
| --- | --- | --- |
| Day 1 — Market inputs | Implementation complete; acceptance gaps retained | [Validation](docs/day1-validation.md); ingestion commit `ab90223` |
| Days 2–3 — LLM labeling and benchmark | Not started; next | Working LLM pipeline, iterative development guide, schemas, 30–50 reviewed pairs, frozen test split, baseline |
| Day 4 — Proof and payoff | Not started | Threshold rules, state tables, counterexamples |
| Day 5 — Pricing | Not started | Depth, verified fees, exact decimals, freshness and size limits |
| Day 6 — Replay and report | Not started | Ledger, failed-leg handling, audit report |
| Day 7 — Validation and handoff | Not started | Demo, evaluation, runbook, limitations |

## What exists

- `ingest.py`: read-only Gamma discovery and CLOB metadata, actual YES/NO books, and token fee inputs. Bounded HTTP concurrency defaults to eight workers (maximum 16); discovery caps at 50 markets.
- Schema version 6: each run writes only `data/runs/<run_id>/markets.json`, an array of self-contained markets with `event_id`, exact supplied rules/hash, token mappings, books/fees, receipt timestamps, readable trading parameters, and issues.
- 17 offline tests with synthetic fixtures. Live 50-market collection captured 100 books and 100 fee responses with zero ingestion issues in 20.62 seconds. Ten markets took 30.75 seconds sequentially and 4.39 seconds with eight workers (single samples).
- Every record remains `pricing_eligible: false`. No extraction, proof, pricing, model calls, orders, or replay exists.

## Decisions to preserve

Use standard-library Python and JSON files. No database, separate services, raw-byte archive, blob deduplication, manifest, or request log. Preserve separate runs; failures belong in each affected market's issues. Store one parent `event_id`, and group YES/NO outcomes under their market. Keep credentials and runtime data out of Git. User decisions about storage supersede older raw-snapshot/manifest language in the specification.

Default liquidity discovery is a smoke universe, not the research benchmark. Public Gamma/CLOB reads need no API key; the Data API is not called. Do not add `/v2` to these routes based on the separate Data API migration.

## Open acceptance checks and dependencies

- Select and collect a suitable numerical-threshold family; the current live sample spans unrelated liquid events.
- Confirm supported position system, collateral, payout unit, and fee formula/rounding from actual metadata and official documentation before pricing. These are explicitly unverified; 49 of the 50 sampled markets have unsupported negative-risk mechanics.
- Missing-data failure paths passed offline fixtures; live missing-fee/failure behavior is not yet demonstrated. Live negative-risk status is demonstrated.
- Semantic interpretation and human approval remain mandatory before pricing. Books are separate timestamped responses, not an atomic snapshot; freshness/skew gates belong to pricing.

Repeated live runs and a real record trace are documented in [Day 1 validation](docs/day1-validation.md). Runtime evidence is ignored local data, so another checkout must recollect it; synthetic fixtures alone do not establish live success.

## Resume and update protocol

1. Read `AGENTS.md`, this file, the specification, and the milestone document; inspect Git status and relevant code before editing.
2. For combined Days 2–3, select a threshold family and build an initial guide/schema plus a working LLM pipeline. Iterate using development examples. Independently review and freeze held-out test labels before subsequent tuning/evaluation; keep model-assisted development labels distinct. Record live/archived inputs and unsupported cases. Deliver all combined acceptance checks from the milestone document.
3. Run offline checks with `python3 -m unittest discover -s tests -v`. Optional live check: `python3 ingest.py --limit 50 --workers 8`. See `README.md` for event selection and output inspection.
4. At each meaningful task handoff, update this file in the same semantic commit: milestone state, artifacts/checks, open gates, decisions, and next action. Put detailed evidence in `docs/` and link it here. Use Git history for the change log; avoid a second task database or duplicated chronological log.
