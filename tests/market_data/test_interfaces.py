from __future__ import annotations

from datetime import datetime, timezone

from market_data.interfaces import (
    CorporateActionsProvider,
    HistoricalDataProvider,
    MarketDataStorage,
    StreamingDataProvider,
)
from market_data.models import Bar, CorporateAction, Timeframe


class _FakeHistoricalProvider:
    def get_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: Timeframe
    ) -> list[Bar]:
        return []


def test_fake_satisfies_historical_data_provider_protocol() -> None:
    assert isinstance(_FakeHistoricalProvider(), HistoricalDataProvider)


class _FakeCorporateActionsProvider:
    def get_corporate_actions(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[CorporateAction]:
        return []


def test_fake_satisfies_corporate_actions_provider_protocol() -> None:
    assert isinstance(_FakeCorporateActionsProvider(), CorporateActionsProvider)


class _FakeStorage:
    def write_bars(self, bars: object) -> None:
        pass

    def read_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: Timeframe
    ) -> list[Bar]:
        return []

    def latest_timestamp(self, symbol: str, timeframe: Timeframe) -> datetime | None:
        return None


def test_fake_satisfies_market_data_storage_protocol() -> None:
    assert isinstance(_FakeStorage(), MarketDataStorage)


class _FakeStreamingProvider:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    def subscribe_bars(self, symbols: object, handler: object) -> None:
        pass

    def subscribe_trades(self, symbols: object, handler: object) -> None:
        pass

    def subscribe_quotes(self, symbols: object, handler: object) -> None:
        pass

    def last_message_at(self) -> datetime | None:
        return datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_fake_satisfies_streaming_data_provider_protocol() -> None:
    provider: StreamingDataProvider = _FakeStreamingProvider()
    assert isinstance(provider, StreamingDataProvider)
    assert provider.last_message_at() is not None


async def test_streaming_provider_lifecycle_is_awaitable() -> None:
    provider = _FakeStreamingProvider()
    await provider.start()
    assert provider.started is True
    await provider.stop()
    assert provider.stopped is True
