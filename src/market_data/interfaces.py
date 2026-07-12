"""Provider-agnostic contracts for market data.

This module is the architectural center of Milestone 2 — see
docs/engineering-handbook/Architecture/ADR/ADR-002-Market-Data.md. Every
consumer (a future backtester, the HMM feature pipeline, a strategy) is
meant to depend on these `Protocol`s, never on `providers.alpaca_*`
directly, so a second vendor can be added later without touching a single
consumer. Matches the pattern already established in
`regime-trader/main.py`'s `MarketDataProvider`/`ModelStore`/
`SignalGenerator` — define the contract before, or independently of, any
one implementation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Sequence
from datetime import datetime
from typing import Callable, Protocol, runtime_checkable

from common.interfaces import Service
from market_data.models import Bar, CorporateAction, Quote, Timeframe, Trade

BarHandler = Callable[[Bar], Awaitable[None]]
TradeHandler = Callable[[Trade], Awaitable[None]]
QuoteHandler = Callable[[Quote], Awaitable[None]]


@runtime_checkable
class HistoricalDataProvider(Protocol):
    """Fetches historical bars for a symbol over an explicit time window.

    Deliberately takes an explicit `[start, end)` window rather than a
    "lookback_days" integer — the latter requires knowing "now", which
    couples this Protocol to a clock and makes it harder to test
    deterministically. Translating "N days back from today" into an
    explicit window is the caller's job (see
    `regime-trader/broker/alpaca_client.py`'s adapter, which does exactly
    this to satisfy `main.py.MarketDataProvider`'s lookback-based
    contract using an injected `common.interfaces.Clock`).
    """

    def get_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: Timeframe
    ) -> list[Bar]:
        """Return bars for `symbol` in `[start, end)`, ascending by
        timestamp, with no duplicate timestamps. Both `start` and `end`
        must be timezone-aware. Raises `market_data.errors.
        ProviderConnectionError` on transport failure and
        `ProviderAuthenticationError` on a rejected credential, after the
        provider's own retry budget (if any) is exhausted.
        """
        ...


@runtime_checkable
class CorporateActionsProvider(Protocol):
    """Fetches corporate actions (splits, dividends, ...) for a symbol
    over an explicit time window. Kept separate from
    `HistoricalDataProvider` so a provider that only serves bars doesn't
    need to implement this too.
    """

    def get_corporate_actions(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[CorporateAction]:
        """Return corporate actions for `symbol` with `ex_date` in
        `[start, end)`, ascending by `ex_date`.
        """
        ...


@runtime_checkable
class StreamingDataProvider(Service, Protocol):
    """A live market data feed with an explicit start/stop lifecycle
    (composes `common.interfaces.Service` — see that module for why the
    lifecycle shape is shared across every long-lived component in this
    repository, not just this one).

    Subscriptions are registered before `start()` is called; handlers are
    plain async callables, matching `broker/news_streamer.py`'s existing
    `NewsHandler` pattern in `regime-trader/`.
    """

    def subscribe_bars(self, symbols: Sequence[str], handler: BarHandler) -> None:
        """Register `handler` to be awaited once per bar for each symbol
        in `symbols`. May be called multiple times to add more
        symbols/handlers; must be called before `start()`.
        """
        ...

    def subscribe_trades(self, symbols: Sequence[str], handler: TradeHandler) -> None:
        """Register `handler` to be awaited once per trade tick."""
        ...

    def subscribe_quotes(self, symbols: Sequence[str], handler: QuoteHandler) -> None:
        """Register `handler` to be awaited once per quote update."""
        ...

    def last_message_at(self) -> datetime | None:
        """Timestamp this provider last received *any* message from the
        transport (not necessarily a subscribed symbol) — the primitive a
        heartbeat/staleness monitor is built on. `None` if `start()` has
        not been called or no message has arrived yet.
        """
        ...


@runtime_checkable
class MarketDataStorage(Protocol):
    """Durable, queryable storage for bars, keyed by symbol and timeframe.

    `latest_timestamp` is what makes an incremental update possible: a
    caller fetches only `(latest_timestamp, now]` from a
    `HistoricalDataProvider` instead of re-fetching a full history it
    already has stored — see `storage/parquet_store.py`.
    """

    def write_bars(self, bars: Sequence[Bar]) -> None:
        """Persist `bars`. Idempotent: writing a bar whose
        `(symbol, timeframe, timestamp)` already exists overwrites it
        rather than duplicating it.
        """
        ...

    def read_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: Timeframe
    ) -> list[Bar]:
        """Return stored bars for `symbol`/`timeframe` in `[start, end)`,
        ascending by timestamp. Returns an empty list, never raises, if
        nothing is stored for the requested symbol/window.
        """
        ...

    def latest_timestamp(self, symbol: str, timeframe: Timeframe) -> datetime | None:
        """The timestamp of the most recent bar stored for
        `symbol`/`timeframe`, or `None` if nothing is stored yet.
        """
        ...


__all__ = [
    "BarHandler",
    "CorporateActionsProvider",
    "HistoricalDataProvider",
    "MarketDataStorage",
    "QuoteHandler",
    "StreamingDataProvider",
    "TradeHandler",
]
