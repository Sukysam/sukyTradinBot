"""Trade-quality metrics: `win_rate`, `profit_factor`,
`average_holding_period`."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from backtest.models import TradeRecord


def win_rate(trade_log: Sequence[TradeRecord]) -> float:
    if not trade_log:
        return 0.0
    wins = sum(1 for trade in trade_log if trade.pnl > 0)
    return wins / len(trade_log)


def profit_factor(trade_log: Sequence[TradeRecord]) -> float:
    """`gross_profit / gross_loss` (both positive magnitudes).
    `float("inf")` when there are winning trades and zero losing trades
    -- same degenerate-denominator convention as `metrics.returns.
    calmar_ratio`. `0.0` when there are no trades, or no winning trades,
    at all (distinct from the "all wins" case)."""
    gross_profit = sum(trade.pnl for trade in trade_log if trade.pnl > 0)
    gross_loss = abs(sum(trade.pnl for trade in trade_log if trade.pnl < 0))
    if gross_loss == 0.0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def average_holding_period(trade_log: Sequence[TradeRecord]) -> timedelta:
    if not trade_log:
        return timedelta(0)
    total = sum((trade.holding_period for trade in trade_log), timedelta(0))
    return total / len(trade_log)


__all__ = ["average_holding_period", "profit_factor", "win_rate"]
