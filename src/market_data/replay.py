"""Historical replay: turns a stored/fetched bar sequence into either a
simple ordered iterator (for backtesting) or a paced, async, callback-driven
feed (for exercising a `StreamingDataProvider` consumer against historical
data instead of a live websocket).

This is the concrete mechanism behind Milestone 2's stated outcome — every
subsystem consuming the same market data interfaces — for anything that
consumes bars via `BarHandler`: a backtester and a live trading loop can
both be written against `BarHandler`, and `HistoricalReplay` is what lets
the backtester drive one with historical data while
`providers.alpaca_streaming` drives the identical callback with live data.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterator, Sequence
from typing import Callable

from market_data.interfaces import BarHandler
from market_data.models import Bar

AsyncSleep = Callable[[float], Awaitable[None]]


class HistoricalReplay:
    """Replays `bars` in ascending timestamp order.

    Bars are sorted by timestamp at construction time regardless of input
    order, so a caller can never accidentally replay out of causal order
    — see docs/engineering-handbook/Standards/Anti-Lookahead Checklist.md;
    a replay that delivered bars out of order would let a consumer's
    "trailing window" logic see the future.
    """

    def __init__(self, bars: Sequence[Bar]) -> None:
        self._bars: list[Bar] = sorted(bars, key=lambda bar: bar.timestamp)

    def __len__(self) -> int:
        return len(self._bars)

    def __iter__(self) -> Iterator[Bar]:
        """Synchronous, as-fast-as-possible iteration — for backtesting."""
        return iter(self._bars)

    async def run(
        self,
        handler: BarHandler,
        *,
        speed: float = 0.0,
        sleep: AsyncSleep = asyncio.sleep,
    ) -> None:
        """Await `handler(bar)` once per bar, in order.

        `speed`: `0` (default) delivers every bar back-to-back with no
        delay — the backtesting-friendly mode. A positive `speed` paces
        delivery to simulate real time: the wall-clock gap between
        consecutive bars' timestamps is divided by `speed` and awaited
        between deliveries (`speed=1.0` replays at real-time pace,
        `speed=60.0` replays 60x faster than the market moved). Useful for
        exercising a streaming consumer's heartbeat/staleness logic
        against historical data instead of waiting for a live feed to
        produce a gap.

        `sleep` is injectable (defaults to `asyncio.sleep`) so tests can
        verify paced-replay timing without a test actually taking as long
        as the replayed window — see `tests/market_data/test_replay.py`.
        """
        previous_timestamp = None
        for bar in self._bars:
            if speed > 0 and previous_timestamp is not None:
                real_gap_seconds = (bar.timestamp - previous_timestamp).total_seconds()
                if real_gap_seconds > 0:
                    await sleep(real_gap_seconds / speed)
            await handler(bar)
            previous_timestamp = bar.timestamp


__all__ = ["HistoricalReplay"]
