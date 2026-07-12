# ADR-008: Freeze the StrategyDecision Contract

**Status**: Accepted
**Date**: 2026-07-12
**Milestone**: [5 — Strategy Engine](../../../../PROJECT_STATUS.md) (contract only — no
implementation in this record; see Context)

## Context

Milestone 4 established a repeatable pattern: freeze a milestone's output
contract before its implementation exists, so the contract is grounded in
what the *previous* milestone actually produces (`FeatureVector` for the
HMM, `RegimeState` for the Strategy Engine) rather than guessed ahead of
need. This record applies that same discipline one milestone earlier than
before: `src/strategy/` does not exist yet. `StrategyDecision` is frozen
first, reviewed, and only then does implementation begin — a stricter
sequencing than Milestone 4's own contract freeze (ADR-006), which landed
in the same change as the HMM implementation itself. This is a
deliberate tightening of the process, not a one-off: the value of
freezing early compounds when the freeze genuinely precedes every line of
the code it constrains.

Milestone 5's own scope is narrow by design: convert `RegimeState` (plus
`FeatureVector` context) into an investment opinion, not an execution
order. That boundary needs to be a contract property, not just a stated
intention, or a future implementation detail (a capital check, a
liquidity constraint, an order stub) could quietly creep into what
`StrategyDecision` promises.

## Decision

`strategy.models.StrategyDecision` — `timestamp`, `symbol`,
`strategy_id`, `regime_id`, `allocation`, `confidence`,
`expected_holding_period`, `reasoning`, `metadata` — is frozen as a
binding contract, documented in full at
[Standards/StrategyDecision Contract.md](../../Standards/StrategyDecision%20Contract.md),
*before* `src/strategy/` is scaffolded. Two properties are enforced at
the type level, not left to documentation or a call site's discipline:

1. **`allocation` is bounded to `[0.0, 1.0]`** — no negative values.
   This gives [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md)
   invariant #5 ("every strategy is long-only") a concrete, unavoidable
   shape at the exact point a strategy's output is constructed, the same
   way `RegimeState.confidence`/`transition_probability`'s `[0, 1]` bounds
   are enforced in `hmm.models`.
2. **`reasoning` must be non-empty.** Every `StrategyDecision` carries a
   human-readable rationale by construction, extending
   [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md) invariant #6's
   "never submit an order with no reconstructable rationale" one step
   upstream of the order itself.

`expected_holding_period` is a new field with no `RegimeState`/
`FeatureVector` analog — added specifically for the future Adaptive
Learning milestone (9), which needs a stated prior ("this strategy
expected to hold for roughly N periods") to evaluate against realized
behavior, not just realized P&L. This document also notes, without
mandating, that `RegimeState.transition_probability` already implies a
principled default estimate: for a regime with self-transition
probability `p`, the expected number of periods before transitioning
away is `1 / (1 - p)`.

`StrategyDecision.metadata` is frozen with **no guaranteed keys** — unlike
`FeatureVector.metadata` and `RegimeState.metadata`, which were frozen
alongside (or after) a real implementation that already knew what it
needed to put there, no Strategy Engine implementation exists yet to
honestly commit to specific keys. The first real implementation documents
and freezes its actual guaranteed metadata keys in the same change that
adds them, rather than this ADR guessing them now.

## Consequences

- Whoever implements Milestone 5 has one document to build against before
  writing `src/strategy/`'s first line — the registry design, the
  allocation formula, and which strategies exist are all free to be
  designed and iterated on, because none of that is what this freeze
  constrains.
- Milestone 6 (Risk) and Milestone 7 (Execution) both have a stable
  contract to design against well before Milestone 5's implementation is
  even reviewed — the same "next milestone can start designing against a
  known shape" benefit `RegimeState`'s freeze gave this one.
- `allocation`'s `[0.0, 1.0]` bound makes a future short-selling feature a
  genuine breaking change requiring a new ADR and explicit
  [01_SYSTEM_ARCHITECT.md](../../01_SYSTEM_ARCHITECT.md) sign-off, per
  invariant #5's own text — not something that could slip in as an
  unreviewed widening of a float field's practical range.
- Trade-off, accepted: because no implementation exists yet, this freeze
  is more speculative than ADR-004's or ADR-006's — those were written
  with full knowledge of what the immediately-preceding milestone's real
  code produced. `metadata`'s empty guaranteed-key set is the explicit
  acknowledgment of that: better to freeze nothing there than freeze a
  guess.

## Alternatives Considered

- **Wait until Milestone 5's implementation exists, then freeze the
  contract retroactively (matching how ADR-006 was done)** — rejected
  per explicit direction: the stricter sequencing (contract reviewed
  *before* any implementation) is the deliberate process improvement this
  ADR exists to adopt, not a one-off exception.
- **Allow `allocation` to range `[-1.0, 1.0]` now, so a future short-
  selling strategy doesn't require a contract change later** — rejected:
  speculatively widening a bound "in case it's needed later" is exactly
  the kind of premature flexibility [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md)'s
  Definition of Done warns against, and it would silently weaken
  invariant #5's guarantee for every consumer between now and whenever
  shorting is actually authorized. A real short-selling decision gets its
  own ADR and an explicit widening, not a bound left loose "just in case."
- **Include a `model_version`/`feature_pipeline_version`-style
  traceability field on `StrategyDecision` directly, mirroring
  `RegimeState.feature_pipeline_version`** — considered, not adopted:
  `regime_id` already links a decision back to its source `RegimeState`,
  and full audit-trail traceability (which HMM model, which feature
  pipeline version) can live in `metadata` once a real implementation
  defines what it actually needs there, rather than adding a required
  field for a need not yet concretely demonstrated.
