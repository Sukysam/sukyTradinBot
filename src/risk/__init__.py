"""Risk Manager (Milestone 6).

Converts a `StrategyDecision` (plus a `PortfolioState`/`AccountState`
snapshot) into an `ExecutionDecision` -- an approval/sizing verdict, not
an order. No broker calls, no order construction; those are Milestone 7.
A packaged, hardened port of `regime-trader/core/risk_manager.py`'s veto
layer, not a from-scratch build. See
docs/engineering-handbook/Architecture/ADR/ADR-010-ExecutionDecision-Contract.md
and
docs/engineering-handbook/Architecture/ADR/ADR-011-Risk-Manager-Design.md.

`RiskService` is the sanctioned entry point for anything outside this
package. `validators`, `sizing`, and `circuit_breakers` are callable
directly for testing/experimentation.
"""

from __future__ import annotations

from risk.config import RiskServiceConfig
from risk.exceptions import InvalidSizingResultError, RiskError
from risk.interfaces import CircuitBreaker, RiskValidator, SizingRule
from risk.models import AccountState, DecisionType, ExecutionDecision, PortfolioState, Position
from risk.service import RiskService

__version__ = "0.1.0"

__all__ = [
    "AccountState",
    "CircuitBreaker",
    "DecisionType",
    "ExecutionDecision",
    "InvalidSizingResultError",
    "PortfolioState",
    "Position",
    "RiskError",
    "RiskService",
    "RiskServiceConfig",
    "RiskValidator",
    "SizingRule",
    "__version__",
]
