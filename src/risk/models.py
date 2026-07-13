"""`ExecutionDecision` -- the single contract `risk.service.RiskService.
decide` returns, and the only thing about this package any downstream
consumer (Execution, Adaptive Learning, Signal Orchestration) is meant to
depend on. Frozen per
docs/engineering-handbook/Architecture/ADR/ADR-010-ExecutionDecision-Contract.md
*before* this package existed at all; full detail in
"docs/engineering-handbook/Standards/ExecutionDecision Contract.md".

Also defines `PortfolioState`/`Position` (ported from
`regime-trader/core/risk_manager.py`, unchanged in shape) and
`AccountState` (net new -- no legacy precedent) -- the snapshot inputs
`RiskService.decide` evaluates a `StrategyDecision` against. Unlike
`ExecutionDecision`, none of these three are frozen contracts: ADR-010
explicitly leaves the portfolio/account snapshot shape as Milestone 6
implementation detail.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from common.time import require_utc
from strategy.models import StrategyDecision


@dataclass(frozen=True)
class Position:
    """One existing holding in the book. Ported as-is from
    `core/risk_manager.py`'s `Position`."""

    ticker: str
    sector: str
    market_value: float

    def __post_init__(self) -> None:
        if not self.ticker:
            raise ValueError("ticker must not be empty")
        if self.market_value < 0:
            raise ValueError(f"market_value must be >= 0, got {self.market_value}")


def _drawdown_pct(reference_equity: float, current_equity: float) -> float:
    if reference_equity <= 0:
        return 0.0
    return max(0.0, (reference_equity - current_equity) / reference_equity)


@dataclass(frozen=True)
class PortfolioState:
    """A point-in-time portfolio snapshot. Ported as-is from
    `core/risk_manager.py`'s `PortfolioState`, including its drawdown
    properties -- this milestone packages the existing veto layer, it
    doesn't redesign the snapshot it reads.
    """

    equity: float
    positions: tuple[Position, ...]
    equity_start_of_day: float
    equity_start_of_week: float
    equity_peak: float

    @property
    def gross_exposure(self) -> float:
        return sum(p.market_value for p in self.positions)

    @property
    def gross_exposure_pct(self) -> float:
        """Also used as portfolio leverage -- see
        `GrossExposureValidator`/`LeverageValidator`, which check the same
        ratio against two different limits, matching
        `core/risk_manager.py::check_exposure_limits`'s own note that
        gross exposure is always the binding cap in practice (0.80 < 1.25).
        """
        return self.gross_exposure / self.equity if self.equity > 0 else float("inf")

    @property
    def daily_drawdown_pct(self) -> float:
        return _drawdown_pct(self.equity_start_of_day, self.equity)

    @property
    def weekly_drawdown_pct(self) -> float:
        return _drawdown_pct(self.equity_start_of_week, self.equity)

    @property
    def peak_drawdown_pct(self) -> float:
        return _drawdown_pct(self.equity_peak, self.equity)


@dataclass(frozen=True)
class AccountState:
    """Broker-account facts not derivable from `PortfolioState` alone.

    Deliberately minimal: `buying_power` is the only field any validator
    in this milestone consumes. Grown when a real second consumer needs
    another field, not speculatively ahead of one.
    """

    buying_power: float

    def __post_init__(self) -> None:
        if self.buying_power < 0:
            raise ValueError(f"buying_power must be >= 0, got {self.buying_power}")


class DecisionType(str, Enum):
    """Explicit tri-state classification of an `ExecutionDecision`, added
    during contract review (ADR-010) so downstream code branches on
    `decision.decision_type is DecisionType.REDUCED` rather than
    reconstructing that classification from `approved`/
    `approved_allocation`/`risk_adjustments` combinations. Cross-checked
    against those fields at construction -- see `ExecutionDecision.
    __post_init__`.
    """

    APPROVED = "approved"
    REDUCED = "reduced"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ExecutionDecision:
    """One `StrategyDecision`'s approval/sizing verdict as of one point in
    time -- not an order. `approved_allocation` is bounded to
    `[0.0, strategy_reference.allocation]`: this is
    [00_MASTER_CHARTER.md](../../docs/engineering-handbook/00_MASTER_CHARTER.md)
    invariant #5 one layer downstream of `StrategyDecision.allocation` --
    risk only ever holds size steady or reduces it, never increases what
    the strategy asked for. `reasoning` must be non-empty, always,
    extending invariant #6 one step further downstream than
    `StrategyDecision.reasoning` already does.
    """

    timestamp: datetime
    symbol: str
    approved: bool
    approved_allocation: float
    decision_type: DecisionType
    risk_adjustments: tuple[str, ...]
    reasoning: str
    strategy_reference: StrategyDecision
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.symbol != self.strategy_reference.symbol:
            raise ValueError(
                f"symbol {self.symbol!r} does not match "
                f"strategy_reference.symbol {self.strategy_reference.symbol!r}"
            )
        if self.timestamp != self.strategy_reference.timestamp:
            raise ValueError(
                f"timestamp {self.timestamp!r} does not match "
                f"strategy_reference.timestamp {self.strategy_reference.timestamp!r}"
            )
        if not 0.0 <= self.approved_allocation <= self.strategy_reference.allocation:
            raise ValueError(
                f"approved_allocation must be in [0.0, "
                f"{self.strategy_reference.allocation}], got {self.approved_allocation}"
            )
        if not self.approved and self.approved_allocation != 0.0:
            raise ValueError(
                f"approved_allocation must be 0.0 when approved is False, "
                f"got {self.approved_allocation}"
            )
        if not self.approved and not self.risk_adjustments:
            raise ValueError("risk_adjustments must not be empty when approved is False")
        if (
            self.approved_allocation < self.strategy_reference.allocation
            and not self.risk_adjustments
        ):
            raise ValueError(
                "risk_adjustments must not be empty when approved_allocation is reduced "
                "below strategy_reference.allocation"
            )
        if not self.reasoning.strip():
            raise ValueError("reasoning must not be empty")
        self._require_consistent_decision_type()

    def _require_consistent_decision_type(self) -> None:
        reduced = self.approved_allocation < self.strategy_reference.allocation
        if not self.approved:
            expected = DecisionType.REJECTED
        elif reduced:
            expected = DecisionType.REDUCED
        else:
            expected = DecisionType.APPROVED
        if self.decision_type is not expected:
            raise ValueError(
                f"decision_type {self.decision_type!r} is inconsistent with "
                f"approved={self.approved!r}, approved_allocation={self.approved_allocation!r}, "
                f"strategy_reference.allocation={self.strategy_reference.allocation!r} "
                f"(expected {expected!r})"
            )
        if expected is DecisionType.APPROVED and self.risk_adjustments:
            raise ValueError(
                "risk_adjustments must be empty for a clean DecisionType.APPROVED decision"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "approved": self.approved,
            "approved_allocation": self.approved_allocation,
            "decision_type": self.decision_type.value,
            "risk_adjustments": list(self.risk_adjustments),
            "reasoning": self.reasoning,
            "strategy_reference": self.strategy_reference.to_dict(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExecutionDecision:
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            symbol=data["symbol"],
            approved=data["approved"],
            approved_allocation=data["approved_allocation"],
            decision_type=DecisionType(data["decision_type"]),
            risk_adjustments=tuple(data["risk_adjustments"]),
            reasoning=data["reasoning"],
            strategy_reference=StrategyDecision.from_dict(data["strategy_reference"]),
            metadata=dict(data["metadata"]),
        )


__all__ = [
    "AccountState",
    "DecisionType",
    "ExecutionDecision",
    "PortfolioState",
    "Position",
]
