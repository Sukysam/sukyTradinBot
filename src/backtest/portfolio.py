"""`PortfolioEngine` -- mutable, stateful tracker of cash, open
positions, and equity across a replay. Deliberately separate from
`replay.py` (which drives the decision pipeline) so this bookkeeping can
be reused for paper trading later without dragging the replay loop
along with it -- per the technical lead's explicit recommendation.

Not a frozen contract: unlike `backtest.models`, nothing here is
serialized into a `BacktestResult` directly -- `PortfolioEngine` only
*produces* the `TradeRecord`/`EquityPoint` values that are.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from backtest.models import OpenPosition, TradeRecord
from execution.models import OrderSide
from risk.models import AccountState, PortfolioState, Position


@dataclass
class PortfolioEngine:
    cash: float
    _positions: dict[str, OpenPosition] = field(default_factory=dict, init=False)
    _equity_start_of_day: float = field(init=False, default=0.0)
    _equity_start_of_week: float = field(init=False, default=0.0)
    _equity_peak: float = field(init=False, default=0.0)
    _current_day: object = field(init=False, default=None)
    _current_week: object = field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.cash <= 0:
            raise ValueError(f"cash must be > 0, got {self.cash}")
        self._equity_start_of_day = self.cash
        self._equity_start_of_week = self.cash
        self._equity_peak = self.cash

    def equity(self, current_prices: Mapping[str, float]) -> float:
        return self.cash + sum(
            position.market_value(current_prices[symbol])
            for symbol, position in self._positions.items()
        )

    def on_new_bar(self, timestamp: datetime, current_prices: Mapping[str, float]) -> None:
        """Rolls the day/week start-of-period equity markers forward and
        updates the running peak -- called once per replay step, before
        that step's decision pipeline runs, so `snapshot()` reflects
        state as of `timestamp`."""
        day = timestamp.date()
        iso_year, iso_week, _ = timestamp.isocalendar()
        current_equity = self.equity(current_prices)

        if self._current_day != day:
            self._current_day = day
            self._equity_start_of_day = current_equity
        if self._current_week != (iso_year, iso_week):
            self._current_week = (iso_year, iso_week)
            self._equity_start_of_week = current_equity

        self._equity_peak = max(self._equity_peak, current_equity)

    def snapshot(
        self, current_prices: Mapping[str, float], *, sector_map: Mapping[str, str]
    ) -> PortfolioState:
        positions = tuple(
            Position(
                ticker=symbol,
                sector=sector_map.get(symbol, position.sector),
                market_value=position.market_value(current_prices[symbol]),
            )
            for symbol, position in self._positions.items()
        )
        return PortfolioState(
            equity=self.equity(current_prices),
            positions=positions,
            equity_start_of_day=self._equity_start_of_day,
            equity_start_of_week=self._equity_start_of_week,
            equity_peak=self._equity_peak,
        )

    def account_state(self) -> AccountState:
        """No margin modeled (invariant #5: long-only) -- buying power is
        exactly available cash."""
        return AccountState(buying_power=max(self.cash, 0.0))

    def open_or_add(
        self,
        *,
        symbol: str,
        sector: str,
        strategy_id: str,
        regime_id: int,
        timestamp: datetime,
        fill_price: float,
        quantity: int,
    ) -> None:
        """Opens a new position, or tops up an existing one at a
        weighted-average cost basis (the entry timestamp is kept from
        the original open -- average-cost accounting doesn't reset the
        holding-period clock on a top-up)."""
        self.cash -= fill_price * quantity
        existing = self._positions.get(symbol)
        if existing is None:
            self._positions[symbol] = OpenPosition(
                symbol=symbol,
                sector=sector,
                strategy_id=strategy_id,
                regime_id=regime_id,
                entry_timestamp=timestamp,
                entry_price=fill_price,
                quantity=quantity,
            )
            return

        total_quantity = existing.quantity + quantity
        weighted_price = (
            existing.entry_price * existing.quantity + fill_price * quantity
        ) / total_quantity
        self._positions[symbol] = OpenPosition(
            symbol=symbol,
            sector=existing.sector,
            strategy_id=existing.strategy_id,
            regime_id=existing.regime_id,
            entry_timestamp=existing.entry_timestamp,
            entry_price=weighted_price,
            quantity=total_quantity,
        )

    def reduce_or_close(
        self, *, symbol: str, timestamp: datetime, fill_price: float, quantity: int
    ) -> TradeRecord:
        """Reduces (or fully closes) an open position, returning the
        `TradeRecord` for the sold quantity. `quantity` is capped at the
        open position's size -- `router.py` already bounds a SELL this
        way, but this method never oversells regardless of caller
        behavior."""
        existing = self._positions.get(symbol)
        if existing is None:
            raise ValueError(f"no open position for {symbol!r} to reduce")

        sold_quantity = min(quantity, existing.quantity)
        self.cash += fill_price * sold_quantity

        pnl = (fill_price - existing.entry_price) * sold_quantity
        entry_notional = existing.entry_price * sold_quantity
        pnl_pct = pnl / entry_notional if entry_notional > 0 else 0.0

        trade = TradeRecord(
            symbol=symbol,
            strategy_id=existing.strategy_id,
            regime_id=existing.regime_id,
            side=OrderSide.BUY,
            entry_timestamp=existing.entry_timestamp,
            exit_timestamp=timestamp,
            entry_price=existing.entry_price,
            exit_price=fill_price,
            quantity=sold_quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            holding_period=timestamp - existing.entry_timestamp,
        )

        remaining_quantity = existing.quantity - sold_quantity
        if remaining_quantity > 0:
            self._positions[symbol] = OpenPosition(
                symbol=existing.symbol,
                sector=existing.sector,
                strategy_id=existing.strategy_id,
                regime_id=existing.regime_id,
                entry_timestamp=existing.entry_timestamp,
                entry_price=existing.entry_price,
                quantity=remaining_quantity,
            )
        else:
            del self._positions[symbol]

        return trade

    def open_quantity(self, symbol: str) -> int:
        position = self._positions.get(symbol)
        return position.quantity if position is not None else 0


__all__ = ["PortfolioEngine"]
