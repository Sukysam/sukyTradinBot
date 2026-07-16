"""Runtime -- Phase A (Market Data Loop), Phase B (Feature Pipeline),
Phase C (Regime Detection), Phase D (Strategy Engine).

The first pieces of the continuously-running application this platform
has never had. Every `src/` package from `market_data` through
`strategy` was built and tested in isolation; nothing strung them into
a live process until now. `app` is deliberately separate from the
legacy `regime-trader/main.py` skeleton (which still raises
`NotImplementedError` by design) -- see
docs/engineering-handbook/Architecture/ADR/ADR-027-Runtime-Market-Data-Loop-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-028-Runtime-Feature-Pipeline-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-029-Runtime-Regime-Detection-Design.md,
and
docs/engineering-handbook/Architecture/ADR/ADR-030-Runtime-Strategy-Engine-Design.md.

Phase A: connect to Alpaca, fetch bars on an interval, normalize, log.
Phase B: feed those bars into `FeaturePipeline`, log/emit
`FeatureVector`s. Phase C: feed those vectors into `RegimeService`,
log/emit `RegimeState`s. Phase D: feed vector+state pairs into
`StrategyService`, log/emit `StrategyDecision`s. No risk, no execution,
no orchestration -- those are later phases, each its own reviewed
increment, not built speculatively ahead of need.

- `app.frame.RuntimeFrame` -- internal runtime plumbing (not a frozen
  contract) that carries one bar's state through the pipeline, enriched
  by each phase in turn (`bar` -> `feature_vector` -> `regime_state` ->
  `strategy_decision`).
- `app.config.MarketDataLoopConfig`/`FeatureLoopConfig`/
  `RegimeLoopConfig` -- which symbols, how often, how much history to
  retain at each layer.
- `app.runtime.MarketDataLoop` -- the polling loop, a
  `common.interfaces.Service`.
- `app.features_loop.FeatureVectorEmitter` -- turns bars into
  `FeatureVector`s via `MarketDataLoop`'s `on_bar` hook.
- `app.regime_loop.RegimeEmitter` -- turns `FeatureVector`s into
  `RegimeState`s via `FeatureVectorEmitter`'s `on_frame` hook.
- `app.strategy_loop.StrategyEmitter` -- turns vector+state pairs into
  `StrategyDecision`s via `RegimeEmitter`'s `on_frame` hook.
- `app.bootstrap.build_market_data_loop`/`build_feature_loop`/
  `build_regime_loop`/`build_strategy_loop` -- composition roots:
  startup validation (`ops.startup.build_runtime_context`) then loop
  construction. No business logic. `build_regime_loop` requires an
  already-trained/loaded `hmm.service.RegimeService`;
  `build_strategy_loop` additionally requires a `strategy.registry.
  StrategyRegistry` -- this project has no persisted model artifact or
  defined regime-to-strategy mapping yet, so neither has a default to
  construct.
- `app.main` -- the process entrypoint (`python -m app`), currently
  running the Phase B pipeline (Phase C/D aren't wired in as the
  default yet -- see `build_regime_loop`/`build_strategy_loop`'s
  docstrings).
"""

from __future__ import annotations

from app.bootstrap import (
    build_feature_loop,
    build_market_data_loop,
    build_regime_loop,
    build_strategy_loop,
    current_git_commit,
)
from app.config import FeatureLoopConfig, MarketDataLoopConfig, RegimeLoopConfig
from app.exceptions import GitCommitUnavailableError, RuntimeAppError
from app.features_loop import FeatureVectorEmitter
from app.frame import RuntimeFrame
from app.regime_loop import RegimeEmitter
from app.runtime import MarketDataLoop
from app.strategy_loop import StrategyEmitter

__version__ = "0.4.0"

__all__ = [
    "FeatureLoopConfig",
    "FeatureVectorEmitter",
    "GitCommitUnavailableError",
    "MarketDataLoop",
    "MarketDataLoopConfig",
    "RegimeEmitter",
    "RegimeLoopConfig",
    "RuntimeAppError",
    "RuntimeFrame",
    "StrategyEmitter",
    "__version__",
    "build_feature_loop",
    "build_market_data_loop",
    "build_regime_loop",
    "build_strategy_loop",
    "current_git_commit",
]
