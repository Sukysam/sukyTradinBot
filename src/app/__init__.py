"""Runtime -- Phase A (Market Data Loop), Phase B (Feature Pipeline),
Phase C (Regime Detection), Phase D (Strategy Engine), Phase E (Signal
Orchestration).

The first pieces of the continuously-running application this platform
has never had. Every `src/` package from `market_data` through
`orchestration` was built and tested in isolation; nothing strung them
into a live process until now. `app` is deliberately separate from the
legacy `regime-trader/main.py` skeleton (which still raises
`NotImplementedError` by design) -- see
docs/engineering-handbook/Architecture/ADR/ADR-027-Runtime-Market-Data-Loop-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-028-Runtime-Feature-Pipeline-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-029-Runtime-Regime-Detection-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-030-Runtime-Strategy-Engine-Design.md,
and
docs/engineering-handbook/Architecture/ADR/ADR-031-Signal-Orchestration-Design.md.

Phase A: connect to Alpaca, fetch bars on an interval, normalize, log.
Phase B: feed those bars into `FeaturePipeline`, log/emit
`FeatureVector`s. Phase C: feed those vectors into `RegimeService`,
log/emit `RegimeState`s. Phase D: feed vector+state pairs into
`StrategyService`, log/emit `StrategyDecision`s. Phase E: arbitrate
`StrategyDecision` (primary) against optional advisory
`LearningDecision`/`NewsSignal`, log/emit `FinalDecision`s. No risk, no
execution -- those are later phases, each its own reviewed increment,
not built speculatively ahead of need.

Every emitter's `handle_bar`/`handle_frame` takes and returns a
`RuntimeFrame` (or `None` to stop) rather than invoking an injected
"next stage" callback -- `app.pipeline.compose_pipeline` folds them
into one `on_bar`-compatible callable. Composition lives in exactly one
place (`app.bootstrap`), not spread across every emitter's constructor.

- `app.frame.RuntimeFrame` -- internal runtime plumbing (not a frozen
  contract) that carries one bar's state through the pipeline, enriched
  by each phase in turn (`bar` -> `feature_vector` -> `regime_state` ->
  `strategy_decision` -> `final_decision`).
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
- `app.bootstrap.build_market_data_loop`/`build_feature_loop`/
  `build_regime_loop`/`build_strategy_loop`/`build_orchestration_loop`
  -- composition roots: startup validation
  (`ops.startup.build_runtime_context`) then loop construction. No
  business logic. `build_regime_loop` requires an already-trained/
  loaded `hmm.service.RegimeService`; `build_strategy_loop`/
  `build_orchestration_loop` additionally require a `strategy.registry.
  StrategyRegistry` -- this project has no persisted model artifact or
  defined regime-to-strategy mapping yet, so neither has a default to
  construct.
- `app.main` -- the process entrypoint (`python -m app`), currently
  running the Phase B pipeline (Phase C/D/E aren't wired in as the
  default yet -- see `build_regime_loop`/`build_strategy_loop`/
  `build_orchestration_loop`'s docstrings).
"""

from __future__ import annotations

from app.bootstrap import (
    build_feature_loop,
    build_market_data_loop,
    build_orchestration_loop,
    build_regime_loop,
    build_strategy_loop,
    current_git_commit,
)
from app.config import FeatureLoopConfig, MarketDataLoopConfig, RegimeLoopConfig
from app.exceptions import GitCommitUnavailableError, RuntimeAppError
from app.features_loop import FeatureVectorEmitter
from app.frame import RuntimeFrame
from app.orchestration_loop import OrchestrationEmitter
from app.pipeline import compose_pipeline
from app.regime_loop import RegimeEmitter
from app.runtime import MarketDataLoop
from app.strategy_loop import StrategyEmitter

__version__ = "0.5.0"

__all__ = [
    "FeatureLoopConfig",
    "FeatureVectorEmitter",
    "GitCommitUnavailableError",
    "MarketDataLoop",
    "MarketDataLoopConfig",
    "OrchestrationEmitter",
    "RegimeEmitter",
    "RegimeLoopConfig",
    "RuntimeAppError",
    "RuntimeFrame",
    "StrategyEmitter",
    "__version__",
    "build_feature_loop",
    "build_market_data_loop",
    "build_orchestration_loop",
    "build_regime_loop",
    "build_strategy_loop",
    "compose_pipeline",
    "current_git_commit",
]
