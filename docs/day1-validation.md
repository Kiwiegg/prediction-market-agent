# Day 1 validation — 2026-10-09

## Implemented

- One standard-library Python script with bounded discovery or an explicit event/market selector.
- Independent per-run response files, canonical rules, hashes, and retrieval manifests; no deduplication.
- Explicit YES/NO token mapping, both books, CLOB metadata, and per-token fee input capture.
- Failure records and partial-run exit status; unknown/unsupported venue statuses with no pricing eligibility.

## Checks

`python3 -m unittest discover -s tests -v`: **12 tests passed**.

Tests cover independent storage of repeated inputs with distinct observations, original-rule traceability, changed rules, missing rules/fees, unsupported negative risk, invalid/duplicate token mappings, CLOB mapping mismatch, wrong book identity, nonfinite prices, crossed books, HTTP error bodies, DNS errors, invalid JSON, event limits, and a rate-limit retry. These are offline synthetic checks.

`python3 ingest.py --limit 1 --retries 0 --timeout 5`: **exit 1**, partial run with zero markets. The request failed DNS resolution in the restricted environment. A run manifest retained the failed URL, timestamps, and error. No actual live book or rule ingestion is claimed.

## Remaining acceptance evidence

1. Collect a real event family successfully and inspect one real contract through its raw response, canonical rules, outcome mapping, books, and fee inputs.
2. Repeat collection and verify each run retains its own responses and source links, even when contents are unchanged.
3. Verify the selected markets' position system, collateral, and payout unit against actual metadata and official integration documentation. The current adapter deliberately leaves these unverified.
4. Confirm missing/unsupported mechanics produce the expected status against actual market examples, not just synthetic fixtures.

Day 1 is implemented as an ingestion scaffold but its live and venue-verification gates are incomplete.

## Local Git status

The user initialized `main`. Git writes require sandbox escalation; the user enabled the approval flow and staging/committing now work. Planning documents, repository rules, and the Day 1 implementation with tests/documentation are separate local commits. Runtime data is excluded.
