"""Exposure-based metrics: `exposure`, `turnover`."""

from __future__ import annotations

from collections.abc import Sequence

from backtest.models import EquityPoint, TradeRecord


def exposure(equity_curve: Sequence[EquityPoint], trade_log: Sequence[TradeRecord]) -> float:
    """Time-weighted fraction of `equity_curve` during which at least one
    `trade_log` entry's `[entry_timestamp, exit_timestamp]` interval
    covers that point.

    Known limitation: a position still open at the *end* of the replay
    has no `TradeRecord` yet (only closed trades appear in `trade_log`),
    so the tail of a run ending mid-position understates exposure. See
    ADR-015.
    """
    if not equity_curve:
        return 0.0
    exposed = sum(
        1
        for point in equity_curve
        if any(
            trade.entry_timestamp <= point.timestamp <= trade.exit_timestamp for trade in trade_log
        )
    )
    return exposed / len(equity_curve)


def turnover(trade_log: Sequence[TradeRecord], equity_curve: Sequence[EquityPoint]) -> float:
    """Sum of traded notional (both entry and exit legs of every closed
    trade) divided by average equity over the run. No fixed upper bound."""
    if not equity_curve:
        return 0.0
    traded_notional = sum(
        (trade.entry_price * trade.quantity) + (trade.exit_price * trade.quantity)
        for trade in trade_log
    )
    average_equity = sum(point.equity for point in equity_curve) / len(equity_curve)
    if average_equity <= 0:
        return 0.0
    return traded_notional / average_equity


__all__ = ["exposure", "turnover"]
