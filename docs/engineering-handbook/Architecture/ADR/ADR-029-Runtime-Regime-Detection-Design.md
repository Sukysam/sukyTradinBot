# ADR-029: Runtime Regime Detection Design (Phase C)

**Status**: Accepted
**Date**: 2026-07-16
**Milestone**: Post-`v2.0.0` continuous evolution — Trading Validation / Runtime, Phase C

## Context

Phase B (ADR-028) proved the runtime can continuously turn live bars
into `FeatureVector`s. Per direct instruction, Phase C stays
intentionally narrow: wire `FeaturePipeline`'s output to
`hmm.service.RegimeService` so the runtime performs causal regime
inference on each update and emits a regime call — nothing beyond
that. The instruction's own runtime flow diagram:

```
Market Data -> BarBuffer -> FeaturePipeline -> FeatureVector
    -> RegimeService -> RegimePrediction
```

Explicitly out of scope for this phase: Strategy Engine, Memory Loop,
NLP, Signal Orchestration, Risk, Execution — those remain later
phases (D onward).

The instruction also specified a structural convention going forward:
a dedicated runtime component per phase — `RegimeEmitter` here —
whose responsibility is exactly one frozen contract in, exactly one
new object out (`FeatureVector -> RegimeService -> RegimeState`),
mirroring `FeatureVectorEmitter`'s own shape from Phase B. "Avoid
calling the HMM directly from the emitter" is satisfied by
construction: `RegimeEmitter` only ever calls `hmm.service.
RegimeService.infer`, the one sanctioned entry point `hmm/__init__.py`
documents — it never touches `hmmlearn.hmm.GaussianHMM`, a raw feature
matrix, or a `Normalizer` directly, all of which stay fully contained
inside the `hmm` package per ADR-006/ADR-007.

Milestone 4 froze `RegimeState` (not "RegimePrediction" or
"RegimeSnapshot") as the actual output contract — this ADR reuses
that existing, binding type rather than inventing a parallel one; the
instruction's diagram names were describing the concept, not
prescribing a new contract.

## Decision

### 1. `app.buffer.FeatureVectorBuffer`: a second, separate bounded buffer

Structurally identical to `BarBuffer` (`deque(maxlen=...)` per symbol)
but typed to `FeatureVector` and sized at `200` by default — the same
value as `features_loop.DEFAULT_MAX_BARS`, comfortably above the
largest feature lookback (100 bars), so a full buffer eventually
evicts every NaN-flagged, still-warming-up vector. Kept as a second
class rather than generalizing `BarBuffer` into `SymbolBuffer[T]`: the
duplication is a handful of lines, and generalizing now would mean
touching Phase B's already-shipped, tested `BarBuffer` for a saving
that isn't worth the churn — the same reasoning this handbook has
applied to other small, deliberate duplications (e.g.
`current_git_commit` between `app.bootstrap` and `backtest.engine`).

### 2. `app.regime_loop.RegimeEmitter`: buffer + `RegimeService.infer` + metrics + logging

`handle_feature_vector(vector)` is the whole surface: append to
`FeatureVectorBuffer`, call `RegimeService.infer(history)` on
whatever history exists so far, log one `regime_state_emitted`
structured event per success with exactly the fields the instruction
asked for (symbol, timestamp, regime_id, confidence,
transition_probability, model_version, latency), and record two
metrics on an injected `ops.metrics.MetricsRegistry`:
`regime_states_emitted_total` (counter) and
`regime_inference_latency_seconds` (gauge) — satisfying "expose
regime metrics" and "log inference latency" directly, the same
pattern `FeatureVectorEmitter` established for `ops.metrics`'s first
real consumer.

A failure (`hmm.exceptions.HMMError`, most commonly `InsufficientDataError`
while the buffer still contains NaN-flagged warm-up vectors) is
caught, logged (`regime_inference_failed`), and counted
(`regime_inference_errors_total`), never propagated — this
self-heals automatically once the buffer's bounded eviction ages out
every unclean vector, with no separate warm-up-tracking concept
needed, the same reasoning `FeatureVectorEmitter` already applies one
layer down. This directly satisfies "survive reconnects without
corrupting state": a reconnect only affects the underlying provider;
the buffers and their eviction behavior are unaffected and keep
accumulating exactly as before.

`on_regime_state`, optional, is this class's own extension point for
Phase D (strategy) — the same "each phase exposes one clean hook for
the next" shape `MarketDataLoop.on_bar`/`FeatureVectorEmitter.
on_feature_vector` already established.

### 3. `build_market_data_loop`/`build_feature_loop` extended again, not rewritten

`build_feature_loop` gains two additive, optional parameters —
`on_feature_vector` and `extra_checks` — mirroring exactly how
`build_market_data_loop` itself gained `on_bar`/`extra_checks` in
Phase B. `build_regime_loop` builds a `RegimeEmitter` first, then
calls `build_feature_loop` with `on_feature_vector=regime_emitter.
handle_feature_vector` and `extra_checks=[hmm_model_check(...)]`,
returning `(loop, runtime_context, feature_emitter, regime_emitter)`.
No composition logic is duplicated across any of the three bootstrap
functions — the same "extending, not rewriting" shape every phase in
this runtime has followed since ADR-027.

### 4. `regime_service: RegimeService` is a required, injected parameter — no default construction

Unlike `provider`, which defaults to a real `AlpacaHistoricalProvider`
that works given real Alpaca credentials, `build_regime_loop` has no
equivalent default. This project has no trained, persisted HMM model
artifact anywhere yet — `hmm.persistence.load(base_dir, symbol,
model_version)` needs one on disk, and none has ever been produced
against real historical data in this repository's history. Training
one is a legitimate, separate concern (feeding real historical
`FeatureVector`s through `RegimeService.train(...)` and `.save(...)`)
that Phase C's explicit "stop there" scope does not include. Rather
than invent a default-loading path that would fail for every caller
today, `build_regime_loop` requires the caller to supply an
already-trained-or-loaded `RegimeService` directly — an honest
reflection of what this platform can actually do right now, matching
this project's standing preference for disclosed gaps over invented
defaults.

The `hmm_model_check` health check's probe (`lambda: regime_service.
n_states > 0`) is a structural sanity check on the already-constructed
service, not a "does a model exist" check — by the time
`build_regime_loop` runs, the caller has already proven a model
exists by successfully constructing `regime_service`.

### 5. `app.main` is not updated to run Phase C

`python -m app` continues to run the Phase B pipeline
(`build_feature_loop`). Wiring Phase C into the default entrypoint
would require solving "where does a real trained model come from at
process startup" — exactly the gap Decision 4 disclosed as out of
scope. `build_regime_loop` is fully implemented, tested, and available
for a caller (a script, a future phase, or a human at a REPL) that
has already trained or loaded a real `RegimeService`.

## Consequences

- `ops.checks.hmm_model_check` (one of Milestone 12's ten factories,
  unused until now) has its first real consumer, closing another
  piece of the "wiring not yet authorized" gap.
- Adding Phase D (strategy) means extending `app.bootstrap` with a
  `build_strategy_loop` composing `build_regime_loop` and wiring
  `on_regime_state`, not rewriting `app.runtime`, `app.features_loop`,
  or `app.regime_loop` — the same shape every phase before this one
  has followed.
- Trade-off, accepted (and prominently disclosed): `app.main` does not
  run Phase C. The runtime's regime-inference capability exists,
  is tested, and is composable, but is not yet "the thing `python -m
  app` does by default" — that requires a trained model artifact this
  project doesn't have. A future increment (training a real model
  against real historical data and establishing a persistence
  location/convention) is a prerequisite for wiring Phase C into
  `app.main`, and is explicitly not assumed or built speculatively
  here.
- Trade-off, accepted: `RegimeEmitter`'s real-inference success path is
  tested against a genuinely trained `RegimeService` (via `RegimeService
  .train(...)` with a fast config — the same pattern `tests/hmm/
  test_service.py` already established), not a fake — only the failure
  path injects a fake service, since a well-formed trained service has
  no simple way to fail on the valid history it accepts.
- `app.bootstrap.__version__`/`app.__version__` bumped `0.2.0` ->
  `0.3.0`.

## Alternatives Considered

- **Call `hmm.inference.forward_algorithm` or a raw `GaussianHMM`
  directly from `RegimeEmitter`** — rejected per direct instruction and
  ADR-006/ADR-007's own boundary: `RegimeService.infer` is the one
  sanctioned entry point outside `hmm`; bypassing it would mean
  `RegimeEmitter` re-implementing the normalization/contract-validation
  logic `RegimeService` already owns.
- **Introduce a new `RegimePrediction`/`RegimeSnapshot` type** —
  rejected: `hmm.models.RegimeState` is already the frozen, binding
  contract `RegimeService.infer` returns (ADR-006). Inventing a
  second, parallel type for the same concept would fork the contract
  for no reason.
- **Default `build_regime_loop`'s `regime_service` to `RegimeService.
  load(some_default_path, ...)`** — rejected: no model has ever been
  trained and saved anywhere in this project, so any default path
  would be pure fiction today. A required, injected parameter is
  honest about what currently exists; a defaulted one would silently
  fail for every caller until an unrelated, unbuilt training pipeline
  exists.
- **Generalize `BarBuffer` into a generic `SymbolBuffer[T]` reused by
  both Phase B and Phase C** — rejected: touching Phase B's shipped,
  tested `BarBuffer` for a small generalization isn't worth the churn;
  a second near-identical class is the smaller, safer change.
- **Wire Phase C into `app.main` with a placeholder/dummy trained
  model** — rejected: a `python -m app` that silently runs regime
  inference against a fake or trivially-trained model would look
  operational while being meaningless, worse than the honest gap of
  not running Phase C by default at all.
