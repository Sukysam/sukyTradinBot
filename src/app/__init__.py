"""Runtime -- Phase A (Market Data Loop), Phase B (Feature Pipeline),
Phase C (Regime Detection), Phase D (Strategy Engine), Phase E (Signal
Orchestration), Phase F (Risk Management), Phase G (Paper Execution).

The first pieces of the continuously-running application this platform
has never had. Every `src/` package from `market_data` through
`execution` was built and tested in isolation; nothing strung them into
a live process until now. `app` is deliberately separate from the
legacy `regime-trader/main.py` skeleton (which still raises
`NotImplementedError` by design) -- see
docs/engineering-handbook/Architecture/ADR/ADR-027-Runtime-Market-Data-Loop-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-028-Runtime-Feature-Pipeline-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-029-Runtime-Regime-Detection-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-030-Runtime-Strategy-Engine-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-031-Signal-Orchestration-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-032-Runtime-Risk-Management-Design.md,
and
docs/engineering-handbook/Architecture/ADR/ADR-033-Runtime-Paper-Execution-Design.md.

Phase A: connect to Alpaca, fetch bars on an interval, normalize, log.
Phase B: feed those bars into `FeaturePipeline`, log/emit
`FeatureVector`s. Phase C: feed those vectors into `RegimeService`,
log/emit `RegimeState`s. Phase D: feed vector+state pairs into
`StrategyService`, log/emit `StrategyDecision`s. Phase E: arbitrate
`StrategyDecision` (primary) against optional advisory
`LearningDecision`/`NewsSignal`, log/emit `FinalDecision`s. Phase F:
size/approve the arbitrated decision against live portfolio/account
state via `RiskService`, log/emit `ExecutionDecision`s. Phase G: build
an `OrderIntent` via `ExecutionService`, then submit it to a broker via
`BrokerAdapter` (with retry), log/emit `BrokerSubmissionResult`s. **The
runtime stops there** -- no fill handling, trade lifecycle tracking,
position reconciliation, or memory/experience recording; those are
explicitly deferred, future work downstream of a stable, observed
submission path. This is the final phase of the 7-phase runtime plan --
the pipeline now runs end-to-end from a bare `Bar` to a submitted (or
rejected) order.

Every emitter's `handle_bar`/`handle_frame` takes and returns a
`RuntimeFrame` (or `None` to stop) rather than invoking an injected
"next stage" callback -- `app.pipeline.compose_pipeline` folds them
into one `on_bar`-compatible callable. Composition lives in exactly one
place (`app.bootstrap`), not spread across every emitter's constructor.

- `app.frame.RuntimeFrame` -- internal runtime plumbing (not a frozen
  contract) that carries one bar's state through the pipeline, enriched
  by each phase in turn (`bar` -> `feature_vector` -> `regime_state` ->
  `strategy_decision` -> `final_decision` -> `execution_decision` ->
  `order_intent` -> `broker_submission_result`). `require_*` methods
  centralize "does this frame have what I need yet" validation in one
  place rather than each emitter repeating it.
- `app.pipeline.compose_pipeline` -- folds a first-stage `handle_bar`
  and any number of `handle_frame` stages into one `on_bar`-compatible
  callable.
- `app.config.MarketDataLoopConfig`/`FeatureLoopConfig`/
  `RegimeLoopConfig` -- which symbols, how often, how much history to
  retain at each layer.
- `app.runtime.MarketDataLoop` -- the polling loop, a
  `common.interfaces.Service`.
- `app.features_loop.FeatureVectorEmitter` -- turns bars into
  `RuntimeFrame`s carrying a `FeatureVector`.
- `app.regime_loop.RegimeEmitter` -- enriches a frame with a
  `RegimeState`.
- `app.strategy_loop.StrategyEmitter` -- enriches a frame with a
  `StrategyDecision`.
- `app.orchestration_loop.OrchestrationEmitter` -- enriches a frame
  with a `FinalDecision`. No `MemoryEmitter`/`NlpEmitter` stage exists
  in this runtime by design -- `memory`/`nlp` are shadow-mode-only
  (Milestones 9/10); optional `learning_decision_provider`/
  `news_signal_provider` default to `None` (no advisory input).
- `app.risk_loop.RiskEmitter` -- enriches a frame with an
  `ExecutionDecision`, bridging `FinalDecision` into `RiskService.
  decide`'s `StrategyDecision`-shaped input (the specific wiring
  Milestone 11 flagged as "not authorized by this milestone" -- now
  authorized). `portfolio_state_provider`/`account_state_provider` are
  required, live-data callables (no default -- this runtime has no
  broker-query component yet).
- `app.execution_loop.ExecutionEmitter` -- enriches a frame with an
  `OrderIntent` via `ExecutionService`. Never touches a broker.
- `app.execution_loop.BrokerSubmissionEmitter` -- the only stage in
  this runtime allowed to talk to a broker; enriches a frame with a
  `BrokerSubmissionResult` via `execution.retry.submit_with_retry`.
  Deliberately a separate stage from `ExecutionEmitter` so order
  construction and order submission can be swapped, retried, or
  simulated independently.
- `app.bootstrap.build_market_data_loop`/`build_feature_loop`/
  `build_regime_loop`/`build_strategy_loop`/`build_orchestration_loop`/
  `build_risk_loop`/`build_execution_loop` -- composition roots: startup
  validation (`ops.startup.build_runtime_context`) then loop
  construction. No business logic. `build_regime_loop` requires an
  already-trained/loaded `hmm.service.RegimeService`;
  `build_strategy_loop` onward additionally requires a
  `strategy.registry.StrategyRegistry` -- this project has no persisted
  model artifact or defined regime-to-strategy mapping yet, so neither
  has a default to construct. `build_risk_loop` additionally requires
  `portfolio_state_provider`/`account_state_provider`; `risk_service`
  itself *does* default (`RiskService.default()`), unlike the two
  dependencies above it. `build_execution_loop` is the full A-G
  pipeline: `execution_service` defaults to `ExecutionService.default(
  ...)` built from the same resolved `HistoricalDataProvider` used for
  polling; `broker_adapter` defaults to a real `AlpacaBrokerAdapter`
  built from `market_data.auth.AlpacaCredentials.paper`, which itself
  already defaults to `True` (`ALPACA_PAPER` env var, Milestone 2) --
  so this runtime is paper-trading-safe by default, with live
  submission requiring an explicit environment change, never a code
  change.
- `app.main` -- the process entrypoint (`python -m app`), currently
  running the Phase B pipeline (Phase C onward aren't wired in as the
  default yet -- see each `build_*_loop`'s docstring).
"""

from __future__ import annotations

from app.bootstrap import (
    build_execution_loop,
    build_feature_loop,
    build_market_data_loop,
    build_orchestration_loop,
    build_regime_loop,
    build_risk_loop,
    build_strategy_loop,
    current_git_commit,
)
from app.config import FeatureLoopConfig, MarketDataLoopConfig, RegimeLoopConfig
from app.exceptions import GitCommitUnavailableError, RuntimeAppError
from app.execution_loop import BrokerSubmissionEmitter, ExecutionEmitter
from app.features_loop import FeatureVectorEmitter
from app.frame import RuntimeFrame
from app.orchestration_loop import OrchestrationEmitter
from app.pipeline import compose_pipeline
from app.regime_loop import RegimeEmitter
from app.risk_loop import RiskEmitter
from app.runtime import MarketDataLoop
from app.strategy_loop import StrategyEmitter

__version__ = "0.7.0"

__all__ = [
    "BrokerSubmissionEmitter",
    "ExecutionEmitter",
    "FeatureLoopConfig",
    "FeatureVectorEmitter",
    "GitCommitUnavailableError",
    "MarketDataLoop",
    "MarketDataLoopConfig",
    "OrchestrationEmitter",
    "RegimeEmitter",
    "RegimeLoopConfig",
    "RiskEmitter",
    "RuntimeAppError",
    "RuntimeFrame",
    "StrategyEmitter",
    "__version__",
    "build_execution_loop",
    "build_feature_loop",
    "build_market_data_loop",
    "build_orchestration_loop",
    "build_regime_loop",
    "build_risk_loop",
    "build_strategy_loop",
    "compose_pipeline",
    "current_git_commit",
]
