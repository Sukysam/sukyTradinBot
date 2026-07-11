"""WebSocket listener for Alpaca News (Spec Sec. 1, 6).

Pure transport: subscribes to raw headlines and hands each one, converted to
a plain `NewsItem`, to an injected async handler. Deliberately does not
import `sentiment_engine` -- scoring and the Catalyst Strategy threshold
belong in `signal_generator.py`, which wires this stream's output into that
engine. Keeping this layer transport-only means it stays swappable (e.g. a
future non-Alpaca news source) without touching core/ decision logic.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable

from alpaca.data.live.news import NewsDataStream
from alpaca.data.models.news import News

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsItem:
    id: int
    headline: str
    summary: str
    symbols: tuple[str, ...]
    source: str
    created_at: datetime

    @classmethod
    def from_alpaca_news(cls, news: News) -> "NewsItem":
        return cls(
            id=news.id,
            headline=news.headline,
            summary=news.summary or "",
            symbols=tuple(news.symbols or ()),
            source=news.source,
            created_at=news.created_at,
        )


NewsHandler = Callable[[NewsItem], Awaitable[None]]


class NewsStreamer:
    """Wraps `alpaca.data.live.news.NewsDataStream`.

    `NewsDataStream.run()` is a blocking call that owns its own event loop
    internally (`asyncio.run(self._run_forever())`, confirmed by inspecting
    the installed SDK), so it cannot be awaited directly from inside another
    asyncio loop. `start()` runs it in a worker thread via `asyncio.to_thread`
    so `main.py` can hold it alongside the other two pipelines in one
    `asyncio.gather` without a nested-event-loop error.
    """

    def __init__(
        self,
        on_news: NewsHandler,
        api_key: str | None = None,
        secret_key: str | None = None,
        symbols: tuple[str, ...] = ("*",),
    ):
        api_key = api_key or os.environ.get("ALPACA_API_KEY")
        secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY")
        if not api_key or not secret_key:
            raise ValueError(
                "Alpaca API credentials required: pass api_key/secret_key or "
                "set ALPACA_API_KEY/ALPACA_SECRET_KEY"
            )

        self._on_news = on_news
        self._symbols = symbols
        self._stream = NewsDataStream(api_key=api_key, secret_key=secret_key)
        self._stream.subscribe_news(self._handle_raw_news, *symbols)

    async def _handle_raw_news(self, news: News) -> None:
        try:
            item = NewsItem.from_alpaca_news(news)
        except Exception:
            logger.exception("Failed to parse incoming news payload: %r", news)
            return
        logger.debug("News received: %s (%s)", item.headline, ",".join(item.symbols))
        await self._on_news(item)

    async def start(self) -> None:
        """Blocks (in a worker thread) until `stop()` is called or the
        connection is torn down."""
        logger.info("Starting Alpaca news stream for symbols=%s", self._symbols)
        await asyncio.to_thread(self._stream.run)

    def stop(self) -> None:
        self._stream.stop()
