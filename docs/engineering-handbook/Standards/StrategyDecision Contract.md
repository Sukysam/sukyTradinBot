# Standard — StrategyDecision Contract

Governs `strategy.models.StrategyDecision`, the single output type the
Strategy Engine (Milestone 5) is expected to produce. See
[Architecture/ADR/ADR-008-StrategyDecision-Contract.md](../Architecture/ADR/ADR-008-StrategyDecision-Contract.md)
for why this type is frozen *before* `src/strategy/` exists at all —
following the same "freeze interfaces before implementation" discipline
[ADR-004](../Architecture/ADR/ADR-004-FeatureVector-Contract-Freeze.md)
and [ADR-006](../Architecture/ADR/ADR-006-RegimeState-Contract.md)
established for `FeatureVector` and `RegimeState`. This document is the
binding contract for whoever implements the Strategy Engine against it,
and for every future consumer (Risk Management, Execution, Adaptive
Learning) that reads a `StrategyDecision`.

## Why this exists, and why now

Milestone 5's mandate is narrow on purpose: convert `RegimeState` (plus
`FeatureVector` context) into a `StrategyDecision` — an investment
opinion, not an execution order. Nothing about capital adequacy,
liquidity, leverage limits, or order placement belongs in this milestone
or this contract; those are Milestone 6 (Risk) and Milestone 7
(Execution)'s job, consuming `StrategyDecision` the same way Milestone 5
consumes `RegimeState`. Freezing the contract now, before a single
strategy is implemented, means the Strategy Engine's internals (which
strategies exist, how allocation is computed, what the registry looks
like) can be built and iterated on freely without ever being confused
with the one thing every downstream consumer is allowed to depend on.

## Scope

Applies to `strategy.models.StrategyDecision` and whatever public method
the eventual `strategy.service` module exposes to produce it (signature
not yet fixed — that's implementation, not contract). Does **not**
freeze: which strategies are registered, how the registry resolves a
regime to a strategy, or the allocation formula itself — all of that is
Milestone 5 implementation detail, deliberately left open per
[ADR-008](../Architecture/ADR/ADR-008-StrategyDecision-Contract.md)'s
"freeze interfaces, not implementation" framing (the same split
[ADR-007](../Architecture/ADR/ADR-007-HMM-Design.md) applied to the HMM's
own hyperparameters).

## Required fields

| Field | Type | Guarantee |
|---|---|---|
| `timestamp` | `datetime` | Timezone-aware, normalized to UTC. The `RegimeState.timestamp` this decision was made from — the causal "as of" time, not when the decision object was constructed. |
| `symbol` | `str` | Never empty. |
| `strategy_id` | `str` | Which registered strategy produced this decision — never empty. Not stable across a strategy's own internal logic changes the way `regime_id` isn't stable across HMM retraining: pair `strategy_id` with whatever versioning the eventual strategy registry defines before comparing decisions across strategy-implementation changes. |
| `regime_id` | `int` | Copied from the input `RegimeState.regime_id` — links a decision back to the regime call that produced it, the same traceability pattern `RegimeState.feature_pipeline_version` gives `FeatureVector`. `>= 0`. |
| `allocation` | `float` | Target position size as a fraction of the strategy's allocatable capital. **`[0.0, 1.0]` — never negative.** This is not a strategy-level nicety; it's [00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md) invariant #5 ("every strategy is long-only") enforced at the type level, not left to a call site to remember. `0.0` is a valid decision ("no position given this regime"), not an error. |
| `confidence` | `float` | The *strategy's* confidence in this decision, in `[0.0, 1.0]` — distinct from `RegimeState.confidence` (the HMM's confidence in the regime call itself). A strategy may reasonably combine regime confidence with its own signal strength, or ignore regime confidence entirely; this field doesn't prescribe how. |
| `expected_holding_period` | `timedelta` | The strategy's own estimate of how long this position is expected to be held given current regime/market conditions. Informational, not a hard exit rule — nothing about this contract requires a position be closed when this period elapses. Must be positive. Exists specifically so the future Adaptive Learning milestone can evaluate "did this strategy behave as expected" against a stated prior, not just against realized P&L. A strategy with no principled estimate can derive one from `RegimeState.transition_probability` — for a regime with self-transition probability `p`, the expected number of periods before transitioning away is `1 / (1 - p)` (the mean of a geometric distribution) — but this contract doesn't mandate that specific method. |
| `reasoning` | `str` | Human-readable explanation of the decision. Never empty — the same "never submit an order with no reconstructable rationale" principle [00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md) invariant #6 already requires of `TradeDecision`'s rationale fields, applied one step upstream. |
| `metadata` | `Mapping[str, Any]` | Free-form. **No guaranteed keys yet** — unlike `FeatureVector.metadata` and `RegimeState.metadata`, this contract is being frozen before any implementation populates it, so promising specific keys now would be speculation. The first real Strategy Engine implementation documents and freezes its actual guaranteed keys in the same change, following the same "generated/decided alongside real code, not guessed in advance" discipline as everything else in this contract. |

`StrategyDecision` must be an immutable (`frozen=True`) dataclass,
matching `FeatureVector` and `RegimeState`.

## Versioning policy

Follows the same three-tier pattern as
[FeatureVector Contract.md](FeatureVector%20Contract.md#versioning-policy)
and [RegimeState Contract.md](RegimeState%20Contract.md): a contract-shape
version (this document's own "Contract history" below) is independent of
whatever internal versioning the eventual strategy registry defines for
individual strategies. Currently **v1** (this freeze, ADR-008) — no
implementation exists yet to have driven a v2.

## Backward compatibility expectations

Same allowed/requires-a-new-ADR/never-permitted structure as
[RegimeState Contract.md](RegimeState%20Contract.md#backward-compatibility-expectations),
applied to `StrategyDecision`. Notably: adding guaranteed `metadata` keys
once a real implementation exists is additive and doesn't require a new
ADR; changing `allocation`'s `[0.0, 1.0]` bound would — that bound isn't
a formatting detail, it's invariant #5 given a concrete shape, and
loosening it (e.g. to permit negative/short allocations) is exactly the
kind of decision [01_SYSTEM_ARCHITECT.md](../01_SYSTEM_ARCHITECT.md) must
sign off on explicitly, per that invariant's own text ("don't add
short-side code without an explicit spec citation authorizing it").

## Contract history

- **v1** ([ADR-008](../Architecture/ADR/ADR-008-StrategyDecision-Contract.md)):
  initial freeze — `timestamp`, `symbol`, `strategy_id`, `regime_id`,
  `allocation`, `confidence`, `expected_holding_period`, `reasoning`,
  `metadata`. No implementation exists yet; this is the contract Milestone
  5 is built against, not a retrofit onto existing code.

## Enforcement

Not yet mechanically enforced — there is no `strategy.models` module yet.
The first implementation ships `tests/strategy/test_models.py` enforcing
every constraint in the Required Fields table above (frozen dataclass,
UTC timestamp, non-empty `symbol`/`strategy_id`/`reasoning`, `regime_id
>= 0`, `allocation` and `confidence` in `[0.0, 1.0]`,
`expected_holding_period > timedelta(0)`), in the same change that adds
the module, matching every other contract in this handbook.

## Ownership

Build and maintain: [Quant Researcher](../04_QUANT_RESEARCHER.md) (builds
the statistical/allocation logic) jointly with
[Signal Orchestrator](../07_SIGNAL_ORCHESTRATOR.md) (owns how
`StrategyDecision` feeds the eventual cross-source arbitration in
Milestone 11) — see
[00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md)'s Capability Ownership Map
once Milestone 5 lands. Binding on every consumer: Risk Management
(Milestone 6), Execution (Milestone 7), Adaptive Learning (Milestone 9,
via `expected_holding_period`), and Signal Orchestration (Milestone 11).
A consumer that needs a capability this contract doesn't provide raises
it against this document — it doesn't reach into Strategy Engine
internals to work around it.
