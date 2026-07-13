"""`RiskService` -- the single public entry point for this package.

Pipeline: `StrategyDecision` -> validators -> sizing -> circuit breakers ->
`ExecutionDecision`. Validators run first and can reject outright; sizing
then reduces (never increases) whatever survived; the circuit breaker runs
last and can override everything before it, since a portfolio-wide halt
takes priority over any single decision's own verdict. This ordering is a
deliberate choice, not a port of `core/risk_manager.py::evaluate_trade`'s
own order (which checks circuit breakers first, purely as a short-circuit
optimization) -- see ADR-011 for why the two orderings produce identical
final outcomes, differing only in which reasons get computed when a
rejection is already certain.
"""

from __future__ import annotations

from dataclasses import dataclass

from risk.circuit_breakers import CircuitBreakerAction, DrawdownCircuitBreaker
from risk.config import RiskServiceConfig
from risk.exceptions import InvalidSizingResultError
from risk.interfaces import CircuitBreaker, RiskValidator, SizingRule
from risk.models import AccountState, DecisionType, ExecutionDecision, PortfolioState
from risk.sizing import ExposureCapacitySizing
from risk.validators import BuyingPowerValidator
from strategy.models import StrategyDecision

#: Floating-point slack for "did a sizing/circuit-breaker stage actually
#: change the allocation" comparisons -- deterministic float arithmetic
#: (multiplication, subtraction) can differ from the original value by less
#: than this without representing a real, intentional adjustment.
_TOLERANCE = 1e-9


@dataclass(frozen=True)
class RiskService:
    validators: tuple[RiskValidator, ...]
    sizing_rules: tuple[SizingRule, ...]
    circuit_breaker: CircuitBreaker

    @classmethod
    def default(cls, config: RiskServiceConfig | None = None) -> RiskService:
        """A sensible default pipeline favoring graceful degradation:
        `ExposureCapacitySizing` reduces a decision to fit within
        remaining gross-exposure/single-ticker/sector headroom rather than
        rejecting it outright, so only `BuyingPowerValidator` -- a concern
        this milestone treats as a hard yes/no, not something to partially
        fit -- runs as a default validator.

        `GrossExposureValidator`/`LeverageValidator`/
        `SingleTickerExposureValidator`/`SectorExposureValidator` are
        deliberately *not* wired in here: each checks the exact same ratio
        `ExposureCapacitySizing` already computes headroom for, so
        including them here would reject outright the very requests
        sizing exists to gracefully reduce instead, making the reduce
        path unreachable in practice. They remain available, fully
        tested, for a caller who wants a strict zero-tolerance policy
        instead -- construct `RiskService` directly with them. See
        ADR-011 for the full reasoning.
        """
        cfg = config or RiskServiceConfig()
        return cls(
            validators=(BuyingPowerValidator(),),
            sizing_rules=(ExposureCapacitySizing(sector_map=cfg.sector_map),),
            circuit_breaker=DrawdownCircuitBreaker(),
        )

    def decide(
        self,
        decision: StrategyDecision,
        portfolio: PortfolioState,
        account: AccountState,
    ) -> ExecutionDecision:
        adjustments: list[str] = []

        violations: list[str] = []
        for validator in self.validators:
            violations.extend(
                f"{validator.name}: {msg}"
                for msg in validator.validate(decision, portfolio, account)
            )
        rejected_by_validator = bool(violations)
        adjustments.extend(violations)

        allocation = decision.allocation
        if not rejected_by_validator:
            for rule in self.sizing_rules:
                sized = rule.apply(decision, allocation, portfolio, account)
                if sized > allocation + _TOLERANCE:
                    raise InvalidSizingResultError(
                        f"SizingRule {rule.name!r} returned {sized}, which exceeds the "
                        f"{allocation} it was given -- sizing must never increase allocation."
                    )
                if sized < allocation - _TOLERANCE:
                    adjustments.append(
                        f"{rule.name}: reduced allocation from {allocation:.4f} to {sized:.4f}."
                    )
                allocation = min(allocation, sized)

        breaker_result = self.circuit_breaker.evaluate(portfolio)
        if breaker_result.action is not CircuitBreakerAction.NONE:
            adjustments.extend(
                f"{self.circuit_breaker.name}: {reason}" for reason in breaker_result.reasons
            )
        if breaker_result.halts_new_trades:
            allocation = 0.0
        elif breaker_result.size_multiplier < 1.0:
            allocation = min(allocation, allocation * breaker_result.size_multiplier)

        approved = not rejected_by_validator and not breaker_result.halts_new_trades
        if not approved:
            approved_allocation = 0.0
            decision_type = DecisionType.REJECTED
        elif allocation < decision.allocation - _TOLERANCE:
            approved_allocation = allocation
            decision_type = DecisionType.REDUCED
        else:
            # Effectively unchanged -- snap to the exact requested value so
            # floating-point noise from a no-op sizing/breaker pass never
            # trips ExecutionDecision's own strict equality check.
            approved_allocation = decision.allocation
            decision_type = DecisionType.APPROVED

        reasoning = _build_reasoning(decision_type, decision, approved_allocation, adjustments)

        return ExecutionDecision(
            timestamp=decision.timestamp,
            symbol=decision.symbol,
            approved=approved,
            approved_allocation=approved_allocation,
            decision_type=decision_type,
            risk_adjustments=tuple(adjustments),
            reasoning=reasoning,
            strategy_reference=decision,
            metadata={},
        )


def _build_reasoning(
    decision_type: DecisionType,
    decision: StrategyDecision,
    approved_allocation: float,
    adjustments: list[str],
) -> str:
    if decision_type is DecisionType.REJECTED:
        return "Rejected: " + "; ".join(adjustments)
    if decision_type is DecisionType.REDUCED:
        return (
            f"Approved at reduced size ({approved_allocation:.4f} of "
            f"{decision.allocation:.4f} requested) due to: " + "; ".join(adjustments)
        )
    return "Approved at full size; no limits binding."


__all__ = ["RiskService"]
