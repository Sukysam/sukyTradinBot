"""Deterministic fixtures for `execution` tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from execution.models import ExecutionContext, FeatureSnapshot
from risk.models import DecisionType, ExecutionDecision, PortfolioState, Position
from strategy.models import StrategyDecision

UTC = timezone.utc
DEFAULT_TIMESTAMP = datetime(2024, 1, 1, tzinfo=UTC)


def make_strategy_decision(
    *,
    symbol: str = "TEST",
    timestamp: datetime = DEFAULT_TIMESTAMP,
    strategy_id: str = "growth_v1",
    allocation: float = 0.5,
) -> StrategyDecision:
    return StrategyDecision(
        timestamp=timestamp,
        symbol=symbol,
        strategy_id=strategy_id,
        regime_id=0,
        allocation=allocation,
        confidence=0.8,
        expected_holding_period=timedelta(days=5),
        reasoning="test reasoning",
        metadata={},
    )


def make_execution_decision(
    *,
    symbol: str = "TEST",
    timestamp: datetime = DEFAULT_TIMESTAMP,
    approved_allocation: float = 0.5,
    strategy_allocation: float = 0.5,
    approved: bool = True,
) -> ExecutionDecision:
    strategy_decision = make_strategy_decision(
        symbol=symbol, timestamp=timestamp, allocation=strategy_allocation
    )
    if not approved:
        return ExecutionDecision(
            timestamp=timestamp,
            symbol=symbol,
            approved=False,
            approved_allocation=0.0,
            decision_type=DecisionType.REJECTED,
            risk_adjustments=("test: rejected",),
            reasoning="Rejected: test",
            strategy_reference=strategy_decision,
            metadata={},
        )
    decision_type = (
        DecisionType.APPROVED
        if approved_allocation == strategy_allocation
        else DecisionType.REDUCED
    )
    risk_adjustments = () if decision_type is DecisionType.APPROVED else ("test: reduced",)
    reasoning = (
        "Approved at full size; no limits binding."
        if decision_type is DecisionType.APPROVED
        else "Approved at reduced size due to: test: reduced"
    )
    return ExecutionDecision(
        timestamp=timestamp,
        symbol=symbol,
        approved=True,
        approved_allocation=approved_allocation,
        decision_type=decision_type,
        risk_adjustments=risk_adjustments,
        reasoning=reasoning,
        strategy_reference=strategy_decision,
        metadata={},
    )


def make_portfolio_state(
    *,
    equity: float = 100_000.0,
    positions: tuple[Position, ...] = (),
) -> PortfolioState:
    return PortfolioState(
        equity=equity,
        positions=positions,
        equity_start_of_day=equity,
        equity_start_of_week=equity,
        equity_peak=equity,
    )


def make_execution_context(
    *,
    symbol: str = "TEST",
    timestamp: datetime = DEFAULT_TIMESTAMP,
    reference_price: float = 100.0,
    tick_size: float = 0.01,
    price_source: str = "bar_close",
) -> ExecutionContext:
    return ExecutionContext(
        symbol=symbol,
        timestamp=timestamp,
        reference_price=reference_price,
        bid=None,
        ask=None,
        spread=None,
        tick_size=tick_size,
        price_source=price_source,
    )


def make_feature_snapshot(
    *,
    symbol: str = "TEST",
    timestamp: datetime = DEFAULT_TIMESTAMP,
    atr_14: float = 2.0,
    realized_volatility_20: float = 0.02,
) -> FeatureSnapshot:
    return FeatureSnapshot(
        symbol=symbol,
        timestamp=timestamp,
        atr_14=atr_14,
        realized_volatility_20=realized_volatility_20,
    )
