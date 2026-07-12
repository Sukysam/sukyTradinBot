from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from market_data.models import (
    Bar,
    CorporateAction,
    CorporateActionType,
    OrderBook,
    PriceLevel,
    Quote,
    Snapshot,
    Timeframe,
    Trade,
)

UTC_TS = datetime(2026, 6, 1, 9, 30, 0, tzinfo=timezone.utc)
NAIVE_TS = datetime(2026, 6, 1, 9, 30, 0)
NON_UTC_TS = datetime(2026, 6, 1, 9, 30, 0, tzinfo=timezone(timedelta(hours=-4)))


class TestBar:
    def test_valid_bar_constructs(self) -> None:
        bar = Bar(
            symbol="AAPL",
            timestamp=UTC_TS,
            timeframe=Timeframe.MIN_1,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
        )
        assert bar.symbol == "AAPL"
        assert bar.trade_count is None
        assert bar.vwap is None

    def test_rejects_naive_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            Bar(
                symbol="AAPL",
                timestamp=NAIVE_TS,
                timeframe=Timeframe.MIN_1,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000.0,
            )

    def test_rejects_non_utc_timestamp(self) -> None:
        with pytest.raises(ValueError, match="UTC"):
            Bar(
                symbol="AAPL",
                timestamp=NON_UTC_TS,
                timeframe=Timeframe.MIN_1,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000.0,
            )

    def test_rejects_negative_volume(self) -> None:
        with pytest.raises(ValueError, match="volume"):
            Bar(
                symbol="AAPL",
                timestamp=UTC_TS,
                timeframe=Timeframe.MIN_1,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=-1.0,
            )

    def test_rejects_high_below_open_close_low(self) -> None:
        with pytest.raises(ValueError, match="high"):
            Bar(
                symbol="AAPL",
                timestamp=UTC_TS,
                timeframe=Timeframe.MIN_1,
                open=100.0,
                high=99.5,  # below open
                low=99.0,
                close=100.5,
                volume=1000.0,
            )

    def test_rejects_low_above_open_close_high(self) -> None:
        with pytest.raises(ValueError, match="low"):
            Bar(
                symbol="AAPL",
                timestamp=UTC_TS,
                timeframe=Timeframe.MIN_1,
                open=100.0,
                high=101.0,
                low=100.2,  # above open
                close=100.5,
                volume=1000.0,
            )

    def test_is_frozen(self) -> None:
        bar = Bar(
            symbol="AAPL",
            timestamp=UTC_TS,
            timeframe=Timeframe.MIN_1,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
        )
        with pytest.raises(FrozenInstanceError):
            bar.close = 200.0  # type: ignore[misc]


class TestTrade:
    def test_valid_trade_constructs(self) -> None:
        trade = Trade(symbol="AAPL", timestamp=UTC_TS, price=100.0, size=10.0)
        assert trade.exchange == ""
        assert trade.conditions == ()

    def test_rejects_naive_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            Trade(symbol="AAPL", timestamp=NAIVE_TS, price=100.0, size=10.0)

    def test_rejects_zero_price(self) -> None:
        with pytest.raises(ValueError, match="price"):
            Trade(symbol="AAPL", timestamp=UTC_TS, price=0.0, size=10.0)

    def test_rejects_zero_size(self) -> None:
        with pytest.raises(ValueError, match="size"):
            Trade(symbol="AAPL", timestamp=UTC_TS, price=100.0, size=0.0)


class TestQuote:
    def test_valid_quote_constructs(self) -> None:
        quote = Quote(
            symbol="AAPL",
            timestamp=UTC_TS,
            bid_price=99.9,
            bid_size=100,
            ask_price=100.1,
            ask_size=100,
        )
        assert quote.bid_price < quote.ask_price

    def test_allows_crossed_quote(self) -> None:
        # Deliberately permitted -- see Quote's docstring.
        quote = Quote(
            symbol="AAPL",
            timestamp=UTC_TS,
            bid_price=100.5,
            bid_size=100,
            ask_price=100.0,
            ask_size=100,
        )
        assert quote.bid_price > quote.ask_price

    def test_rejects_negative_size(self) -> None:
        with pytest.raises(ValueError):
            Quote(
                symbol="AAPL",
                timestamp=UTC_TS,
                bid_price=99.9,
                bid_size=-1,
                ask_price=100.1,
                ask_size=100,
            )


class TestOrderBook:
    def test_best_bid_and_ask(self) -> None:
        book = OrderBook(
            symbol="AAPL",
            timestamp=UTC_TS,
            bids=(PriceLevel(price=99.9, size=100), PriceLevel(price=99.8, size=200)),
            asks=(PriceLevel(price=100.1, size=150),),
        )
        assert book.best_bid == PriceLevel(price=99.9, size=100)
        assert book.best_ask == PriceLevel(price=100.1, size=150)

    def test_empty_sides_return_none(self) -> None:
        book = OrderBook(symbol="AAPL", timestamp=UTC_TS, bids=(), asks=())
        assert book.best_bid is None
        assert book.best_ask is None

    def test_price_level_rejects_non_positive_price(self) -> None:
        with pytest.raises(ValueError):
            PriceLevel(price=0.0, size=100)


class TestSnapshot:
    def test_valid_snapshot_constructs(self) -> None:
        snapshot = Snapshot(symbol="AAPL", timestamp=UTC_TS)
        assert snapshot.latest_trade is None
        assert snapshot.latest_quote is None


class TestCorporateAction:
    def test_split_requires_ratio(self) -> None:
        with pytest.raises(ValueError, match="ratio"):
            CorporateAction(symbol="AAPL", ex_date=UTC_TS, action_type=CorporateActionType.SPLIT)

    def test_valid_split(self) -> None:
        action = CorporateAction(
            symbol="AAPL", ex_date=UTC_TS, action_type=CorporateActionType.SPLIT, ratio=2.0
        )
        assert action.ratio == 2.0

    def test_dividend_requires_cash_amount(self) -> None:
        with pytest.raises(ValueError, match="cash_amount"):
            CorporateAction(symbol="AAPL", ex_date=UTC_TS, action_type=CorporateActionType.DIVIDEND)

    def test_valid_dividend(self) -> None:
        action = CorporateAction(
            symbol="AAPL",
            ex_date=UTC_TS,
            action_type=CorporateActionType.DIVIDEND,
            cash_amount=0.25,
        )
        assert action.cash_amount == 0.25

    def test_rejects_non_positive_ratio(self) -> None:
        with pytest.raises(ValueError, match="ratio"):
            CorporateAction(
                symbol="AAPL", ex_date=UTC_TS, action_type=CorporateActionType.SPLIT, ratio=0.0
            )
