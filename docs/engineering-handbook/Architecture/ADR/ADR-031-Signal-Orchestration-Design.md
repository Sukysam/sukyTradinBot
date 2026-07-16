# ADR-031: Signal Orchestration Design (Phase E) + Frame-Returning Emitters

**Status**: Accepted
**Date**: 2026-07-16
**Milestone**: Post-`v2.0.0` continuous evolution — Trading Validation / Runtime, Phase E

## Context

Phase D (ADR-030) proved the runtime can dispatch a regime call to a
strategy and emit a `StrategyDecision`. Per direct instruction, Phase
E stays intentionally narrow: arbitrate `StrategyDecision` (primary)
against optional advisory `LearningDecision`/`NewsSignal`, producing a
`FinalDecision` (Milestone 11's existing, frozen contract), and stop
there.

Two directives came together in the same instruction. First, the
runtime flow: `StrategyDecision -> OrchestrationEmitter ->
FinalDecision`, with an explicit constraint — **no `MemoryEmitter`/
`NlpEmitter` stage** feeding sequentially into the bar-driven pipeline.
`memory`/`nlp` stay advisory inputs consulted *by* `OrchestrationEmitter`,
not additional pipeline stages before it. Second, an architectural
correction to the pattern used since Phase D: stop adding a new
callback parameter (`on_frame`) to every emitter's constructor: from
this point on, every emitter should expose `handle_frame(frame) ->
RuntimeFrame | None` — consume a frame, enrich it, return it — so
composition becomes ordinary function composition, not an expanding
web of "next stage" hooks each emitter has to carry.

## Decision

### 1. `app.orchestration_loop.OrchestrationEmitter`: `arbitrate`, no new pipeline stage for Memory/NLP

`handle_frame` calls `orchestration.arbitration.arbitrate(strategy_decision,
learning_decision, news_signal, config=..., policy=...)` (default
policy: `SafetyFirstPolicy`), logs one `final_decision_emitted` event
per success (symbol, timestamp, outcome, primary_allocation,
final_allocation, confidence, latency), records `ops.metrics.
MetricsRegistry`'s third real production consumer, and returns the
enriched frame. A failure (`orchestration.exceptions.OrchestrationError`,
most commonly `MismatchedSignalError` if a supplied advisory signal's
context doesn't match) is caught, logged, and counted, never
propagated, matching every earlier emitter's failure-isolation
convention.

`learning_decision_provider`/`news_signal_provider` are optional
constructor parameters, both defaulting to `None` (meaning: no
advisory input, ever). This is not a placeholder — `arbitrate` already
treats a missing advisory signal as the *ordinary* case
(`SignalInput(considered=False, agrees=False, weight=0.0)`), not a
degraded one, because Milestones 9 and 10 built `memory`/`nlp` as
shadow-mode-only: neither has ever been authorized to influence a real
decision, and this runtime has no `MemoryEmitter`/`NlpEmitter` stage
producing live signals to feed a provider with anyway. A caller that
*does* supply a provider is expected to return `None` for "nothing to
contribute right now"; a provider that raises is caught the same way
an `arbitrate` failure is (logged, treated as no advisory input) — an
advisory source misbehaving must never block the primary decision.

### 2. Every emitter now exposes `handle_frame(frame) -> RuntimeFrame | None`, not an injected callback

`FeatureVectorEmitter.handle_bar`, `RegimeEmitter.handle_frame`,
`StrategyEmitter.handle_frame`, and the new `OrchestrationEmitter.
handle_frame` all lose their `on_frame`/`on_feature_vector`/
`on_regime_state` constructor parameter and instead **return** the
frame they produced (or `None` to mean "stop here"). No emitter holds
a reference to "whatever comes next" anymore.

This is a **deliberate breaking change to Phase B/C/D's internal-only
hooks** — the same class of change ADR-030 already made once
(renaming `on_feature_vector` to `on_frame`), taken to its logical
conclusion: instead of renaming the hook again, remove it. None of
these hooks were ever part of a frozen contract or consumed outside
`app`; every call site was updated in this same PR.

### 3. `app.pipeline.compose_pipeline`: composition in one place, not spread across constructors

```python
def compose_pipeline(
    handle_bar: Callable[[Bar], RuntimeFrame | None],
    *stages: FrameStage,
) -> BarCallback: ...
```

Folds a first-stage `handle_bar` (the only stage that takes a `Bar`
instead of a `RuntimeFrame` — it's the one that builds the first
frame) and any number of `handle_frame` stages into a single
`on_bar`-compatible closure: call `handle_bar`, then each stage in
order, short-circuiting the rest of the chain the moment any stage
returns `None`. `MarketDataLoop.on_bar` is unaffected — it still gets
exactly one `Callable[[Bar], None]`; `compose_pipeline`'s result
satisfies that by discarding whatever the final stage returns, since
nothing downstream of `on_bar` itself needs the frame back.

A stage raising is not caught inside `compose_pipeline` — `MarketDataLoop
._poll_symbol`'s own try/except around calling `on_bar` (established
since Phase A) is the existing safety net for that. Every *expected*
failure mode inside a stage is already caught by that stage itself and
turned into a `None` return, not an exception; anything that does
propagate through `compose_pipeline` is a genuine bug (e.g. a
`RuntimeFrame` reaching a stage without a field it needed — this
should only happen from a wiring mistake in `app.bootstrap`), and
`MarketDataLoop`'s existing `on_bar_callback_failed` log path already
surfaces it.

### 4. `app.bootstrap`: flat composition, not nested delegation

`MarketDataLoop.on_bar` is fixed at construction time (no public
setter). Previously (Phase B-D), each `build_*_loop` called the
*previous* phase's `build_*_loop` and injected its own `on_frame`
callback into the emitter that function had already built — that
pattern breaks once there's no `on_frame` to inject. Each `build_*_loop`
now builds its own emitters directly and composes its own `on_bar`
via `compose_pipeline`, calling `build_market_data_loop` itself rather
than delegating to a shorter-pipeline `build_*_loop`.

To avoid re-deriving "which buffer, which health check" per phase, the
actual construction logic for each stage lives in one small
`_build_*_stage` helper (`_build_feature_stage`, `_build_regime_stage`,
`_build_strategy_stage`), each returning `(emitter, health_checks)`.
`build_feature_loop`/`build_regime_loop`/`build_strategy_loop`/
`build_orchestration_loop` each call the `_build_*_stage` helpers for
every phase up to and including their own, then compose the resulting
`handle_bar`/`handle_frame` callables via `compose_pipeline` and pass
the result as `on_bar` to `build_market_data_loop`. No phase's
construction logic is duplicated; only the *list* of which stages to
include is repeated per function, which is the minimum necessary
consequence of "a later phase can't retroactively add a stage to an
already-built `MarketDataLoop`."

## Consequences

- `ops.metrics.MetricsRegistry` now has a fourth emitter-level
  production consumer.
- Adding Phase F (risk) means writing a `RiskEmitter.handle_frame`
  and a `build_risk_loop` that calls the existing `_build_*_stage`
  helpers plus its own, composing one more stage — no callback
  signature to invent, no existing emitter to modify.
- Trade-off, accepted and disclosed: Phase B/C/D's internal hook APIs
  changed shape again (the `on_frame` parameter is now gone entirely,
  not just renamed). Every test exercising those hooks was rewritten
  in this PR to verify behavior end-to-end (driving `loop._on_bar(bar)`
  and asserting on a later stage's recorded metrics) rather than
  comparing callable identity, which is no longer meaningful once
  composition produces an opaque closure.
- Trade-off, accepted: verifying "is stage X wired to stage Y" in
  `tests/app/test_bootstrap.py` now requires actually invoking the
  composed `on_bar` (via the private `loop._on_bar` attribute, the
  same attribute Phase A/B's own tests already reached into) rather
  than a same-line identity assertion. This is arguably a better test
  than the one it replaced — it verifies real behavior, not just
  structural wiring — but it does mean `_FakeRegimeService` in that
  test file now needs a working `infer()`, not just an `n_states`
  attribute.
- There is still no `MemoryEmitter`/`NlpEmitter` stage in this runtime,
  and none is planned — `memory`/`nlp` remain queried (optionally) by
  `OrchestrationEmitter` itself, exactly as designed.
- `app.bootstrap.__version__`/`app.__version__` bumped `0.4.0` ->
  `0.5.0`.

## Alternatives Considered

- **Add a `MemoryEmitter`/`NlpEmitter` stage to the sequential pipeline,
  each producing a `LearningDecision`/`NewsSignal` per bar** —
  rejected per direct instruction: `memory`/`nlp` are advisory inputs
  *to* arbitration, not additional pipeline stages in their own right;
  treating them as sequential stages would also require them to
  produce a signal for every single bar, which doesn't match how
  either package is actually used (batch/shadow evaluation, not a
  per-tick call).
- **Keep renaming the "next stage" callback instead of removing it**
  (e.g. `on_final_decision` on `OrchestrationEmitter` for a
  hypothetical Phase F) — rejected per direct instruction: the
  callback-per-emitter pattern was exactly what was to be stopped:
  each new phase would otherwise keep adding one more differently-named
  parameter that does the same job `compose_pipeline` now does once,
  in one place.
- **Keep `build_*_loop` delegating to the previous phase's function
  and mutate `MarketDataLoop.on_bar` after construction** — rejected:
  `MarketDataLoop` has no public setter for `on_bar` by design (Phase
  A froze that construction-time-only shape), and adding one just to
  support later phases would be a Phase A behavior change for a Phase
  E convenience.
- **Give `compose_pipeline` its own try/except per stage** — rejected:
  `MarketDataLoop._poll_symbol`'s existing wrapper around `on_bar`
  already provides that safety net; a second one inside
  `compose_pipeline` would be redundant and would obscure which layer
  actually caught a given failure.
