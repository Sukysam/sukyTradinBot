# ADR-028: Runtime Feature Pipeline Design (Phase B)

**Status**: Accepted
**Date**: 2026-07-16
**Milestone**: Post-`v2.0.0` continuous evolution — Trading Validation / Runtime, Phase B

## Context

Phase A (ADR-027) proved the runtime can continuously fetch and log
bars via `app.runtime.MarketDataLoop`. Per direct instruction, Phase B
stays intentionally narrow: wire `MarketDataLoop` to
`features.pipeline.FeaturePipeline` so the runtime produces valid
`FeatureVector` objects from live market data — nothing beyond that.
No HMM, no strategy, no execution.

The instruction specified a structure (`MarketDataLoop -> Bar Buffer ->
FeaturePipeline -> FeatureVector -> Structured Logging`) and required
every emitted `FeatureVector` to log symbol, timestamp, pipeline
version, feature count, and computation latency. It also asked that
the runtime survive reconnects/transient failures, expose health
metrics, and run for an extended period without memory growth —
success criteria this design addresses directly (see Decisions 1 and
3 below).

## Decision

### 1. `app.buffer.BarBuffer`: bounded per-symbol history via `deque(maxlen=N)`

Sized at `200` bars per symbol by default (`FeatureLoopConfig.
max_bars_per_symbol`) — comfortably above `100`, the largest lookback
among this codebase's registered features (`features/statistical.py`).
A `deque(maxlen=N)` per symbol makes the "no memory growth over an
extended run" requirement structural rather than something downstream
code has to remember to enforce: the buffer cannot grow past `N * len(
symbols)` bars no matter how long the process stays up.

### 2. `MarketDataLoop` gains an `on_bar: BarCallback | None` hook

`BarCallback = Callable[[Bar], None]` — deliberately synchronous,
unlike `market_data.interfaces.BarHandler` (`Callable[[Bar],
Awaitable[None]]`, used by `AlpacaStreamingProvider`'s async streaming
context). `_poll_symbol` is itself synchronous, and Phase B's
consumer (`FeatureVectorEmitter.handle_bar`) does synchronous,
CPU-bound work with no I/O — an async callback type would add
event-loop plumbing this phase doesn't need. The hook is called once
per newly-seen bar, after it's logged. A callback failure is caught
and logged (`on_bar_callback_failed`), never propagated — one
symbol's downstream feature computation failing must not stop
`MarketDataLoop` from polling every other symbol, the same isolation
`_poll_symbol`'s own fetch-failure handling already provides. This is
purely additive to `MarketDataLoop`'s existing constructor (default
`None`); every Phase A test and call site is unaffected.

### 3. `app.features_loop.FeatureVectorEmitter`: buffer + pipeline + metrics + logging

`handle_bar(bar)` is the whole surface: append to `BarBuffer`, call
`FeaturePipeline.compute(bars, symbol, strict=False)` on whatever
history exists so far (even a single bar — `compute`'s own `strict`
tolerance for partial warm-up, expressed via `FeatureVector.
quality_flags`, means there's no need to invent a second "enough
history yet?" concept on top of the one the pipeline already has), log
one `feature_vector_computed` structured event per success with
exactly the fields requested (symbol, timestamp, `PIPELINE_VERSION`,
`len(feature_names)`, measured latency), and record two metrics on an
injected `ops.metrics.MetricsRegistry`: a `feature_vectors_emitted_
total` counter and a `feature_pipeline_latency_seconds` gauge — this
is `ops.metrics`'s first real consumer beyond its own tests, directly
satisfying the "expose health metrics" success criterion. A
computation failure (`features.errors.FeatureError`) is caught,
logged (`feature_computation_failed`), and increments a
`feature_computation_errors_total` counter rather than propagating —
matching `MarketDataLoop`'s own "one bad tick doesn't kill the
process" convention at this layer too.

`on_feature_vector`, an optional callback, is this class's own
extension point for Phase C (regime inference) — the same "each phase
exposes one clean hook for the next" shape `MarketDataLoop.on_bar`
established. Its failures are caught and logged
(`on_feature_vector_callback_failed`), never propagated, for the same
containment reason.

### 4. `app.bootstrap.build_market_data_loop` extended, not rewritten

Gains two additive, optional parameters: `on_bar` and `extra_checks:
Sequence[HealthCheck]` — both default to values that reproduce Phase
A's exact prior behavior. `build_feature_loop` is a new function that
builds a `FeatureVectorEmitter` first, then calls `build_market_data_
loop` with `on_bar=emitter.handle_bar` and `extra_checks=
[feature_registry_check(...)]`, returning `(loop, runtime_context,
emitter)`. No composition logic is duplicated between the two
functions — exactly the "extending, not rewriting" `app.bootstrap`
ADR-027's own Consequences section predicted. `feature_registry_check`
(one of the nine `ops.checks` factories Phase A explicitly excluded as
premature) is now included, since Phase B is the first code path that
actually touches `features.registry.DEFAULT_REGISTRY`.

### 5. `app.main` runs the Phase B pipeline

`_run()` now calls `build_feature_loop` instead of `build_market_data_
loop` — as of Phase B, "the runtime" means market data plus feature
computation, not market data alone. `build_market_data_loop` itself
remains intact, tested, and available for direct use (by tests, or by
any future caller that genuinely wants Phase A behavior in isolation).

## Consequences

- `ops.metrics.MetricsRegistry` now has a genuine production consumer,
  closing another piece of the "wiring not yet authorized" gap M12's
  ADRs flagged as future work — the same gap ADR-027 began closing for
  `ops.checks`/`ops.startup`.
- Adding Phase C (regime inference) means extending `app.bootstrap`
  further (a new `build_regime_loop` composing `build_feature_loop`)
  and wiring `on_feature_vector`, not rewriting `app.runtime` or
  `app.features_loop` — the same "extend, don't rewrite" shape this
  phase itself followed from Phase A.
- Trade-off, accepted: `FeaturePipeline.compute(strict=False)` is
  called on every new bar regardless of how little history exists yet
  — early vectors will have most or all features flagged in `quality_
  flags`. This is intentional (see Decision 3) rather than an
  oversight: a consumer that cares about warm-up state reads `quality_
  flags`/`has_any_flag` off the emitted vector, the same contract
  `FeaturePipeline.compute` already defines.
- Trade-off, accepted: `FeatureVectorEmitter`'s real-pipeline
  computation path is exercised with the actual `DEFAULT_REGISTRY` in
  tests (fast, deterministic, no network) rather than a fake pipeline
  for the success path — only the failure path injects a fake, since
  the real pipeline has no built-in way to fail on valid, non-empty
  bar input. This intentionally re-uses `features`'s own correctness
  guarantees rather than re-testing them.

## Alternatives Considered

- **Reuse `market_data.interfaces.BarHandler` (async) for `MarketDataLoop
  .on_bar`** — rejected: that type exists for `AlpacaStreamingProvider`'s
  async streaming context. Phase B's callback does synchronous,
  CPU-bound work; making it async would require `_poll_symbol` to
  become async (or scheduling a task per bar) for no benefit, adding
  event-loop complexity this phase doesn't need.
- **Wrap `MarketDataLoop` from outside instead of adding an `on_bar`
  hook** — rejected: `_poll_symbol` is private, so there is no way to
  observe new bars from outside `MarketDataLoop` without either
  duplicating its polling/dedup logic or modifying the class. A
  strictly additive, optional constructor parameter is the smaller
  change and matches ADR-027's own prediction.
- **Require a minimum bar count before attempting `FeaturePipeline
  .compute`** — rejected: `compute`'s own `strict=False` tolerance for
  partial warm-up already communicates readiness via `quality_flags`;
  adding a second, redundant warm-up threshold in `app` would be an
  unnecessary duplicate concept.
- **Give `FeatureVectorEmitter` a `Clock` dependency for its own
  timestamps** — rejected: `FeaturePipeline` already stamps each
  vector's `provenance.generated_at`, and structured logging uses the
  bar's own `timestamp`; a second clock in `app.features_loop` would
  have no use it isn't already served by.
