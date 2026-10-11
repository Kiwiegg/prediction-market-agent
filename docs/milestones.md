# Prediction-Market Consistency Agent — One-Week Milestones

**Planning basis:** One experienced developer working full-time for seven working days, with access to market data and an LLM API. Days are relative to project start. This is an implementation plan, not a promise of research accuracy or profitable opportunities.

**Reference:** [Project specification v0.2](project-specification.md).

**Active experiment — 2026-10-10:** The user authorized historical Bitcoin data collection and removal of the earlier Codex discovery pipeline. The active deliverable is a deterministic Python/JSON collector for daily, weekly and monthly threshold/hit markets, with historical prices, actual Binance measurements, settlement evidence and explicit coverage gaps. No embedded LLM session, database or historical order books. See [research plan](historical-bitcoin-action-plan.md) and [STATUS.md](../STATUS.md) for actual progress. Original arbitrage deliverables and acceptance gates below remain deferred/incomplete; this collection does not satisfy them.

## 1. Week-one outcome

Deliver a working vertical slice that ingests real contracts, extracts auditable settlement fields, verifies numerical threshold implication under explicit assumptions, and calculates portfolio surplus using actual asks, depth, and fees.

A reviewer must be able to trace one decision from original rules through extraction, human review, proof, payoff table, book snapshots, and pricing. A reproducible no-trade decision counts as a successful demonstration. Finding positive surplus is optional.

The week-one prototype is a milestone toward the full specification. It does not satisfy its full benchmark, autonomous eligibility, or 14-day operational gates.

## 2. Scope and delivery rules

| Area | Week-one commitment |
| --- | --- |
| Venue | Polymarket; only binary markets supported by the implemented venue adapter |
| Universe | One numerical-threshold event family; cap the live universe at 50 contracts |
| Relationship | Directed implication between thresholds with identical subject, units, observation method, source, observation time, and compatible exceptions |
| Discovery | Metadata and deterministic threshold grouping; manual seeding allowed and disclosed |
| Semantics | Structured LLM extraction with exact evidence spans; explicit abstention |
| Eligibility | Human approval of settlement-critical fields before a relationship reaches pricing |
| Portfolio | Buy-only `NO(A) + YES(B)` where A implies B; no short sales or conversions |
| Pricing | Actual token asks, depth, market-specific fees, size constraints, and a configured capital cap |
| Execution | Basic paper replay and ledger; incomplete or unavailable replay cannot count as a completed portfolio |
| Audit interface | Stored report required; simple local dashboard optional |
| Evaluation | 30–50 manually reviewed pairs, including hard negatives; one simple baseline |

Prioritize thresholds observed at the same instant. Exclude comparisons between “ever exceeded” and “closing price,” mismatched deadlines, missing authoritative rules, and unmodeled exceptional payouts. If a suitable live family is unavailable, use archived real contracts for semantic evaluation and demonstrate ingestion separately on current markets. Do not imply that archived contracts are live-tradable.

## 3. Daily milestones

### Day 1 — Reproducible market inputs

**Deliverables**

- A documented local setup and configuration example without credentials.
- An ingestion command for the bounded contract universe.
- Self-contained market records with event membership, supplied rule text and hashes, retrieval timestamps, token mappings, and inline books/fees.
- Actual YES and NO book snapshots with receipt timestamps, market metadata, and fee inputs.
- A venue capability record identifying supported position system, collateral, and payout unit.

**Acceptance:** Run ingestion twice, retaining self-contained market records and timestamps separately for each run. Trace one contract to its original rules and actual outcome token IDs. Unsupported mechanics or unavailable fee data produce explicit statuses.

**Dependency:** Confirm that authoritative rules, token books, and fee parameters can be retrieved before building pricing assumptions.

### Days 2–3 — LLM labeling pipeline and reviewed benchmark

**Current delivery boundary:** Historical collection has replaced the earlier runtime LLM discovery experiment. Collect auditable contract definitions, source price histories and settlement evidence, and measure coverage across timeframes. The earlier discovery script, prompts, schema and dedicated tests were removed at the user's request. The benchmark, held-out evaluation, general relation schema and human pricing approval deliverables below remain deferred/incomplete.

Build the pipeline and guide together over the two-day block. Iterate on development examples; keep held-out test examples out of prompt and guide tuning. This combines the original Day 2 and Day 3 work without removing their deliverables or advancing later milestones.

**Deliverables**

- A labeling guide defining threshold implication, direction, ambiguity, and disqualifying differences.
- Versioned `ContractSpec` and `RelationSpec` schemas.
- An LLM command producing schema-valid settlement extraction and proposed relation assertions, direction, evidence, and explicit abstention/unsupported statuses.
- Evidence references for subject, comparator, threshold, units, source, observation method/time, timezone, and exceptions; exact spans for relationship judgments.
- Stored model responses, model identifier, prompt/guide versions, and usage/latency records.
- A review workflow recording approved fields, corrections, reviewer identity, and the rule hash reviewed. LLM drafts are predictions, not automatically reference labels.
- 30–50 reviewed reference pairs with evidence and rationale, including at least 10 hard negatives and several ambiguous or unsupported cases.
- A development/test split by underlying event and rule-template family, with overlap disclosed if the pilot is too small to separate families adequately.
- A deterministic grouping baseline evaluated independently of the LLM.

**Working sequence:** Select a threshold family, define initial schemas and guide, and get a small LLM run working. Inspect development predictions and revise the guide/prompt together. Establish independently reviewed held-out labels without showing reviewers model predictions or prices; freeze them before further tuning and final evaluation. Disclose model-assisted development labels separately from independent test labels.

**Acceptance:** Every quoted span matches stored rule text. Missing fields remain missing. A changed rule hash invalidates prior approval. Every reference positive identifies direction and matching observation rules; each negative explains the rule difference. Report review method and limitations; a single reviewer does not satisfy the full specification's two-annotator requirement. Evaluate raw extraction and relation predictions separately from reviewer-corrected output. Freeze test labels before tuning on evaluation results. Discovery recall is not claimed unless an independently reviewed universe supplies its denominator.

**Dependency:** Reviewed, complete contract records and fixed proof-language schemas are available for Day 4. Human approval and verified venue mechanics remain required before pricing.

### Day 4 — Deterministic proof and payoff engine

**Deliverables**

- An allowlisted rule for compatible threshold implication, including strict/inclusive comparator boundaries.
- A proof record containing premises, rule version, source hashes, and rejection reasons.
- The admissible states and token payout table for an accepted pair.
- The portfolio template `NO(A) + YES(B)` and its minimum terminal payoff.
- Hand-checked positive and counterexample fixtures.

**Acceptance:** For `A → B`, the state `A=true, B=false` is excluded and the portfolio pays at least one payout unit in every admitted binary state. Mismatched source, units, time, observation definition, exceptions, and unsupported payouts fail eligibility. Empty or contradictory state sets cannot generate a guarantee.

**Dependency:** Pricing consumes only reviewed, proven relationships. A proof remains conditional on correct interpretation of the source rules.

### Day 5 — Live portfolio pricing

**Deliverables**

- A scanner that refreshes both token books for verified pairs.
- Depth-aware sizing using actual asks and all modeled fees.
- Configured quote-age, cross-leg timestamp-skew, capital, minimum-size, and minimum-surplus limits.
- A pricing record with quantity, trade legs, gross cost, fees, net cost, minimum modeled payout, and surplus.
- Explicit no-trade reasons and rejection counts.

**Acceptance:** Reproduce one result by hand from saved books. Demonstrate rejection of stale data, missing fees, insufficient depth, and nonpositive surplus. Use exact decimal arithmetic and supported fee rounding. A synthetic positive-edge fixture verifies the success path if live prices produce no opportunity; label it as synthetic.

**Dependency:** Distinguish a decision-time snapshot opportunity from simulated execution before displaying results.

### Day 6 — Paper replay and audit report

**Deliverables**

- A paper ledger tracking cash, inventory, reservations, fees, and simulated fills.
- Sequential leg replay with configured arrival delay and price limits.
- Handling for insufficient later-leg depth, partial execution, and bounded unwind attempts.
- Persistent-signal deduplication and capital/depth sharing across overlapping plans.
- A generated audit report linking rules, review, proof, payoff table, quotes, pricing, and replay outcomes.

**Acceptance:** Replay one completed fixture and one failed-leg fixture. Earlier fills remain recorded when a later leg fails. Unavailable replay data produces `execution_indeterminate`. If unwind liquidity is unavailable, retain and report inventory rather than invent a fill. Deterministic replay reproduces ledger changes.

**Dependency:** Basic replay is a prototype execution model. If replay cannot be completed reliably, ship snapshot analysis with execution marked unavailable and record this milestone as incomplete.

### Day 7 — Validation and handoff

**Deliverables**

- An end-to-end demo using real contracts and saved market inputs.
- A pilot evaluation comparing the simple baseline and raw LLM extraction/relationship pipeline on the frozen test set.
- Precision, recall, abstention, coverage, sample sizes, error examples, and confidence intervals where meaningful.
- A validation report covering proof, pricing, and replay fixtures.
- A runbook, known limitations, model cost/latency summary, and prioritized follow-up backlog.

**Acceptance:** A fresh local run following the README produces an inspectable decision. Replaying stored inputs reproduces deterministic proof and pricing outputs. Raw agent results and reviewer-assisted results are separately identified. No claims of reliable autonomous execution or persistent alpha are inferred from the pilot.

## 4. Final handoff package

Suggested artifact names are implementation choices; equivalent paths are acceptable.

| Artifact | Required contents |
| --- | --- |
| `README.md` | Setup, configuration, ingest/scan/evaluate/replay commands, and demo instructions |
| `schemas/` | Versioned extraction, proof, pricing, and execution schemas |
| `data/benchmark/` | Labeling guide, pilot labels, frozen splits, and source references |
| `data/runs/<run_id>/` | Self-contained market inputs, extraction outputs, review records, and proof/pricing records |
| `reports/demo.md` | One complete auditable decision and representative rejection examples |
| `reports/evaluation.md` | Baseline comparison, raw/assisted metrics, errors, sample sizes, and limitations |
| `reports/validation.md` | Required checks, results, and unresolved failures |
| `docs/runbook.md` | Operation, input refresh, failure recovery, costs, and known limitations |
| `docs/backlog.md` | Deferred work with dependencies and completion gates |

Source snapshots must be accessible to reproduce the local demonstration. Public redistribution follows the source's applicable permissions; it is not a requirement for the week-one handoff.

## 5. Week-one completion checklist

- [ ] Real contract rules and actual token books are ingested and retained.
- [ ] Settlement extraction is auditable and supports abstention.
- [ ] Human-reviewed threshold implication is checked deterministically.
- [ ] The payoff template is verified against all admitted states.
- [ ] Pricing incorporates spreads, depth, fees, and explicit limits.
- [ ] A 30–50-pair pilot dataset and simple baseline are evaluated.
- [ ] Paper replay handles a complete portfolio and a failed later leg without fabricating fills.
- [ ] Stored inputs reproduce deterministic outputs.
- [ ] A report lets another person trace an entire decision.
- [ ] Limitations and incomplete milestones are recorded explicitly.

Zero live opportunities does not fail this checklist. Missing replay or insufficient pilot labels must be reported as incomplete deliverables rather than hidden behind a working dashboard.

## 6. Scope cuts and contingencies

| Pressure or blocker | Response |
| --- | --- |
| No suitable live threshold group | Use archived real contracts for semantics; retain separate live ingestion demonstration |
| Rule extraction is unreliable | Keep human review; reduce supported predicate types and expose errors |
| Missing venue metadata or fee behavior | Reject affected markets; use labeled fixtures to validate the calculation path |
| Time runs short | Drop dashboard polish, embeddings, streaming feeds, and generalized discovery first |
| Data feed cannot support replay | Deliver honest snapshot analysis; mark execution milestone incomplete |
| No positive live surplus | Demonstrate real no-trade decisions plus a clearly labeled synthetic success fixture |

Keep evidence, proof correctness, fee accounting, and truthful execution status even when scope shrinks. Do not spend the final day expanding the ontology.

## 7. Milestones after the first week

These are follow-up work blocks, not guaranteed one-week allocations.

| Milestone | Deliverables | Completion gate |
| --- | --- | --- |
| Benchmark expansion | Two-annotator labeling, adjudication, 500–1,000 groups, stronger baselines and ablations | Frozen event/template-separated evaluation and reported agreement |
| Execution validation | Better feed recovery, calibrated latency/depth assumptions, redemption reconciliation, stress fixtures | Replay and ledger checks from the full specification pass |
| Relationship expansion | Equivalence, cumulative deadlines, exclusivity, and partitions added individually | Each family has semantic evidence rules, counterexamples, payout fixtures, and verified venue compatibility |
| Continuous observation | Scanner monitoring, opportunity episodes, outages, coverage, cost and rejection metrics | At least 14 consecutive calendar days of collection with gaps disclosed |
| Autonomous paper eligibility | Development-only score calibration and a frozen eligibility policy | Full specification's precision/coverage gate is met; otherwise retain review |
| Research and public product | Representative live-sample analysis, polished audit interface, reproducible repository and report | Findings distinguish semantic accuracy, snapshot surplus, replay results, and realized redemption |

The full project succeeds through defensible evidence and an auditable system. A one-week prototype provides the foundation for that work.
