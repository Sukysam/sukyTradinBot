"""`MarketDataLoop` -- Phase A of the runtime this platform has never
had: connect, fetch bars on an interval, normalize, log, repeat. No
features, no HMM, no trading -- see
docs/engineering-handbook/Architecture/ADR/ADR-027-Runtime-Market-Data-Loop-Design.md.

Implements `common.interfaces.Service` (`start`/`stop`), the same
lifecycle shape every other long-lived component in this repository
uses (`market_data.providers.alpaca_streaming.AlpacaStreamingProvider`),
so a future supervisor can start/stop this loop the same way it would
start/stop a streaming provider, without knowing which one it's holding.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Sequence
from datetime import datetime, timedelta, timezone
from typing import Callable

from common.errors import AppError
from common.interfaces import Clock
from market_data.interfaces import HistoricalDataProvider
from market_data.models import Timeframe

logger = logging.getLogger(__name__)

AsyncSleep = Callable[[float], Awaitable[None]]

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class MarketDataLoop:
    """Polls `provider.get_bars` for each symbol in `symbols` every
    `poll_interval_seconds`, logging exactly one structured event per
    newly-seen bar. A fetch failure for one symbol is logged and never
    stops the loop -- one symbol's provider hiccup must not take every
    other symbol down with it, and a hiccup on any symbol must not kill
    the process (matching `AlpacaStreamingProvider.start`'s own
    reconnect-rather-than-die convention).

    `stop()` is idempotent and takes effect on the next poll cycle --
    up to `poll_interval_seconds` after being called. Acceptable for
    Phase A (no trading happens here); a tighter shutdown bound would
    matter once orders are involved, not before.
    """

    def __init__(
        self,
        provider: HistoricalDataProvider,
        *,
        symbols: Sequence[str],
        timeframe: Timeframe,
        poll_interval_seconds: float,
        lookback: timedelta,
        clock: Clock,
        sleep: AsyncSleep = asyncio.sleep,
    ) -> None:
        self._provider = provider
        self._symbols = tuple(symbols)
        self._timeframe = timeframe
        self._poll_interval_seconds = poll_interval_seconds
        self._lookback = lookback
        self._clock = clock
        self._sleep = sleep
        self._stop_requested = False
        self._last_seen: dict[str, datetime] = {}

    async def start(self) -> None:
        self._stop_requested = False
        while not self._stop_requested:
            for symbol in self._symbols:
                self._poll_symbol(symbol)
            await self._sleep(self._poll_interval_seconds)

    async def stop(self) -> None:
        """Idempotent: safe to call even if `start()` was never called."""
        self._stop_requested = True

    def _poll_symbol(self, symbol: str) -> None:
        end = self._clock.now()
        start = end - self._lookback
        try:
            bars = self._provider.get_bars(symbol, start, end, self._timeframe)
        except AppError as exc:
            logger.warning(
                "market data fetch failed",
                extra={"event": "market_data_fetch_failed", "symbol": symbol, "error": str(exc)},
            )
            return

        last_seen = self._last_seen.get(symbol, _EPOCH)
        new_bars = [bar for bar in bars if bar.timestamp > last_seen]
        for bar in new_bars:
            logger.info(
                "new bar received",
                extra={
                    "event": "bar_received",
                    "symbol": bar.symbol,
                    "timestamp": bar.timestamp.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                },
            )
        if new_bars:
            self._last_seen[symbol] = new_bars[-1].timestamp


__all__ = ["AsyncSleep", "MarketDataLoop"]
