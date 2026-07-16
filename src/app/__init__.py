"""Runtime -- Phase A (Market Data Loop), Phase B (Feature Pipeline),
Phase C (Regime Detection).

The first pieces of the continuously-running application this platform
has never had. Every `src/` package from `market_data` through `ops`
was built and tested in isolation; nothing strung them into a live
process until now. `app` is deliberately separate from the legacy
`regime-trader/main.py` skeleton (which still raises
`NotImplementedError` by design) -- see
docs/engineering-handbook/Architecture/ADR/ADR-027-Runtime-Market-Data-Loop-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-028-Runtime-Feature-Pipeline-Design.md,
and
docs/engineering-handbook/Architecture/ADR/ADR-029-Runtime-Regime-Detection-Design.md.

Phase A: connect to Alpaca, fetch bars on an interval, normalize, log.
Phase B: feed those bars into `FeaturePipeline`, log/emit
`FeatureVector`s. Phase C: feed those vectors into `RegimeService`,
log/emit `RegimeState`s. No strategy, no trading -- those are later
phases, each its own reviewed increment, not built speculatively ahead
of need.

- `app.config.MarketDataLoopConfig`/`FeatureLoopConfig`/
  `RegimeLoopConfig` -- which symbols, how often, how much history to
  retain at each layer.
- `app.runtime.MarketDataLoop` -- the polling loop, a
  `common.interfaces.Service`.
- `app.features_loop.FeatureVectorEmitter` -- turns bars into
  `FeatureVector`s via `MarketDataLoop`'s `on_bar` hook.
- `app.regime_loop.RegimeEmitter` -- turns `FeatureVector`s into
  `RegimeState`s via `FeatureVectorEmitter`'s `on_feature_vector` hook.
- `app.bootstrap.build_market_data_loop`/`build_feature_loop`/
  `build_regime_loop` -- composition roots: startup validation
  (`ops.startup.build_runtime_context`) then loop construction. No
  business logic. `build_regime_loop` requires an already-trained/
  loaded `hmm.service.RegimeService` -- this project has no persisted
  model artifact yet, so there is no default to construct.
- `app.main` -- the process entrypoint (`python -m app`), currently
  running the Phase B pipeline (Phase C isn't wired in as the default
  yet -- see `build_regime_loop`'s docstring).
"""

from __future__ import annotations

from app.bootstrap import (
    build_feature_loop,
    build_market_data_loop,
    build_regime_loop,
    current_git_commit,
)
from app.config import FeatureLoopConfig, MarketDataLoopConfig, RegimeLoopConfig
from app.exceptions import GitCommitUnavailableError, RuntimeAppError
from app.features_loop import FeatureVectorEmitter
from app.regime_loop import RegimeEmitter
from app.runtime import MarketDataLoop

__version__ = "0.3.0"

__all__ = [
    "FeatureLoopConfig",
    "FeatureVectorEmitter",
    "GitCommitUnavailableError",
    "MarketDataLoop",
    "MarketDataLoopConfig",
    "RegimeEmitter",
    "RegimeLoopConfig",
    "RuntimeAppError",
    "__version__",
    "build_feature_loop",
    "build_market_data_loop",
    "build_regime_loop",
    "current_git_commit",
]
