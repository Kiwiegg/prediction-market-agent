# Bitcoin closing-price extraction guide — v1

The current experiment asks whether related Polymarket prices can describe an implied distribution for Bitcoin at a particular close. The LLM finds candidates and extracts settlement meaning. It does not estimate Bitcoin movement or calculate probabilities. Distribution construction is a later deterministic step.

## Contract fields

Use [the fixed schema](../schemas/bitcoin-contracts.json). `comparator` describes the YES outcome. `threshold` is a positive decimal string; do not introduce float rounding. `observation_kind` distinguishes a closing price from touching a threshold at any point. `observation_time` identifies the actual measurement instant, including UTC offset; `timezone` preserves the rule convention. Trading end dates and expected resolution dates are not substitutes.

`resolution_source` names the exchange/provider/instrument. `price_definition` preserves candle, sampling, and rounding rules. `exceptions` includes fallback, cancellation, tie, missing-data, and fractional-payout clauses. `payout_model` is an interpretation requiring review; two outcome tokens alone do not establish binary settlement under all exceptions.

Every populated field needs an exact quote from that contract's retained rules. Character offsets are derived locally from unique quotes, and each span carries the reviewed source rule hash. A matching quote proves that the text exists, not that the extracted value follows from it. A threshold's numeric value must also appear in its supporting quote.

## Status and review

- `extracted`: all required fields are populated for a BTC/USD closing threshold with a binary settlement interpretation and no unresolved ambiguity. It remains unreviewed.
- `abstained`: rules are insufficient, ambiguous, contradictory, or depend on linked details not retrieved. Null fields must appear in `missing_fields`.
- `unsupported`: rules describe another asset/currency, intraday/path-dependent behavior, a range bucket, or a nonbinary payoff outside the current slice.

Future distribution analysis should disclose whether semantics were reviewed and remain conditional on correct settlement interpretation. Human approval remains required for week-one pricing eligibility. Corrected/approved records need reviewer identity and the reviewed rule hash; a review-writing command is not implemented yet. A changed rule hash invalidates prior approval. Negative-risk mechanics remain unsupported for pricing; semantic research does not enable trading eligibility.

For a potential distribution family, check identical asset, units, measurement instant, source/instrument, price definition, and compatible exceptions. Event membership or similar titles alone do not establish compatibility. Above/below contracts need explicit complement and boundary treatment. Never mix an intraday barrier, range bucket, or different observation time into a closing-threshold cumulative distribution by inference.

## Iteration and later evaluation

Tune this guide and the prompt together using development examples. Start with available real contracts rather than forcing a predetermined number of pairs. Preserve rejected cases and report candidate availability. Synthetic fixtures validate software behavior only.

The earlier 30–50-pair benchmark, independent held-out labels, baseline, and relation schemas remain deferred acceptance work. If evaluating accuracy, independently label held-out examples without model predictions or prices, freeze them before further tuning, and report raw versus reviewer-corrected results separately. Do not report discovery recall without a reviewed universe and denominator.
