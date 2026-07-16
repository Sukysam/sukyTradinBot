# ADR-030: Runtime Strategy Engine Design (Phase D) + RuntimeFrame

**Status**: Accepted
**Date**: 2026-07-16
**Milestone**: Post-`v2.0.0` continuous evolution — Trading Validation / Runtime, Phase D

## Context

Phase C (ADR-029) proved the runtime can perform causal regime
inference and emit `RegimeState`s. Per direct instruction, Phase D
stays intentionally narrow: `RegimeState -> StrategyService ->
StrategyDecision`, and stop there — no Risk, no Execution, no Signal
Orchestration, no Memory, no NLP.

`strategy.service.StrategyService.decide(feature_vector, regime_state)`
needs *both* a `FeatureVector` and the `RegimeState` derived from it in
the same call (it validates the two agree on `symbol`/`timestamp`
before dispatching). Before this phase, `RegimeEmitter.
handle_feature_vector` received only a `FeatureVector` and, on success,
passed only the resulting `RegimeState` onward via `on_regime_state` —
the original `FeatureVector` was never available to whatever consumed
that hook. Phase D genuinely cannot be built on top of Phase C's prior
wiring without solving this.

Per direct instruction, this ADR also introduces `app.frame.
RuntimeFrame`: an internal carrier object that each phase enriches in
turn (`bar` -> `feature_vector` -> `regime_state` ->
`strategy_decision`) instead of each phase inventing its own
single-purpose callback signature. This directly solves the problem
above (Phase D needs two objects together) and is adopted now rather
than deferred, since Phase D is the first phase that actually needs
it — building it earlier, with no real consumer, would have been
speculative infrastructure this project's own discipline avoids.

## Decision

### 1. `app.frame.RuntimeFrame` -- internal plumbing, not a frozen contract

A frozen dataclass carrying `bar: Bar` (always present) plus
`feature_vector`/`regime_state`/`strategy_decision`, each `None` until
the phase that produces it enriches the frame via `with_feature_vector`/
`with_regime_state`/`with_strategy_decision` (each returns a new frame,
never mutates the original — `dataclasses.replace` under the hood).
`__post_init__` enforces enrichment order as an invariant (no
`regime_state` without a `feature_vector`, no `strategy_decision`
without a `regime_state`) — catching a wiring bug in `app.bootstrap`
immediately rather than letting a later phase silently receive a gap
it didn't expect.

Deliberately **not** a `features`/`hmm`/`strategy`-style frozen
contract: no Standards doc, no contract-freeze ADR, no consumer outside
`app` itself. It exists purely to move data between this package's own
emitters and can change shape freely as later phases (E onward) are
added — the same "no premature abstraction, but also no over-caution
once a real need exists" balance this project has held throughout.

### 2. `FeatureVectorEmitter`/`RegimeEmitter`'s hooks now carry a `RuntimeFrame`, not a bare payload

`FeatureVectorEmitter.on_feature_vector` (took a `FeatureVector`) is
replaced by `on_frame` (takes a `RuntimeFrame`); `FeatureVectorEmitter`
constructs `RuntimeFrame(bar=bar, feature_vector=vector)` before
calling it. `RegimeEmitter.handle_feature_vector`/`on_regime_state` are
replaced by `handle_frame`/`on_frame`; `RegimeEmitter` reads `frame.
feature_vector` (raising `ValueError` if a caller wires a frame that
hasn't been enriched with one yet -- an `app`-internal wiring bug, not
a runtime data condition) and enriches via `frame.with_regime_state`
before calling `on_frame`.

This is a **breaking change to Phase B/C's internal-only public API**
(constructor parameter names, method names) — deliberate, not
accidental. Neither `on_feature_vector`/`on_regime_state` nor
`handle_feature_vector` were ever consumed by anything outside `app`
itself (no external contract, no Standards doc, no other package
depends on them), so this is the same class of change as renaming a
private implementation detail, just one layer more visible than
`_`-prefixed. Keeping both old and new hooks side by side to preserve
backward compatibility was considered and rejected — see Alternatives
Considered.

### 3. `app.strategy_loop.StrategyEmitter`: frame in, frame out, no buffer

`handle_frame(frame)` reads `frame.feature_vector`/`frame.regime_state`
(raising `ValueError` if either is missing -- the same wiring-bug
guard `RegimeEmitter` uses), calls `StrategyService.decide(...)`, logs
one `strategy_decision_emitted` event per success (symbol, timestamp,
strategy_id, regime_id, allocation, confidence, latency), and records
`ops.metrics.MetricsRegistry`'s third real production consumer
(`strategy_decisions_emitted_total`, `strategy_decision_latency_seconds`,
`strategy_decision_errors_total`). A failure (`strategy.exceptions.
StrategyError`, most commonly `UnsupportedRegimeError` for a
`regime_id` no registered strategy — and no configured default —
supports) is caught, logged, and counted, never propagated, matching
every earlier emitter's failure-isolation convention.

Unlike `FeatureVectorEmitter`/`RegimeEmitter`, `StrategyEmitter` holds
no buffer: `StrategyService.decide` needs only the current
`(FeatureVector, RegimeState)` pair, no rolling history, since strategy
dispatch is a pure function of the current regime call.

### 4. `strategy_registry: StrategyRegistry` is a required, injected parameter -- same reasoning as `regime_service`

`build_strategy_loop` takes `regime_service` (as `build_regime_loop`
already required) and a new `strategy_registry: StrategyRegistry`,
both with no default construction. The reasoning mirrors ADR-029's
Decision 4 exactly, but for a different underlying cause: which
`regime_id`s map to which strategy style is inherently tied to a
*specific trained model's* regime semantics (`RegimeState.regime_id`
is an arbitrary MAP-state index with no fixed meaning across models --
see `strategy.interfaces.Strategy.supports`'s own docstring). Since no
model has ever been trained and interpreted in this project, nobody
has defined that mapping. An empty default registry would fail every
dispatch (`UnsupportedRegimeError`); a registry with invented
regime_id assignments would be actively misleading, appearing to work
while meaning nothing for whatever `regime_service` the caller
actually supplies.

Unlike `RegimeService`, `StrategyService` itself is cheap to construct
(no training, no I/O -- `StrategyService(registry, config)` is a plain
constructor call), so `build_strategy_loop` builds it internally from
`strategy_registry`/`strategy_config` rather than asking the caller to
hand over an already-built `StrategyService`. This also keeps
`strategy_registry` directly available for `strategy_registry_check`'s
probe (`lambda: len(strategy_registry.names()) > 0`), which a
pre-built, opaque `StrategyService` wouldn't expose.

### 5. `build_market_data_loop`/`build_feature_loop`/`build_regime_loop` extended again, not rewritten

`build_feature_loop`'s `on_feature_vector` parameter is renamed to
`on_frame` (typed `RuntimeFrameCallback`) to match Decision 2;
`build_regime_loop` gains the same additive `on_frame`/`extra_checks`
parameters `build_feature_loop` already had, so `build_strategy_loop`
can wire `strategy_emitter.handle_frame` in and add
`strategy_registry_check` without rewriting `build_regime_loop`. No
composition logic is duplicated across any of the four bootstrap
functions.

### 6. `app.main` is not updated to run Phase D

For the same reason `app.main` doesn't run Phase C: it would require a
real, trained `RegimeService` *and* a real, deliberately-configured
`StrategyRegistry` at process startup, neither of which exists yet.
`build_strategy_loop` is fully implemented and tested, ready for a
caller that supplies both.

## Consequences

- `ops.checks.strategy_registry_check` (another of Milestone 12's ten
  factories, unused until now) has its first real consumer.
- `ops.metrics.MetricsRegistry` now has its third emitter-level
  production consumer (`FeatureVectorEmitter`, `RegimeEmitter`,
  `StrategyEmitter`), each following an identical
  counter/gauge/error-counter shape -- a pattern now established
  enough that Phase E can be expected to follow it too.
- Adding Phase E (signal orchestration) means extending `app.bootstrap`
  with a `build_orchestration_loop` composing `build_strategy_loop` and
  wiring a new emitter's `on_frame`, not rewriting `app.runtime`,
  `app.features_loop`, `app.regime_loop`, or `app.strategy_loop` — the
  same shape every phase before this one has followed, now made
  slightly easier by `RuntimeFrame` already carrying everything a
  Phase E emitter would need (`feature_vector`, `regime_state`, and now
  `strategy_decision`) without inventing a fourth parallel callback
  signature.
- Trade-off, accepted and disclosed: Phase B and Phase C's internal
  hook APIs changed shape (Decision 2). Every test exercising those
  hooks was updated in the same PR; no external contract or Standards
  doc was affected, since `RuntimeFrame`/the `on_*` hooks were never
  part of any frozen contract.
- Trade-off, accepted (same reasoning as ADR-029): `app.main` does not
  run Phase D. Two prerequisites — a trained model and a deliberately
  configured strategy registry — remain outside this phase's scope.
- `app.bootstrap.__version__`/`app.__version__` bumped `0.3.0` ->
  `0.4.0`.

## Alternatives Considered

- **Keep both `on_feature_vector`/`on_regime_state` and the new
  `on_frame` hooks side by side** — rejected: the whole point of
  `RuntimeFrame` is that "downstream phases don't need parallel
  callback signatures" (the exact problem it was introduced to solve);
  keeping the old ones around as dead weight would reintroduce that
  problem while adding unused surface area.
- **Have `MarketDataLoop.on_bar` construct and pass a `RuntimeFrame`
  instead of a bare `Bar`** — rejected: `MarketDataLoop` is Phase A's
  already-shipped, tested component and has no need to know
  `RuntimeFrame` exists; `FeatureVectorEmitter` is the natural place to
  construct the first frame, since it's the first component that
  produces a second piece of state (`feature_vector`) to attach to the
  bar. Keeping `MarketDataLoop.on_bar`'s signature untouched avoids a
  third breaking change for no benefit.
- **Default `strategy_registry` to one populated with all four
  reference strategies (bull/bear/sideways/defensive) mapped to
  regime_ids `0-3`** — rejected: this would silently assume a specific
  trained model's regime semantics (4+ states, in a specific order)
  that may not match whatever `regime_service` the caller actually
  supplies, producing confidently-wrong strategy dispatch rather than
  an honest, loud gap.
- **Have `RuntimeFrame` validate `symbol`/`timestamp` consistency
  across `bar`/`feature_vector`/`regime_state`/`strategy_decision`** —
  rejected: `StrategyService.decide` (and, by extension, every future
  consumer) already performs this exact check at its own layer;
  duplicating it inside "just runtime plumbing" would be redundant
  business logic living in the wrong place.
- **Give `StrategyEmitter` a buffer, mirroring `FeatureVectorEmitter`/
  `RegimeEmitter`** — rejected: `StrategyService.decide` takes exactly
  one `(FeatureVector, RegimeState)` pair and needs no rolling history;
  adding a buffer with nothing to buffer would be unused machinery.
