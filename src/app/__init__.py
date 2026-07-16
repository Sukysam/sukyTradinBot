"""Runtime -- Phase A: Market Data Loop.

The first piece of the continuously-running application this platform
has never had. Every `src/` package from `market_data` through `ops`
was built and tested in isolation; nothing strung them into a live
process until now. `app` is deliberately separate from the legacy
`regime-trader/main.py` skeleton (which still raises
`NotImplementedError` by design) -- see
docs/engineering-handbook/Architecture/ADR/ADR-027-Runtime-Market-Data-Loop-Design.md.

Phase A only: connect to Alpaca, fetch bars on an interval, normalize,
log. No features, no HMM, no trading -- those are later phases, each
its own reviewed increment, not built speculatively ahead of need.

- `app.config.MarketDataLoopConfig` -- which symbols, how often.
- `app.runtime.MarketDataLoop` -- the loop itself, a
  `common.interfaces.Service`.
- `app.bootstrap.build_market_data_loop` -- composition root: startup
  validation (`ops.startup.build_runtime_context`) then loop
  construction. No business logic.
- `app.main` -- the process entrypoint (`python -m app`).
"""

from __future__ import annotations

from app.bootstrap import build_market_data_loop, current_git_commit
from app.config import MarketDataLoopConfig
from app.exceptions import GitCommitUnavailableError, RuntimeAppError
from app.runtime import MarketDataLoop

__version__ = "0.1.0"

__all__ = [
    "GitCommitUnavailableError",
    "MarketDataLoop",
    "MarketDataLoopConfig",
    "RuntimeAppError",
    "__version__",
    "build_market_data_loop",
    "current_git_commit",
]
