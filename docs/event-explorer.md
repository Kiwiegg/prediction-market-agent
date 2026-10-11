# Event explorer

Run from the repository root:

```sh
python3 scripts/visualize_events.py
```

Open `data/analysis/event-explorer.html` in a browser. It is a standalone file with the data embedded; no server, API call, dependency install or internet connection is needed. The current report is about 28 MB.

## Controls

Choose a timeframe, date range and event. Date filters select measurement windows overlapping that range; the selected markets retain their full saved histories. Reaching and dipping markets have separate panels. Select thresholds with Cmd/Ctrl-click, or use Select all. Include excluded markets to restore the flat tails; include after-hit observations to show their saved prices. The 0.05 filter is retrospective and uses the existing analysis selection.

The shared slider moves the event heatmap marker and updates the threshold curves. Clicking a heatmap cell sets its bucket-end time. In the cross-event chart, the marker represents the same UTC instant or the same remaining hours, depending on alignment. Price histories stay disconnected across gaps; a gray cell is missing or filtered, not a zero price.

## Views

| View | Reading it |
| --- | --- |
| Threshold × time heatmap | Each row is a threshold; darker teal means a higher YES price. Green ticks mark source-candle hits. Check marks identify venue-recorded YES outcomes. |
| Threshold curve at the slider time | Shows fresh completed buckets across thresholds. Missing thresholds break the line. Prices are descriptive history, not a tested probability model. |
| Same threshold across dates | Compare markets at the same threshold/direction in UTC or by time remaining. Hover for dates, prices and each market's window. Narrow the date range when repeated colors become hard to distinguish. |
| Distance × time-remaining heatmap | Shows mean YES price, with bucket, market and event counts on hover. Positive distance means a move toward the barrier is still needed. Counts are correlated, with each saved bucket weighted equally. |
| Neighboring-market change correlations | Uses exact matched five-minute changes over the full saved event window. Positive lag matches row A with column B later. Gray means fewer than 12 pairs or constant changes. No gaps are bridged. |

The correlation panel picks up to eight thresholds nearest spot at the slider time, or nearest the median threshold when spot is unavailable. This makes it an exploratory selection, not a fixed forecasting universe.

## Coverage and limits

The current file includes 39 events, 651 supported-rule markets and 563,720 granular points within their measurement windows. One supported market has no usable granular window history. The 53 unsupported-rule markets are reported as omitted. The full 704-market source collection remains unchanged.

Daily, weekly and monthly windows are shown with their actual dates. Creation-based windows remain distinct from calendar windows. Their unresolved creation-minute boundaries keep hit status unknown; those observations are excluded from path-dependent pooling and change correlations. Other unknown paths and missing BTC candles are also excluded from the pooled distance view.

The threshold curve accepts the latest completed bucket only while its age is less than the bucket's actual width. It never reads a later bucket. Hit status uses only completed source candles as of each observation. The green venue badges do not resolve historical rule-version uncertainty. Venue resolution time and source crossing time are separate.

Different event dates are different path conditions. Overlapping windows do not by themselves imply a contract relationship. The full-history market filter, repeated thresholds, unequal coverage and overlapping windows can bias these descriptive views. No forecasting performance, proof, pricing eligibility or executable opportunity is established.

## Verification

```sh
python3 -m unittest discover -s tests -v
node tests/test_event_explorer.js
```

Python tests use small saved fixtures. JavaScript checks use a mock DOM/canvas and exercise controls, exact-time sampling, missing paths, lag matching and correlation failure cases. Node is needed only for these JavaScript checks.

An optional local-data smoke check exercises the generated report's full dataset:

```sh
node tests/test_event_explorer.js data/analysis/event-explorer.html
```

The current build passed 44 Python tests, fixture JavaScript checks, full-dataset control checks, provenance/source-hash checks and a headless Chrome screenshot of the default view. Full-dataset checks cover daily/weekly/monthly/all timeframes, hit/tail toggles, UTC/relative alignment and slider endpoints for all 32 daily events. Browser inspection does not replace fixture checks of the calculations.
