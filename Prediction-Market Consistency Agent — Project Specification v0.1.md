# Prediction-Market Consistency Agent

**Revision:** v0.2 · 2026-10-08

This revision preserves the research objective and adds implementation contracts, validation limits, reproducibility requirements, and acceptance gates. Numerical operating limits below are proposed defaults, to be frozen before evaluation rather than represented as measured results.

**Current experiment — 2026-10-10:** The user authorized historical Bitcoin data collection and removal of the earlier Codex discovery pipeline. The active deliverable is a deterministic Python/JSON collector for daily, weekly and monthly threshold/hit markets, with historical prices, actual Binance measurements, settlement evidence and explicit coverage gaps. No embedded LLM session, database or historical order books. See [research plan](docs/historical-bitcoin-action-plan.md) and `STATUS.md` for actual progress. Original arbitrage deliverables and acceptance gates below remain deferred/incomplete; this collection does not satisfy them.

## 1. Core research question

**Can an agent reliably convert natural-language prediction-market contracts into formal payoff relationships, then use those relationships to identify executable violations of no-arbitrage constraints after accounting for spreads, fees, liquidity, and venue mechanics?**

The project has two deliberately separate components:

**Semantic problem:** infer what contracts actually mean and how their settlement conditions relate.

**Financial problem:** given those relationships and live order books, determine whether a risk-free or economically dominated portfolio exists.

The LLM extracts evidence-backed contract semantics. Deterministic code derives supported relationships from those semantics and evaluates portfolios. A deterministic proof is conditional on the extracted semantics being correct; it does not establish that the original contract was interpreted correctly.

Use “guaranteed payoff under the settlement model” rather than an unqualified “risk-free” claim. Execution, settlement disputes, collateral value, and redemption delays remain separate sources of risk.

---

## 2. Primary hypotheses

**H1 — Contract understanding:** An LLM agent with access to full settlement rules can identify formal relationships between contracts more accurately than lexical or embedding-similarity baselines.

**H2 — Structured reasoning:** Converting contracts into a normalized intermediate representation and deriving relationships programmatically will be more reliable than asking an LLM directly, “Are these markets arbitrageable?”

**H3 — Market consistency:** Many apparent probability inconsistencies disappear after using executable bid/ask prices, fees, available depth, and exact settlement rules.

**H4 — Tradability:** A small subset of semantic inconsistencies may survive these filters and produce paper-executable opportunities.

A successful project does **not** require H4 to be true. Showing rigorously that apparent arbitrage almost always disappears is itself an interesting market-efficiency result.

---

## 3. Initial scope

Start with **Polymarket only**.

Monitor active, sufficiently liquid markets and search for logical relationships among contracts on the same or closely related underlying event.

Do not begin with arbitrary relationships between every market on the exchange. V1 should support a small number of high-confidence relationship families.

### Delivery boundary

The first vertical slice supports ordinary binary contracts, equivalent predicates, and directional implication from numerical thresholds or cumulative deadlines. It uses buy-only two-leg payoff-cover templates and paper execution. Other relationship families remain in the research ontology and labeled dataset, but enter the executable scanner only after their proof rules and venue operations pass dedicated checks.

Default maximum group size is four contracts. Multi-outcome conversions, negative-risk adapters, and unsupported position systems are excluded from executable V1 results. Their contracts may be retained for semantic evaluation with an explicit unsupported-mechanics status.

### V1 relationship ontology

**Equivalent**

- A and B have the same payoff in every admissible state.

**Implication / subset**

- If A occurs, B must also occur.
- Therefore the payoff of A is weakly dominated by B.

Examples include nested thresholds or deadlines.

**Mutually exclusive**

- A and B cannot both resolve YES.

**Complementary**

- Exactly one of A or B can occur.

**Exhaustive partition**

- Exactly one event among A₁ … Aₙ occurs.

**Threshold nesting**

- Same variable and settlement time, different thresholds.
- Example structure: `X > 120` implies `X > 100`.

**Temporal nesting**

- Same event definition, nested deadlines.
- Example structure: “occurs by June” implies “occurs by December.”

Represent equivalence, directed implication, exclusivity, and exhaustiveness as independent assertions: a pair can satisfy more than one. Complementarity is exclusivity plus exhaustiveness; threshold and temporal nesting are derivation families for implication, not competing classification labels.

Distinguish **NONE** (reviewed; no supported relationship established), **UNKNOWN / ABSTAIN** (insufficient or ambiguous evidence), and **UNSUPPORTED** (meaning understood but outside the implemented proof language).

Temporal implication requires a cumulative predicate such as “occurred at least once by deadline.” A snapshot predicate such as “holds office on date” is not cumulative. Threshold implication requires matching units, source, observation definition, and timestamp; “ever exceeded” and “closing price exceeded” are different predicates.

---

## 4. Contract representation

Instead of having the LLM emit a free-form opinion, the agent converts each contract into a structured representation such as:

```text
ContractSpec
  schema_version
  contract_id / condition_id / outcome_token_ids
  venue / position_system / collateral_asset / payout_unit
  rule_document_id / rule_content_hash / retrieved_at
  subject
  event/predicate
  comparator
  threshold/value
  units / observation_method
  valid_time_window / timezone / boundary_inclusivity
  observation_time
  resolution_time
  resolution_source
  outcome_definition
  exceptions / cancellation_or_nonbinary_resolution
  field_evidence: document_id + character_offsets + exact_quote
  missing_fields / ambiguity_flags
  extraction_model / prompt_version / extraction_status
```

For example, a threshold contract should ideally reduce to something conceptually like:

```text
subject: BTC/USD
predicate: closing_price
comparator: >
threshold: 100000
resolution_time: 2026-12-31
resolution_source: <specified source>
```

The agent must preserve differences in resolution source, timestamp convention, inclusivity (`>` versus `>=`), exceptional resolution clauses, and other details that can break an apparent equivalence.

The output must include exact rule spans supporting every settlement-relevant field. Evidence offsets refer to an immutable canonical text snapshot; retain the original response too. External sources have their own snapshots, hashes, and retrieval timestamps. Derived fields identify their derivation and input evidence. Missing data stays null; the agent must not substitute a market title, end-date metadata, or its memory for settlement rules.

Observation time, trading end time, expected resolution time, and actual redemption time are distinct. Unsupported cancellation or fractional payouts must block binary payoff assumptions unless the engine explicitly represents all such states. Rule changes invalidate dependent extractions, proofs, and opportunities.

---

## 5. Agent workflow

The agent operates as a tool-using contract analyst rather than a trading oracle.

**Step A — Discovery**

Retrieve active markets and generate candidate groups using metadata, event grouping, lexical similarity, and embeddings.

The goal here is high recall. False positives are acceptable because later stages filter them.

**Step B — Investigation**

For each candidate group, the agent can call tools to:

- retrieve complete market descriptions and settlement rules
- inspect related contracts
- compare dates and numerical thresholds
- retrieve resolution-source information
- request missing metadata

**Step C — Formalization**

Convert each contract into `ContractSpec`.

**Step D — Relationship inference**

Produce a structured `RelationSpec`:

```text
RelationSpec
  contract_ids
  assertions: type + direction + derivation_family
  logical_conditions / explicit_assumptions
  evidence
  calibrated_score / calibration_version
  ambiguity_flags / proof_status / rejection_reason
```

The agent should be able to abstain.

**Step E — Deterministic verification**

A non-LLM engine validates whether the proposed logical relationship actually follows from the structured contracts.

Only relationships that pass this stage reach the pricing system. Verification consists of schema checks, evidence-span checks, settlement-mechanics compatibility, and an allowlisted proof rule. The proof record stores rule name/version, premises, derived assertions, and source hashes. Reject inconsistent premises or an empty admissible-state set; never let an empty state set create a vacuous payoff guarantee.

The engine must not silently remove exceptions or treat matching resolution-source names as proof of matching observation rules. Initial paper-trade eligibility also requires human review of the extracted settlement fields. Automated eligibility can be enabled only after the held-out precision gate in section 18 is satisfied. Human review is a research control, not evidence of autonomous semantic accuracy.

---

## 6. Payoff / arbitrage engine

For every validated group, construct the set of logically admissible terminal states.

Each outcome token is represented by its payoff across those states.

Example:

```text
State                 Contract A     Contract B
A true, B true             1              1
A false, B true            0              1
A false, B false           0              0
```

This makes the relationship `A → B` explicit.

The pricing engine should then determine whether currently available trades create a portfolio whose cost and future payoffs violate no-arbitrage.

V1 enumerates a small, verified set of portfolio templates. General constrained optimization is a later extension; it must agree with the template engine on shared fixtures.

For a completed portfolio, let `C` be net cash paid, including trading and operation costs, and let `P(s)` be redemption proceeds in admissible state `s`. Report `G = min_s P(s) - C`. A positive `G` is a nominal settlement-model surplus. Report holding period and capital opportunity cost separately; where configured, subtract a conservative funding allowance before eligibility. Use a declared numerical tolerance and minimum absolute surplus to prevent rounding artifacts.

Illustrative buy-only templates, before costs, for tokens paying one collateral unit:

| Proven relationship | Buy portfolio | Minimum payoff | Candidate condition |
| --- | --- | --- | --- |
| A implies B | NO(A) + YES(B) | 1 | ask_NO(A) + ask_YES(B) < 1 |
| A equivalent to B | NO(A) + YES(B), or reverse | 1 | either cross-pair ask sum < 1 |
| A and B exclusive | NO(A) + NO(B) | 1 | NO ask sum < 1 |
| A and B complementary | YES(A) + YES(B) | 1 | YES ask sum < 1 |
| Exactly one of n events | one YES per event | 1 | sum of YES asks < 1 |

These examples assume complete fills and compatible binary settlement. A theoretical YES-price ordering violation alone does not guarantee any template is executable. Never estimate the NO ask as `1 - YES bid`; consume the actual token book.

For a future optimizer, define nonnegative buy/sell quantities per depth level, operation quantities, and resulting inventory. Constrain level capacity, inventory availability at each step, capital, quantity increments, and supported operations. Maximize minimum terminal surplus after costs. Any sale must be funded by initial inventory or a preceding valid operation. Include initial inventory at a declared opportunity cost; report inventory-dependent rebalancing separately from fresh-capital arbitrage.

**Optimization inputs and outputs**

**Inputs**

- bid/ask prices
- order-book depth
- trading fees
- permitted token operations
- maximum available quantity
- capital/risk limits

**Output**

- trade legs
- executable quantity
- initial cash flow
- payoff by terminal state
- minimum guaranteed terminal payoff
- gross edge
- costs
- net edge

The solver must use **actual executable prices**, never midpoint prices, when determining whether an opportunity is tradable.

---

## 7. Venue mechanics

The paper simulator should model the operations actually available on the exchange rather than assuming frictionless short selling.

The first vertical slice requires buying and eventual redemption. The complete V1 simulator additionally supports, where its venue adapter is verified:

- buying outcome tokens at asks
- selling owned outcome tokens at bids
- splitting collateral into YES/NO token pairs
- merging complete pairs back into collateral
- eventual redemption

Each operation is enabled only by a versioned venue adapter for the contract’s actual position system and collateral. Record operation costs, prerequisites, confirmation delays, payout precision, and availability. V1 supports the above operations only where verified; unsupported mechanics produce a rejection rather than an assumed conversion.

The official documentation describes position operations and multiple integration paths. Implementation must pin the supported path and inspect actual metadata rather than assume all markets use one collateral or token system. See [position management](https://docs.polymarket.com/trading/positions/manage) and the [documentation index and migration guides](https://docs.polymarket.com/llms.txt).

Fees are market-dependent and can depend on execution price. Cache fee parameters with a version and timestamp, compute them per fill with the supported rounding convention, and reject missing or stale parameters. Do not assume universal zero fees or include prospective rewards as guaranteed edge. See [official fee documentation](https://docs.polymarket.com/trading/fees).

More complicated multi-outcome conversion mechanics can come later. In particular, negative-risk conversion is a distinct adapter capability, not a consequence of natural-language exclusivity. See the [official adapter repository](https://github.com/Polymarket/neg-risk-ctf-adapter).

Every opportunity should therefore answer two different questions:

**Theoretical inconsistency:** Do displayed prices violate the inferred payoff relationship?

**Executable arbitrage:** Can a valid sequence of allowed venue operations capture the inconsistency at current prices and depth?

---

## 8. Evaluation dataset

Create a manually labeled benchmark before optimizing the agent.

Target roughly **500–1,000 contract pairs/groups** initially, deliberately including both easy and difficult negatives.

Labels should contain:

```text
relation assertions / direction / derivation family
exact / conditional / none / unknown / unsupported
evidence spans and adjudicated reason
important settlement-rule differences
binary-payoff eligibility / annotation confidence
```

Include examples that look similar but are **not** equivalent because of:

- different deadlines
- different resolution sources
- different threshold definitions
- different geographic or entity scopes
- exceptional settlement clauses
- subtly different event wording

These hard negatives will be more valuable than hundreds of obvious unrelated pairs.

Start with a 100-group pilot to refine the labeling guide, then expand to 500–1,000 groups. Use two independent annotators and adjudicate disagreements. Labels include independent relation assertions, direction, evidence spans, binary-payoff eligibility, unsupported/unknown status, and adjudication rationale. Preserve disagreement rates.

Split by underlying event family and rule-template family, keeping duplicates and near duplicates in one split. Freeze the held-out test set before prompt tuning. Add a later-time holdout for drift. Annotators must not see prices or model predictions. Report enriched hard-negative benchmark results separately from a representative live-market sample; their prevalence differs.

Candidate recall requires a separately reviewed bounded universe with known related groups. Define k, the retrieval unit, and the denominator; evaluating only retrieved pairs cannot measure discovery recall. Multi-label metrics apply to relation assertions; abstention and unsupported status are reported separately.

---

## 9. Baselines

Compare the full system against progressively stronger baselines.

**Baseline A:** lexical/title similarity.

**Baseline B:** embedding similarity plus simple deterministic matching.

**Baseline C:** single-shot LLM pair classification using contract text.

**System:** tool-using agent → structured `ContractSpec` → deterministic relationship validation.

Evaluate both candidate discovery and relationship classification.

Important metrics:

```text
candidate recall@k
precision / recall / F1 by relationship type
high-confidence precision
false-positive rate
abstention rate
calibration
```

The most important metric should be **precision among paper-trade-eligible relationships**, reported with coverage and a 95% confidence interval. Self-reported LLM confidence is not calibrated probability. Fit any score-to-accuracy mapping on development data only, and freeze its eligibility threshold before testing.

For H2, add an ablation using identical structured extraction with LLM relation classification but without deterministic proof rules. Compare baselines on the same contracts, rule snapshots, splits, and evaluation labels. Record token cost, tool calls, latency, and human-review time so improvements can be interpreted against resource use.

For a trading system, incorrectly declaring two contracts equivalent is much more dangerous than failing to detect one relationship.

---

## 10. Trading evaluation

Run the scanner continuously in paper mode.

Record a funnel for every scan:

```text
markets scanned
candidate relationships
agent-classified relationships
validated relationships
price inconsistencies
inconsistencies surviving bid/ask spreads
inconsistencies surviving fees
inconsistencies with sufficient liquidity
paper-executable trades
```

For every simulated trade, preserve the order books used in the decision so the result can later be reconstructed.

Use conservative fill assumptions. A decision-time quote establishes only a snapshot opportunity. A paper-executed portfolio requires replay at simulated leg arrival times, with depth consumption and all costs applied. Multi-leg orders are not assumed atomic.

Capture source and local receipt timestamps, book hash/sequence where supplied, and tick/minimum-size metadata. Record cross-leg snapshot skew and reject stale, crossed, incomplete, or unsynchronized books. On feed gaps, stop pricing affected tokens and recover from a fresh snapshot. See [official order-book documentation](https://docs.polymarket.com/market-data/prices-order-books).

Default paper execution uses marketable limit orders, explicit leg ordering, a 1-second arrival delay, at most 1-second quote age, and at most 250-ms cross-leg receipt-time skew. These are conservative research defaults to validate against recorded feed behavior, not assertions about venue performance. Report sensitivity at 250 ms, 1 s, and 3 s arrival delays. Unavailable replay observations produce an indeterminate execution result rather than a fill.

At each leg, consume observed depth up to the price limit and configured depth haircut; respect quantity increments and minimum sizes. Model order semantics per leg. Failure of a later leg triggers a documented bounded unwind policy and realized loss/inventory accounting; it never retroactively cancels an earlier simulated fill. Book replay cannot prove counterfactual fills, so label results as simulated and report this limitation.

Use one portfolio ledger for the run: cash, inventory, reservations, fees, operations, and redemption. Overlapping opportunities compete for capital and depth; deduplicate persistent signals into opportunity episodes rather than counting every scan as a new trade.

Track:

```text
gross theoretical edge
net executable edge
capital required
available quantity
realized P&L / marked inventory / modeled terminal surplus
partial-fill and unwind losses
peak capital tied up / time to redemption
time opportunity remained available
whether contracts ultimately resolved as modeled
```

Paper trading is primarily evidence that the system operates correctly. A few weeks of paper P&L should **not** be presented as proof of persistent alpha.

---

## 11. Public product

Build a live dashboard around **auditability**, not around displaying a giant P&L number.

For each candidate, show:

```text
Contract A
Contract B / related contracts

original settlement rules
normalized contract representation
inferred logical relationship
supporting rule text
payoff table

current order books
theoretical consistency bound
trade legs
available size
gross edge
fees / costs
net executable edge

agent confidence
ambiguities / warnings
decision:
  no trade
  monitor
  paper trade
```

Users should be able to understand exactly why the system believes two contracts are related and why it did or did not trade.

This makes the product useful even when genuine arbitrage opportunities are rare.

---

## 12. Research outputs

The final project should produce three artifacts.

**Research report**

A serious writeup answering:

> How reliably can language-model agents formalize prediction-market contracts, and how frequently do semantically valid relationships produce executable pricing inconsistencies?

Include methodology, benchmark construction, baseline comparisons, error analysis, market-efficiency findings, and execution results.

**Live system**

A scanner/dashboard continuously analyzing active contracts.

**Open-source repository**

Clean implementations of the semantic pipeline, formal relationship engine, paper execution simulator, evaluation suite, and dashboard.

---

## 13. Error analysis

Do not stop at aggregate accuracy.

Create a taxonomy of failures such as:

```text
missed exception clause
incorrect date nesting
different resolution sources
entity ambiguity
threshold inclusivity error
incorrect assumption of mutual exclusivity
incorrect assumption of exhaustiveness
agent hallucination
candidate-generation failure
execution/liquidity failure
```

The strongest research discussion may come from understanding **why contract interpretation fails** rather than maximizing one headline score.

---

## 14. Development sequence

**Phase 1 — Market/data layer**

Build Polymarket market discovery, rule ingestion, order-book snapshots, and persistent storage.

No LLM required yet.

**Phase 2 — Contract dataset**

Manually label an initial benchmark and define the relationship ontology precisely.

This happens before substantial prompt engineering.

**Phase 3 — Baselines**

Implement lexical, embedding, and single-shot LLM baselines.

Establish the benchmark the agent must beat.

**Phase 4 — Contract reasoning agent**

Implement tool calling, structured `ContractSpec` extraction, relationship inference, abstention, and evidence tracking.

**Phase 5 — Formal payoff engine (fixtures can start alongside Phase 2)**

Translate validated relationships into state/payoff representations and deterministic consistency constraints.

**Phase 6 — Execution simulator**

Consume live order books and determine whether theoretical violations remain executable after spreads, costs, liquidity, and venue mechanics.

**Phase 7 — Live scanner**

Run continuously and collect real-world evidence.

**Phase 8 — Dashboard + research report**

Expose decisions publicly and analyze accumulated results.

---

## 15. MVP definition

The MVP is **not** “automatically make profitable trades.”

The MVP is complete when:

1. Real Polymarket contracts and rule text are ingested automatically.
2. Candidate related markets are discovered.
3. The agent converts them into auditable structured representations.
4. A labeled test set measures relationship-classification performance.
5. Baselines exist for comparison.
6. Valid relationships are converted into formal payoff constraints.
7. Live order books are checked against those constraints.
8. A paper simulator determines whether an opportunity is actually executable.
9. Every decision can be inspected through a dashboard or stored report.

At that point, the system already constitutes a substantial research project even if it finds zero persistent arbitrage.

---

## 16. Success criteria

A strong outcome would look something like:

**Semantic result:** materially outperform simple retrieval and single-shot LLM baselines while achieving very high precision on relationships the system chooses to trade.

**Financial result:** quantify how frequently apparent logical inconsistencies occur, how many disappear after spreads/liquidity/settlement analysis, and whether any survive as executable opportunities.

**Systems result:** run continuously against live markets with auditable decisions and reproducible paper execution.

**Research result:** produce a defensible analysis of where LLM contract reasoning works, where it fails, and what those errors imply for autonomous financial agents.

Finding profitable arbitrage is a bonus, not the definition of project success.

---

## 17. Explicit non-goals for V1

Do not initially build:

- cross-exchange Kalshi/Polymarket arbitrage
- real-money autonomous execution
- general probability forecasting
- news-based directional trading
- arbitrary multi-hop logical reasoning across dozens of markets
- a generic financial chatbot
- complicated portfolio optimization
- every possible prediction-market relationship

The first version should prove one thing convincingly:

> **An agent can translate messy natural-language financial contracts into sufficiently reliable formal relationships that deterministic trading logic can reason over them.**

Everything else is an extension.

---

## 18. Acceptance gates and required checks

These gates define completion; finding positive edge is not a gate.

| Gate | Acceptance evidence |
| --- | --- |
| Data integrity | Every evaluated contract and quote links to an immutable source snapshot; changed rules invalidate dependencies; unsupported mechanics and stale data yield explicit rejection reasons. |
| Semantic evaluation | Frozen pilot guide, adjudicated 500–1,000-group benchmark, event/template-separated test split, baseline comparisons, coverage, confidence intervals, and error analysis. |
| Automatic paper eligibility | One-sided 95% lower confidence bound of at least 99% precision on the frozen eligible test subset, using an exact binomial bound and reporting sample size; if unmet or underpowered, continue with reviewed paper eligibility. |
| Formal correctness | Every supported rule has positive and counterexample fixtures; generated small state spaces confirm payoff bounds; contradictory premises and unsupported exceptional payouts cannot pass. |
| Financial correctness | Hand-calculated fixtures cover spreads, depth levels, fee rounding, capital limits, inventory constraints, and zero/negative edge; deterministic replay produces identical decisions. |
| Execution correctness | Replay covers stale books, feed gaps, partial fills, failed legs, unwind losses, overlapping signals, and eventual redemption; ledger conserves cash/tokens under the modeled operations. |
| Operational completion | At least 14 consecutive calendar days of paper collection, with scan coverage, outages, skipped decisions, and cost reported; every paper trade and sampled rejection can be replayed and inspected. |

For perspective, even 100 correct eligible classifications with zero errors cannot establish the proposed 99% lower-bound precision gate. With independent Bernoulli trials, roughly 299 zero-error cases are required for a one-sided exact 95% lower bound of 99%; correlated event groups weaken that interpretation. Also report uncertainty clustered by event family and avoid claiming independence for repeated pairs from one event.

A missed performance target is a reportable research outcome. Do not change test thresholds after observing results or equate reviewed eligibility with an autonomous-agent result.

## 19. Component interfaces and reproducibility

Use the following boundaries, without requiring a particular programming language, cloud provider, or model vendor:

| Component | Input | Persisted output |
| --- | --- | --- |
| Venue ingestion | Discovery API and market data feed | Versioned market/rule records, token mapping, raw book events and snapshots |
| Candidate retrieval | Frozen contract universe | Candidate group IDs, retrieval scores, strategy/version |
| Semantic extraction | Rule snapshots and bounded read-only tools | Schema-valid ContractSpec, evidence, model/prompt versions, tool trace |
| Proof engine | ContractSpec group | Verified RelationSpec, proof certificate or rejection |
| Payoff engine | Proof and venue capabilities | Admissible states, token payout matrix, assumptions |
| Portfolio engine | Payout matrix, fresh books, fee data, ledger limits | Sized trade plan or rejection, cash flows and minimum surplus |
| Paper executor | Plan and timestamped replay events | Fill/unwind records, ledger changes, replay result |
| Evaluation/dashboard | Stored records | Metrics and auditable decision views |

Contracts, relations, books, opportunities, and executions have stable IDs and explicit schema versions. All derived records reference their inputs. Store exact decimal prices/quantities; define rounding and solver tolerance centrally. A run manifest records code revision, configuration, model identifier, prompt hashes, random seeds where supported, and dataset split version. Preserve model responses because model calls may not replay identically; downstream deterministic decisions must replay from stored outputs.

Cache extraction by contract rule hash plus extractor version. Rule retrieval and reasoning operate on a slower loop than book pricing; reprice verified groups as books change. Bound candidate count, tool calls, retries, and per-run model spend. Record rate-limit failures and use backoff; missing data never silently becomes a zero fee or an empty book interpreted as liquidity.

Treat fetched contract text as untrusted data. The analyst has allowlisted read-only tools and no signing or live-order credentials. The public view excludes secrets and private traces; it includes settlement evidence and decision inputs needed for audit.

Suggested decision reasons include `missing_rules`, `ambiguous_semantics`, `unsupported_relation`, `unsupported_mechanics`, `proof_rejected`, `stale_book`, `missing_fee_data`, `insufficient_depth`, `capital_limit`, `nonpositive_surplus`, `eligible_pending_review`, `execution_indeterminate`, and `partial_execution`. Keep rejection counts and denominators visible.

## 20. Research reporting and revision notes

Report H1–H4 separately. Measure extraction accuracy on settlement-critical fields as well as relation accuracy; a proof can be internally correct on a wrong extraction. Count opportunity episodes and report scan-hours, eligible groups, quote coverage, and rejection rates alongside opportunity frequency. Separate snapshot surplus, simulated execution, realized redeemed profit, and unresolved inventory. An unresolved trade is not realized profit, and unequal redemption timing must be disclosed.

Track actual resolutions against the predicted payout model, including disputes and delays, even after the main observation window ends. Resolution is a venue process rather than an automatic consequence of the event predicate; see [official resolution documentation](https://docs.polymarket.com/concepts/resolution).

Compared with v0.1, this revision narrows the executable first slice, separates ontology assertions from derivation families, makes semantic proof assumptions explicit, defines executable portfolio templates and cash accounting, specifies replay and failed-leg behavior, prevents benchmark leakage, and replaces qualitative completion claims with measurable gates. The 500–1,000-group research benchmark and broader ontology remain project deliverables; a small vertical slice is an implementation milestone.

Venue references were reviewed for this revision on 2026-10-08. Documentation and market parameters may evolve; archive the applicable documentation and adapter assumptions at implementation time, and derive runtime eligibility from actual market metadata.
