"""Protocol interfaces for the Risk Manager's three pluggable stages:
validation (reject/pass), sizing (reduce-only), and circuit breakers
(portfolio-wide, independent of any single decision). `risk.service.
RiskService` composes implementations of these; nothing else in this
package depends on a concrete implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from risk.models import AccountState, PortfolioState
from strategy.models import StrategyDecision

if TYPE_CHECKING:
    from risk.circuit_breakers import CircuitBreakerResult


class RiskValidator(Protocol):
    """Evaluates one concern (e.g. gross exposure, sector concentration)
    against a single proposed `StrategyDecision`. Returns a tuple of
    human-readable violation strings -- empty means no violation. Never
    raises for an ordinary limit breach; a validator that cannot evaluate
    at all (e.g. genuinely malformed input) is the one case that should
    raise, and that's a caller bug, not a risk finding.

    A `RiskValidator` never reduces or approves anything itself -- it only
    reports. `RiskService` decides what a non-empty violation list means
    for the final decision.
    """

    @property
    def name(self) -> str:
        """Short, stable identifier for this validator, used to prefix its
        violation strings in `ExecutionDecision.risk_adjustments` so a
        rejection is traceable back to the specific check that fired."""
        ...

    def validate(
        self,
        decision: StrategyDecision,
        portfolio: PortfolioState,
        account: AccountState,
    ) -> tuple[str, ...]: ...


class SizingRule(Protocol):
    """Computes an allocation for a `StrategyDecision` that has already
    passed every `RiskValidator` -- never larger than `requested_allocation`.
    `RiskService` treats any rule that returns a larger value as a bug
    (`risk.exceptions.InvalidSizingResultError`), not a legitimate outcome.

    `decision` and `requested_allocation` are deliberately separate
    parameters: `requested_allocation` starts as `decision.allocation` but
    may already reflect an earlier `SizingRule` in a chain, while
    `decision` (symbol, in particular) stays fixed throughout -- a rule
    that needs to know *which* symbol it's sizing (e.g. remaining
    single-ticker headroom) reads it from `decision`, never from
    `requested_allocation`.
    """

    @property
    def name(self) -> str:
        """Short, stable identifier for this rule, used the same way as
        `RiskValidator.name`."""
        ...

    def apply(
        self,
        decision: StrategyDecision,
        requested_allocation: float,
        portfolio: PortfolioState,
        account: AccountState,
    ) -> float: ...


class CircuitBreaker(Protocol):
    """Evaluates portfolio-wide state (PnL drawdown tiers, the emergency
    halt lock file) independent of any single `StrategyDecision` --
    ported behavior from `core/risk_manager.py::evaluate_circuit_breakers`.
    Deliberately separate from `RiskValidator`: a validator judges one
    proposed decision, a circuit breaker judges the book as a whole and
    can override every validator's verdict (a halted book rejects new
    size regardless of how clean an individual decision looks).
    """

    @property
    def name(self) -> str:
        """Short, stable identifier for this circuit breaker, used the
        same way as `RiskValidator.name`."""
        ...

    def evaluate(self, portfolio: PortfolioState) -> CircuitBreakerResult: ...


__all__ = ["CircuitBreaker", "RiskValidator", "SizingRule"]
