# ADR-020: Freeze the FinalDecision Contract

**Status**: Accepted
**Date**: 2026-07-14
**Milestone**: [11 — Signal Orchestration](../../../../PROJECT_STATUS.md) (contract
only — no implementation in this record; see Context)

## Context

Milestones 5, 9, and 10 each froze a contract answering one question in
isolation: `StrategyDecision` ("what does the Strategy Engine think?"),
`LearningDecision` ("what would the learner have recommended, in
shadow?"), `NewsSignal` ("what does current sentiment look like?").
Milestone 11 is the first milestone whose entire purpose is
reconciliation, not production of a new independent opinion — per direct
product-owner review: "it is not another signal generator. It is a
signal arbitration system." `PROJECT_STATUS.md`'s own pre-existing
Milestone 11 row anticipated this ("Final arbitration... into one
`TradeDecision`"), but product-owner review narrowed and hardened the
actual first-version scope considerably below what a naive reading of
that row would suggest.

Three explicit directives shape this freeze:

1. **`StrategyDecision` remains primary; `LearningDecision`/`NewsSignal`
   are advisory only.** The orchestrator may reduce confidence, adjust
   allocation downward, or suppress a decision when advisory signals
   disagree strongly — it must not let an advisory signal increase
   allocation beyond what the Strategy Engine proposed, or substitute its
   own recommendation as the final answer, "in the first implementation."
2. **Arbitration should be policy-based** (weighted-vote, confidence-
   threshold, consensus, safety-first, named as examples, none mandated)
   so the framework supports experimentation without the orchestration
   service itself changing shape.
3. **Freeze first.** `FinalDecision` is frozen and reviewed before
   `src/orchestration/` is scaffolded, matching every milestone since
   Milestone 5.

## Decision

Two types are frozen together as `orchestration.models.SignalInput` and
`orchestration.models.FinalDecision`, documented in full at
[Standards/FinalDecision Contract.md](../../Standards/FinalDecision%20Contract.md),
*before* `src/orchestration/` is scaffolded.

`SignalInput` (`source`, `considered`, `agrees`, `weight`) is a small,
reusable sub-schema representing one advisory source's contribution.
`FinalDecision` embeds exactly two — `learner_input` and `news_input` —
always present (never `Optional`), with `considered=False` recording "no
signal available" explicitly rather than omitting the field. This
follows the sub-schema pattern [ADR-014](ADR-014-BacktestResult-Contract.md)
established for `BacktestResult`'s `TradeRecord`/`EquityPoint`/`ReplayRun`,
and avoids every consumer needing to branch on `Optional[SignalInput]`
being `None`.

`FinalDecision` itself (`timestamp`, `symbol`, `strategy_id`, `regime_id`,
`primary_allocation`, `final_allocation`, `confidence`, `outcome`,
`learner_input`, `news_input`, `rationale`, `metadata`) enforces two
properties at the type level, not left to documentation or a call site's
discipline:

1. **`final_allocation` is bounded to `[0.0, primary_allocation]`** —
   directly operationalizing Directive 1 as an unavoidable, construction-
   time guarantee rather than a policy convention a future arbitration
   policy could quietly violate. This mirrors
   [ADR-010](ADR-010-ExecutionDecision-Contract.md)'s `approved_allocation
   ∈ [0.0, strategy_reference.allocation]` bound, applied one layer
   earlier: the same "a downstream arbiter reduces, never manufactures,
   conviction" principle, now protecting the Strategy Engine's own
   authority the way it previously protected against Risk inventing size
   the strategy never proposed.
2. **`outcome` (`ArbitrationOutcome`: `CONFIRMED`/`ADJUSTED`/`SUPPRESSED`)
   is validated against `primary_allocation`/`final_allocation` at
   construction** — the same discipline `ExecutionDecision.decision_type`
   already established (see ADR-010 invariant 7). A caller cannot
   construct a `FinalDecision` claiming `SUPPRESSED` while
   `final_allocation` is nonzero, or `CONFIRMED` while the allocations
   differ.

`SignalInput.agrees`/`weight` are also validated: both must be falsy
(`False`/`0.0`) when `considered` is `False` — a source that contributed
nothing cannot be recorded as agreeing with or influencing the outcome.

Per Directive 2, the arbitration *algorithm* is deliberately not part of
this freeze — `orchestration.arbitration`'s eventual policy classes
(`WeightedVotePolicy`, `ConfidencePolicy`, `ConsensusPolicy`,
`SafetyFirstPolicy`, or whatever set an implementation actually ships)
are implementation detail behind whatever Protocol `orchestration.
interfaces` defines, the same "freeze interfaces, not implementation"
split [ADR-008](ADR-008-StrategyDecision-Contract.md) established for
`StrategyDecision`'s own allocation formula.

**Wiring `FinalDecision` into `risk.RiskService` as a replacement for
`StrategyDecision` is explicitly not authorized by this freeze.** Per
invariant #2 ("the risk veto is the only gate on order submission"),
something must reach `RiskService` for every trade; until wiring is a
separate, explicit, later decision, that something remains the
unarbitrated `StrategyDecision`. This is a deliberate extension of the
shadow-mode discipline ADR-016/ADR-018 established for Milestones 9 and
10 — except, unlike those two (which are *fully* shadow, never touching
a production code path at all), nothing here forbids computing a real
`FinalDecision` against live decisions; only the execution-path wiring
itself remains gated.

## Consequences

- Whoever implements Milestone 11 has one document to build against
  before writing `src/orchestration/`'s first line — which arbitration
  policy is default, how `LearningDecision`/`NewsSignal` are retrieved
  and paired with a given `StrategyDecision`, and the exact service
  surface are all free to be designed and iterated on, because none of
  that is what this freeze constrains.
- `final_allocation`'s upper bound makes "let an advisory signal actually
  increase conviction beyond the primary strategy" a visible, reviewable,
  ADR-requiring contract change — not an emergent behavior a sufficiently
  aggressive `WeightedVotePolicy` could produce by accident.
- The wiring gate means Milestone 11 can ship a complete, tested,
  benchmarked orchestrator — and even run it against real production
  decisions for observability — without yet taking on the risk of
  changing what `RiskService` actually evaluates. That's a separate,
  later change with its own review, the same staged-trust pattern this
  handbook has used for every new signal source so far.
- Trade-off, accepted: like every fresh contract in this handbook, this
  freeze is more speculative than one written against a real
  implementation — no `src/orchestration/` code exists yet to have
  grounded these field choices in real arbitration behavior. The
  `SignalInput` sub-schema in particular may prove too coarse (e.g. if a
  richer per-source signal turns out to matter) once real policies are
  built against it; that's a additive, not breaking, contract evolution
  if so.

## Alternatives Considered

- **Let the orchestrator produce a `StrategyDecision` or `ExecutionDecision`
  directly**, reusing an existing contract instead of introducing
  `FinalDecision` — rejected: per product-owner direction, `FinalDecision`
  answers a genuinely different question ("what should the platform
  actually do, given everything it currently believes") than either
  existing contract, and conflating them would either misrepresent an
  arbitrated decision as a raw strategy opinion, or require widening
  `StrategyDecision`/`ExecutionDecision` with arbitration-specific fields
  neither contract's own consumers need.
- **Allow `final_allocation` to exceed `primary_allocation`** (e.g. strong
  agreement from both advisory signals boosts conviction) — rejected per
  Directive 1: explicitly out of scope for "the first implementation";
  revisit only as a deliberate, separately-reviewed widening once
  arbitration behavior has been observed and validated.
- **Make `learner_input`/`news_input` `Optional[SignalInput]`, `None`
  when not considered** — rejected: every consumer would need to handle
  a `None` case, and `considered: bool` on an always-present `SignalInput`
  gives the same information without introducing an `Optional` required
  field, which no other contract in this handbook uses.
- **Authorize wiring `FinalDecision` into `RiskService` as part of this
  same freeze**, since Milestone 11 is explicitly about convergence —
  rejected: invariant #2's weight (the risk veto is the *only* gate on
  order submission) means changing what reaches it is a significant,
  reviewable production behavior change on its own, deserving a
  dedicated decision once the orchestrator's real behavior is observable
  — not something to bundle into the contract freeze that makes the
  orchestrator's existence possible in the first place.
- **Include a dedicated `contributing_versions: Mapping[str, str]` field**
  for per-subsystem model-version traceability (mirroring
  `ReplayRun.pipeline_versions`) — considered, not adopted: per
  [ADR-008](ADR-008-StrategyDecision-Contract.md)'s precedent for
  `StrategyDecision.metadata`, full audit-trail traceability can live in
  `metadata` once a real implementation defines what it actually needs
  there, rather than a required field speculating ahead of a
  demonstrated need.
