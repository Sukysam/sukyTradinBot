"""Deterministic fixtures for `risk` tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from risk.models import AccountState, PortfolioState, Position
from strategy.models import StrategyDecision

UTC = timezone.utc
DEFAULT_TIMESTAMP = datetime(2024, 1, 1, tzinfo=UTC)


def make_strategy_decision(
    *,
    symbol: str = "TEST",
    timestamp: datetime = DEFAULT_TIMESTAMP,
    strategy_id: str = "growth_v1",
    regime_id: int = 0,
    allocation: float = 0.5,
    confidence: float = 0.8,
    expected_holding_period: timedelta = timedelta(days=5),
    reasoning: str = "test reasoning",
) -> StrategyDecision:
    return StrategyDecision(
        timestamp=timestamp,
        symbol=symbol,
        strategy_id=strategy_id,
        regime_id=regime_id,
        allocation=allocation,
        confidence=confidence,
        expected_holding_period=expected_holding_period,
        reasoning=reasoning,
        metadata={},
    )


def make_portfolio_state(
    *,
    equity: float = 100_000.0,
    positions: tuple[Position, ...] = (),
    equity_start_of_day: float | None = None,
    equity_start_of_week: float | None = None,
    equity_peak: float | None = None,
) -> PortfolioState:
    return PortfolioState(
        equity=equity,
        positions=positions,
        equity_start_of_day=equity_start_of_day if equity_start_of_day is not None else equity,
        equity_start_of_week=(equity_start_of_week if equity_start_of_week is not None else equity),
        equity_peak=equity_peak if equity_peak is not None else equity,
    )


def make_account_state(*, buying_power: float = 100_000.0) -> AccountState:
    return AccountState(buying_power=buying_power)
