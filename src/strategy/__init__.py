"""Strategy Engine (Milestone 5).

Converts `RegimeState` (with `FeatureVector` as context) into a
`StrategyDecision` -- investment intent, not an execution order. No
broker, no risk, no position sizing against account equity, no memory, no
NLP; those are later milestones. See
docs/engineering-handbook/Architecture/ADR/ADR-008-StrategyDecision-Contract.md
and
docs/engineering-handbook/Architecture/ADR/ADR-009-Strategy-Engine-Design.md.

`StrategyService` is the sanctioned entry point for anything outside this
package. `registry`, `strategies`, and the four reference strategy
factories are callable directly for testing/experimentation.
"""

from __future__ import annotations

from strategy.config import StrategyEngineConfig
from strategy.exceptions import (
    AmbiguousStrategyError,
    ContractViolationError,
    StrategyError,
    StrategyNotFoundError,
    UnsupportedRegimeError,
)
from strategy.interfaces import Strategy
from strategy.models import StrategyDecision
from strategy.registry import StrategyRegistry
from strategy.service import StrategyService

__version__ = "0.1.0"

__all__ = [
    "AmbiguousStrategyError",
    "ContractViolationError",
    "Strategy",
    "StrategyDecision",
    "StrategyEngineConfig",
    "StrategyError",
    "StrategyNotFoundError",
    "StrategyRegistry",
    "StrategyService",
    "UnsupportedRegimeError",
    "__version__",
]
