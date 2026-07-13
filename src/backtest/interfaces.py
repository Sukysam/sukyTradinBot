"""Protocol interfaces for the Backtesting & Validation layer's one
pluggable stage: fill simulation. ADR-014 deliberately leaves fill
realism (slippage, whether an order fills at all) as implementation
detail, not part of the frozen `BacktestResult` contract -- this
Protocol is what makes that swappable without touching `replay.py`.
"""

from __future__ import annotations

from typing import Protocol

from execution.models import OrderIntent
from market_data.models import Bar


class FillModel(Protocol):
    """Computes the price an `OrderIntent` fills at, given the next bar
    available after the decision was made. Never the same bar the
    decision was based on -- see `replay.py`'s next-bar-open convention
    and why it exists (avoiding look-ahead, invariant #1)."""

    def fill_price(self, intent: OrderIntent, next_bar: Bar) -> float: ...


__all__ = ["FillModel"]
