"""Return-based metrics: `cagr`, `sharpe_ratio`, `sortino_ratio`,
`calmar_ratio`. Grouped separately from risk/exposure/trade-quality
metrics per the technical lead's explicit "classify them into groups...
that tends to scale better" recommendation.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime

from backtest.models import EquityPoint

TRADING_DAYS_PER_YEAR = 252
DAYS_PER_YEAR = 365.25


def _period_returns(equity_curve: Sequence[EquityPoint]) -> list[float]:
    returns = []
    for prev_point, curr_point in zip(equity_curve, equity_curve[1:]):
        if prev_point.equity > 0:
            returns.append(curr_point.equity / prev_point.equity - 1.0)
    return returns


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def cagr(
    initial_equity: float, final_equity: float, start_date: datetime, end_date: datetime
) -> float:
    years = (end_date - start_date).days / DAYS_PER_YEAR
    if years <= 0 or initial_equity <= 0:
        return 0.0
    return float((final_equity / initial_equity) ** (1.0 / years) - 1.0)


def sharpe_ratio(
    equity_curve: Sequence[EquityPoint], *, periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> float:
    returns = _period_returns(equity_curve)
    if not returns:
        return 0.0
    std = _std(returns)
    if std == 0.0:
        # No return volatility at all -- not the same degenerate case
        # `calmar_ratio`/`profit_factor` document as `inf`; this codebase
        # has no precedent for an "infinitely good" Sharpe, so a flat
        # equity curve reports 0.0 (no signal), not inf.
        return 0.0
    mean = sum(returns) / len(returns)
    return (mean / std) * math.sqrt(periods_per_year)


def sortino_ratio(
    equity_curve: Sequence[EquityPoint], *, periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> float:
    returns = _period_returns(equity_curve)
    if not returns:
        return 0.0
    downside = [r for r in returns if r < 0.0]
    downside_std = _std(downside) if len(downside) > 1 else (abs(downside[0]) if downside else 0.0)
    if downside_std == 0.0:
        return 0.0
    mean = sum(returns) / len(returns)
    return (mean / downside_std) * math.sqrt(periods_per_year)


def calmar_ratio(cagr_value: float, max_drawdown_value: float) -> float:
    """`float("inf")` when `max_drawdown_value == 0.0` -- matches
    `risk.models.PortfolioState.gross_exposure_pct`'s existing
    inf-for-degenerate-denominator convention, per
    Standards/BacktestResult Contract.md."""
    if max_drawdown_value == 0.0:
        return float("inf")
    return cagr_value / max_drawdown_value


__all__ = [
    "DAYS_PER_YEAR",
    "TRADING_DAYS_PER_YEAR",
    "cagr",
    "calmar_ratio",
    "sharpe_ratio",
    "sortino_ratio",
]
