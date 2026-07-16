# Changelog

Historical record of what shipped in each tagged version. Never rewritten
after the fact — if a past decision turns out to have been wrong, that's a
new entry (and often a new ADR), not an edit to this one. For where the
project is *headed*, see [PROJECT_STATUS.md](PROJECT_STATUS.md); for *why*
a past decision was made, see
[docs/engineering-handbook/Architecture/ADR/](docs/engineering-handbook/Architecture/ADR/).

Format loosely follows [Keep a Changelog](https://keepachangelog.com/):
each tagged version gets Added / Changed / Known limitations sections.
Versions are tagged per milestone (`vN-<milestone-name>`), not per
semantic-versioning release — this project doesn't ship releases in the
traditional sense yet.

As of 2026-07-13, a second, coarser tag layer also exists —
**umbrella releases** (`v1.0-alpha`, `v1.1-beta`, ...) grouping several
milestone tags for external communication. `v1.0-alpha` points at the
same commit as `v0.7-execution-layer`; it introduces no code of its own
and has no entry below. See [PROJECT_STATUS.md](PROJECT_STATUS.md)'s
"Release Milestones" section for the full grouping and what each
umbrella tag actually points at.

## Unreleased - Runtime Phase F: Risk Management (2026-07-16, no tag)

Sixth of seven post-`v2.0.0` runtime phases. Wires `FinalDecision`s to
`RiskService.decide` so the runtime sizes/approves the arbitrated
decision against live portfolio/account state and emits an
`ExecutionDecision` -- nothing beyond that (no broker calls, no order
submission; the runtime remains completely paper-safe). Design and
implementation recorded together in ADR-032, which also resolves a gap
`orchestration/__init__.py`'s own module docstring explicitly flagged
during Milestone 11 as "not authorized by this milestone": wiring
`FinalDecision` into `risk.RiskService`.

### Added
- `app.risk_loop.RiskEmitter` -- `handle_frame(frame)` bridges
  `FinalDecision` into `RiskService.decide`'s `StrategyDecision`-shaped
  input (`_effective_strategy_decision`: `dataclasses.replace(
  strategy_decision, allocation=final_decision.final_allocation,
  confidence=final_decision.confidence, reasoning=final_decision
  .rationale)`), calls `RiskService.decide(effective_decision,
  portfolio, account)`, logs one `execution_decision_emitted` event
  per success (symbol, timestamp, approved, approved_allocation,
  decision_type, latency), and records `ops.metrics.MetricsRegistry`'s
  fifth real production metrics (`execution_decisions_emitted_total`
  counter, `execution_decision_latency_seconds` gauge,
  `execution_decision_errors_total` counter). A failure
  (`risk.exceptions.RiskError`) is caught and logged
  (`execution_decision_failed`), never propagated.
- `portfolio_state_provider`/`account_state_provider` -- required
  constructor parameters (no default), called fresh on every
  `handle_frame` since portfolio/account state is live and changes
  with every trade. A provider that raises is caught, logged with a
  specific event (`portfolio_state_provider_failed`/
  `account_state_provider_failed`), and the frame is dropped rather
  than proceeding with fabricated state.
- `app.frame.RuntimeFrame` gains an `execution_decision:
  ExecutionDecision | None` field, `with_execution_decision`, and the
  enrichment-order invariant extended (`execution_decision` requires
  `final_decision`).
- `app.frame.RuntimeFrame.require_feature_vector`/
  `require_regime_state`/`require_strategy_decision`/
  `require_final_decision`/`require_execution_decision` -- fully typed
  accessors (return the concrete type, not `Any`) that raise the same
  `ValueError` shape a caller previously had to write inline.
  `RegimeEmitter`, `StrategyEmitter`, and `OrchestrationEmitter`
  (already merged) are retrofitted to use these instead of repeating
  their own `if frame.x is None: raise` checks; `RiskEmitter` uses
  them from the start.
- `app.bootstrap.build_risk_loop` -- Phase F's composition root: the
  full A-F pipeline composed via `compose_pipeline`. `risk_service`
  defaults to `RiskService.default()` if not given -- a deliberate
  contrast with `regime_service`/`strategy_registry`'s "no default"
  reasoning, since a sensible default risk pipeline needs no trained
  model or per-model domain mapping to be meaningful.
- 28 new tests across `tests/app/` (`test_risk_loop.py`, plus
  `require_*`/`execution_decision` coverage in `test_frame.py` and
  `build_risk_loop` tests in `test_bootstrap.py`), bringing
  `tests/app/` to 134 total (up from 106).

### Changed
- `app.__version__` bumped `0.5.0` -> `0.6.0`; `app.bootstrap.
  __version__` likewise bumped `0.5.0` -> `0.6.0`.
- Nothing in Phase A-E's tested public behavior changed beyond the
  `require_*` retrofit, which preserves the exact same raised
  `ValueError` message substrings every existing test already matched
  against.

### Known limitations
- `app.frame`/`app.risk_loop`/`app.pipeline`/`app.orchestration_loop`/
  `app.strategy_loop`/`app.regime_loop`/`app.features_loop`/
  `app.buffer`/`app.config`/`app.runtime`/`app.__init__`/
  `app.exceptions` are at 100% test coverage; `app.bootstrap` is at
  98% (same one disclosed real-provider-construction line as Phase
  A-E); `app.main` is at 43% (same disclosed signal-handling gap).
- `app.main` is *not* updated to run Phase F, for the same reason
  Phase C/D/E weren't wired in: no trained `RegimeService` or
  deliberately-configured `StrategyRegistry` exists to default to
  (Phase F adds no new blocker of its own -- `portfolio_state_provider`/
  `account_state_provider` are a `python -m app` configuration
  question for whichever phase eventually wires broker/account access
  in, not a reason on their own).
- Phase G (paper execution) is not yet started. No code path in this
  runtime touches a broker or submits an order.

## Unreleased - Runtime Phase E: Signal Orchestration (2026-07-16, no tag)

Fifth of seven post-`v2.0.0` runtime phases. Wires `StrategyDecision`s
to `orchestration.arbitration.arbitrate` so the runtime arbitrates the
primary strategy call against optional advisory `LearningDecision`/
`NewsSignal` input and emits a `FinalDecision` -- nothing beyond that
(no risk, no execution). Design and implementation recorded together
in ADR-031, which also applies an architectural correction to every
emitter built since Phase B: the `on_frame`/`on_feature_vector`/
`on_regime_state` callback parameter is removed entirely, in favor of
each `handle_bar`/`handle_frame` returning the enriched `RuntimeFrame`
(or `None` to stop) directly.

### Added
- `app.orchestration_loop.OrchestrationEmitter` -- `handle_frame(frame)`
  calls `arbitrate(frame.strategy_decision, learning_decision,
  news_signal, config=..., policy=...)` (default policy:
  `SafetyFirstPolicy`), logs one `final_decision_emitted` event per
  success (symbol, timestamp, outcome, primary_allocation,
  final_allocation, confidence, latency), and records `ops.metrics
  .MetricsRegistry`'s fourth real production metrics
  (`final_decisions_emitted_total` counter, `final_decision_latency_
  seconds` gauge, `final_decision_errors_total` counter). A failure
  (`orchestration.exceptions.OrchestrationError`) is caught and logged
  (`final_decision_failed`), never propagated. Optional
  `learning_decision_provider`/`news_signal_provider` default to
  `None` -- there is deliberately no `MemoryEmitter`/`NlpEmitter`
  pipeline stage; `memory`/`nlp` remain shadow-mode-only (Milestones
  9/10), and `arbitrate` already treats a missing advisory signal as
  the ordinary case. A provider that raises is caught and treated as
  "no advisory input", never blocking the primary decision.
- `app.frame.RuntimeFrame` gains a `final_decision: FinalDecision |
  None` field and `with_final_decision`, with the same enrichment-order
  invariant extended (`final_decision` requires `strategy_decision`).
- `app.pipeline.compose_pipeline(handle_bar, *stages) -> BarCallback`
  -- folds a first-stage `handle_bar` and any number of `handle_frame`
  stages into one `on_bar`-compatible callable, short-circuiting the
  moment any stage returns `None`. `MarketDataLoop.on_bar` itself is
  unaffected; the composed callable satisfies its `Callable[[Bar],
  None]` type by discarding whatever the final stage returns.
- `app.bootstrap.build_orchestration_loop` -- Phase E's composition
  root: the full A-E pipeline composed via `compose_pipeline`. Reuses
  `regime_service`/`strategy_registry` injection exactly as Phase D
  required them (no new gap introduced).
- 21 new tests across `tests/app/` (`test_pipeline.py`,
  `test_orchestration_loop.py`, plus rewritten wiring tests in
  `test_features_loop.py`/`test_regime_loop.py`/`test_strategy_loop.py`/
  `test_bootstrap.py`/`test_frame.py`), bringing `tests/app/` to 106
  total (up from 88).

### Changed
- **Breaking change to every emitter's internal-only hooks** (never
  part of any frozen contract): `FeatureVectorEmitter`/`RegimeEmitter`/
  `StrategyEmitter` all lose their `on_frame` constructor parameter;
  `handle_bar`/`handle_frame` now return `RuntimeFrame | None` instead
  of invoking a callback. `app.bootstrap` correspondingly moved from
  nested delegation (each phase injecting a callback into the previous
  phase's builder) to flat composition: `_build_feature_stage`/
  `_build_regime_stage`/`_build_strategy_stage` helpers each return
  `(emitter, health_checks)`; every `build_*_loop` composes its own
  full stage list directly against `build_market_data_loop` via
  `compose_pipeline`, since `MarketDataLoop.on_bar` has no public
  setter and can't be extended after construction.
- `app.__version__` bumped `0.4.0` -> `0.5.0`; `app.bootstrap.
  __version__` likewise bumped `0.4.0` -> `0.5.0`.

### Known limitations
- `app.frame`/`app.pipeline`/`app.orchestration_loop`/
  `app.strategy_loop`/`app.buffer`/`app.regime_loop`/
  `app.features_loop`/`app.config`/`app.runtime`/`app.__init__`/
  `app.exceptions` are at 100% test coverage; `app.bootstrap` is at
  98% (same one disclosed real-provider-construction line as Phase
  A-D); `app.main` is at 43% (same disclosed signal-handling gap).
- `app.main` is *not* updated to run Phase E, for the same reason
  Phase C/D weren't wired in: no trained `RegimeService` or
  deliberately-configured `StrategyRegistry` exists to default to.
- Phases F through G (risk, paper execution) are not yet started.

## Unreleased - Runtime Phase D: Strategy Engine (2026-07-16, no tag)

Fourth of seven post-`v2.0.0` runtime phases. Wires `RegimeState`s to
`strategy.service.StrategyService` so the runtime dispatches a regime
call to a registered strategy and emits a `StrategyDecision` --
nothing beyond that (no risk, no execution, no signal orchestration).
Design and implementation recorded together in ADR-030, which also
introduces `app.frame.RuntimeFrame` -- internal plumbing (not a frozen
contract) that carries `bar -> feature_vector -> regime_state ->
strategy_decision` through the pipeline, replacing the earlier
per-phase callback payloads because `StrategyService.decide` needs a
`FeatureVector` and its derived `RegimeState` together, which the
prior wiring had no way to carry.

### Added
- `app.frame.RuntimeFrame` -- a frozen dataclass enriched strictly in
  order by each emitter (`with_feature_vector`/`with_regime_state`/
  `with_strategy_decision`, each returning a new frame). `__post_init__`
  enforces enrichment order as an invariant.
- `app.strategy_loop.StrategyEmitter` -- `handle_frame(frame)` calls
  `StrategyService.decide(frame.feature_vector, frame.regime_state)`
  (raising `ValueError` if either is missing -- an `app`-internal
  wiring bug), logs one `strategy_decision_emitted` event per success
  (symbol, timestamp, strategy_id, regime_id, allocation, confidence,
  latency), and records `ops.metrics.MetricsRegistry`'s third real
  production metrics (`strategy_decisions_emitted_total` counter,
  `strategy_decision_latency_seconds` gauge,
  `strategy_decision_errors_total` counter). A failure
  (`strategy.exceptions.StrategyError`) is caught and logged
  (`strategy_decision_failed`), never propagated. Holds no buffer --
  `decide` needs no rolling history. Exposes an optional `on_frame`
  hook for the next phase (Phase E: signal orchestration).
- `app.bootstrap.build_strategy_loop` -- Phase D's composition root:
  builds a `StrategyEmitter`, then delegates to `build_regime_loop`
  with `on_frame=strategy_emitter.handle_frame` and
  `extra_checks=[strategy_registry_check(...)]`. Returns `(loop,
  runtime_context, feature_emitter, regime_emitter, strategy_emitter)`.
  **`strategy_registry: StrategyRegistry` is a required, injected
  parameter alongside `regime_service` -- no default, since which
  `regime_id`s map to which strategy style is inherently tied to a
  specific trained model's regime semantics nobody has defined yet.**
  `StrategyService` itself is built internally from the injected
  registry (cheap -- no training/persistence, unlike `RegimeService`).
- 21 new tests across `tests/app/` (`test_frame.py`,
  `test_strategy_loop.py`, plus additions to `test_bootstrap.py`),
  bringing `tests/app/` to 88 total (up from 67).

### Changed
- **Breaking change to Phase B/C's internal-only hooks** (never part
  of any frozen contract): `FeatureVectorEmitter.on_feature_vector` ->
  `on_frame` (now takes a `RuntimeFrame`, not a bare `FeatureVector`);
  `RegimeEmitter.handle_feature_vector`/`on_regime_state` ->
  `handle_frame`/`on_frame`. `build_feature_loop`'s `on_feature_vector`
  parameter renamed to `on_frame`; `build_regime_loop` gained the same
  additive `on_frame`/`extra_checks` parameters `build_feature_loop`
  already had.
- `app.__version__` bumped `0.3.0` -> `0.4.0`; `app.bootstrap.
  __version__` likewise bumped `0.3.0` -> `0.4.0`.

### Known limitations
- `app.frame`/`app.strategy_loop`/`app.buffer`/`app.regime_loop`/
  `app.features_loop`/`app.config`/`app.runtime`/`app.__init__`/
  `app.exceptions` are at 100% test coverage; `app.bootstrap` is at
  97% (same one disclosed real-provider-construction line as Phase
  A/B/C); `app.main` is at 43% (same disclosed signal-handling gap).
- **`app.main` is *not* updated to run Phase D**, for the same reason
  Phase C wasn't wired in (ADR-029): it would require a real, trained
  `RegimeService` *and* a real, deliberately-configured
  `StrategyRegistry` at process startup, neither of which exists yet.
- Phases E through G (signal orchestration, risk, paper execution) are
  not yet started.

## Unreleased - Runtime Phase C: Regime Detection (2026-07-16, no tag)

Third of seven post-`v2.0.0` runtime phases. Wires `FeatureVector`s to
`hmm.service.RegimeService` so the runtime performs causal regime
inference on each update and emits a `RegimeState` -- nothing beyond
that (no strategy, no memory, no NLP, no orchestration, no risk, no
execution). Design and implementation recorded together in ADR-029,
extending Phase B's `app.bootstrap`/`app.features_loop` rather than
rewriting either.

### Added
- `app.buffer.FeatureVectorBuffer` -- a second bounded per-symbol
  buffer (`deque(maxlen=200)`), structurally identical to `BarBuffer`
  but typed to `FeatureVector`; kept as a separate class rather than
  generalizing `BarBuffer` to avoid touching Phase B's shipped code.
- `app.regime_loop.RegimeEmitter` -- `handle_feature_vector(vector)`
  appends to a `FeatureVectorBuffer`, calls `RegimeService.infer` (the
  one sanctioned entry point into `hmm` -- never a raw `GaussianHMM`),
  logs one `regime_state_emitted` event per success (symbol, timestamp,
  regime_id, confidence, transition_probability, model_version,
  latency), and records `ops.metrics.MetricsRegistry`'s second real
  production consumer (`regime_states_emitted_total` counter,
  `regime_inference_latency_seconds` gauge,
  `regime_inference_errors_total` counter). An inference failure
  (typically `InsufficientDataError` while warm-up-flagged vectors
  remain in the buffer) is caught and logged
  (`regime_inference_failed`), never propagated -- self-heals once the
  buffer's bounded eviction ages those vectors out. Exposes an optional
  `on_regime_state` hook for the next phase (Phase D: strategy).
- `app.config.RegimeLoopConfig` -- composes `FeatureLoopConfig` plus
  `max_feature_vectors_per_symbol` (default `200`).
- `app.bootstrap.build_feature_loop` gains two additive, optional
  parameters -- `on_feature_vector` and `extra_checks` -- mirroring
  Phase B's own `on_bar`/`extra_checks` on `build_market_data_loop`.
- `app.bootstrap.build_regime_loop` -- Phase C's composition root:
  builds a `RegimeEmitter`, then delegates to `build_feature_loop`
  with `on_feature_vector=regime_emitter.handle_feature_vector` and
  `extra_checks=[hmm_model_check(...)]`. Returns `(loop,
  runtime_context, feature_emitter, regime_emitter)`. **`regime_service:
  RegimeService` is a required, injected parameter -- unlike
  `provider`, there is no default construction, since this project has
  no trained/persisted HMM model artifact anywhere yet.**
- 24 new tests across `tests/app/` (`test_regime_loop.py`, plus
  additions to `test_buffer.py`, `test_bootstrap.py`,
  `test_config.py`), bringing `tests/app/` to 67 total (up from 43).
  The regime-emitter success path uses a real, cheaply-trained
  `RegimeService` (same pattern as `tests/hmm/test_service.py`), not a
  fake.

### Changed
- `app.__version__` bumped `0.2.0` -> `0.3.0`; `app.bootstrap.
  __version__` likewise bumped `0.2.0` -> `0.3.0`.
- Nothing in Phase A/B's tested public behavior changed -- every new
  parameter on `build_market_data_loop`/`build_feature_loop` is
  optional and defaults to the prior behavior exactly.

### Known limitations
- `app.buffer`/`app.regime_loop`/`app.features_loop`/`app.config`/
  `app.runtime`/`app.__init__`/`app.exceptions` are at 100% test
  coverage; `app.bootstrap` is at 97% (same one disclosed
  real-provider-construction line as Phase A/B); `app.main` is at 43%
  (same disclosed signal-handling gap as Phase A/B).
- **`app.main` is *not* updated to run Phase C.** Wiring it in would
  require a real, trained, persisted `RegimeService` at process
  startup -- this project has never trained and saved a model against
  real historical data, and building that training/persistence
  pipeline is explicitly out of Phase C's scope. `build_regime_loop`
  is fully implemented and tested, ready for a caller that supplies
  its own `RegimeService`.
- Phases D through G (strategy, signal orchestration, risk, paper
  execution) are not yet started.

## Unreleased - Runtime Phase B: Feature Pipeline (2026-07-16, no tag)

Second of seven post-`v2.0.0` runtime phases. Wires `MarketDataLoop` to
`FeaturePipeline` so the runtime produces valid `FeatureVector` objects
from live market data -- nothing beyond that (no HMM, no strategy, no
execution). Design and implementation recorded together in ADR-028,
extending Phase A's `app.bootstrap`/`app.runtime` rather than rewriting
either, per ADR-027's own Consequences prediction.

### Added
- `app.buffer.BarBuffer` -- bounded per-symbol bar history via
  `collections.deque(maxlen=200)`, sized above the largest registered
  feature lookback (100 bars, `features/statistical.py`), keeping
  memory bounded for the life of the process regardless of runtime.
- `app.runtime.MarketDataLoop` gains an optional, additive `on_bar:
  BarCallback | None` constructor parameter -- called once per new bar
  after it's logged. `BarCallback = Callable[[Bar], None]`, deliberately
  synchronous (unlike `market_data.interfaces.BarHandler`'s async
  shape, built for the streaming-provider context). A callback failure
  is caught and logged (`on_bar_callback_failed`), never propagated.
- `app.features_loop.FeatureVectorEmitter` -- `handle_bar(bar)` appends
  to a `BarBuffer`, calls `FeaturePipeline.compute(strict=False)`, logs
  one `feature_vector_computed` event per success (symbol, timestamp,
  `PIPELINE_VERSION`, feature count, latency), and records `ops.metrics
  .MetricsRegistry`'s first real production metrics
  (`feature_vectors_emitted_total` counter, `feature_pipeline_latency_
  seconds` gauge, `feature_computation_errors_total` counter). A
  computation failure is caught and logged (`feature_computation_
  failed`), never propagated. Exposes an optional `on_feature_vector`
  hook for the next phase (Phase C: regime inference).
- `app.config.FeatureLoopConfig` -- composes `MarketDataLoopConfig`
  plus `max_bars_per_symbol` (default `200`).
- `app.bootstrap.build_market_data_loop` gains two additive, optional
  parameters -- `on_bar` and `extra_checks: Sequence[HealthCheck]` --
  both defaulting to values that reproduce Phase A's exact prior
  behavior.
- `app.bootstrap.build_feature_loop` -- Phase B's composition root:
  builds a `FeatureVectorEmitter`, then delegates to
  `build_market_data_loop` with `on_bar=emitter.handle_bar` and
  `extra_checks=[feature_registry_check(...)]`. Returns `(loop,
  runtime_context, emitter)`.
- `app.main` now builds and runs the Phase B pipeline via
  `build_feature_loop` instead of Phase A's bare `build_market_data_
  loop` -- as of Phase B, "the runtime" means market data plus feature
  computation.
- 24 new tests across `tests/app/` (`test_buffer.py`,
  `test_features_loop.py`, plus additions to `test_runtime.py`,
  `test_bootstrap.py`, `test_config.py`), bringing `tests/app/` to 43
  total (up from 19).

### Changed
- `app.__version__` bumped `0.1.0` -> `0.2.0`; `app.bootstrap.
  __version__` (used for `RuntimeContext.platform_info.version`)
  likewise bumped `0.1.0` -> `0.2.0`.
- Nothing in Phase A's tested public behavior changed --
  `MarketDataLoop.on_bar` and `build_market_data_loop`'s new parameters
  are both optional and default to the prior behavior exactly.

### Known limitations
- `app.buffer`/`app.features_loop`/`app.config`/`app.runtime`/
  `app.__init__`/`app.exceptions` are at 100% test coverage;
  `app.bootstrap` is at 97% (same one disclosed real-provider-
  construction line as Phase A, still untested for the same reason);
  `app.main` is at 43% (same disclosed signal-handling gap as Phase A).
- `FeaturePipeline.compute(strict=False)` is called on every new bar
  regardless of how little history exists -- early vectors will have
  most or all features flagged in `quality_flags`. Intentional (see
  ADR-028), not a bug: a consumer that cares about warm-up state reads
  `quality_flags`/`has_any_flag` off the emitted vector.
- Phases C through G (regime detection, strategy, signal orchestration,
  risk, paper execution) are not yet started. (Phase C has since
  shipped -- see the entry above.)

## Unreleased - Runtime Phase A: Market Data Loop (2026-07-15, no tag)

First of seven post-`v2.0.0` runtime phases (A through G), the
continuously-running application this platform has never had. Per
explicit direction, this is deliberately *not* "Milestone 13" — the
planned roadmap is done; this is continuous product evolution, one
small reviewed increment at a time. Design and implementation recorded
together in ADR-027, same single-record cadence Milestone 12's work
packages established.

### Added
- `src/app/` -- a new runtime package, deliberately separate from the
  legacy `regime-trader/main.py` skeleton (which still raises
  `NotImplementedError` by design).
- `app.runtime.MarketDataLoop` -- polls `HistoricalDataProvider.get_bars`
  per symbol on an interval, dedupes against a per-symbol last-seen
  timestamp, logs one structured `bar_received` event per new bar.
  Implements `common.interfaces.Service` (`start`/`stop`), mirroring
  `AlpacaStreamingProvider`'s exact lifecycle shape. A fetch failure for
  one symbol is logged (`market_data_fetch_failed`) and never stops the
  loop or crashes the process.
- `app.config.MarketDataLoopConfig` -- which symbols, how often.
- `app.bootstrap.build_market_data_loop` -- composition root: validates
  `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` via `ops.validation` before
  constructing the default provider, then calls `ops.startup.
  build_runtime_context` with a real `market_data_check` connectivity
  probe. `provider` is injectable, matching this codebase's DI
  convention throughout.
- `app.main` -- `python -m app` process entrypoint with
  `SIGINT`/`SIGTERM` graceful shutdown.
- `market_data.providers.alpaca_historical.AlpacaHistoricalProvider`
  gains a `feed: DataFeed` parameter, defaulting to `DataFeed.IEX` --
  fixes a real gap this phase's own first live-account exercise
  surfaced: no explicit `feed` silently defaulted to Alpaca's SIP feed,
  unreachable on a free-tier account for data less than ~15 minutes
  old (`403 subscription does not permit querying recent SIP data`).
  Now matches `AlpacaStreamingProvider`'s existing `DataFeed.IEX`
  default, closing a pre-existing inconsistency between the two
  providers.
- 19 new tests across `tests/app/` and two new feed-configuration tests
  in `tests/market_data/test_alpaca_historical.py`.

### Changed
- Nothing in any existing package's public contract changed --
  `AlpacaHistoricalProvider.feed` is a new optional constructor
  parameter with a default, not a breaking change.

### Known limitations
- `src/app/config.py`/`runtime.py`/`exceptions.py`/`__init__.py` are at
  100% test coverage; `bootstrap.py` is at 96% (the real-provider-
  construction path, when no provider is injected, is untested --
  exercising it would require either a real network call or mocking
  `alpaca-py`'s SDK internals, the same boundary
  `tests/market_data/test_alpaca_historical.py` already draws for
  `AlpacaHistoricalProvider` itself); `main.py` is at 43% (the
  signal-handling entrypoint body is untested -- meaningfully
  exercising OS signal delivery needs a subprocess, not a unit test,
  the same honest gap already accepted for `nlp.sentiment.
  FinBertSentimentScorer`'s untested body).
- Phase A's symbol list and poll interval are a hardcoded module-level
  default in `app.main` -- a real configuration source (env vars,
  `config/*.yaml`) is deferred to a later phase.
- Phases B through G (features, regime detection, strategy, signal
  orchestration, risk, paper execution) are not yet started.

## v2.0.0 - Milestone 12 Complete: Production Operations (2026-07-15, tag `v2.0.0`)

The umbrella release marking completion of the full planned roadmap —
all twelve milestones. Per this file's own convention, umbrella tags
normally introduce no code of their own and get no entry (see
`v1.0-alpha` above) — this one is the deliberate exception, written as
a release-audit narrative summarizing the evolution from repository
foundation through production operations, per direct request ahead of
cutting this tag. `v2.0.0` points at the same commit as the WP5 merge
below (Milestone 12 has no single `vN-<name>` milestone tag of its
own — see [PROJECT_STATUS.md](PROJECT_STATUS.md)'s Release Milestones
table for why).

### The decision pipeline (Milestones 2–7, 11)

Market Data (`src/market_data`) → Feature Engineering (`src/features`,
`FeatureVector` v2) → HMM Regime Detection (`src/hmm`, `RegimeState`
v1) → Strategy Engine (`src/strategy`, `StrategyDecision` v1) → Signal
Orchestration (`src/orchestration`, `FinalDecision` v1, reconciling
Strategy against advisory Memory/NLP input) → Risk Management
(`src/risk`, `ExecutionDecision` v1, the one gate on order submission)
→ Execution Layer (`src/execution`, `OrderIntent` v1) → Alpaca broker
adapter. Every boundary in this chain is a frozen, versioned contract,
each with its own ADR pair (freeze + design) and binding Standards
document — see [docs/Compatibility.md](docs/Compatibility.md) for the
full version/consumer matrix.

### Supporting platforms (Milestones 8–10)

Backtesting & Validation (`src/backtest`, `BacktestResult` v1) replays
historical bars through the entire real pipeline above, never
retraining models, verified against a mandatory golden-dataset
regression baseline. Adaptive Learning (`src/memory`, `LearningDecision`
v1) and NLP & Event Processing (`src/nlp`, `NewsSignal` v1) both run in
shadow mode only — neither has ever influenced `strategy`/`risk`/
`execution` at any point in this project; the "adaptive learning
observes the system, it does not control it" principle held from
Milestone 9 through today.

### Operational maturity (Milestone 12)

Unlike Milestones 1–11, each built around one frozen domain contract,
Milestone 12 was deliberately built as five independently-merged work
packages (PRs #21–#25) — operational maturity work has no business-
domain contract to freeze ahead of it. `src/ops` (pure stdlib, zero
transitive third-party dependencies throughout): `PlatformHealth`/ten
subsystem health checks (WP1); metrics/tracing/structured logging/alert
rules, all reading `PlatformHealth` as the single operational model
(WP2); injectable secret resolution and fail-fast runtime validation,
composed into an immutable `RuntimeContext` (WP3); deployment/rollback
validation and release-artifact checksum verification, deliberately
stopping short of any CI/CD platform integration since no deployment
target has been chosen (WP4); and `DiagnosticReport` plus six
`docs/operations/` runbooks translating all of the above into concrete
release, incident-response, disaster-recovery, backup-restore, on-call,
and production-readiness procedures (WP5).

### What this release is and isn't

`v2.0.0` marks the planned architecture complete: contract-first
design, ADR governance (26 ADRs), compatibility tracking, benchmarks,
golden-dataset regression tests, CI verification, and now operational
tooling and runbooks, all in place. It is **not** a claim that the
software is finished, validated against real market data, or
authorized for live trading — see
[docs/operations/production-checklist.md](docs/operations/production-checklist.md)
for the explicit gate between "architecture complete" and "cleared to
trade real capital," and
[Architecture/Known Gaps.md](docs/engineering-handbook/Architecture/Known%20Gaps.md)
for what remains open at the component level.

## Unreleased - Milestone 12 WP5: Operations & Runbooks (2026-07-14, no tag)

Fifth and final work package of Milestone 12. Per direct instruction:
most of WP5 moves *out* of `src/` into documentation and operational
assets, with one small runtime addition where it genuinely supports
operational workflows.

### Added
- `ops.models.DiagnosticReport{runtime_context, health, deployment_info,
  generated_at}` -- composes an already-built `RuntimeContext`,
  `PlatformHealth`, and optional `DeploymentInfo` into one snapshot for
  production investigation. Holds no field that already lives on one
  of its components (`version`/`git_commit`/`environment` all read
  through `runtime_context`).
- `ops.diagnostics.build_diagnostic_report` -- pure composition, no new
  validation logic, mirrors `ops.startup.build_runtime_context`'s
  orchestration-only role.
- `ops.reporting.generate_diagnostic_report` -- text rendering,
  alongside the existing `generate_health_report`.
- `docs/operations/release-runbook.md` -- operationalizes WP1-WP4's
  mechanisms into a step-by-step release and rollback procedure.
- `docs/operations/incident-response.md` -- new `src/ops`-detectable
  incident classes (startup validation failure, platform unhealthy/
  degraded, deployment drift, checksum mismatch, no rollback target),
  complementing the pre-existing `SOPs/Incident Response Runbook.md`.
- `docs/operations/disaster-recovery.md` -- host-loss/state-corruption
  recovery procedure, prioritized by what must survive.
- `docs/operations/backup-restore.md` -- what must be backed up (HMM
  model artifacts, experience/news stores, `EMERGENCY_HALT.lock`,
  deployment history), what must never be backed up as plaintext
  (secrets), and restore verification steps.
- `docs/operations/on-call-guide.md` -- what pages on-call, the
  diagnostic-report-first response pattern, and the escalation path.
- `docs/operations/production-checklist.md` -- pre-go-live gate
  synthesizing Known Gaps closure, runtime/deployment validation,
  Master Charter invariants, backup verification, and shadow-mode
  component status into one sign-off checklist.
- `ADR-026-Operations-And-Diagnostics-Design.md` -- design and
  implementation recorded together, same cadence as ADR-022 through
  ADR-025.
- 15 new tests in `tests/ops/` (195 total). 100% line/branch coverage on
  `src/ops/`.

### Changed
- `ops.__version__` bumped `0.4.0` -> `0.5.0`.
- Nothing in any existing package changed -- `src/ops/` remains pure
  stdlib, zero transitive third-party dependencies, across all five
  Milestone 12 work packages.

### Known limitations
- Every `docs/operations/` procedure is manual -- no automation exists
  to run any runbook without a human invoking the underlying `ops`
  function, consistent with ADR-025's "no deployment target chosen
  yet" scope.
- This closes Milestone 12's five planned work packages
  (WP1 Health & Readiness, WP2 Observability, WP3 Configuration &
  Secrets, WP4 Deployment & Release Automation, WP5 Operations &
  Runbooks). A final umbrella release (`v2.0.0` or similar) remains a
  separate, explicit decision, not assumed by this entry.

## Unreleased - Milestone 12 WP4: Deployment & Release Automation (2026-07-14, no tag)

Fourth of Milestone 12's five work packages. Per direct instruction:
keep this work package focused on deployment mechanics rather than
runtime behavior, extend `src/ops/` only where runtime code is
actually needed, and keep deployment-specific assets (workflows,
manifests, scripts) outside `src/` where appropriate.

### Added
- `ops.models.DeploymentInfo{version, git_commit, build_time,
  deployment_environment, deployment_id, rollback_target}` -- one
  deployment instance, distinct from `PlatformInfo` (the build): the
  same build can be deployed more than once, to more than one
  environment, each a separate `DeploymentInfo`.
- `ops.deployment.validate_deployment` -- checks a `DeploymentInfo`
  actually describes the `RuntimeContext` it's paired with
  (`version`/`git_commit` must match).
- `ops.deployment.ReleaseManifest`/`compute_checksum`/
  `verify_release_manifest` -- release-artifact SHA-256 checksum
  verification. Both `validate_deployment` and `verify_release_manifest`
  return `ops.validation.ValidationResult`, the same report shape
  `validate_runtime` already uses; `require_valid_deployment` mirrors
  `require_valid_runtime`.
- `ops.rollback.select_rollback_target`/`require_rollback_target` --
  picks the most recent prior deployment (excluding the current one)
  from deployment history; raises `NoRollbackTargetError` when none
  exists. A separate module from `ops.deployment` because it operates
  on a *sequence* of deployments, not one.
- `ADR-025-Deployment-And-Release-Automation-Design.md` -- design and
  implementation recorded together, same cadence as ADR-022/023/024.
- 33 new tests in `tests/ops/` (180 total). 100% line/branch coverage on
  `src/ops/`.

### Changed
- `ops.__version__` bumped `0.3.0` -> `0.4.0`.
- Nothing in any existing package changed -- `src/ops/` remains pure
  stdlib, zero transitive third-party dependencies.

### Known limitations
- Deliberately deferred: literal Kubernetes manifests, a CI "deploy"
  job, and any release/rollback shell script -- no deployment target
  has been chosen for this platform. Only a `Dockerfile`/
  `docker-compose.yml` (Milestone 1, build/run a container) and
  `.github/workflows/ci.yml` (lint/type/test/build) exist; neither is a
  deployment target. This work package builds the mechanism a real
  deployment script would call into once a target is chosen, not the
  script itself.
- `DeploymentInfo`/rollback selection are not yet wired into `ops.health`,
  `ops.metrics`, `ops.logging`, or `ops.alerts` -- no deployment or
  rollback event triggers a metric, log line, or alert yet.
- WP5 (Operations) is not yet started.

## Unreleased - Milestone 12 WP3: Configuration & Secrets (2026-07-14, no tag)

Third of Milestone 12's five work packages, extending `src/ops/` per
direct product-owner instruction rather than creating a new top-level
package. Scoped around one immutable runtime identity object,
`RuntimeContext` -- "the operational equivalent of your domain
contracts."

### Added
- `ops.models.RuntimeContext{platform_info, environment, startup_time}`
  -- deliberately narrower than first proposed: no embedded
  `validated_config` field (a constructed `RuntimeContext` *is* the
  proof that startup validation passed -- `ops.startup.
  build_runtime_context` is the only place that constructs one, and
  will not return one unless it does), and no duplicate `git_commit`
  (already on `platform_info`). Never carries secret material.
- `ops.secrets` -- `SecretSource` Protocol, `EnvSecretSource` (reads
  `os.environ`, the same source `common.config.Settings` and
  `market_data.auth.AlpacaCredentials` already use), `SecretValue`
  (redacted `__repr__`/`__str__`, `reveal()` the one explicit way to
  read the actual value), and `resolve_secret`. No secrets-manager
  client dependency -- no backend has been chosen yet.
- `ops.validation` -- `ValidationResult`, `validate_runtime` (collects
  every failure in one pass, not just the first), and
  `require_valid_runtime` -- mirrors `ops.health`'s report/gate split.
- `ops.startup.build_runtime_context` -- the one startup sequence:
  validate environment/secrets, optionally evaluate health checks (only
  when a non-empty `checks` sequence is given -- no real subsystem
  probes are wired to this function in this work package), then build a
  `RuntimeContext`. Accepts `environment` as a plain `str` rather than
  importing `common.config.Settings` directly, so `ops` stays free of
  the `pydantic`/`pydantic-settings` dependency `Settings` requires.
- `ADR-024-Configuration-And-Secrets-Design.md` -- design and
  implementation recorded together, same cadence as ADR-022/ADR-023.
- 36 new tests in `tests/ops/` (147 total). 100% line/branch coverage on
  `src/ops/`.

### Changed
- `ops.__version__` bumped `0.2.0` -> `0.3.0`.
- Corrected a test-count error in this file's own WP2 entry below: "167
  total" should have read "111 total" (55 from WP1 + 56 from WP2) --
  caught while computing this entry's own count.
- Nothing in any existing package changed -- `src/ops/` remains pure
  stdlib, zero transitive third-party dependencies.

### Known limitations
- No real deployment entrypoint calls `build_runtime_context` yet, and
  no real `SecretSource` beyond `EnvSecretSource` exists -- wiring a
  real secrets-manager backend, if one is ever adopted, is a later,
  explicit decision, not assumed here.
- `RuntimeContext` is not yet read by any of WP1's health checks,
  WP2's metrics/tracing/logging/alerts, or anything else -- it is a new
  model, not yet wired to the modules built in prior work packages.
- WP4 (Deployment) and WP5 (Operations) are not yet started.

## Unreleased - Milestone 12 WP2: Observability (2026-07-14, no tag)

Second of Milestone 12's five work packages. Per direct product-owner
review of WP1: `PlatformHealth` is now the single operational model
every WP2 module reads -- none recomputes health independently.
Dashboards are explicitly out of scope ("should consume exported
metrics rather than being part of the runtime").

### Added
- `ops.models.PlatformInfo{version, git_commit, build_time,
  python_version}` -- static build identity, deliberately kept separate
  from `PlatformHealth` (different recomputation cadence: `PlatformInfo`
  never changes for a running process, `PlatformHealth` can flip between
  any two evaluations).
- `ops.metrics` -- `Counter`/`Gauge` primitives, a `MetricsRegistry`
  with get-or-create semantics, `record_health_metrics` (reads a
  `PlatformHealth`, writes one gauge per check plus one aggregate status
  gauge), and `export_prometheus_text` (hand-written Prometheus
  exposition-format text -- no `prometheus_client` dependency).
- `ops.tracing` -- `Span{name, started_at, ended_at, metadata}` with a
  derived `duration_seconds`, and `Tracer.span()`, a context manager
  that times its block and calls every registered hook with the
  completed `Span`. No distributed-tracing SDK integration (deliberately
  deferred until a real backend is chosen).
- `ops.logging.log_health_status`/`log_alert` -- structured
  `health_status`/`alert_fired` operational events emitted through a
  caller-supplied `logging.Logger`, built on `common.logging`'s existing
  JSON formatter (`extra=` fields). Does not reconfigure logging.
- `ops.alerts` -- `Alert`/`AlertSeverity`, `CallableAlertRule` (the same
  generic-wrapper pattern `ops.checks.CallableHealthCheck` established),
  named `unhealthy_platform_rule`/`degraded_platform_rule` factories, and
  `evaluate_alerts(health, rules)`.
- `ADR-023-Observability-Design.md` -- design and implementation
  recorded together, same cadence as ADR-022.
- 56 new tests in `tests/ops/` (111 total). 100% line/branch coverage on
  `src/ops/`.

### Changed
- `ops.__version__` bumped `0.1.0` -> `0.2.0`.
- Nothing in any existing package changed -- `src/ops/` remains pure
  stdlib, zero transitive third-party dependencies.

### Known limitations
- `MetricsRegistry` has no thread-safety guarantees and no built-in HTTP
  exposition endpoint -- serving `/metrics` (or pushing to a gateway) is
  WP4 (Deployment)'s job, not WP2's.
- `Tracer`'s hooks run synchronously in-process; no batching, async
  export, or sampling.
- WP3 (Configuration & Secrets), WP4 (Deployment), and WP5 (Operations)
  are not yet started.

## Unreleased - Milestone 12 WP1: Health & Readiness (2026-07-14, no tag)

Operational maturity work, not a domain-decision milestone -- per
explicit product-owner direction, Milestone 12 is split into five
independently-reviewable work packages instead of one contract-first
implementation; this is the first, and does not get its own `vN-<name>`
tag the way Milestones 1-11 each did (no umbrella version bump until
Milestone 12 as a whole closes).

### Added
- `src/ops/` -- a new, independently packaged platform: aggregated
  platform health reporting. Not built around a frozen domain contract
  like `FinalDecision`/`NewsSignal` -- `ADR-022-Health-And-Readiness-
  Design.md` records both the design and implementation decisions
  together, since there is no preceding contract-freeze PR this time.
- `PlatformHealth{status, checks, timestamp, version, git_commit}` and
  `HealthCheckResult{name, healthy, detail, checked_at}` -- a stable,
  documented operational model (not a business-domain contract).
  `classify_status` is the single source of truth for aggregating
  individual check results into one `HealthStatus`
  (`HEALTHY`/`DEGRADED`/`UNHEALTHY`), cross-checked at
  `PlatformHealth` construction so the two can never silently disagree.
- `ops.checks.CallableHealthCheck` -- one generic wrapper around any
  injected zero-argument probe, with ten named factory functions
  (`configuration_check`, `market_data_check`, `model_artifact_check`,
  `feature_registry_check`, `hmm_model_check`, `strategy_registry_check`,
  `risk_service_check`, `execution_adapter_check`, `memory_store_check`,
  `nlp_pipeline_check`) covering every subsystem the platform depends
  on. A probe's exception is converted into a failing `HealthCheckResult`
  rather than propagating, so one unreachable subsystem never prevents
  the other nine from being reported.
- `ops.health.evaluate_health`/`require_healthy` -- the aggregation
  entrypoint and a fail-fast startup gate (`UnhealthyPlatformError`) for
  production start-up code.
- `ops.reporting.generate_health_report` -- a plain-text summary,
  mirroring `backtest.reporting`/`memory.evaluation`/`nlp.evaluation`'s
  own "consumes the model, never shapes it" rendering convention.
- 55 new tests in `tests/ops/` (models, checks, health, reporting).
  100% line/branch coverage on `src/ops/`.

### Changed
- Nothing in any existing package changed -- `src/ops/` has zero
  transitive third-party dependencies and zero dependencies on any other
  first-party package; it is a leaf.

### Known limitations
- Nothing in this milestone wires the ten check factories to real probes
  (a live Alpaca connection check, an actual on-disk HMM-model check,
  etc.) -- WP1 proves the aggregation/reporting layer against injected
  probes; real-probe wiring belongs to whichever later work package
  introduces the deployment entrypoint that constructs them for real.
- The proposed six-module layout (`health.py`/`readiness.py`/
  `startup.py`/`status.py`/`models.py`/`interfaces.py`) was deliberately
  consolidated to five modules (`readiness`/`startup` are facets of the
  same aggregation mechanism, not separate algorithms; `status` became
  `reporting.py` for naming consistency with the rest of this codebase)
  -- see ADR-022's "File-structure consolidation" decision.
- WP2 (Observability), WP3 (Configuration & Secrets), WP4 (Deployment),
  and WP5 (Operations) are not yet started.

## v0.11 - Signal Orchestration (2026-07-14, tag `v0.11-signal-orchestration`)

### Added
- `src/orchestration/` -- a new, independently packaged platform: the
  first milestone whose purpose is *reconciling* `StrategyDecision`
  (primary), `LearningDecision`, and `NewsSignal` (both advisory) rather
  than producing an independent opinion.
- Built in three explicit phases, each independently verified before the
  next began. Phase A (`arbitration.py`, `signals.py`): `arbitrate` --
  a single, deterministic rule (one disagreement cuts allocation, two
  suppress it entirely) with context validation and agreement
  classification factored into shared helpers from the start. Phase B
  (`interfaces.py`, `policies/`): `ArbitrationPolicy`, a single-method
  Protocol, behind four genuinely distinct mechanisms --
  `SafetyFirstPolicy` (Phase A's original rule, now the default),
  `ConsensusPolicy` (any disagreement suppresses), `WeightedVotePolicy`
  (continuous blend, structurally can never fully suppress as long as
  `strategy_weight > 0`), and `ConfidencePolicy` (scales by relative
  confidence, independent of agreement direction). Phase C
  (`evaluation.py`): `evaluate`/`generate_evaluation_report` --
  agreement rate, signal conflict rate, strategy-vs-learner divergence,
  news alignment, orchestration confidence, override frequency, read
  from paired `(FinalDecision, LearningDecision, NewsSignal)` history.
- `final_allocation` is type-level bounded to `[0.0, primary_allocation]`
  on every policy -- no arbitration mechanism can let an advisory signal
  manufacture conviction the Strategy Engine never had, mirroring
  `ExecutionDecision.approved_allocation`'s bound one layer earlier.
  `outcome` (`CONFIRMED`/`ADJUSTED`/`SUPPRESSED`) is validated against
  the allocation fields at construction, the same discipline
  `ExecutionDecision.decision_type` established.
- `ADR-020-FinalDecision-Contract.md` and
  `ADR-021-Signal-Orchestration-Design.md` -- the `FinalDecision`/
  `SignalInput` contract freeze and this milestone's three-phase
  implementation decisions; binding spec: `Standards/FinalDecision
  Contract.md`.
- 113 new tests: 105 in `tests/orchestration` (models, arbitration, four
  policies, evaluation, performance) plus 8 in `tests/contracts`. 100%
  line/branch coverage on `src/orchestration/`.
- `benchmarks/v0.11-signal-orchestration.json` -- per-policy arbitration
  latency (all four policies, sub-millisecond, pure in-memory).

### Changed
- Nothing in `strategy`, `memory`, `nlp`, `risk`, or `execution` changed
  -- `src/orchestration/` depends on `strategy`/`memory`/`nlp`'s already-
  frozen contracts (reading `StrategyDecision`/`LearningDecision`/
  `NewsSignal`), but none of them gain a new dependency on
  `orchestration`, and `risk` gains no new dependency on it either.

### Known limitations
- Wiring `FinalDecision` into `risk.RiskService` in place of
  `StrategyDecision` remains explicitly not authorized -- the execution
  path still runs on the unarbitrated `StrategyDecision`, exactly as
  every milestone before this one. That wiring is a separate, later,
  explicitly-reviewed decision.
- The four policies' specific parameters (`disagreement_penalty = 0.5`,
  `learner_weight = news_weight = 0.5`, etc.) are reasonable defaults,
  not empirically tuned -- no real arbitration history exists yet to
  tune them against.
- `orchestration.evaluation`'s `strategy_vs_learner_divergence` requires
  the raw `LearningDecision` alongside each `FinalDecision` (not derivable
  from `SignalInput` alone, since `weight`'s meaning differs per policy).

## v0.10 - NLP & Event Processing (2026-07-14, tag `v0.10-nlp-news-engine`)

### Added
- `src/nlp/` -- a new, independently packaged platform: a **shadow-mode-
  only** news signal pipeline that records a `NewsSignal` for every
  processed story, without ever influencing `strategy`, `risk`, or
  `execution`.
- Built in three explicit phases, each independently verified before the
  next began. Phase A (`store.py`, `normalize.py`): `InMemoryNewsItemStore`
  and `JsonlNewsItemStore` -- deterministic ingestion and deduplication on
  `(source, source_id)`, no sentiment model yet; `JsonlNewsItemStore`'s
  `add` is idempotent, writing nothing to disk for a redelivered duplicate.
  Phase B (`sentiment.py`, `service.py`): a batch-only `SentimentScorer`
  Protocol -- no single-headline method exists, architecturally preventing
  the per-headline scoring anti-pattern -- with two implementations:
  `DeterministicSentimentScorer` (dependency-free, used by every Phase B/C
  test) and `FinBertSentimentScorer` (adapts the legacy
  `regime-trader/core/sentiment_engine.py::SentimentEngine`, lazy
  `torch`/`transformers` import so the rest of `nlp` needs zero new
  third-party dependencies). `NlpService.build_signals` assembles the
  frozen `NewsSignal`. Phase C (`evaluation.py`): `evaluate_ingestion`,
  `evaluate_sentiment`, `generate_evaluation_report` -- ingestion latency,
  deduplication rate, sentiment distribution, processing throughput.
  Read-only: no production influence, no state mutation.
- A new `@pytest.mark.integration` marker (alongside the existing
  `performance` marker) for `tests/nlp/test_sentiment_integration.py`,
  which uses `pytest.importorskip` so `FinBertSentimentScorer`'s real
  tests skip gracefully -- not fail -- in any environment (including this
  repository's own base CI matrix) without the `trading` extra installed.
- `ADR-018-NewsSignal-Contract.md` and `ADR-019-NLP-News-Engine-Design.md`
  -- the `NewsSignal` contract freeze (adapting, not porting, the legacy
  FinBERT `SentimentScore` and `NewsItem` shapes, with a new type-level
  `sentiment_label`-matches-argmax check) and this milestone's three-phase
  implementation decisions; binding spec: `Standards/NewsSignal
  Contract.md`.
- 105 new tests (`tests/nlp`) plus 5 in `tests/contracts`, plus 5
  integration tests gated on `torch`/`transformers`. 100% line/branch
  coverage on `src/nlp/` except `FinBertSentimentScorer`'s body (not
  installed in this environment -- see Known limitations).
- `benchmarks/v0.10-nlp-news-engine.json` -- a new benchmark category
  (ingest, dedup check, batch sentiment scoring), all sub-millisecond and
  pure in-memory.

### Changed
- Nothing in `strategy`, `risk`, or `execution` changed -- `src/nlp/`
  gains no new dependency on any of them, and none of them gain a new
  dependency on `src/nlp/`.

### Known limitations
- `FinBertSentimentScorer`'s real behavior is unverified by this
  repository's own CI today -- `torch`/`transformers` (the `trading`
  extra) aren't installed there. The `@pytest.mark.integration` marker
  and `pytest.importorskip` guard make this an honest, visible gap
  (the test file always exists and always attempts to run) rather than a
  silently untested code path.
- Entity extraction is deliberately deferred -- every `NewsSignal`
  produced this milestone has `entities=()`. The frozen contract
  explicitly allows this; a real extractor is future work.
- Deduplication is exact `(source, source_id)` match only -- no fuzzy
  cross-source duplicate detection (the same real story reported by two
  different providers produces two separate `NewsSignal`s today).
- `signal_id` is derived deterministically from `(source, source_id)`,
  which assumes exactly one `NewsSignal` per stored `NewsItem` -- no
  re-scoring or multiple signals per story in this milestone.
- Letting a `NewsSignal` actually influence a real `StrategyDecision`/
  `ExecutionDecision`/`OrderIntent` remains a separate, later,
  explicitly-authorized decision -- that convergence is Milestone 11's
  job (Signal Orchestration), not this one's.

## v0.9 - Adaptive Learning / Memory Loop (2026-07-14, tag `v0.9-memory-loop`)

### Added
- `src/memory/` -- a new, independently packaged platform: a **shadow-mode-
  only** adaptive learning loop that records what it would have
  recommended for every real `StrategyDecision`, without ever influencing
  `strategy`, `risk`, or `execution`. The first package in this handbook
  with zero transitive third-party dependencies.
- Built in three explicit phases, each independently verified before the
  next began. Phase A (`memory.store`): `InMemoryExperienceStore` and
  `JsonlExperienceStore` -- an immutable, append-only Experience Store, no
  learning yet. `JsonlExperienceStore` persists one JSON object per line
  with sorted keys for byte-for-byte deterministic output, and follows
  the load-or-init pattern (a missing file is a legitimate first-run
  state). Phase B (`memory.bandit`, `memory.service`):
  `ThompsonSamplingPolicy`/`BetaArm` -- a contextual multi-armed bandit
  (Thompson Sampling over Beta posteriors, `(strategy_id, regime_id)`
  context) reusing the exact update rule already validated by the legacy
  `regime-trader/core/learning_engine.py`, plus `MemoryService`, the
  sanctioned entry point wiring store and policy together. Phase C
  (`memory.evaluation`): `evaluate`/`generate_evaluation_report` --
  agreement rate, recommendation drift, simulated P&L (linear rescaling
  assumption), cumulative regret, and mean confidence, comparing shadow
  recommendations against realized outcomes. Read-only: no production
  influence, no state mutation.
- `recommended_allocation = production_allocation * sampled_weight` --
  the bandit only ever scales production's own allocation down (or close
  to unchanged for a strong posterior), never proposes a larger
  allocation than production chose, extending invariant #5 (long-only)
  into shadow territory. `confidence = sample_size / (sample_size +
  confidence_smoothing)`, a simpler, more explainable proxy than a
  variance-derived confidence interval.
- `ADR-016-LearningDecision-Contract.md` and `ADR-017-Memory-Loop-Design.md`
  -- the `ExperienceRecord`/`LearningDecision` contract freeze (the first
  contract pair in this handbook adapted from, not ported from, a
  pre-existing legacy implementation) and this milestone's three-phase
  implementation decisions; binding spec: `Standards/LearningDecision
  Contract.md`.
- 114 new tests: 105 in `tests/memory` (models, store, bandit, service,
  evaluation, config, performance) plus 9 in `tests/contracts`. 100% line/
  branch coverage on `src/memory/`.
- `benchmarks/v0.9-memory-loop.json` -- a new benchmark category
  (experience insert, bandit update, recommendation generation), all
  sub-millisecond and pure in-memory.

### Changed
- Nothing in `strategy`, `risk`, or `execution` changed -- `src/memory/`
  gains no new dependency on any of them, and none of them gain a new
  dependency on `src/memory/`. This is the property Milestone 9 exists to
  prove out safely: shadow mode is architectural, not just documented.

### Known limitations
- SHAP-based `rationale` and a LightGBM learning policy are both
  explicitly deferred -- the bandit's posterior summary and a simple,
  non-empty human-readable rationale satisfy this milestone's contract;
  see ADR-016/ADR-017's Alternatives Considered for why.
- The learning context is `(strategy_id, regime_id)` only -- no per-
  symbol, RSI-bucket, or other feature-derived dimension, narrower than
  the legacy design's own context. Widening it is a deliberate, reviewed,
  separately-ADR'd decision, not a natural next increment.
- `evaluation.evaluate`'s `simulated_pnl` uses a linear rescaling
  assumption (realized P&L scaled by the ratio of recommended to
  production allocation) -- not a real counterfactual simulation;
  slippage, liquidity, and risk-limit interactions at a different
  position size are all ignored.
- `JsonlExperienceStore` assumes a single writer per path, with no file
  locking -- matches the legacy `data/trade_context_db.json`'s own
  assumption, not yet revisited for a genuine multi-writer scenario.
- Not yet wired to a real backtest replay or live trading loop as an
  experience producer -- every test in this milestone constructs
  synthetic `ExperienceRecord`s directly.
- Letting a `LearningDecision` actually influence a real
  `StrategyDecision`/`ExecutionDecision`/`OrderIntent` remains a separate,
  later, explicitly-authorized decision -- not something this milestone's
  existence should be read as already permitting.

## v0.8 - Backtesting & Validation (2026-07-13, tag `v0.8-backtesting`)

### Added
- `src/backtest/` -- a new, independently packaged platform: the first
  real consumer of `OrderIntent` (and, transitively, every contract
  before it), replaying historical bars through the *entire* decision
  pipeline (Features -> HMM -> Strategy -> Risk -> Execution) and
  producing the canonical `BacktestResult`. Never retrains models.
  Distinct from the pre-existing, untooled `backtest/` crypto SMA
  sandbox at the repository root.
- Built in two explicit phases: Phase A (`backtest.replay.run_replay`)
  proved deterministic replay to a trade log -- verified with two
  identical runs producing byte-identical output -- *before* a single
  metric was written. Phase B (`backtest.metrics`, `backtest.engine`)
  layered performance metrics and reproducibility metadata on top.
- `backtest.replay.run_replay` -- fills every `OrderIntent` at the
  deciding bar's own open (never the same bar used to make the
  decision), the causal boundary invariant #1 requires. Equity is
  marked at each bar's close, after that step's fills. All symbols
  replay in lockstep at each shared timestamp, so portfolio-level risk
  checks (gross exposure, sector concentration) see every symbol's
  state together; `InsufficientReplayHistoryError` if symbols' bars
  aren't calendar-aligned.
- `backtest.portfolio.PortfolioEngine` -- mutable, stateful cash/position/
  equity tracking, deliberately kept separate from `replay.py` so it can
  be reused for paper trading later. Weighted-average cost basis on
  position top-ups; partial exits keep the remainder open at the
  original average entry price and timestamp.
- `backtest.metrics` -- grouped into `returns` (`cagr`, `sharpe_ratio`,
  `sortino_ratio`, `calmar_ratio`), `risk` (`max_drawdown`), `exposure`
  (`exposure`, `turnover`), and `trade_quality` (`win_rate`,
  `profit_factor`, `average_holding_period`) rather than one large
  module. Degenerate ratios (`calmar_ratio`, `profit_factor`) return
  `float("inf")`, matching `risk.models.PortfolioState.
  gross_exposure_pct`'s existing convention.
- `backtest.engine.BacktestEngine` -- Phase B orchestration: calls
  `run_replay`, computes metrics, assembles `ReplayRun` reproducibility
  metadata (`run_id`, `dataset`, `pipeline_versions` collected from
  every upstream package's own version, `git_commit`, `timestamp`), and
  constructs the frozen `BacktestResult`. `git_commit` is a required,
  explicit input -- `current_git_commit()` is a separate, opt-in helper,
  never invoked implicitly.
- `backtest.reporting.generate_report` -- a minimal, human-readable text
  summary of a `BacktestResult`.
- `ADR-014-BacktestResult-Contract.md` and
  `ADR-015-Backtesting-Engine-Design.md` -- the `BacktestResult` contract
  freeze (the first run-level, not single-event, contract in this
  handbook; embeds a `ReplayRun` reproducibility record added during
  review) and this milestone's implementation decisions; binding spec:
  `Standards/BacktestResult Contract.md`.
- A mandatory golden-dataset regression suite
  (`tests/regression/golden_dataset.py`,
  `tests/regression/baseline_results/synthetic_daily_2024.json`,
  `tests/regression/test_golden_dataset.py`) comparing every CI run
  against a checked-in deterministic synthetic scenario, with a
  documented relative tolerance (not exact equality) given this
  project's own CI matrix runs Python 3.9 and 3.11 against different
  resolved `numpy`/`scipy` versions -- a real, previously observed
  source of cross-version behavioral difference, not a hypothetical one.
- 123 new tests: 101 in `tests/backtest` (models, portfolio, replay
  determinism, metrics incl. degenerate-case boundaries, end-to-end
  engine, config validation) plus 10 in `tests/contracts` and 12 in
  `tests/regression`.
- `benchmarks/v0.8-backtesting.json` -- a single-symbol, one-year
  (252-bar) replay measured at ~2.8s.
- `PROJECT_STATUS.md`'s new "Release Milestones" section and the
  `v1.0-alpha` umbrella tag (grouping Milestones 1-7), declared in the
  same window as this milestone but introducing no code of its own.

### Changed
- Nothing in `regime-trader/` or the pre-existing `backtest/` sandbox
  changed -- `src/backtest/` is not yet wired to any live consumer.

### Known limitations
- Only exercised against deterministic *synthetic* bars (`SYNTH`), never
  real historical equity data -- no live market-data credentials exist
  in this environment (see Known Gaps item 2). Partially, not fully,
  closes Known Gaps item 6: the replay *mechanism* is real, but a
  regime-aware backtest against real historical equity OHLCV still
  needs a live account.
- Fill simulation assumes a full fill at the bar's open with zero
  slippage (`NextBarOpenFillModel`, the only `FillModel` shipped) --
  will overstate performance relative to a real venue's execution
  quality. The `FillModel` Protocol exists specifically so a more
  realistic model can be substituted later without touching `replay.py`.
- `metrics.exposure.exposure` undercounts a position still open at the
  very end of a replay (no `TradeRecord` exists for it yet, only closed
  trades are counted) -- documented in the function's own docstring.
- Multi-symbol replay requires every symbol's bars to share identical
  timestamps (no calendar-alignment/forward-fill support yet) --
  `InsufficientReplayHistoryError` otherwise.

## v0.7 - Execution Layer (2026-07-13, tag `v0.7-execution-layer`)

### Added
- `src/execution/` — a new, independently packaged platform: the first
  real consumer of `ExecutionDecision`, converting it (with current
  `PortfolioState`) into the canonical `OrderIntent` (`timestamp`,
  `symbol`, `side`, `quantity`, `order_type`, `limit_price`,
  `time_in_force`, `reference_price`, `stop_loss`, `take_profit`,
  `idempotency_key`, `reasoning`, `execution_reference`, `metadata`) --
  broker-agnostic: every field type is first-party, never an Alpaca SDK
  type.
- `execution.router.route` -- reconciles `ExecutionDecision.
  approved_allocation` (a target fraction of equity) against the
  existing position for that symbol to decide buy/sell/hold and a
  whole-share quantity. Neither `StrategyDecision` nor `ExecutionDecision`
  expresses an order delta directly; this is genuinely new logic, not a
  port. A `SELL` quantity is capped at an approximate current share
  count (`market_value / reference_price`), documented as an
  approximation rather than an exact guarantee.
- `execution.models.ExecutionContext`/`FeatureSnapshot` -- internal,
  deliberately *unfrozen* value objects carrying a transient market
  observation (price) and the minimal feature slice
  (`atr_14`/`realized_volatility_20`) a stop-loss policy needs. Per
  ADR-012's amended principle ("execution contracts describe trading
  intent, not market observations"), neither is a frozen contract and
  neither is embedded in `OrderIntent`.
- `execution.interfaces.{MarketSnapshotProvider,FeatureSnapshotProvider,
  StopLossPolicy,BrokerAdapter}` -- four pluggable `Protocol`s.
  `BrokerAdapter` is kept structurally separate from `ExecutionService`:
  building an `OrderIntent` and submitting one are different operations
  with different failure modes.
- `execution.stop_loss.{ATRStopPolicy,FixedPercentPolicy}` -- pluggable
  stop-loss sizing. `ATRStopPolicy` (the default) sets a stop
  `atr_multiplier` average-true-ranges below the reference price;
  `FixedPercentPolicy` is a fallback ignoring volatility entirely. No
  concrete "volatility tier" formula exists anywhere in this codebase to
  port, so both are new designs grounded in `src/features`'s existing
  ATR feature, not a port of unfound legacy logic.
- `execution.providers.{BarSnapshotProvider,FeaturePipelineSnapshotProvider}`
  -- concrete provider implementations wrapping `market_data.interfaces.
  HistoricalDataProvider` and `features.FeaturePipeline`. Never import a
  specific provider (`AlpacaHistoricalProvider`) or `alpaca-py` directly.
  `BarSnapshotProvider` is honest about what a `Bar`-only data source
  can't supply: `bid`/`ask`/`spread` are always `None`.
- `execution.order_builder.OrderBuilder` / `execution.execution_service.
  ExecutionService` -- orchestration. `ExecutionService.default(
  historical_provider)` wires a sensible default pipeline (bar-close
  snapshots, `FeaturePipeline`-computed features, `ATRStopPolicy`).
- `execution.broker_adapter.AlpacaBrokerAdapter` -- the *only* module
  under `src/execution/` that imports `alpaca-py`. Translates an
  `OrderIntent` into a real OTO/BRACKET `MarketOrderRequest`, matching
  `regime-trader/broker/order_executor.py`'s existing construction logic
  (ported, not reimplemented from scratch) but consuming `OrderIntent`
  instead of raw `entry_price`/`stop_price`/`notional_value` parameters.
  Whole-share quantity and the mandatory-stop-for-a-BUY rule are already
  guaranteed by `OrderIntent`'s own construction-time invariants by the
  time an intent reaches this adapter -- no re-validation needed.
- `execution.retry.submit_with_retry` -- bridges `BrokerAdapter.
  submit_order`'s result-based failure (it never raises, matching
  `OrderExecutor`'s existing pattern) into `common.retry.call_with_retry`'s
  exception-based mechanism. Every retry resubmits the same `OrderIntent.
  idempotency_key` as `client_order_id` -- a real improvement over the
  legacy `order_executor.py`, whose per-call `uuid.uuid4()` could not
  have supported genuine idempotent retries.
- `ADR-012-OrderIntent-Contract.md` and
  `ADR-013-Execution-Layer-Design.md` -- the `OrderIntent` contract
  freeze (including the "execution contracts describe trading intent,
  not market observations" principle, added during review before
  implementation began) and this milestone's implementation decisions;
  binding spec: `Standards/OrderIntent Contract.md`.
- `execution` extras group in `pyproject.toml` (pandas, numpy,
  `alpaca-py`) -- the first milestone-5-onward package with a real
  third-party dependency of its own, scoped to the one module
  (`broker_adapter.py`) that actually needs it.
- 85 new tests: 74 in `tests/execution` (routing buy/sell/hold/no-action,
  stop-loss policies, order building incl. a non-protective-stop guard,
  concrete providers against a fake `HistoricalDataProvider`, broker
  translation against a mocked `TradingClient`, retry/idempotency,
  end-to-end `ExecutionService` wiring) plus 11 in `tests/contracts`.
- `benchmarks/v0.7-execution-layer.json` -- `ExecutionService.decide`
  latency (~0.017ms/call over 10,000 trials against fake in-memory
  providers; excludes real bar-fetch/feature-computation cost).

### Changed
- Nothing in `regime-trader/` changed -- `broker/order_executor.py`
  remains untouched; `src/execution/` is not yet wired to any live
  consumer.

### Known limitations
- `OrderType.LIMIT` is modeled in the frozen contract but has no broker
  translation yet -- `AlpacaBrokerAdapter.submit_order` raises
  `NotImplementedError` for one. No current requirement or legacy
  precedent calls for a limit order.
- No live bid/ask: `BarSnapshotProvider` always reports `bid=ask=spread=
  None` -- a `Bar` carries no quote data. A `MarketSnapshotProvider`
  backed by `market_data.interfaces.StreamingDataProvider`'s live quotes
  is future work.
- `DEFAULT_TICK_SIZE = 0.01` is a flat placeholder for all US equities,
  not a real venue-specific tick table.
- `router.py`'s `SELL` quantity cap
  (`current_position_value / reference_price`) is an approximation --
  `Position.market_value` is a dollar mark-to-market figure, not a
  stored share count, the same documented caveat `core/risk_manager.py`'s
  `ProposedTrade.dollar_risk` already carries.
- Only exercised against synthetic `ExecutionDecision`/`PortfolioState`
  pairs and fake providers -- not yet run end-to-end against real
  historical data or a real (even paper) Alpaca account.

## v0.6 - Risk Management (2026-07-13, tag `v0.6-risk-management`)

### Added
- `src/risk/` — a new, independently packaged platform: the first real
  consumer of `StrategyDecision`, converting it (with a `PortfolioState`/
  `AccountState` snapshot) into the canonical `ExecutionDecision`
  (`timestamp`, `symbol`, `approved`, `approved_allocation`,
  `decision_type`, `risk_adjustments`, `reasoning`, `strategy_reference`,
  `metadata`). A packaged, hardened port of `regime-trader/core/
  risk_manager.py`'s veto layer, not a from-scratch build.
- `risk.models.DecisionType` — explicit `APPROVED`/`REDUCED`/`REJECTED`
  classification, added during contract review, cross-checked against
  `approved`/`approved_allocation`/`risk_adjustments` at construction.
- `risk.validators` — small, composable, one-concern-each validators
  ported from `core/risk_manager.py::check_exposure_limits`
  (`GrossExposureValidator`, `LeverageValidator`,
  `SingleTickerExposureValidator`, `SectorExposureValidator`) plus a net
  new `BuyingPowerValidator` (`AccountState` has no legacy precedent).
  `LiquidityValidator` ships as a deliberate `NotImplementedError`
  placeholder (Master Charter invariant #4) — no volume/spread data
  exists in any current input.
- `risk.sizing.ExposureCapacitySizing` — a new, reduce-only sizing rule
  with no legacy equivalent: fits a decision's allocation to remaining
  gross-exposure/single-ticker/sector headroom instead of rejecting it
  outright. `RiskService.default()` uses this, not the four exposure
  validators above, as its default policy for those concerns — see the
  redundancy bug below.
- `risk.circuit_breakers.DrawdownCircuitBreaker` — ported from
  `core/risk_manager.py::evaluate_circuit_breakers`: the same drawdown
  tiers, most-severe-first evaluation, and disk-backed emergency
  hard-stop lock file (never programmatically deleted, per Master
  Charter invariant #3).
- `risk.service.RiskService` — the package's single entry point:
  `StrategyDecision -> validators -> sizing -> circuit breakers ->
  ExecutionDecision`. `RiskService.default()` assembles a sensible
  default pipeline; a caller wanting the legacy module's zero-tolerance
  exposure policy constructs `RiskService` directly with the four
  exposure validators instead.
- `ADR-010-ExecutionDecision-Contract.md` and
  `ADR-011-Risk-Manager-Design.md` — the `ExecutionDecision` contract
  freeze (landed ahead of this tag, ungoverned by it, later amended
  during review to add `decision_type`) and this milestone's
  implementation decisions: the validator/sizing redundancy bug and its
  fix, the validators→sizing→circuit-breakers pipeline order and why
  it's outcome-equivalent to the legacy order, float-precision handling
  for `decision_type`, minimal `AccountState`, and what's deliberately
  deferred (per-trade dollar risk, correlation filtering, real
  liquidity); binding spec: `Standards/ExecutionDecision Contract.md`.
- 102 new tests: 87 in `tests/risk` (boundary tests for every threshold,
  approval/rejection/reduction paths, multiple simultaneous violations,
  circuit-breaker activation and most-severe-first ordering, the
  emergency lock file's idempotency, determinism, validator/sizing
  composition, an `InvalidSizingResultError` regression test) plus 12 in
  `tests/contracts/test_executiondecision_contract.py`; `src/risk/`
  reaches 100% line and branch coverage.
- `benchmarks/v0.6-risk-management.json` — `RiskService.decide` latency
  (~0.026ms/call over 10,000 trials), comfortably under the milestone's
  <1ms target.

### Changed
- Nothing in `regime-trader/` changed — `core/risk_manager.py` remains
  the live risk-veto path; `src/risk/` is not yet wired to any consumer.

### Known limitations
- A real design bug was found via testing, not caught in review before
  implementation: the first cut wired all four exposure/leverage
  validators into `RiskService.default()` alongside
  `ExposureCapacitySizing`, both checking the identical ratio against
  the identical threshold — meaning any decision sizing would have
  reduced was instead always rejected outright first, making
  `DecisionType.REDUCED` structurally unreachable in the default
  pipeline. Fixed by excluding those four validators from
  `RiskService.default()` (they remain fully implemented and tested for
  a caller wanting the stricter, zero-tolerance policy instead). See
  ADR-011 Decision 1.
- Per-trade dollar-risk and correlation-filter checks from
  `core/risk_manager.py` were not ported — both need data
  (`entry_price`/`stop_price`, a rolling return history) that isn't part
  of `StrategyDecision`, `PortfolioState`, or `AccountState` in this
  milestone's pipeline. Both remain real, working checks in the still-live
  `core/risk_manager.py`; nothing regresses in production. See ADR-011
  Decision 5.
- `LiquidityValidator` has no real implementation — it raises
  `NotImplementedError` unconditionally and is never wired into
  `RiskService.default()`. See ADR-011 Decision 6.
- Only exercised against synthetic `StrategyDecision`/`PortfolioState`/
  `AccountState` triples constructed directly in tests — not yet run
  end-to-end against a real `StrategyService.decide` output.
- `RiskService.default()`'s policy (graceful reduction over hard
  rejection for gross/single-ticker/sector exposure) is more permissive
  than `core/risk_manager.py`'s original binary-reject behavior — a
  deliberate product decision, not an oversight; see ADR-011 Decision 1
  for the full reasoning and how to opt into the stricter policy instead.

## v0.5 - Strategy Engine (2026-07-12, tag `v0.5-strategy-engine`)

### Added
- `src/strategy/` — a new, independently packaged platform: the first real
  consumer of `RegimeState`, converting `RegimeState` (with `FeatureVector`
  as context) into the canonical `StrategyDecision` (`timestamp`, `symbol`,
  `strategy_id`, `regime_id`, `allocation`, `confidence`,
  `expected_holding_period`, `reasoning`, `metadata`). Scoped strictly to
  selecting a strategy and expressing allocation intent — no capital/
  liquidity/leverage checks, no order placement, no broker/risk/memory/NLP
  integration.
- `strategy.interfaces.Strategy` — a `Protocol` with `supports(regime_id)`
  and `allocate(feature_vector, regime_state) -> StrategyDecision`.
- `strategy.registry.StrategyRegistry` — dispatch driven entirely by each
  registered strategy's own `supports()` method, with no separate
  `regime_id -> strategy_id` map to drift out of sync; raises
  `UnsupportedRegimeError` on zero matches (unless a `default_strategy_id`
  fallback is configured) and `AmbiguousStrategyError` on more than one.
- `strategy.strategies.{bull,bear,sideways,defensive}` — four reference
  strategies (`create_growth_strategy`, `create_bear_strategy`,
  `create_mean_reversion_strategy`, `create_defensive_strategy`) built on
  a shared `RegimeMappedStrategy`: `allocation = base_allocation *
  regime_state.confidence`, `confidence = regime_state.confidence`
  directly. None hardcode which `regime_id` values they apply to —
  `supported_regime_ids` is always caller-supplied per trained model (see
  ADR-009 Decision 4).
- `strategy.service.StrategyService` — the package's single entry point:
  resolves a strategy via the registry, then calls `allocate`.
  `StrategyEngineConfig.default_strategy_id` is an explicit opt-in
  fallback (`None` by default — fails loudly on an unmapped regime until
  an operator deliberately configures one).
- `ADR-008-StrategyDecision-Contract.md` and
  `ADR-009-Strategy-Engine-Design.md` — the `StrategyDecision` contract
  freeze (landed ahead of this tag, ungoverned by it) and this milestone's
  implementation decisions: `supports()`-only dispatch, the fallback-vs-
  direct-dispatch bug found and fixed during smoke testing, the
  confidence-propagation formula, and caller-supplied `regime_id`
  semantics; binding spec: `Standards/StrategyDecision Contract.md`.
- `to_dict`/`from_dict` on `FeatureVector`, `Provenance`, and `RegimeState`
  (previously only `hmm.models.ModelMetadata` had them) — additive, no
  contract version bump, added to support this milestone's new
  `tests/contracts/` requirement.
- `tests/contracts/` — a new cross-package regression suite (distinct from
  each package's own unit tests) verifying `FeatureVector`, `RegimeState`,
  and `StrategyDecision` each have exactly their frozen field set, correct
  version metadata, lossless `to_dict`/`from_dict` round-trips, and
  documented backward-compatibility behavior (unknown metadata keys
  tolerated, invariant violations rejected).
- 83 new tests: 55 in `tests/strategy` (registry resolution, unsupported-
  regime/ambiguous-match/fallback-to-default paths, confidence propagation
  and allocation-bounds across a base×confidence grid, deterministic
  output, configuration overrides, service dispatch, a dedicated
  regression test for the fallback-dispatch bug fix) plus 28 in
  `tests/contracts`.
- `benchmarks/v0.5-strategy-engine.json` — `StrategyService.decide`
  latency (~0.0096ms/call over 10,000 trials), comfortably under the
  milestone's <1ms target and, expectedly, several orders of magnitude
  cheaper than `hmm.service.RegimeService.infer`'s ~20.9ms (v0.4) since
  this milestone adds no computation heavier than a dict/set lookup and a
  multiplication.
- `common.time.require_utc` consolidation completed: `market_data.models`
  and `features.feature_vector` now both import the shared helper (already
  used by `hmm.models` since v0.4) instead of each independently
  reimplementing the same UTC check.

### Changed
- Nothing in `regime-trader/` changed — `core/regime_strategies.py` (not
  yet built there) remains a gap; `src/strategy/` is not yet wired to any
  consumer.

### Known limitations
- No tooling exists yet to help an operator determine which `regime_id`
  is "bull-like" for a freshly trained HMM (e.g. inspecting
  `GaussianHMM.means_` per fitted component) — `supported_regime_ids` must
  currently be derived by hand per trained model. See ADR-009 Decision 4.
- Confidence and allocation are a single linear formula off `RegimeState.
  confidence` alone — no independent signal (sentiment, bandit confidence)
  factors in yet; combining future signal sources is an open design
  question for whichever milestone introduces them, not decided here. See
  ADR-009 Decision 3.
- Only exercised against synthetic `FeatureVector`/`RegimeState` pairs
  constructed directly in tests — not yet run end-to-end against a real
  `RegimeService.infer` output.
- No portfolio construction or optimization across multiple symbols —
  `StrategyService.decide` operates on one `(FeatureVector, RegimeState)`
  pair at a time, by design (deferred, not an oversight).

## v0.4 - HMM & Regime Detection (2026-07-12, tag `v0.4-hmm-regime-detection`)

### Added
- `src/hmm/` — a new, independently packaged platform: `hmm.service.
  RegimeService`, a deterministic Gaussian HMM engine consuming only
  `FeatureVector` and producing only the canonical `RegimeState`
  (`timestamp`, `symbol`, `regime_id`, `confidence`,
  `transition_probability`, `model_version`, `feature_pipeline_version`,
  `metadata`).
- `hmm.normalizer.ZScoreNormalizer` — deterministic per-feature
  normalization with explicit missing-value handling (`drop_incomplete_
  rows`; never silent imputation).
- `hmm.trainer`/`hmm.selector` — Baum-Welch/EM training with configurable
  state count, covariance type, and random seed (multiple restarts,
  highest-log-likelihood kept), plus BIC+AIC model selection over a
  configurable candidate state range — both criteria always computed and
  recorded regardless of which one drives selection.
- `hmm.inference.forward_algorithm` — the causal Forward Algorithm
  (`P(S_t | X_{1:t})`), ported from `regime-trader/core/hmm_engine.py`;
  `GaussianHMM.predict_proba`/`.predict`/`.decode` are never called
  anywhere in this package.
- `hmm.persistence` — filesystem artifact save/load (`model.pkl`,
  `normalizer.pkl`, `metadata.json`), versioned per symbol.
- Hard-fail feature-version drift detection: `RegimeService.infer`/
  `infer_series` refuse to run if a `FeatureVector`'s
  `provenance.feature_versions` doesn't match what the loaded model was
  trained on — the direct payoff of Milestone 3's `Provenance` addition
  (v0.3.x, ADR-005).
- `ADR-006-RegimeState-Contract.md` and `ADR-007-HMM-Design.md` — the
  `RegimeState` contract freeze and the modeling/engineering decisions
  behind `src/hmm/`; binding spec: `Standards/RegimeState Contract.md`.
- `hmm` extras group in `pyproject.toml` (pandas, numpy, scipy, hmmlearn),
  depending on `features.feature_vector`/`features.pipeline` at import
  time but never on `market_data` directly.
- `common.time.require_utc` — a shared UTC-timestamp validation helper,
  promoted out of three independent copies of the same check
  (`market_data.models.Bar`, `features.feature_vector`, and now
  `hmm.models.RegimeState`).
- 91 tests for `src/hmm` (unit, integration, quantitative regime-
  switching/stability/noise/constant-series/missing-value scenarios,
  reproducibility, and performance), plus one true end-to-end integration
  test running real `Bar`s through `FeaturePipeline` into `RegimeService`.
- `benchmarks/` — one JSON snapshot per tagged milestone (timing +
  peak-RSS memory), so performance regressions are diffable against
  history instead of re-derived from old PR descriptions. Includes a
  backfilled `v0.3-feature-engineering.json` alongside this tag's own
  `v0.4-hmm-regime-detection.json`.
- As a prerequisite landed in this same tag: `FeatureVector` contract v2
  — a required `provenance: Provenance` field (`pipeline_version`,
  `manifest_version`, `feature_versions`, `generated_at`,
  `source_dataset`), replacing the old duplicated `version`/
  `metadata["pipeline_version"]`/`metadata["source"]` fields (ADR-004,
  ADR-005; binding spec: `Standards/FeatureVector Contract.md`).

### Changed
- Nothing in `regime-trader/` changed — `core/hmm_engine.py` remains the
  live regime-detection path; `src/hmm/` is not yet wired to any consumer
  or to `main.py.ModelStore` (deliberate — see ADR-007 Decision 7).

### Known limitations
- Only exercised against synthetic `FeatureVector`s and real
  `FeaturePipeline` output over synthetic bars — no model in this
  milestone has been trained or run against real historical or live
  market data.
- Single-inference latency measured at ~20ms over a 252-bar window, not
  the originally-targeted <5ms — that target assumed an incremental,
  O(1)-per-call live filter (`hmm_engine.py`'s `ForwardFilter`) that this
  milestone deliberately didn't build; `RegimeService.infer` re-runs the
  batch Forward Algorithm over the full supplied window every call
  instead. See ADR-007 Decision 7.
- `main.py.ModelStore.get_model(ticker) -> GaussianHMM` is incompatible
  with `RegimeService`'s "never expose `hmmlearn` internals" rule and is
  not satisfied by this milestone — reconciling the two is left to
  whichever milestone first wires a real consumer to `src/hmm/`.
- A real bug (`scipy.stats.multivariate_normal.logpdf` raising on a
  singular covariance matrix, reproduced by a constant-valued feature)
  was found and fixed in `src/hmm/inference.py`
  (`allow_singular=True`); the identical, unfixed exposure in the ported-
  from `regime-trader/core/hmm_engine.py` is flagged as a follow-up, not
  fixed in this change.
- `ModelMetadata.feature_versions` snapshots only the *last* row of the
  training window, not the whole window — a feature-formula change that
  lands mid-training-window isn't separately detected.

## v0.3 - Feature Engineering Platform (2026-07-12, tag `v0.3-feature-engineering`)

### Added
- `src/features/` — a new, independently packaged platform: registry-
  backed causal feature library (39 features across price, volatility,
  trend, volume, market structure, statistical, and regime categories),
  `FeaturePipeline` (validation → cleaning → corporate-action adjustment →
  feature computation → output validation), and a canonical
  `FeatureVector(timestamp, symbol, feature_values, feature_names,
  metadata, quality_flags, version)` output type every downstream
  consumer is meant to read.
- `FeatureRegistry` / `@feature(...)` decorator — every registered feature
  enforces `uses_future_data=False` at construction (no opt-out), and a
  registry-driven perturbation test (`test_no_lookahead_all_features.py`)
  proves causality automatically for every feature without a per-feature
  test being hand-written.
- `config/feature_manifest.yaml` — a generated-but-checked-in, machine-
  readable feature catalog (name, category, version, lookback, dtype,
  description, `uses_future_data`, `depends_on`), regenerated from the
  registry via `features.manifest.write_manifest` and kept fresh by a
  dedicated test.
- `features` extras group in `pyproject.toml` (pandas, numpy, ta),
  depending on `market_data.models`/`market_data.validation` at import
  time but not on `market_data`'s heavier storage/provider dependencies.
- `ADR-003-Feature-Engineering.md` — key decisions: canonical
  `FeatureVector`, registration-time leakage protection, reuse of
  `market_data.validation` rather than re-implementing bar cleaning,
  confirmed/lagged reporting for market-structure signals, the manifest,
  and what was deliberately deferred (cross-symbol correlation, `main.py`
  wiring).
- 199 tests for `src/features`, covering per-category correctness,
  registry/`FeatureVector` contract behavior, the pipeline, output
  validation, the manifest, the explicit Milestone 3 edge-case checklist
  (NaNs, missing bars, duplicate timestamps, timezone/DST transitions,
  stock splits, insufficient history, constant prices, extreme
  volatility), and measured performance against the milestone's targets.

### Changed
- Nothing in `regime-trader/` changed — `data/feature_engineering.py`
  remains the live feature path for the existing HMM; `src/features` is
  not yet wired to any consumer (deliberate, per this milestone's scope —
  see Milestone 4).

### Known limitations
- Only exercised against a deterministic synthetic bar generator
  (`tests/features/conftest.py::make_bars`) — no feature in this registry
  has yet been run against real historical or live data pulled through
  `market_data`'s Alpaca providers.
- `hurst_exponent_100` is, by a wide margin, the most computationally
  expensive feature in the registry (~2.6s for a 21-trading-day, 1-minute-
  bar run) and is excluded from the platform's recommended 1-minute-bar
  feature subset on conventional-use grounds (a 100-bar window covers
  under two trading hours at that granularity) — see `test_performance.py`
  and ADR-003's Verification note.
- The "Regime" category ships two features (`liquidity_proxy_20`,
  `volatility_clustering_20`), not the originally-scoped cross-symbol
  "correlation changes" feature — every feature here is a pure function of
  one symbol's own bar history; a cross-symbol feature needs a design this
  milestone deliberately didn't make (see ADR-003 Decision 6).
- Two real bugs in the third-party `ta` library (`ADXIndicator.adx()` and
  `AverageTrueRange.average_true_range()` both raising an unguarded
  `IndexError`, not a graceful NaN, below their true minimum input length)
  were found and worked around with explicit length guards — not fixed
  upstream.

## v0.2 - Market Data Platform (2026-07-12, tag `v0.2-market-data`)

### Added
- `src/market_data/` — a new, independently packaged platform: provider-
  agnostic domain models (`Bar`, `Trade`, `Quote`, `OrderBook`, `Snapshot`,
  `CorporateAction`), `Protocol`-based provider interfaces
  (`HistoricalDataProvider`, `StreamingDataProvider`,
  `CorporateActionsProvider`, `MarketDataStorage`).
- Alpaca historical provider (paginated internally by the SDK, retried via
  `common.retry`, rate-limited) and Alpaca streaming provider (custom
  reconnect-with-backoff loop, heartbeat staleness detection, per-message
  latency tracking).
- Parquet-backed storage (`ParquetBarStore`) doubling as local cache and
  incremental-update mechanism, plus a DuckDB SQL query layer
  (`DuckDBBarQuery`) for cross-symbol analytics.
- Validation: missing-bar detection, duplicate-timestamp handling,
  timezone normalization, corporate-action split adjustment.
- `HistoricalReplay` — sync iteration for backtesting, paced async replay
  for exercising streaming consumers against historical data.
- `regime-trader/broker/alpaca_client.py` — a thin adapter satisfying
  `main.py.MarketDataProvider`, closing Known Gaps item 2.
- `market-data` extras group in `pyproject.toml` (pandas, numpy, pyarrow,
  duckdb, alpaca-py), independent of the `trading` extra.
- `docs/engineering-handbook/Architecture/ADR/` — the ADR process itself
  (`README.md`, `TEMPLATE.md`), plus `ADR-001-Foundation.md` (retroactively
  documenting Milestone 1's decisions) and `ADR-002-Market-Data.md`.
- `PROJECT_STATUS.md` — the live milestone dashboard.
- 168 tests for `src/market_data` and the `regime-trader` adapter contract
  (97% coverage).

### Changed
- `regime-trader/main.py` now constructs `AlpacaMarketDataClient()` in
  place of the `_NotYetImplemented("broker/alpaca_client.py ...")`
  placeholder — a two-line diff; no other line in `regime-trader/` changed.
- MyPy/Ruff/Black scope extended by exactly one file:
  `regime-trader/broker/alpaca_client.py` is now checked alongside `src/`
  and `tests/`; the rest of `regime-trader/` remains outside this
  repository's own tooling (tracked in Known Gaps.md).

### Known limitations
- Not exercised against a live Alpaca account — no credentials available
  in the environment this was built in. SDK usage (request/response
  shapes, method signatures) was verified by inspecting the actually-
  installed `alpaca-py==0.43.5` package directly, not by a live API call.
- `DAY_1` gap detection in `validation.find_missing_bars` only accounts
  for weekends, not market holidays (no trading-calendar dependency yet).
- Corporate-actions handling covers splits and cash dividends; mergers,
  spinoffs, and other action types are parsed but silently skipped (logged
  at debug level).

## v0.1 - Foundation (2026-07-12, tag `v0.1-foundation`)

### Added
- `pyproject.toml` — PEP 621 packaging, dependency groups (`dev`,
  `trading`), Ruff/Black/MyPy/Pytest configuration.
- `src/common/` — the foundation package: `Settings` (pydantic-settings,
  env + `.env` file, safe-by-default `environment`), structured JSON/
  console logging (`configure_logging`), base interfaces (`Clock`,
  `Service`, `HealthCheck`), and utilities (`SystemClock`/`FixedClock`,
  `RetryPolicy`/`call_with_retry`, `atomic_write_json`/
  `read_json_or_default`, an `AppError` exception hierarchy).
- `Dockerfile` + `docker-compose.yml` — multi-stage build, non-root user,
  healthcheck; runs `python -m common`'s smoke-test entrypoint.
- `.github/workflows/ci.yml` — lint, typecheck, test (Python 3.9 + 3.11
  matrix), Docker build.
- `.pre-commit-config.yaml`, `.env.example`, `config/app.example.yaml`,
  `.gitignore`.
- Root `README.md`.
- 49 tests for `src/common` (99% coverage).

### Changed
- Repository initialized under git (`git init`) for the first time.

### Known limitations
- `regime-trader/` and `backtest/` are deliberately untouched and remain
  outside this repository's own Ruff/Black/MyPy/CI coverage — see the
  tooling-scope note in
  [Architecture/Known Gaps.md](docs/engineering-handbook/Architecture/Known%20Gaps.md).
- `requires-python = ">=3.9"` reflects the newest interpreter available in
  the environment this was built in, not a deliberately chosen floor —
  see `pyproject.toml`'s note on raising it later.
- Local verification ran on Python 3.9.6; CI targets 3.9 and 3.11, but the
  3.11 path was not exercised locally before this tag.
