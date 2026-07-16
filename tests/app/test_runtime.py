"""Tests for `app.runtime.MarketDataLoop`."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

import pytest

from app.runtime import MarketDataLoop
from common.time import FixedClock
from market_data.errors import ProviderConnectionError
from market_data.models import Bar, Timeframe

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _bar(symbol: str, ts: datetime, close: float = 100.0) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=ts,
        timeframe=Timeframe.DAY_1,
        open=close - 1,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
    )


class _FakeProvider:
    """Returns one pre-scripted list of bars per call, in order,
    ignoring `start`/`end`/`timeframe` -- the loop's own dedup logic is
    what's under test, not the provider's window semantics (already
    covered by `tests/market_data/test_alpaca_historical.py`)."""

    def __init__(
        self,
        responses: list[list[Bar]] | None = None,
        raise_on_calls: set[int] | None = None,
    ) -> None:
        self.calls = 0
        self._responses = responses or []
        self._raise_on_calls = raise_on_calls or set()

    def get_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: Timeframe
    ) -> list[Bar]:
        self.calls += 1
        if self.calls in self._raise_on_calls:
            raise ProviderConnectionError("simulated failure")
        idx = self.calls - 1
        return self._responses[idx] if idx < len(self._responses) else []


def _stopping_sleep(
    loop_holder: list[MarketDataLoop], stop_after: int
) -> Callable[[float], Awaitable[None]]:
    calls = 0

    async def _sleep(_seconds: float) -> None:
        nonlocal calls
        calls += 1
        if calls >= stop_after:
            await loop_holder[0].stop()

    return _sleep


def _bar_events(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if getattr(r, "event", None) == "bar_received"]


class TestMarketDataLoop:
    async def test_logs_new_bars_and_stops_after_n_cycles(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider = _FakeProvider(responses=[[_bar("AAPL", T0)]])
        loop_holder: list[MarketDataLoop] = []
        loop = MarketDataLoop(
            provider,
            symbols=["AAPL"],
            timeframe=Timeframe.DAY_1,
            poll_interval_seconds=1.0,
            lookback=timedelta(days=5),
            clock=FixedClock(T0),
            sleep=_stopping_sleep(loop_holder, stop_after=1),
        )
        loop_holder.append(loop)

        with caplog.at_level(logging.INFO, logger="app.runtime"):
            await loop.start()

        events = _bar_events(caplog.records)
        assert len(events) == 1
        assert events[0].symbol == "AAPL"  # type: ignore[attr-defined]

    async def test_does_not_log_the_same_bar_twice_across_polls(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        bar = _bar("AAPL", T0)
        provider = _FakeProvider(responses=[[bar], [bar]])
        loop_holder: list[MarketDataLoop] = []
        loop = MarketDataLoop(
            provider,
            symbols=["AAPL"],
            timeframe=Timeframe.DAY_1,
            poll_interval_seconds=1.0,
            lookback=timedelta(days=5),
            clock=FixedClock(T0),
            sleep=_stopping_sleep(loop_holder, stop_after=2),
        )
        loop_holder.append(loop)

        with caplog.at_level(logging.INFO, logger="app.runtime"):
            await loop.start()

        assert len(_bar_events(caplog.records)) == 1

    async def test_logs_a_second_bar_with_a_later_timestamp(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        first = _bar("AAPL", T0)
        second = _bar("AAPL", T0 + timedelta(days=1))
        provider = _FakeProvider(responses=[[first], [first, second]])
        loop_holder: list[MarketDataLoop] = []
        loop = MarketDataLoop(
            provider,
            symbols=["AAPL"],
            timeframe=Timeframe.DAY_1,
            poll_interval_seconds=1.0,
            lookback=timedelta(days=5),
            clock=FixedClock(T0),
            sleep=_stopping_sleep(loop_holder, stop_after=2),
        )
        loop_holder.append(loop)

        with caplog.at_level(logging.INFO, logger="app.runtime"):
            await loop.start()

        assert len(_bar_events(caplog.records)) == 2

    async def test_fetch_failure_is_logged_and_does_not_stop_the_loop(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider = _FakeProvider(responses=[[], []], raise_on_calls={1})
        loop_holder: list[MarketDataLoop] = []
        loop = MarketDataLoop(
            provider,
            symbols=["AAPL"],
            timeframe=Timeframe.DAY_1,
            poll_interval_seconds=1.0,
            lookback=timedelta(days=5),
            clock=FixedClock(T0),
            sleep=_stopping_sleep(loop_holder, stop_after=2),
        )
        loop_holder.append(loop)

        with caplog.at_level(logging.WARNING, logger="app.runtime"):
            await loop.start()

        assert provider.calls == 2
        failures = [
            r for r in caplog.records if getattr(r, "event", None) == "market_data_fetch_failed"
        ]
        assert len(failures) == 1

    async def test_polls_every_symbol_each_cycle(self) -> None:
        provider = _FakeProvider(responses=[[_bar("AAPL", T0)], [_bar("MSFT", T0)]])
        loop_holder: list[MarketDataLoop] = []
        loop = MarketDataLoop(
            provider,
            symbols=["AAPL", "MSFT"],
            timeframe=Timeframe.DAY_1,
            poll_interval_seconds=1.0,
            lookback=timedelta(days=5),
            clock=FixedClock(T0),
            sleep=_stopping_sleep(loop_holder, stop_after=1),
        )
        loop_holder.append(loop)

        await loop.start()

        assert provider.calls == 2

    async def test_stop_is_idempotent(self) -> None:
        provider = _FakeProvider()
        loop = MarketDataLoop(
            provider,
            symbols=["AAPL"],
            timeframe=Timeframe.DAY_1,
            poll_interval_seconds=1.0,
            lookback=timedelta(days=5),
            clock=FixedClock(T0),
        )
        await loop.stop()
        await loop.stop()  # must not raise

    async def test_on_bar_is_called_once_per_new_bar(self) -> None:
        bar = _bar("AAPL", T0)
        provider = _FakeProvider(responses=[[bar]])
        received: list[Bar] = []
        loop_holder: list[MarketDataLoop] = []
        loop = MarketDataLoop(
            provider,
            symbols=["AAPL"],
            timeframe=Timeframe.DAY_1,
            poll_interval_seconds=1.0,
            lookback=timedelta(days=5),
            clock=FixedClock(T0),
            sleep=_stopping_sleep(loop_holder, stop_after=1),
            on_bar=received.append,
        )
        loop_holder.append(loop)

        await loop.start()

        assert received == [bar]

    async def test_on_bar_failure_is_logged_and_does_not_stop_the_loop(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        first = _bar("AAPL", T0)
        second = _bar("AAPL", T0 + timedelta(days=1))
        provider = _FakeProvider(responses=[[first], [first, second]])
        loop_holder: list[MarketDataLoop] = []

        def _boom(_bar: Bar) -> None:
            raise RuntimeError("simulated callback failure")

        loop = MarketDataLoop(
            provider,
            symbols=["AAPL"],
            timeframe=Timeframe.DAY_1,
            poll_interval_seconds=1.0,
            lookback=timedelta(days=5),
            clock=FixedClock(T0),
            sleep=_stopping_sleep(loop_holder, stop_after=2),
            on_bar=_boom,
        )
        loop_holder.append(loop)

        with caplog.at_level(logging.INFO, logger="app.runtime"):
            await loop.start()

        failures = [
            r for r in caplog.records if getattr(r, "event", None) == "on_bar_callback_failed"
        ]
        assert len(failures) == 2
        assert len(_bar_events(caplog.records)) == 2
