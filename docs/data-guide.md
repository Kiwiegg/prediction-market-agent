# Reading the collected data

The current dataset is in `data/bitcoin/`. Open `data/README.md`, then `data/bitcoin/README.md`: it lists all 39 events by name and links to their market definitions. Earlier development runs and probes were removed at the user's request; catalog source-run paths are historical identifiers, not available files. New historical collections go to `data/collections/<run_id>/`; they do not replace the current dataset automatically.

```text
data/
  README.md                       Start here
  bitcoin/                        Current research dataset
    README.md                     Named event index
    catalog.json                  Which events are included and their source runs
    report.md                     Readable coverage summary
    coverage.json                 Machine-readable coverage summary
    1151848/                      Bitcoin hit on October 8, 2026
      markets.json
      prices.json
      btc.json
      labels.json
      observations.json
      coverage.json
    ...                           Other event folders, identified by event ID
  collections/                    Future collector runs, created when needed
```

## How the records connect

An event contains several markets. Each market asks about one threshold and has YES and NO token IDs. `market_id` joins its definition, price history, label and cutoff observations. `event_id` joins it to the catalog. `condition_id` identifies its venue settlement condition. Do not join arrays by position.

Start with one daily event such as October 8 (`1151848`). Its `markets.json` is an array with 16 markets: eight upside targets and eight downside targets. Here is a shortened real record:

```json
{
  "event_id": "1151848",
  "market_id": "5422663",
  "title": "Will Bitcoin reach $90,000 on October 8?",
  "semantics": {
    "kind": "window_high",
    "comparator": "gte",
    "threshold": "90000",
    "quote": "USDT",
    "window_start": "2026-10-08T04:00:00+00:00",
    "window_end": "2026-10-09T04:00:00+00:00"
  }
}
```

That means a Binance BTC/USDT one-minute candle high must reach at least 90,000 during the Eastern calendar day. The full record also contains exact rules, rule/source hashes, receipt time, actual token IDs, template version and review issues. A missing `semantics` value means the rule variant is unsupported. `pricing_eligible` is false.

## What to open

| File | Shape and purpose |
| --- | --- |
| `markets.json` | Array of market definitions. Read titles, exact rules and parsed thresholds/windows first. |
| `prices.json` | Object with a `markets` array. Each entry has `market_id`, the YES `token_id`, coarse lifetime `points`, finer `granular` segments and retrieval errors. Each segment records its requested window, actual points and completeness. |
| `btc.json` | Object with `candles`, shared by markets in the event. Actual Binance BTC/USDT one-minute open/high/low/close prices, including preceding data for later baselines. Overlapping events repeat candles. |
| `labels.json` | Object with a `markets` array. Each entry keeps the venue `resolution`, separately computed `source_yes`, accepted `reported_yes` if available, and a review `status`. |
| `observations.json` | Object with `records`: price and source-candle candidates at fixed cutoffs. Includes whether a barrier had already been reached. This is the easiest entry point for later analysis once quality gates are settled. |
| `coverage.json` | Request completeness, missing data, supported-market counts and limitations. Check this before interpreting other files. |

### Market prices

This is a real finer-history point from the $90,000 market:

```json
{
  "timestamp": 1791432000,
  "price": "0.015",
  "resolution_seconds": 300,
  "bucket_end": 1791432300,
  "forecasting_candidate": true,
  "exclusion": null
}
```

The interval starts at October 8, 04:00 UTC and lasts five minutes. `price` is the YES token's historical price on a 0–1 scale; it is not Bitcoin's price. Its aggregation method is still unverified, so do not assume it is a last trade, midpoint, executable quote or calibrated probability. Decimal values are strings to preserve precision. `forecasting_candidate` only means the point passed structural/settlement-point screening; it does not mean the observation is analysis-ready.

Market-history timestamps, bucket ends and cutoffs are **epoch seconds**. Candle `open_time_ms` and `close_time_ms` are **epoch milliseconds**. Definition windows and receipt times are ISO timestamps. A bucket must finish by the cutoff, and a source candle must have closed before it. Zero-width points on resolved tokens are quarantined because they can include synthetic settlement values.

### Cutoff observations

For the same $90,000 market, six hours before the daily window ended, a saved record contains:

```json
{
  "market_id": "5422663",
  "basis": "before_window_end",
  "hours_before": 6,
  "cutoff_observed": true,
  "price": {
    "cutoff": 1791496800,
    "point": { "price": "0.0005", "resolution_seconds": 300 },
    "age_seconds": 0,
    "series": "granular"
  },
  "btc_last_completed_candle": { "close": "81713.98000000" },
  "barrier_reached_so_far": false,
  "analysis_ready": false
}
```

This is October 8 at 22:00 UTC. The market-price bucket had finished, the latest completed Binance candle closed at 81,713.98 USDT, and the source had not reached the $90,000 barrier earlier in the window. The excerpt omits other fields; open the full record for source timestamps and provenance. `age_seconds` measures the gap from bucket end to cutoff; freshness still needs a separate gate.

`before_window` records look before the measurement window starts; `before_window_end` records look during the window at a fixed time remaining. Daily markets often open at the beginning of their window, so pre-window price candidates can be missing. `barrier_reached_so_far: true` means a new-hit prediction would already be settled by the observed price path. `null` means that status could not be established, for example because coverage or creation-boundary interpretation is missing.

### Labels and limitations

For this market, `source_yes` is false, but `reported_yes` is null and `status` is `rule_version_review_required`. The venue's raw resolution is retained; the API marks its rules as updated after posing. Do not replace that uncertainty with an automatically accepted label.

The pilot contains 704 markets, 651 matching inspected templates, and finer history for 650. Fifty-three weekly/monthly rule variants are unsupported. All 704 settlement records have rule-update flags. Monthly/weekly creation-based windows can differ from full calendar periods even within the same event. The source measurements and data are available for investigation, but `analysis_ready` remains false throughout.

## Repeatable checks

```sh
python3 -m unittest discover -s tests -v
python3 scripts/collect_history.py --derive-run data/bitcoin
```

The second command uses saved data and no network. It rebuilds derived observations and aggregate coverage/report while preserving market definitions, price histories, source candles and settlement records. Collected data remains outside Git; another checkout must recollect it. See [collection validation](history-validation.md) for the live evidence and remaining gates.

## Analysis selection

`data/bitcoin/analysis-selection.json` records which markets to include in the analysis view; `.md` summarizes the counts. The current cutoff drops markets whose usable stored YES history never exceeds 0.05. It examines completed lifetime and granular request records, excluding zero-width/quarantined points. Missing history and low peaks with failed requests are unknown, not drops. The full 704-market source collection remains intact.

Generate with `python3 scripts/select_markets.py`; rebuild the selected browser with `python3 scripts/visualize_market.py --all-daily`. `--include-all` restores the full daily browser. This retrospective full-history maximum uses future information and must not define a forecasting/backtest universe.
