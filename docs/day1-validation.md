# Day 1 validation — 2026-10-09

## Implemented

- One standard-library Python ingestion script with bounded discovery or explicit event/market selection.
- One `markets.json` list per run; no manifest, request log, response archive, or deduplication.
- Self-contained market records with event membership, supplied rules and hashes, outcome token mappings, inline books/fees, and receipt timestamps.
- Missing/invalid data and final retrieval errors recorded in the affected market's `issues`; discovery failures exit without a dataset.
- Unknown/unsupported venue statuses with no pricing eligibility.

## Checks

`python3 -m unittest discover -s tests -v`: **13 tests passed**.

Offline synthetic tests cover standalone output records, independent runs, unchanged rules, changed rule hashes, reversed token ordering, missing rules/fees, unsupported negative risk, invalid token mappings, CLOB mapping mismatch, wrong book identity, nonfinite prices, crossed books, discovery failures, partial collection after a failed book request, parent event ID, missing/ambiguous parent handling, limits, and a rate-limit retry.

The earlier live smoke attempt on 2026-10-09 failed DNS resolution. This refactor was validated offline; no successful live collection or venue verification is claimed.

## Remaining acceptance evidence

1. Collect a real event family and inspect one record's rules, event membership, tokens, inline books, and fees.
2. Repeat collection and verify independent records and timestamps.
3. Verify position system, collateral, payout unit, and fee formulas against actual metadata and official documentation. These remain unverified.
4. Check unsupported mechanics and missing-data behavior against real markets.

The implementation remains an ingestion scaffold; live and venue-verification gates are incomplete. Runtime data is excluded from Git.
