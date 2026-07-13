"""Backtesting & Validation (Milestone 8).

Replays historical bars through the entire real decision pipeline
(Features -> HMM -> Strategy -> Risk -> Execution), simulates fills, and
computes performance metrics -- never retrains models. See
docs/engineering-handbook/Architecture/ADR/ADR-014-BacktestResult-Contract.md
and
docs/engineering-handbook/Architecture/ADR/ADR-015-Backtesting-Engine-Design.md.

Distinct from the pre-existing, untooled `backtest/` directory at the
repository root (a crypto SMA-crossover sandbox) -- see
docs/engineering-handbook/00_MASTER_CHARTER.md Section 1.

`BacktestEngine` is the sanctioned entry point for anything outside this
package. `replay.run_replay` (Phase A: deterministic replay to a trade
log) and `metrics`/`portfolio` are callable directly for testing or a
narrower need than a full `BacktestResult`.
"""

from __future__ import annotations

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine, current_git_commit
from backtest.exceptions import BacktestError, InsufficientReplayHistoryError
from backtest.models import BacktestResult, EquityPoint, ReplayRun, TradeRecord
from backtest.reporting import generate_report

__version__ = "0.1.0"

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestError",
    "BacktestResult",
    "EquityPoint",
    "InsufficientReplayHistoryError",
    "ReplayRun",
    "TradeRecord",
    "__version__",
    "current_git_commit",
    "generate_report",
]
