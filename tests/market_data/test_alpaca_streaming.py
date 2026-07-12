from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Callable

import pytest

from common.time import FixedClock
from market_data.models import Bar, Quote, Trade
from market_data.providers.alpaca_streaming import AlpacaStreamingProvider

UTC = timezone.utc

_RawHandler = Callable[[object], Awaitable[None]]


async def _wait_until(
    predicate: Callable[[], bool], timeout: float = 2.0, interval: float = 0.01
) -> None:
    """Poll `predicate` until it's truthy or `timeout` elapses -- avoids
    guessing a fixed sleep duration for background-thread work to finish.
    """
    elapsed = 0.0
    while not predicate():
        if elapsed >= timeout:
            raise AssertionError(f"condition not met within {timeout}s")
        await asyncio.sleep(interval)
        elapsed += interval


class _FakeStreamClient:
    """Stands in for `alpaca.data.live.stock.StockDataStream` -- the "mock
    websocket" this milestone's test suite is built around. `run()` mimics
    the real SDK's blocking behavior: it either raises (simulating a
    dropped connection) per `run_side_effects`, or blocks until `stop()`
    is called (simulating a healthy, long-lived connection), exactly like
    the real client would when run via `asyncio.to_thread`.
    """

    def __init__(self, run_side_effects: list[Exception | None] | None = None) -> None:
        self.run_calls = 0
        self.stop_calls = 0
        self._run_side_effects = run_side_effects or []
        self._stop_event = threading.Event()
        self.bar_handler: _RawHandler | None = None
        self.trade_handler: _RawHandler | None = None
        self.quote_handler: _RawHandler | None = None
        self.subscribed_bar_symbols: tuple[str, ...] = ()

    def subscribe_bars(self, handler: _RawHandler, *symbols: str) -> None:
        self.bar_handler = handler
        self.subscribed_bar_symbols = symbols

    def subscribe_trades(self, handler: _RawHandler, *symbols: str) -> None:
        self.trade_handler = handler

    def subscribe_quotes(self, handler: _RawHandler, *symbols: str) -> None:
        self.quote_handler = handler

    def run(self) -> None:
        idx = self.run_calls
        self.run_calls += 1
        if idx < len(self._run_side_effects):
            effect = self._run_side_effects[idx]
            if effect is not None:
                raise effect
            return
        self._stop_event.wait(timeout=5.0)

    def stop(self) -> None:
        self.stop_calls += 1
        self._stop_event.set()


async def _fire_bar(client: _FakeStreamClient, raw: object) -> None:
    assert client.bar_handler is not None, "subscribe_bars must be called first"
    await client.bar_handler(raw)


async def _fire_trade(client: _FakeStreamClient, raw: object) -> None:
    assert client.trade_handler is not None, "subscribe_trades must be called first"
    await client.trade_handler(raw)


async def _fire_quote(client: _FakeStreamClient, raw: object) -> None:
    assert client.quote_handler is not None, "subscribe_quotes must be called first"
    await client.quote_handler(raw)


def _raw_bar(ts: datetime, close: float = 100.0) -> object:
    return SimpleNamespace(
        symbol="AAPL",
        timestamp=ts,
        open=close - 0.5,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
        trade_count=5,
        vwap=close + 0.1,
    )


def _raw_trade(ts: datetime, price: float = 100.0) -> object:
    return SimpleNamespace(
        symbol="AAPL", timestamp=ts, price=price, size=10.0, exchange="V", id="1", conditions=["@"]
    )


def _raw_quote(ts: datetime) -> object:
    return SimpleNamespace(
        symbol="AAPL",
        timestamp=ts,
        bid_price=99.9,
        bid_size=100.0,
        ask_price=100.1,
        ask_size=100.0,
        bid_exchange="V",
        ask_exchange="V",
    )


class TestSubscriptions:
    """Exercises the mock websocket's subscribe_bars/trades/quotes wiring."""

    async def test_subscribe_bars_converts_and_forwards_to_handler(self) -> None:
        client = _FakeStreamClient()
        provider = AlpacaStreamingProvider(client=client)
        received: list[Bar] = []

        async def handler(bar: Bar) -> None:
            received.append(bar)

        provider.subscribe_bars(["AAPL"], handler)
        assert client.subscribed_bar_symbols == ("AAPL",)

        ts = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        await _fire_bar(client, _raw_bar(ts, close=101.0))

        assert len(received) == 1
        assert received[0].symbol == "AAPL"
        assert received[0].close == 101.0

    async def test_subscribe_trades_converts_and_forwards_to_handler(self) -> None:
        client = _FakeStreamClient()
        provider = AlpacaStreamingProvider(client=client)
        received: list[Trade] = []

        async def handler(trade: Trade) -> None:
            received.append(trade)

        provider.subscribe_trades(["AAPL"], handler)
        await _fire_trade(client, _raw_trade(datetime(2026, 6, 1, tzinfo=UTC)))

        assert received[0].price == 100.0
        assert received[0].conditions == ("@",)

    async def test_subscribe_quotes_converts_and_forwards_to_handler(self) -> None:
        client = _FakeStreamClient()
        provider = AlpacaStreamingProvider(client=client)
        received: list[Quote] = []

        async def handler(quote: Quote) -> None:
            received.append(quote)

        provider.subscribe_quotes(["AAPL"], handler)
        await _fire_quote(client, _raw_quote(datetime(2026, 6, 1, tzinfo=UTC)))

        assert received[0].bid_price == 99.9
        assert received[0].ask_price == 100.1


class TestHeartbeat:
    def test_not_stale_before_any_message(self) -> None:
        provider = AlpacaStreamingProvider(client=_FakeStreamClient())
        assert provider.is_stale() is False
        assert provider.last_message_at() is None

    async def test_not_stale_within_threshold(self) -> None:
        clock = FixedClock(datetime(2026, 6, 1, 9, 30, tzinfo=UTC))
        client = _FakeStreamClient()
        provider = AlpacaStreamingProvider(
            client=client, clock=clock, heartbeat_stale_after_seconds=60.0
        )
        received: list[Bar] = []

        async def handler(bar: Bar) -> None:
            received.append(bar)

        provider.subscribe_bars(["AAPL"], handler)
        await _fire_bar(client, _raw_bar(clock.now()))

        clock.advance(seconds=30)
        assert provider.is_stale() is False

    async def test_stale_after_threshold_with_no_new_messages(self) -> None:
        clock = FixedClock(datetime(2026, 6, 1, 9, 30, tzinfo=UTC))
        client = _FakeStreamClient()
        provider = AlpacaStreamingProvider(
            client=client, clock=clock, heartbeat_stale_after_seconds=60.0
        )

        async def handler(bar: Bar) -> None:
            pass

        provider.subscribe_bars(["AAPL"], handler)
        await _fire_bar(client, _raw_bar(clock.now()))

        clock.advance(seconds=61)
        assert provider.is_stale() is True


class TestLatency:
    async def test_latency_is_gap_between_event_timestamp_and_receipt(self) -> None:
        event_time = datetime(2026, 6, 1, 9, 30, 0, tzinfo=UTC)
        clock = FixedClock(event_time)
        client = _FakeStreamClient()
        provider = AlpacaStreamingProvider(client=client, clock=clock)

        async def handler(bar: Bar) -> None:
            pass

        provider.subscribe_bars(["AAPL"], handler)

        assert provider.last_latency_seconds is None

        clock.advance(seconds=2.5)  # simulate the gap between event and local receipt
        await _fire_bar(client, _raw_bar(event_time))

        assert provider.last_latency_seconds == pytest.approx(2.5)


class TestReconnect:
    """Exercises disconnect recovery / reconnect / backoff — the failure
    mode this provider adds on top of `NewsStreamer`'s pattern.
    """

    async def test_healthy_connection_calls_run_once(self) -> None:
        client = _FakeStreamClient()
        provider = AlpacaStreamingProvider(client=client)

        task = asyncio.create_task(provider.start())
        await _wait_until(lambda: client.run_calls >= 1)
        await provider.stop()
        await asyncio.wait_for(task, timeout=2.0)

        assert client.run_calls == 1
        assert client.stop_calls == 1
        assert provider.reconnect_count == 0

    async def test_disconnect_triggers_reconnect(self) -> None:
        client = _FakeStreamClient(run_side_effects=[ConnectionError("dropped")])
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        provider = AlpacaStreamingProvider(client=client, sleep=fake_sleep)

        task = asyncio.create_task(provider.start())
        await _wait_until(lambda: client.run_calls >= 2)
        await provider.stop()
        await asyncio.wait_for(task, timeout=2.0)

        assert provider.reconnect_count == 1
        assert sleeps == [pytest.approx(1.0)]

    async def test_reconnect_backoff_increases_with_repeated_failures(self) -> None:
        client = _FakeStreamClient(
            run_side_effects=[ConnectionError("a"), ConnectionError("b"), ConnectionError("c")]
        )
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        provider = AlpacaStreamingProvider(
            client=client,
            sleep=fake_sleep,
            reconnect_initial_delay_seconds=1.0,
            reconnect_backoff_multiplier=2.0,
            reconnect_max_delay_seconds=60.0,
        )

        task = asyncio.create_task(provider.start())
        await _wait_until(lambda: client.run_calls >= 4)
        await provider.stop()
        await asyncio.wait_for(task, timeout=2.0)

        assert provider.reconnect_count == 3
        assert sleeps == [pytest.approx(1.0), pytest.approx(2.0), pytest.approx(4.0)]

    async def test_backoff_caps_at_max_delay(self) -> None:
        client = _FakeStreamClient(
            run_side_effects=[ConnectionError("a"), ConnectionError("b"), ConnectionError("c")]
        )
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        provider = AlpacaStreamingProvider(
            client=client,
            sleep=fake_sleep,
            reconnect_initial_delay_seconds=10.0,
            reconnect_backoff_multiplier=3.0,
            reconnect_max_delay_seconds=15.0,
        )

        task = asyncio.create_task(provider.start())
        await _wait_until(lambda: client.run_calls >= 4)
        await provider.stop()
        await asyncio.wait_for(task, timeout=2.0)

        assert sleeps == [pytest.approx(10.0), pytest.approx(15.0), pytest.approx(15.0)]

    async def test_stop_is_idempotent(self) -> None:
        client = _FakeStreamClient()
        provider = AlpacaStreamingProvider(client=client)
        await provider.stop()
        await provider.stop()
        assert client.stop_calls == 2  # each call still forwards to the client, no error raised

    async def test_stop_before_start_does_not_raise(self) -> None:
        provider = AlpacaStreamingProvider(client=_FakeStreamClient())
        await provider.stop()  # must not raise
