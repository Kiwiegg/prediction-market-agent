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

## Repeated live runs and record trace

The two 10-market runs are retained separately at `data/runs/20261009T024639-91805289/markets.json` and `data/runs/20261009T024629-559c6f89/markets.json`. Market `559687`, parent event `30829`, appears in both. Its discovery receipt timestamps differ (`2026-10-09T02:46:09.654090+00:00` and `2026-10-09T02:46:26.272597+00:00`), as do its book receipt timestamps.

That record retains 389 characters of supplied rules with SHA-256 `3d1bf365dbb0d29449c28c4efbe3784069de8c0e226a4f5e2463707e4b137fd7`. Its YES token is `2213957649161627793381994368131485505647723208738124952452819345058597751695`; its NO token is `44046525152074436753629616217525652949736205933417533647338274649282385796755`. Both have inline books and fee inputs. This verifies retained supplied rules and token traceability, not authoritative settlement interpretation.

## Remaining acceptance evidence

1. Select and collect a suitable numerical-threshold event family.
2. Verify position system, collateral, payout unit, and fee formulas/rounding against actual metadata and official documentation. These remain unverified.
3. Check missing-data behavior against real markets; failure paths are currently covered by offline fixtures. Unsupported negative-risk status was observed live.

Day 1 implementation is closed at the user's direction with these acceptance gaps retained in [project status](../STATUS.md). Runtime data is excluded from Git and is not available automatically in another checkout.
