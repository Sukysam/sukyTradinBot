"""Runtime -- Phase A (Market Data Loop) and Phase B (Feature Pipeline).

The first pieces of the continuously-running application this platform
has never had. Every `src/` package from `market_data` through `ops`
was built and tested in isolation; nothing strung them into a live
process until now. `app` is deliberately separate from the legacy
`regime-trader/main.py` skeleton (which still raises
`NotImplementedError` by design) -- see
docs/engineering-handbook/Architecture/ADR/ADR-027-Runtime-Market-Data-Loop-Design.md
and
docs/engineering-handbook/Architecture/ADR/ADR-028-Runtime-Feature-Pipeline-Design.md.

Phase A: connect to Alpaca, fetch bars on an interval, normalize, log.
Phase B: feed those bars into `FeaturePipeline`, log/emit
`FeatureVector`s. No HMM, no strategy, no trading -- those are later
phases, each its own reviewed increment, not built speculatively ahead
of need.

- `app.config.MarketDataLoopConfig`/`FeatureLoopConfig` -- which
  symbols, how often, how much history to retain.
- `app.runtime.MarketDataLoop` -- the polling loop, a
  `common.interfaces.Service`.
- `app.features_loop.FeatureVectorEmitter` -- turns bars into
  `FeatureVector`s via `MarketDataLoop`'s `on_bar` hook.
- `app.bootstrap.build_market_data_loop`/`build_feature_loop` --
  composition roots: startup validation
  (`ops.startup.build_runtime_context`) then loop construction. No
  business logic.
- `app.main` -- the process entrypoint (`python -m app`), currently
  running the Phase B pipeline.
"""

from __future__ import annotations

from app.bootstrap import build_feature_loop, build_market_data_loop, current_git_commit
from app.config import FeatureLoopConfig, MarketDataLoopConfig
from app.exceptions import GitCommitUnavailableError, RuntimeAppError
from app.features_loop import FeatureVectorEmitter
from app.runtime import MarketDataLoop

__version__ = "0.2.0"

__all__ = [
    "FeatureLoopConfig",
    "FeatureVectorEmitter",
    "GitCommitUnavailableError",
    "MarketDataLoop",
    "MarketDataLoopConfig",
    "RuntimeAppError",
    "__version__",
    "build_feature_loop",
    "build_market_data_loop",
    "current_git_commit",
]
