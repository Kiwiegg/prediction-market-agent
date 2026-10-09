# Day 1 validation — 2026-10-09

## Implemented

- One standard-library Python ingestion script with bounded discovery or explicit event/market selection.
- One `markets.json` list per run; no manifest, request log, response archive, or deduplication.
- Self-contained market records with event membership, supplied rules and hashes, outcome token mappings, inline books/fees, and receipt timestamps.
- Missing/invalid data and final retrieval errors recorded in the affected market's `issues`; discovery failures exit without a dataset.
- Readable trading parameters instead of abbreviated CLOB response fields; unknown/unsupported venue statuses with no pricing eligibility.

## Checks

`python3 -m unittest discover -s tests -v`: **17 tests passed**.

Offline synthetic tests cover standalone output records, independent runs, unchanged rules, changed rule hashes, reversed token ordering, missing rules/fees, unsupported negative risk, invalid token mappings, CLOB mapping mismatch, wrong book identity, nonfinite prices, crossed books, discovery failures, partial collection after a failed book request, parent event ID, missing/ambiguous parent handling, limits, a rate-limit retry, bounded parallel requests, preserved output order, and invalid worker counts.

The earlier sandboxed attempt failed DNS resolution. With approved network access on 2026-10-09, the command below completed successfully:

```sh
python3 ingest.py --limit 50 --workers 8 --retries 0 --timeout 10
```

Wall time: **20.62 seconds**. Output: `data/runs/20261009T024550-6add2436/markets.json`. Inspected counts: 50 markets from 8 event IDs, 100 books, 100 token fee responses, and zero ingestion issues. Venue statuses: 49 unsupported negative-risk markets and one unverified market. This is a liquid-market ingestion check, not a selected threshold-family validation or pricing eligibility result.

For 10 markets, one worker took **30.75 seconds** and eight workers took **4.39 seconds**, approximately 7× faster in this comparison. Both completed successfully. Timings are single live samples, affected by API/cache/network behavior; they do not establish a fixed throughput guarantee.

## Remaining acceptance evidence

1. Collect a real event family and inspect one record's rules, event membership, tokens, inline books, and fees.
2. Repeat collection and verify independent records and timestamps.
3. Verify position system, collateral, payout unit, and fee formulas against actual metadata and official documentation. These remain unverified.
4. Check unsupported mechanics and missing-data behavior against real markets.

The implementation remains an ingestion scaffold; live and venue-verification gates are incomplete. Runtime data is excluded from Git.
