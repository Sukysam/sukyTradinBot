"""Performance metrics, grouped by concern rather than one large module
-- per the technical lead's explicit recommendation:

- `returns`: `cagr`, `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`
- `risk`: `max_drawdown`
- `exposure`: `exposure`, `turnover`
- `trade_quality`: `win_rate`, `profit_factor`, `average_holding_period`

`compute_metrics` is the one aggregating entry point `engine.py` calls to
get every metric `BacktestResult` needs in one dict.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from backtest.metrics import exposure as exposure_metrics
from backtest.metrics import returns as returns_metrics
from backtest.metrics import risk as risk_metrics
from backtest.metrics import trade_quality as trade_quality_metrics
from backtest.models import EquityPoint, TradeRecord


def compute_metrics(
    *,
    equity_curve: Sequence[EquityPoint],
    trade_log: Sequence[TradeRecord],
    initial_equity: float,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, Any]:
    final_equity = equity_curve[-1].equity if equity_curve else initial_equity
    cagr_value = returns_metrics.cagr(initial_equity, final_equity, start_date, end_date)
    max_drawdown_value = risk_metrics.max_drawdown(equity_curve)
    return {
        "cagr": cagr_value,
        "sharpe_ratio": returns_metrics.sharpe_ratio(equity_curve),
        "sortino_ratio": returns_metrics.sortino_ratio(equity_curve),
        "calmar_ratio": returns_metrics.calmar_ratio(cagr_value, max_drawdown_value),
        "max_drawdown": max_drawdown_value,
        "win_rate": trade_quality_metrics.win_rate(trade_log),
        "profit_factor": trade_quality_metrics.profit_factor(trade_log),
        "average_holding_period": trade_quality_metrics.average_holding_period(trade_log),
        "exposure": exposure_metrics.exposure(equity_curve, trade_log),
        "turnover": exposure_metrics.turnover(trade_log, equity_curve),
    }


__all__ = ["compute_metrics"]
