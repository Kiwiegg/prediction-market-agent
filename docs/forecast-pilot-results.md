# One-hour forecast pilot: results

Completed on 2026-10-16 under the [fixed protocol](forecast-pilot.md), commit `fad474c`.

**The selected market inputs did not improve forecast error in this test.** This is a result from one small historical dataset. It does not show that all prediction-market information is useless.

## Data used

The source has 32 daily events from September 7 to October 8, 2026. There were 736 hourly candidates. The study accepted 682 and rejected 54.

| Period | Events | Accepted rows | Rejected candidates |
| --- | --- | --- | --- |
| Training: September 7–25 | 19 | 396 | 41 |
| Validation: September 26–October 1 | 6 | 132 | 6 |
| Test: October 2–8 | 7 | 154 | 7 |

All events had accepted rows. Each test event had 22 rows. Rejections: 32 candidates had a selected market that did not exist one hour before the forecast; 22 had no unhit downward threshold within 5% of BTC spot. These are first-failure counts; a candidate can have more than one problem.

The study used the full source collection. It did not use the retrospective 0.05 filter. Both models used exactly the same accepted rows. Market selection used the source path and spot at the forecast time. The target was the next-hour BTC/USDT return, not a venue settlement outcome.

## Test results

One basis point is 0.01 percentage point of return. Lower error is better. The primary score gives each test day equal weight.

| Forecast | Mean daily absolute error (basis points) | Pooled root mean square error (basis points) |
| --- | --- | --- |
| BTC inputs only | 21.1225 | 33.9441 |
| BTC plus market inputs | 21.4218 | 34.1898 |
| Zero price-change forecast | 21.1064 | 33.8346 |

Adding market inputs increased mean absolute error by **0.2993 basis points**. The augmented model had lower error on three of seven days. Median daily improvement was −0.0380 basis points. The mean improvement stayed negative when each test day was omitted in turn; those values ranged from −0.3773 to −0.1896 basis points. The zero-change forecast also had slightly lower error than either fitted model.

Validation selected ridge penalties of 10 for the BTC model and 0.1 for the augmented model. Both models were then fitted on training plus validation data. Test labels did not enter model fitting or penalty selection.

## Limits and decision

This is an exploratory result, not a qualified forecast. The [official price-history schema](https://data-api.polymarket.com/v2/openapi.json) confirms observation windows and zero-width settlement points. It does not define the aggregate-price calculation. Historical publication delays, later revisions and original rule versions remain unverified. The saved dataset was collected after the event windows.

The test has only seven days. Hourly observations and neighboring thresholds are not independent trials. No statistical significance or profit estimate is reported. The selected daily events are not a random sample of all market conditions.

Do not tune features, the horizon or the model against these test results. The test period is now used. The current evidence does not justify a forecasting or trading claim. A broader experiment would need a new question and new untouched data. No further model search is part of this task.

## Reproduce and review

```sh
python3 scripts/forecast_pilot.py
python3 -m unittest discover -s tests -v
```

The local report is `data/forecast/pilot-v1/report.md`. It lists per-day errors and the main coverage failures. The other files are:

- `rows.json`: exact derived feature/target strings, selected token IDs, point times and ages.
- `rejections.json`: every rejected candidate, its first failure, and fixed event/date assignments.
- `results.json`: model coefficients and input scaling, validation choices, test predictions, scores and source/protocol/code hashes.

All 55 offline tests pass. Forecast fixtures check barrier equality, missing candles, stale prices, wrong token mappings, future-data exclusion, event separation, fitting-only scaling, constant features, daily weighting and isolation of test labels. A second local-data run produced byte-identical outputs. Source files and source hashes are unchanged. No market API requests or model API calls were used by the experiment. The separate documentation check used the public API schema.

Code review found that a market created after a forecast time could enter the candidate list before the creation check. The final code excludes it before selection. A saved-fixture test covers this case. This correction did not change the dataset row counts, fitted models, validation choices, test predictions or scores. The protocol and features were not changed.
