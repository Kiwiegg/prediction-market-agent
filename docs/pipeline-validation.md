# LLM discovery pipeline validation — 2026-10-09

## Implemented

`discover.py` runs Codex CLI with ChatGPT authentication, without an API-key billing path. Codex emits structured search/read/final actions; Python alone executes bounded read-only Gamma/CLOB requests. The extraction schema and initial Bitcoin labeling guide are committed. Records identify retained input files/hashes, rule hashes, actual token mappings, and exact evidence offsets. All records remain unreviewed and ineligible for pricing.

## Offline evidence

`python3 -m unittest discover -s tests -v`: **40 tests passed** (17 ingestion, 23 discovery).

Checks cover the complete simulated search/read/extract loop, CLI adapter arguments and event handling, rule-hash changes, invented/missing IDs, exact evidence spans, missing-field abstention, unsupported intraday/nonbinary cases, decimal thresholds, timezone-aware timestamps, refusal/incomplete/malformed responses, partial collection, bounded calls, unauthorized tools/slugs, and deterministic replay of a saved final model response. All API and inference inputs in tests are synthetic. No unit test needs credentials or live network.

The offline demo command is documented in the README. It returns two synthetic threshold contracts with eligibility false and saves a session for inspection.

## Live model evidence

With approved execution/network access:

```sh
python3 discover.py --markets tests/fixtures/bitcoin-markets.json --max-calls 1 --timeout 120
```

Succeeded using **Codex CLI 0.161.0**, **gpt-6.1-sol**, and the existing **ChatGPT login**, with no API key. Output: `data/research/20261009T115601-7aa0bdad/`. One inference took **33.48 seconds** and reported 9,213 input tokens and 695 output tokens. Native events were thread start, turn start, assistant message, and turn completion, with no built-in tool activity.

Both synthetic markets returned `extracted`, thresholds `85000` / `87500`, comparator `lt`, and observation time `2026-10-10T00:00:00+00:00`. Local schema/evidence validation passed. This establishes CLI authentication and structured extraction on synthetic rules, not live-market semantic accuracy or full discovery success. The earlier sandbox invocation failed; the approved invocation succeeded. Runtime output is ignored and is not automatically available in another checkout.

## Live venue limitation

A direct `search_events('Bitcoin price')` smoke check first failed sandbox DNS. The approved network retry received **HTTP 451: Unavailable For Legal Reasons** from Gamma `/public-search`. No successful live search/read/model-discovery run is claimed. The pipeline stops on HTTP 451 rather than attempting to work around access denial. Existing permitted saved-market inputs can still be analyzed.

## Open checks

- Successful live discovery on an environment permitted to access Gamma search, followed by real event retrieval and LLM extraction.
- Human inspection of real closing-price contract extraction, difficult rules, missing linked-source details, and actual candidate availability.
- Compatible family grouping, real-rule inspection, and a human approval workflow before pricing.
- Distribution curves, interval probabilities, quote uncertainty/freshness, repeated snapshots, and forecasting evaluation are not implemented.
- The combined Days 2–3 benchmark, frozen test split, baseline, relation schema, and extraction accuracy evaluation remain incomplete/deferred. Venue/fee verification from Day 1 remains open.

No forecast, arbitrage, or completed-milestone claim follows from fixture or model-smoke success.
