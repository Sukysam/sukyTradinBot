"""Alpaca live market data streaming provider.

Satisfies `market_data.interfaces.StreamingDataProvider` (which composes
`common.interfaces.Service`). Wraps `alpaca.data.live.stock.StockDataStream`
— confirmed against the actually-installed SDK (`alpaca-py==0.43.5`) to
have the same shape as `regime-trader/broker/news_streamer.py`'s existing
`NewsDataStream` usage: `.run()` is blocking and owns its own internal
event loop, so it must run inside `asyncio.to_thread`, never awaited
directly. This has not been exercised against a live Alpaca account in
this environment (no credentials available) — see
docs/engineering-handbook/Architecture/ADR/ADR-002-Market-Data.md's
verification note.

Adds three things `NewsStreamer` doesn't need: a reconnect-with-backoff
loop around `.run()` (a market data feed dropping and silently never
recovering is a materially worse failure mode than a dropped news feed —
see Milestone 2's "Disconnect recovery"/"Reconnect" deliverables), a
heartbeat/staleness check (`is_stale`), and per-message latency tracking
(`last_latency_seconds`).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Sequence
from datetime import datetime
from typing import Callable, Protocol

from alpaca.data.enums import DataFeed
from alpaca.data.live.stock import StockDataStream

from common.interfaces import Clock
from common.time import SystemClock
from market_data.auth import AlpacaCredentials, load_alpaca_credentials
from market_data.interfaces import BarHandler, QuoteHandler, TradeHandler
from market_data.models import Bar, Quote, Timeframe, Trade
from market_data.validation import normalize_timezone

logger = logging.getLogger(__name__)

DEFAULT_RECONNECT_INITIAL_DELAY_SECONDS = 1.0
DEFAULT_RECONNECT_MAX_DELAY_SECONDS = 60.0
DEFAULT_RECONNECT_BACKOFF_MULTIPLIER = 2.0
DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS = 60.0

AsyncSleep = Callable[[float], Awaitable[None]]


class _StreamClient(Protocol):
    """The narrow slice of `StockDataStream` this provider actually
    calls — a test fake only needs to implement this, not the whole SDK
    client.
    """

    def subscribe_bars(self, handler: Callable[..., Awaitable[None]], *symbols: str) -> None: ...
    def subscribe_trades(self, handler: Callable[..., Awaitable[None]], *symbols: str) -> None: ...
    def subscribe_quotes(self, handler: Callable[..., Awaitable[None]], *symbols: str) -> None: ...
    def run(self) -> None: ...
    def stop(self) -> None: ...


def _default_stream_client(credentials: AlpacaCredentials) -> StockDataStream:
    return StockDataStream(
        api_key=credentials.api_key, secret_key=credentials.secret_key, feed=DataFeed.IEX
    )


class AlpacaStreamingProvider:
    """Satisfies `StreamingDataProvider`. See module docstring."""

    def __init__(
        self,
        client: _StreamClient | None = None,
        *,
        credentials: AlpacaCredentials | None = None,
        clock: Clock | None = None,
        sleep: AsyncSleep = asyncio.sleep,
        reconnect_initial_delay_seconds: float = DEFAULT_RECONNECT_INITIAL_DELAY_SECONDS,
        reconnect_max_delay_seconds: float = DEFAULT_RECONNECT_MAX_DELAY_SECONDS,
        reconnect_backoff_multiplier: float = DEFAULT_RECONNECT_BACKOFF_MULTIPLIER,
        heartbeat_stale_after_seconds: float = DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS,
    ) -> None:
        self._client: _StreamClient = client or _default_stream_client(
            credentials or load_alpaca_credentials()
        )
        self._clock = clock or SystemClock()
        self._sleep = sleep
        self._reconnect_initial_delay_seconds = reconnect_initial_delay_seconds
        self._reconnect_max_delay_seconds = reconnect_max_delay_seconds
        self._reconnect_backoff_multiplier = reconnect_backoff_multiplier
        self._heartbeat_stale_after_seconds = heartbeat_stale_after_seconds

        self._last_message_at: datetime | None = None
        self._last_latency_seconds: float | None = None
        self._stop_requested = False
        self.reconnect_count = 0

    # ---- StreamingDataProvider ------------------------------------------

    def subscribe_bars(self, symbols: Sequence[str], handler: BarHandler) -> None:
        async def _wrapped(raw: object) -> None:
            bar = _to_bar(raw)
            self._record_message(bar.timestamp)
            await handler(bar)

        self._client.subscribe_bars(_wrapped, *symbols)

    def subscribe_trades(self, symbols: Sequence[str], handler: TradeHandler) -> None:
        async def _wrapped(raw: object) -> None:
            trade = _to_trade(raw)
            self._record_message(trade.timestamp)
            await handler(trade)

        self._client.subscribe_trades(_wrapped, *symbols)

    def subscribe_quotes(self, symbols: Sequence[str], handler: QuoteHandler) -> None:
        async def _wrapped(raw: object) -> None:
            quote = _to_quote(raw)
            self._record_message(quote.timestamp)
            await handler(quote)

        self._client.subscribe_quotes(_wrapped, *symbols)

    def last_message_at(self) -> datetime | None:
        return self._last_message_at

    # ---- heartbeat / latency ---------------------------------------------

    def _record_message(self, event_timestamp: datetime) -> None:
        now = self._clock.now()
        self._last_message_at = now
        self._last_latency_seconds = (now - event_timestamp).total_seconds()

    @property
    def last_latency_seconds(self) -> float | None:
        """Seconds between the most recent message's own event timestamp
        and the local time it was received/processed. `None` until the
        first message arrives.
        """
        return self._last_latency_seconds

    def is_stale(self) -> bool:
        """`True` if a message has previously arrived but none has arrived
        within `heartbeat_stale_after_seconds`. Returns `False` (not
        "stale", but not confirmed healthy either) if no message has ever
        arrived — that's a "not yet connected" state, distinct from a
        connection that went quiet after working.
        """
        if self._last_message_at is None:
            return False
        elapsed = (self._clock.now() - self._last_message_at).total_seconds()
        return elapsed > self._heartbeat_stale_after_seconds

    # ---- Service (start/stop lifecycle) ----------------------------------

    async def start(self) -> None:
        """Run the stream, reconnecting with exponential backoff (capped
        at `reconnect_max_delay_seconds`) on any disconnect, until `stop()`
        is called. `self._client.run()` is blocking and owns its own
        event loop (confirmed by SDK inspection, matching
        `NewsStreamer.start()`'s existing rationale in `regime-trader/`),
        so it always runs via `asyncio.to_thread`, never awaited directly.
        """
        self._stop_requested = False
        delay = self._reconnect_initial_delay_seconds

        while not self._stop_requested:
            try:
                await asyncio.to_thread(self._client.run)
                break  # run() returned without raising: assume stop() caused it
            except Exception:
                if self._stop_requested:
                    break
                self.reconnect_count += 1
                logger.warning(
                    "Streaming connection lost (reconnect attempt %d), retrying in %.1fs",
                    self.reconnect_count,
                    delay,
                    exc_info=True,
                )
                await self._sleep(delay)
                delay = min(
                    delay * self._reconnect_backoff_multiplier, self._reconnect_max_delay_seconds
                )

    async def stop(self) -> None:
        """Idempotent: safe to call even if `start()` was never called or
        has already returned.
        """
        self._stop_requested = True
        self._client.stop()


def _to_bar(raw: object) -> Bar:
    return Bar(
        symbol=raw.symbol,  # type: ignore[attr-defined]
        timestamp=normalize_timezone(raw.timestamp),  # type: ignore[attr-defined]
        timeframe=Timeframe.MIN_1,  # StockDataStream.subscribe_bars delivers 1-minute aggregates
        open=float(raw.open),  # type: ignore[attr-defined]
        high=float(raw.high),  # type: ignore[attr-defined]
        low=float(raw.low),  # type: ignore[attr-defined]
        close=float(raw.close),  # type: ignore[attr-defined]
        volume=float(raw.volume),  # type: ignore[attr-defined]
        trade_count=(
            int(raw.trade_count)  # type: ignore[attr-defined]
            if getattr(raw, "trade_count", None) is not None
            else None
        ),
        vwap=(float(raw.vwap) if getattr(raw, "vwap", None) is not None else None),  # type: ignore[attr-defined]
    )


def _to_trade(raw: object) -> Trade:
    return Trade(
        symbol=raw.symbol,  # type: ignore[attr-defined]
        timestamp=normalize_timezone(raw.timestamp),  # type: ignore[attr-defined]
        price=float(raw.price),  # type: ignore[attr-defined]
        size=float(raw.size),  # type: ignore[attr-defined]
        exchange=str(getattr(raw, "exchange", "") or ""),
        trade_id=str(getattr(raw, "id", "") or ""),
        conditions=tuple(getattr(raw, "conditions", None) or ()),
    )


def _to_quote(raw: object) -> Quote:
    return Quote(
        symbol=raw.symbol,  # type: ignore[attr-defined]
        timestamp=normalize_timezone(raw.timestamp),  # type: ignore[attr-defined]
        bid_price=float(raw.bid_price),  # type: ignore[attr-defined]
        bid_size=float(raw.bid_size),  # type: ignore[attr-defined]
        ask_price=float(raw.ask_price),  # type: ignore[attr-defined]
        ask_size=float(raw.ask_size),  # type: ignore[attr-defined]
        bid_exchange=str(getattr(raw, "bid_exchange", "") or ""),
        ask_exchange=str(getattr(raw, "ask_exchange", "") or ""),
    )


__all__ = ["AlpacaStreamingProvider"]
