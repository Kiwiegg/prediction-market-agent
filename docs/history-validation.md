# Historical collection validation

Collected 2026-10-10; final verification 2026-10-11. Public read-only APIs, no credentials or model calls. Runtime data is ignored local JSON, not committed evidence that another checkout automatically possesses.

## Offline checks

`python3 -m unittest discover -s tests -v`: 30 checks passed (17 existing ingestion checks and 13 historical checks). Historical checks cover actual reversed token mapping, exact-template abstention, DST, weekly/monthly boundaries, strict/inclusive comparator extraction, source-price equality, rule-version quarantine, unavailable future buckets, synthetic settlement-point quarantine, invalid decimal prices, cursor filter preservation, repeated cursors, partial pagination failures, missing Binance candles, and saved-data replay that excludes future prices/hits without changing source files. Small inspected rule texts are real samples; the test market data are synthetic. Fixture success does not establish live coverage. Final saved-data audit checked all 39 events: 3,906 cutoff records, matching input hashes, price bucket ends no later than their cutoff, and source candle closes strictly before it. This does not establish price aggregation semantics or historical rule correctness.

## Live collection

Initial headerless probes returned HTTP 403. Subsequent requests using the existing `ingest.fetch` public client succeeded. These are endpoint availability observations, not proof that access is always reliable.

A corrected initial run at `data/history/20261010T120832Z-ad38797d` collected the June 30 noon-close event and the user's October 10 daily hit event: 27 markets with nonempty lifetime YES histories, source candles and resolution records. It completed the requested collection. The October 10 event was still open; its source window was incomplete. June labels were quarantined by resolution rule-version flags. An earlier run exposed a collector assumption that resolution responses contained pagination; the actual `/v2/resolutions` response only contains `data`. That assumption was fixed before the completed run.

A dated listing discovered daily, weekly and monthly Bitcoin hit events. A first broad pilot also retained one ETH/BTC-ratio event because its title included Bitcoin; discovery was tightened to the intended Bitcoin event slug families. That intermediate pilot is not the recommended dataset.

The review dataset is `data/history/20261010T125801Z-478e8721/`. Its `report.md` and `coverage.json` are the starting point. It contains:

| Data | Count |
| --- | ---: |
| Closed events | 39: 32 daily, 5 weekly, 2 monthly |
| Markets / nonempty lifetime YES histories | 704 / 704 |
| Markets matching inspected templates | 651 |
| Markets with nonempty granular histories | 650 |
| Lifetime price points | 6,589 |
| Granular price points | 564,540: 563,728 five-minute points and 812 zero-width points |
| Stored Binance one-minute candle rows | 577,440 |
| Derived cutoff records | 3,906 |

Counts include repeated data across overlapping event windows; they are not counts of independent observations. Zero-width points on resolved tokens are quarantined, not accepted forecasting inputs. One supported market lacks granular history; its coarse series and missing coverage remain visible. Fifty-three weekly/monthly markets have unsupported rule variants. All 704 resolution records have `new_version_q` set, documented as rules updated after posing, so no venue label is accepted as verified. Source measurements are retained separately.

The first pilot at `data/history/20261010T121302Z-183fe6b2/` had 28 complete events and 11 with actual connection resets/timeouts. The separate retry at `data/history/20261010T125217Z-373ef115/` completed all 11. The review directory copies successful event records from those runs; its catalog identifies each event's source run. Both originals remain intact. Collection is complete for the selected 39 events; exchange-wide coverage is not claimed. No collected history is analysis-ready.

The server restart also disconnected progress output, causing `BrokenPipeError` after data had been saved. Progress printing now tolerates a lost terminal. `--derive-run` rebuilds cutoff observations and the aggregate coverage/report from saved event records without modifying market/price/candle/label sources. This corrected the aggregate summary without hiding genuine API failures. The collection happened during development; the original pilot did not record a collector code hash. The assembled catalog states that gap explicitly; receipt times, source hashes, exact rules and token mappings remain available.

Review commands:

```sh
python3 -m unittest discover -s tests -v
python3 collect_history.py --derive-run data/history/20261010T125801Z-478e8721
```

The second command uses no network. Live recollection commands are in README; it produces a new run rather than changing these source files.

## Known limits

- Discovery is restricted by tag, closed status and venue end metadata; early YES resolution can make event end metadata differ from its advertised calendar window. Seed-only collection has a separate scope. Bounded selection is disclosed, not exhaustive historical coverage.
- Templates are exact inspected strings. Changed or unsupported rules keep source data and abstain. Historical rules/version flags and creation-minute boundaries need review; source matches alone do not certify settlement interpretation.
- Lifetime history and finer window requests are separate series. Sparse points and retention gaps remain visible. No fake uniformly spaced prices or interpolation are generated.
- Data v2 can append synthetic zero-width settlement points; all such points on resolved tokens are conservatively excluded from cutoff candidates. Genuine ticks can also be excluded by this conservative rule.
- Cutoff candidates use bucket ends, not just timestamps, and contain age. There is no freshness eligibility gate yet. Price aggregation semantics are unknown. `analysis_ready` is false throughout.
- Venue outcome encodings are not Bitcoin prices. Source NO labels require complete measurement windows. Disputed/updated rule records are not accepted as matched labels.
- No trades/activity collection, full trade-pagination live check, statistical analysis, probability calibration, execution pricing or backtest is implemented.
