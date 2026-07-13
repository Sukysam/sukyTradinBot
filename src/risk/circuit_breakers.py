"""Portfolio-wide PnL circuit breakers.

Ported from `regime-trader/core/risk_manager.py::evaluate_circuit_breakers`
and the emergency hard-stop lock file functions -- same thresholds
(`risk.limits`), same most-severe-first evaluation order, same disk-backed
halt semantics (survives a process restart, cleared only by a human
deleting the lock file). Kept in its own module, separate from
`validators.py`, because a circuit breaker judges the whole book, not one
proposed `StrategyDecision` -- see `risk.interfaces.CircuitBreaker`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from risk.limits import (
    DAILY_DRAWDOWN_HALT_PCT,
    DAILY_DRAWDOWN_SIZE_CUT_MULTIPLIER,
    DAILY_DRAWDOWN_SIZE_CUT_PCT,
    PEAK_DRAWDOWN_EMERGENCY_PCT,
    WEEKLY_DRAWDOWN_HALT_PCT,
)
from risk.models import PortfolioState

logger = logging.getLogger(__name__)

DEFAULT_EMERGENCY_LOCK_PATH = Path("risk_manager.EMERGENCY_HALT.lock")


class CircuitBreakerAction(str, Enum):
    """Not part of the frozen `ExecutionDecision` contract (ADR-010
    deliberately excludes whole-book actions from it) -- this is
    `RiskService`'s internal signal for how much a circuit breaker should
    override a per-decision verdict."""

    NONE = "none"
    CUT_SIZE_50 = "cut_size_50"
    HALT_DAY = "halt_day"
    HALT_WEEK = "halt_week"
    EMERGENCY_HARD_STOP = "emergency_hard_stop"


#: Actions that force a decision to be rejected outright, regardless of
#: what every `RiskValidator` and `SizingRule` concluded.
_HALTING_ACTIONS = (
    CircuitBreakerAction.EMERGENCY_HARD_STOP,
    CircuitBreakerAction.HALT_DAY,
    CircuitBreakerAction.HALT_WEEK,
)


@dataclass(frozen=True)
class CircuitBreakerResult:
    action: CircuitBreakerAction
    size_multiplier: float
    liquidate: bool
    reasons: tuple[str, ...] = ()

    @property
    def halts_new_trades(self) -> bool:
        return self.action in _HALTING_ACTIONS


def is_emergency_halted(lock_path: Path = DEFAULT_EMERGENCY_LOCK_PATH) -> bool:
    return lock_path.exists()


def trigger_emergency_hard_stop(
    portfolio: PortfolioState, lock_path: Path = DEFAULT_EMERGENCY_LOCK_PATH
) -> None:
    """Write the emergency halt lock file. Idempotent, and never overwrites
    or deletes an existing lock -- clearing it is a manual, human action by
    design (Master Charter invariant #3).
    """
    if lock_path.exists():
        return
    lock_path.write_text(
        "EMERGENCY HARD STOP\n"
        f"peak_drawdown_pct={portfolio.peak_drawdown_pct:.4f}\n"
        f"equity_peak={portfolio.equity_peak:.2f}\n"
        f"equity={portfolio.equity:.2f}\n"
        "Delete this file manually to resume trading.\n"
    )
    logger.critical(
        "EMERGENCY HARD STOP triggered: peak drawdown %.2f%%. Lock written to %s",
        portfolio.peak_drawdown_pct * 100,
        lock_path,
    )


@dataclass(frozen=True)
class DrawdownCircuitBreaker:
    """The one `CircuitBreaker` implementation this milestone ships --
    PnL-drawdown tiers plus the disk-backed emergency lock file, evaluated
    most-severe-first exactly as `core/risk_manager.py` does, since the
    thresholds are not mutually exclusive (a >10% peak drawdown almost
    always also breaches the daily and weekly tiers).
    """

    lock_path: Path = DEFAULT_EMERGENCY_LOCK_PATH

    @property
    def name(self) -> str:
        return "drawdown_circuit_breaker"

    def evaluate(self, portfolio: PortfolioState) -> CircuitBreakerResult:
        if is_emergency_halted(self.lock_path):
            return CircuitBreakerResult(
                action=CircuitBreakerAction.EMERGENCY_HARD_STOP,
                size_multiplier=0.0,
                liquidate=True,
                reasons=(
                    "Emergency hard stop lock file present; manual deletion required to resume.",
                ),
            )

        if portfolio.peak_drawdown_pct > PEAK_DRAWDOWN_EMERGENCY_PCT:
            trigger_emergency_hard_stop(portfolio, self.lock_path)
            return CircuitBreakerResult(
                action=CircuitBreakerAction.EMERGENCY_HARD_STOP,
                size_multiplier=0.0,
                liquidate=True,
                reasons=(
                    f"Peak drawdown {portfolio.peak_drawdown_pct:.2%} > "
                    f"{PEAK_DRAWDOWN_EMERGENCY_PCT:.0%} emergency threshold.",
                ),
            )

        if portfolio.weekly_drawdown_pct > WEEKLY_DRAWDOWN_HALT_PCT:
            return CircuitBreakerResult(
                action=CircuitBreakerAction.HALT_WEEK,
                size_multiplier=0.0,
                liquidate=True,
                reasons=(
                    f"Weekly drawdown {portfolio.weekly_drawdown_pct:.2%} > "
                    f"{WEEKLY_DRAWDOWN_HALT_PCT:.0%} weekly halt threshold.",
                ),
            )

        if portfolio.daily_drawdown_pct > DAILY_DRAWDOWN_HALT_PCT:
            return CircuitBreakerResult(
                action=CircuitBreakerAction.HALT_DAY,
                size_multiplier=0.0,
                liquidate=True,
                reasons=(
                    f"Daily drawdown {portfolio.daily_drawdown_pct:.2%} > "
                    f"{DAILY_DRAWDOWN_HALT_PCT:.0%} daily halt threshold.",
                ),
            )

        if portfolio.daily_drawdown_pct > DAILY_DRAWDOWN_SIZE_CUT_PCT:
            return CircuitBreakerResult(
                action=CircuitBreakerAction.CUT_SIZE_50,
                size_multiplier=DAILY_DRAWDOWN_SIZE_CUT_MULTIPLIER,
                liquidate=False,
                reasons=(
                    f"Daily drawdown {portfolio.daily_drawdown_pct:.2%} > "
                    f"{DAILY_DRAWDOWN_SIZE_CUT_PCT:.0%} size-cut threshold.",
                ),
            )

        return CircuitBreakerResult(
            action=CircuitBreakerAction.NONE, size_multiplier=1.0, liquidate=False
        )


__all__ = [
    "DEFAULT_EMERGENCY_LOCK_PATH",
    "CircuitBreakerAction",
    "CircuitBreakerResult",
    "DrawdownCircuitBreaker",
    "is_emergency_halted",
    "trigger_emergency_hard_stop",
]
