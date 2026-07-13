"""Tests for `backtest.portfolio.PortfolioEngine`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backtest.portfolio import PortfolioEngine

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)  # a Monday


class TestConstruction:
    def test_rejects_non_positive_cash(self) -> None:
        with pytest.raises(ValueError, match="cash"):
            PortfolioEngine(cash=0.0)

    def test_equity_starts_markers_at_initial_cash(self) -> None:
        engine = PortfolioEngine(cash=100_000.0)
        snapshot = engine.snapshot({}, sector_map={})
        assert snapshot.equity_start_of_day == 100_000.0
        assert snapshot.equity_start_of_week == 100_000.0
        assert snapshot.equity_peak == 100_000.0


class TestEquity:
    def test_equity_is_cash_when_no_positions(self) -> None:
        engine = PortfolioEngine(cash=50_000.0)
        assert engine.equity({}) == 50_000.0

    def test_equity_includes_open_positions_marked_at_current_price(self) -> None:
        engine = PortfolioEngine(cash=50_000.0)
        engine.open_or_add(
            symbol="TEST",
            sector="Tech",
            strategy_id="growth_v1",
            regime_id=0,
            timestamp=T0,
            fill_price=100.0,
            quantity=100,
        )
        # cash reduced by 100*100=10,000 -> 40,000 remaining
        assert engine.equity({"TEST": 100.0}) == 40_000.0 + 100 * 100.0
        assert engine.equity({"TEST": 120.0}) == 40_000.0 + 100 * 120.0


class TestOpenOrAdd:
    def test_open_creates_a_new_position(self) -> None:
        engine = PortfolioEngine(cash=100_000.0)
        engine.open_or_add(
            symbol="TEST",
            sector="Tech",
            strategy_id="growth_v1",
            regime_id=0,
            timestamp=T0,
            fill_price=100.0,
            quantity=50,
        )
        assert engine.open_quantity("TEST") == 50
        assert engine.cash == 100_000.0 - 50 * 100.0

    def test_add_to_existing_position_uses_weighted_average_price(self) -> None:
        engine = PortfolioEngine(cash=100_000.0)
        engine.open_or_add(
            symbol="TEST",
            sector="Tech",
            strategy_id="growth_v1",
            regime_id=0,
            timestamp=T0,
            fill_price=100.0,
            quantity=100,
        )
        engine.open_or_add(
            symbol="TEST",
            sector="Tech",
            strategy_id="growth_v1",
            regime_id=0,
            timestamp=T0 + timedelta(days=1),
            fill_price=120.0,
            quantity=100,
        )
        assert engine.open_quantity("TEST") == 200
        # weighted avg: (100*100 + 100*120) / 200 = 110
        trade = engine.reduce_or_close(
            symbol="TEST", timestamp=T0 + timedelta(days=10), fill_price=110.0, quantity=200
        )
        assert trade.entry_price == pytest.approx(110.0)
        assert trade.entry_timestamp == T0  # kept from the original open


class TestReduceOrClose:
    def test_full_close_removes_the_position(self) -> None:
        engine = PortfolioEngine(cash=100_000.0)
        engine.open_or_add(
            symbol="TEST",
            sector="Tech",
            strategy_id="growth_v1",
            regime_id=0,
            timestamp=T0,
            fill_price=100.0,
            quantity=100,
        )
        trade = engine.reduce_or_close(
            symbol="TEST", timestamp=T0 + timedelta(days=5), fill_price=110.0, quantity=100
        )
        assert engine.open_quantity("TEST") == 0
        assert trade.pnl == pytest.approx(1000.0)
        assert trade.pnl_pct == pytest.approx(0.1)
        assert trade.holding_period == timedelta(days=5)

    def test_partial_reduce_keeps_the_remainder_open_at_same_entry_price(self) -> None:
        engine = PortfolioEngine(cash=100_000.0)
        engine.open_or_add(
            symbol="TEST",
            sector="Tech",
            strategy_id="growth_v1",
            regime_id=0,
            timestamp=T0,
            fill_price=100.0,
            quantity=100,
        )
        trade = engine.reduce_or_close(
            symbol="TEST", timestamp=T0 + timedelta(days=5), fill_price=110.0, quantity=40
        )
        assert trade.quantity == 40
        assert engine.open_quantity("TEST") == 60

    def test_reduce_quantity_is_capped_at_open_quantity(self) -> None:
        engine = PortfolioEngine(cash=100_000.0)
        engine.open_or_add(
            symbol="TEST",
            sector="Tech",
            strategy_id="growth_v1",
            regime_id=0,
            timestamp=T0,
            fill_price=100.0,
            quantity=50,
        )
        trade = engine.reduce_or_close(
            symbol="TEST", timestamp=T0 + timedelta(days=1), fill_price=105.0, quantity=999
        )
        assert trade.quantity == 50
        assert engine.open_quantity("TEST") == 0

    def test_raises_when_no_open_position(self) -> None:
        engine = PortfolioEngine(cash=100_000.0)
        with pytest.raises(ValueError, match="no open position"):
            engine.reduce_or_close(symbol="TEST", timestamp=T0, fill_price=100.0, quantity=10)


class TestOnNewBar:
    def test_rolls_start_of_day_marker_on_day_change(self) -> None:
        engine = PortfolioEngine(cash=100_000.0)
        engine.open_or_add(
            symbol="TEST",
            sector="Tech",
            strategy_id="growth_v1",
            regime_id=0,
            timestamp=T0,
            fill_price=100.0,
            quantity=100,
        )
        engine.on_new_bar(T0, {"TEST": 100.0})
        next_day = T0 + timedelta(days=1)
        engine.on_new_bar(next_day, {"TEST": 130.0})
        snapshot = engine.snapshot({"TEST": 130.0}, sector_map={})
        assert snapshot.equity_start_of_day == 90_000.0 + 100 * 130.0

    def test_peak_never_decreases(self) -> None:
        engine = PortfolioEngine(cash=100_000.0)
        engine.on_new_bar(T0, {})
        engine.on_new_bar(T0 + timedelta(days=1), {})
        snapshot = engine.snapshot({}, sector_map={})
        assert snapshot.equity_peak == 100_000.0

    def test_start_of_week_resets_on_iso_week_change(self) -> None:
        engine = PortfolioEngine(cash=100_000.0)
        monday = T0  # 2024-01-01 is a Monday
        next_monday = monday + timedelta(days=7)
        engine.on_new_bar(monday, {})
        engine.on_new_bar(next_monday, {})
        snapshot = engine.snapshot({}, sector_map={})
        assert snapshot.equity_start_of_week == 100_000.0


class TestAccountState:
    def test_buying_power_equals_cash(self) -> None:
        engine = PortfolioEngine(cash=42_000.0)
        assert engine.account_state().buying_power == 42_000.0


class TestSnapshot:
    def test_sector_map_overrides_stored_sector(self) -> None:
        engine = PortfolioEngine(cash=100_000.0)
        engine.open_or_add(
            symbol="TEST",
            sector="",
            strategy_id="growth_v1",
            regime_id=0,
            timestamp=T0,
            fill_price=100.0,
            quantity=10,
        )
        snapshot = engine.snapshot({"TEST": 100.0}, sector_map={"TEST": "Technology"})
        assert snapshot.positions[0].sector == "Technology"
