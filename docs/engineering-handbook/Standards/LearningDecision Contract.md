# Standard — LearningDecision Contract

Governs `memory.models.LearningDecision` and `memory.models.ExperienceRecord`,
the two output types the Adaptive Learning / Memory Loop (Milestone 9) is
expected to produce. See
[Architecture/ADR/ADR-016-LearningDecision-Contract.md](../Architecture/ADR/ADR-016-LearningDecision-Contract.md)
for why these types are frozen *before* `src/memory/` exists at all —
following the same "freeze interfaces before implementation" discipline
[ADR-008](../Architecture/ADR/ADR-008-StrategyDecision-Contract.md),
[ADR-010](../Architecture/ADR/ADR-010-ExecutionDecision-Contract.md),
[ADR-012](../Architecture/ADR/ADR-012-OrderIntent-Contract.md), and
[ADR-014](../Architecture/ADR/ADR-014-BacktestResult-Contract.md)
established for every prior milestone's output. This document is the
binding contract for whoever implements the Memory Loop against it, and
for every future consumer.

## Why this exists, and why now

Milestone 9's mandate, per direct product-owner review of Milestone 8, is
narrower than the reference design in
[Architecture/Reinforcement Learning Memory Loop.md](../Architecture/Reinforcement%20Learning%20Memory%20Loop.md)
and [05_MEMORY_ENGINEER.md](../05_MEMORY_ENGINEER.md) implies at first
read: **shadow mode only**. The learner observes every real
`StrategyDecision` and the `TradeRecord` outcome it eventually produced,
forms its own opinion of what allocation it would have chosen given the
same context, and records that opinion — it never feeds back into
`strategy`, `risk`, or `execution` in this milestone. That boundary needs
to be a contract property, not just a stated intention, the same way
Milestone 5's `StrategyDecision` freeze made "opinion, not order" a type-
level fact rather than a documentation promise.

Two types are frozen together because they represent the two ends of the
same loop: `ExperienceRecord` is what the learner learns *from* (closed,
realized outcomes), and `LearningDecision` is what the learner produces
*from* that experience (an unexecuted, shadow-only recommendation). Both
are new to this handbook; neither has a `regime-trader/` legacy analog
frozen as a contract — `core/learning_engine.py`'s `TradeContext` and
implicit weight lookups were never formalized this way. This freeze
supersedes that legacy design's shape (see ADR-016 for what carries over
and what doesn't), while keeping its core reinforcement-learning
formulation: a contextual multi-armed bandit over `(strategy_id,
regime_id)`.

## Scope

Applies to `memory.models.ExperienceRecord` and `memory.models.
LearningDecision`, and whatever public method the eventual `memory.
service` module exposes to produce them (signatures not yet fixed —
that's implementation, not contract). Does **not** freeze: how experience
is persisted (in-memory, file-backed, or otherwise), which policy
algorithm computes `recommended_allocation` (Thompson Sampling over Beta
posteriors is the *expected* starting point per product-owner direction,
not mandated by this contract), or the exact bucketing granularity of the
learning context beyond what's specified below — all Milestone 9
implementation detail.

## Required fields — `ExperienceRecord`

One `ExperienceRecord` is the atomic unit of the Experience Store — a
single closed trade's context and realized outcome, the raw material the
learner learns from. Conceptually downstream of `backtest.models.
TradeRecord` (or, once a live trading loop exists, whatever produces the
equivalent live outcome), not a replacement for it.

| Field | Type | Guarantee |
|---|---|---|
| `symbol` | `str` | Never empty. |
| `strategy_id` | `str` | Never empty. Copied from the `StrategyDecision` that led to this trade — same non-stability-across-implementation-changes caveat as `StrategyDecision.strategy_id` itself. |
| `regime_id` | `int` | Copied from the `RegimeState` in force when the originating `StrategyDecision` was made. `>= 0`. |
| `production_allocation` | `float` | The `StrategyDecision.allocation` that was actually acted on for this trade. `[0.0, 1.0]`. Recorded here (not just derivable from the trade's position size) so a `LearningDecision` can later compare its own recommendation against exactly what production chose, without needing to reconstruct it from `quantity`/`entry_price`. |
| `realized_pnl` | `float` | Realized profit/loss in account currency for the closed trade. May be negative. |
| `realized_pnl_pct` | `float` | Realized profit/loss as a fraction of entry notional. May be negative. |
| `won` | `bool` | `True` iff `realized_pnl > 0` — the binary reward signal the reference bandit design uses. Validated at construction to be consistent with `realized_pnl`'s sign (`realized_pnl == 0.0` is `won = False`, matching "no reward" rather than "positive reward," the same strict-inequality convention [Architecture/Reinforcement Learning Memory Loop.md](../Architecture/Reinforcement%20Learning%20Memory%20Loop.md) already documents). |
| `entry_timestamp` | `datetime` | Timezone-aware, normalized to UTC. |
| `exit_timestamp` | `datetime` | Timezone-aware, normalized to UTC. Strictly after `entry_timestamp`. |
| `holding_period` | `timedelta` | Must equal `exit_timestamp - entry_timestamp` — same invariant `backtest.models.TradeRecord` already enforces, kept consistent rather than re-derived differently here. |
| `source_run_id` | `str` | Traceability back to the `backtest.models.ReplayRun.run_id` (or eventual live-session identifier) that produced this experience. Never empty — an experience record with no traceable origin can't be debugged when a posterior looks wrong. |
| `metadata` | `Mapping[str, Any]` | Free-form. No guaranteed keys yet — first real implementation documents and freezes whatever it needs, same discipline `StrategyDecision.metadata` followed. |

`ExperienceRecord` must be an immutable (`frozen=True`) dataclass.

**Deliberate scope boundary**: the learning *context* this milestone
buckets on is `(strategy_id, regime_id)` only — no per-symbol dimension,
no RSI-bucket or other feature-derived dimension, even though the
reference design ([Architecture/Reinforcement Learning Memory Loop.md](../Architecture/Reinforcement%20Learning%20Memory%20Loop.md))
bucketed on `(strategy, regime_label, rsi_bucket)`. `ExperienceRecord`
still carries `symbol` for traceability, but nothing in this contract
requires the learning policy to bucket by it. Narrowing the context this
way is the same trade-off the reference design's own "Deliberate scope
boundary" section already named: fewer dimensions means more samples
accumulate per arm, strengthening posterior estimates sooner. Widening
the bucketed context (adding symbol, an RSI bucket, or anything else) is
a deliberate, reviewed decision per that same precedent — not a natural
next increment slipped in without an ADR.

## Required fields — `LearningDecision`

One `LearningDecision` is the learner's shadow opinion at the moment a
real `StrategyDecision` was made for a given `(symbol, strategy_id,
regime_id)` — recorded for later comparison, **never consumed by
`risk`, `execution`, or `strategy`** in this milestone. That boundary is
enforced architecturally (no import edge from those packages into
`memory`, and no import edge from `memory` back into them beyond reading
already-frozen contracts), not just by convention.

| Field | Type | Guarantee |
|---|---|---|
| `timestamp` | `datetime` | Timezone-aware, normalized to UTC. Equal to the `StrategyDecision.timestamp` this recommendation shadows — the causal "as of" time. |
| `symbol` | `str` | Never empty. |
| `strategy_id` | `str` | Never empty. |
| `regime_id` | `int` | `>= 0`. |
| `production_allocation` | `float` | The real `StrategyDecision.allocation` this recommendation shadows. `[0.0, 1.0]`. Copied, not referenced, so a `LearningDecision` is self-contained and comparable without joining back to strategy-service state that may no longer exist by the time anyone reviews it. |
| `recommended_allocation` | `float` | What the learner would have chosen given the same context. `[0.0, 1.0]` — bound to the same long-only invariant (00_MASTER_CHARTER.md invariant #5) every allocation-shaped field in this system already carries, even though this one is never executed. |
| `confidence` | `float` | The *learner's* confidence in `recommended_allocation`, `[0.0, 1.0]` — distinct from `StrategyDecision.confidence` (the strategy's own confidence) and from `RegimeState.confidence` (the HMM's). Expected to reflect posterior certainty (e.g., derived from accumulated sample size), not to be confused with `production_allocation`'s correctness. |
| `sample_size` | `int` | Number of `ExperienceRecord`s the recommendation was computed from for this `(strategy_id, regime_id)` context. `>= 0`. A `LearningDecision` with `sample_size == 0` is a cold-start default, not a real signal — callers reviewing recommendations must treat low-`sample_size` decisions skeptically; this contract makes the sample size inspectable specifically so they can. |
| `rationale` | `str` | Human-readable explanation of the recommendation. Never empty — same "never produce an unexplained decision" principle every prior decision-shaped contract in this handbook (`StrategyDecision.reasoning`, `ExecutionDecision.reasoning`) already carries. Deliberately **not** a SHAP attribution — per explicit product-owner direction, SHAP is postponed until the learner has accumulated enough real examples to make attribution meaningful; a simple, human-readable summary (e.g., posterior mean and sample counts for the context) satisfies this field for Milestone 9. See [Architecture/SHAP Trade Attribution.md](../Architecture/SHAP%20Trade%20Attribution.md) for the deferred design. |
| `model_version` | `str` | Identifies the learning-policy version that produced this recommendation. Never empty. Same traceability role `hmm.models.ModelMetadata.model_version` plays for `RegimeState` — a posterior computed under one policy version shouldn't be silently compared against one computed under another without that being visible. |
| `metadata` | `Mapping[str, Any]` | Free-form. No guaranteed keys yet — first real implementation documents and freezes whatever it needs. |

`LearningDecision` must be an immutable (`frozen=True`) dataclass,
matching every other decision-shaped contract in this handbook.

## The shadow-mode guarantee

This is the property Milestone 9 exists to prove out safely, so it's
stated here explicitly rather than left implicit in the field list
above: **no code path in this milestone constructs an `OrderIntent`,
`ExecutionDecision`, or `StrategyDecision` from a `LearningDecision`'s
`recommended_allocation`.** `LearningDecision` is written to the
Experience Store's companion recommendation log and nowhere else. A
future milestone that wants the learner to actually influence production
allocation is a deliberate, reviewed, separately-ADR'd decision — not
something this contract's existence should be read as already
authorizing.

## Versioning policy

Follows the same three-tier pattern as every prior contract in this
handbook (see
[StrategyDecision Contract.md](StrategyDecision%20Contract.md#versioning-policy)):
a contract-shape version (this document's own "Contract history" below)
is independent of whatever internal versioning the eventual learning
policy defines for itself (`model_version`). Currently **v1** (this
freeze, ADR-016) — no implementation exists yet to have driven a v2.

## Backward compatibility expectations

Same allowed/requires-a-new-ADR/never-permitted structure as
[RegimeState Contract.md](RegimeState%20Contract.md#backward-compatibility-expectations),
applied to `ExperienceRecord` and `LearningDecision`. Notably: adding
guaranteed `metadata` keys once a real implementation exists is
additive; widening the `(strategy_id, regime_id)` learning context (see
"Deliberate scope boundary" above) or allowing a `LearningDecision` to be
consumed by `strategy`/`risk`/`execution` would each require a new ADR
and explicit [01_SYSTEM_ARCHITECT.md](../01_SYSTEM_ARCHITECT.md)
sign-off — the second of those in particular is exactly the kind of
decision this contract's shadow-mode guarantee exists to make
deliberate, not incidental.

## Contract history

- **v1** ([ADR-016](../Architecture/ADR/ADR-016-LearningDecision-Contract.md)):
  initial freeze — `ExperienceRecord` (`symbol`, `strategy_id`,
  `regime_id`, `production_allocation`, `realized_pnl`,
  `realized_pnl_pct`, `won`, `entry_timestamp`, `exit_timestamp`,
  `holding_period`, `source_run_id`, `metadata`) and `LearningDecision`
  (`timestamp`, `symbol`, `strategy_id`, `regime_id`,
  `production_allocation`, `recommended_allocation`, `confidence`,
  `sample_size`, `rationale`, `model_version`, `metadata`). No
  implementation exists yet; this is the contract Milestone 9 is built
  against, not a retrofit onto existing code.

## Enforcement

Not yet mechanically enforced — there is no `memory.models` module yet.
The first implementation ships `tests/memory/test_models.py` enforcing
every constraint in the Required Fields tables above (frozen dataclasses,
UTC timestamps, non-empty string fields, `regime_id >= 0`, every
allocation/confidence field in `[0.0, 1.0]`, `sample_size >= 0`,
`holding_period == exit_timestamp - entry_timestamp`, `won` consistent
with `realized_pnl`'s sign), in the same change that adds the module,
matching every other contract in this handbook.

## Ownership

Build and maintain: [Memory Engineer](../05_MEMORY_ENGINEER.md), per that
role's existing mandate over the Reinforcement Learning memory loop and
online learning. A consumer that needs a capability this contract doesn't
provide — in particular, anything that would let a `LearningDecision`
influence a real trade — raises it against this document and
[01_SYSTEM_ARCHITECT.md](../01_SYSTEM_ARCHITECT.md) explicitly. It does
not reach into `memory` internals, or into `strategy`/`risk`/`execution`,
to wire that up unreviewed.
