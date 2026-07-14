# ADR-021: Signal Orchestration Design

**Status**: Accepted
**Date**: 2026-07-14
**Milestone**: [11 — Signal Orchestration](../../../../PROJECT_STATUS.md)

## Context

ADR-020 froze `FinalDecision`/`SignalInput` before `src/orchestration/`
existed. This record covers the implementation decisions made building
against that freeze: how `StrategyDecision`/`LearningDecision`/
`NewsSignal` are actually reconciled, how the arbitration algorithm is
made pluggable, and how cross-signal quality is measured — the same
category of decision ADR-019 recorded for Milestone 10.

Per explicit product-owner direction, Milestone 11 was built in three
independently-verified phases, the same discipline Milestones 8–10 each
used:

1. **Phase A — Arbitration.** A single, deterministic rule
   (`StrategyDecision + LearningDecision + NewsSignal → FinalDecision`).
   No execution, no broker, no risk.
2. **Phase B — Policies.** "I would avoid hard-coding orchestration
   logic" — Phase A's rule becomes one of four pluggable
   `ArbitrationPolicy` implementations, each behind the same interface,
   so the orchestrator delegates rather than hardcoding a specific
   mechanism.
3. **Phase C — Evaluation.** Cross-signal metrics (agreement rate, signal
   conflict rate, strategy-vs-learner divergence, news alignment,
   orchestration confidence, override frequency) — the first point in
   this handbook where multiple independent signal sources exist to
   compare, per direct product-owner review ("those metrics become much
   more informative once multiple signal sources exist to compare").

## Decision

### 1. Phase A: a single rule, factored for reuse from day one

`arbitrate` (`orchestration.arbitration`) implements one disagreement
cutting `final_allocation` by `config.disagreement_penalty`, two
disagreements suppressing entirely. Context validation and considered/
agrees classification were factored into `orchestration.signals` from
the start (not refactored out later), anticipating Phase B's multiple
policies needing the same logic — the same "shared helper, not
duplicated per consumer" discipline `memory`/`nlp`'s own metric modules
already used.

### 2. Phase B: `ArbitrationPolicy` Protocol, four genuinely distinct mechanisms

`orchestration.interfaces.ArbitrationPolicy` is a single-method Protocol
(`arbitrate(strategy_decision, learning_decision, news_signal) →
FinalDecision`) — the same "freeze interfaces, not implementation" split
`strategy.interfaces.Strategy`/`memory.interfaces.LearningPolicy`/`nlp.
interfaces.SentimentScorer` each already established for their own
package's pluggable stage. Phase A's original rule became `orchestration.
policies.SafetyFirstPolicy`; `arbitrate` now delegates to it by default
(`policy=None` → `SafetyFirstPolicy(config=config)`), preserving every
Phase A call site and test unchanged.

Three more policies, each a genuinely different arbitration mechanism,
not just a parameter variation on `SafetyFirstPolicy`:

- **`ConsensusPolicy`** — stricter: *any* considered disagreement
  suppresses entirely (not two). Models "unless everyone agrees, don't
  act."
- **`WeightedVotePolicy`** — continuous: a configurable vote weight per
  source (`strategy_weight`, `learner_weight`, `news_weight`), blended
  into a multiplier. Structurally can never fully suppress a decision as
  long as `strategy_weight > 0` — a deliberate, named property
  distinguishing it from `SafetyFirstPolicy`/`ConsensusPolicy`, which
  *can* suppress. Models "advisory signals nudge conviction," not
  "advisory signals can veto it."
- **`ConfidencePolicy`** — orthogonal axis: scales by how confident
  advisory signals are *relative to the strategy's own confidence*,
  independent of directional agreement entirely. A highly confident but
  disagreeing signal and a barely-confident agreeing one are treated
  very differently — the only policy of the four where `SignalInput.
  agrees` doesn't drive the allocation math at all (it's still populated,
  for audit consistency, using the same direction check every other
  policy uses).

Every policy independently satisfies `FinalDecision`'s own construction-
time invariants (`final_allocation ≤ primary_allocation`, `outcome`
consistency) — those are enforced by the frozen contract itself, not
something any policy implementation could bypass even with a bug.

### 3. Phase C: paired `(FinalDecision, LearningDecision, NewsSignal)` history, not `FinalDecision` alone

`orchestration.evaluation.evaluate` takes triples, not bare
`FinalDecision`s, because `SignalInput` alone doesn't carry the raw
magnitude a divergence metric needs (e.g. `strategy_vs_learner_divergence`
needs `LearningDecision.recommended_allocation`, not just `SignalInput.
agrees`/`weight`). This mirrors `memory.evaluation`/`nlp.evaluation`'s
own precedent of accepting richer paired input rather than trying to
reconstruct everything from a single summary object. All six requested
metrics are computed: `agreement_rate` (fraction `CONFIRMED`),
`override_frequency` (its exact complement — the only case where
"override" and "not agreement" differ would require a third state this
contract doesn't have), `signal_conflict_rate` (fraction of
both-considered decisions where the two advisory signals disagree with
*each other*, independent of the primary), `strategy_vs_learner_divergence`
(mean absolute allocation gap), `news_alignment` (fraction of
news-paired decisions where news agreed), and `orchestration_confidence`
(mean `FinalDecision.confidence`). Like `memory.evaluation`/`nlp.
evaluation`, this module never mutates state and never influences a
decision — comparison only.

### 4. Wiring remains unauthorized in this milestone

Per ADR-020's own "Wiring is not yet authorized" section, nothing in
this implementation constructs a `StrategyDecision`, `ExecutionDecision`,
or `OrderIntent` from a `FinalDecision`. `risk` gains no new dependency
on `orchestration` in this milestone. `FinalDecision` can be computed
against real decisions for observability, but the execution path still
runs on the unarbitrated `StrategyDecision`, exactly as every milestone
before this one.

## Consequences

- The three-phase build gave the shadow-mode-adjacent guarantee three
  independent checkpoints: Phase A proved the arbitration math is
  deterministic and contract-consistent before any policy pluggability
  existed, Phase B proved four genuinely different mechanisms can all
  satisfy the same contract without weakening its bound, and Phase C
  proved cross-signal comparison is possible without ever touching
  production.
- `ArbitrationPolicy`'s single-method Protocol means adding a fifth
  policy later is a contained, additive change — implement the Protocol,
  no change to `arbitrate`, `orchestration.signals`, or any existing
  policy.
- `WeightedVotePolicy`'s "never fully suppresses" property and
  `ConfidencePolicy`'s "agreement-independent" property are both
  deliberately named, tested characteristics — a future caller choosing
  between the four policies has a documented behavioral difference to
  reason about, not just four black boxes producing the same shape.
- Trade-off, accepted: like every fresh contract-adjacent implementation
  in this handbook, the four policies' specific parameters
  (`disagreement_penalty = 0.5`, `learner_weight = news_weight = 0.5`,
  etc.) are reasonable defaults, not empirically tuned — no real
  arbitration history exists yet to tune them against. Revisit once
  Phase C's own metrics, run against real decisions, suggest a direction.

## Alternatives Considered

- **Keep Phase A's rule as the only mechanism, defer pluggable policies
  to a later milestone** — rejected per explicit direction: "I would
  avoid hard-coding orchestration logic" was stated as a requirement for
  *this* milestone, not a future one.
- **Give each policy its own bespoke agreement/context-validation logic**
  — rejected: `orchestration.signals`'s shared helpers exist specifically
  so `SafetyFirstPolicy`/`ConsensusPolicy`/`WeightedVotePolicy`/
  `ConfidencePolicy` can't silently diverge on what "agrees" or "matching
  context" means; a bug fix or refinement to that logic benefits all four
  at once.
- **Have `evaluate` accept bare `FinalDecision`s and reconstruct
  divergence from `SignalInput.weight`** — rejected: `weight`'s meaning
  differs per policy (see each policy's own docstring), so reconstructing
  a magnitude from it would silently conflate four different semantics
  into one number. Accepting the raw paired advisory input is honest
  about what's actually needed.
- **Make `override_frequency` and `agreement_rate` independently
  computed rather than exact complements** — considered, not adopted:
  with only three `ArbitrationOutcome` values and `CONFIRMED` meaning
  exactly "no override happened," the two are definitionally
  complementary; computing them independently would only risk them
  silently drifting apart from a future bug, not add real information.
