"""Risk-based metrics: `max_drawdown`."""

from __future__ import annotations

from collections.abc import Sequence

from backtest.models import EquityPoint


def max_drawdown(equity_curve: Sequence[EquityPoint]) -> float:
    """Largest peak-to-trough decline in `equity_curve`, as a fraction in
    `[0.0, 1.0]`. `0.0` if equity never declined."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0].equity
    worst = 0.0
    for point in equity_curve:
        peak = max(peak, point.equity)
        if peak > 0:
            worst = max(worst, (peak - point.equity) / peak)
    return worst


__all__ = ["max_drawdown"]
