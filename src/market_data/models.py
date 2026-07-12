"""Market data domain models.

Every subsystem that consumes market data (HMM regime detection,
backtesting, NLP, execution) is meant to consume *these* types — see
docs/engineering-handbook/Architecture/ADR/ADR-002-Market-Data.md. They are
provider-agnostic on purpose: nothing here imports `alpaca-py` or knows
Alpaca's wire format. A provider's only job is translating its vendor's
response into these types (see `providers/alpaca_historical.py`'s
`_to_bar`) so that swapping or adding a data vendor later never ripples
into a consumer.

All timestamps are timezone-aware and normalized to UTC — see
`validation.normalize_timezone` for the enforcement point at the provider
boundary. Every type here validates that invariant itself in
`__post_init__` so a naive timestamp fails immediately at construction,
not silently three modules downstream in a rolling-window computation
(see docs/engineering-handbook/Standards/Anti-Lookahead Checklist.md —
inconsistent timestamps are exactly the kind of thing that produces subtle
causal-ordering bugs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _require_utc(timestamp: datetime, *, field_name: str = "timestamp") -> None:
    if timestamp.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware, got naive datetime {timestamp!r}")
    if timestamp.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError(
            f"{field_name} must be normalized to UTC, got offset "
            f"{timestamp.utcoffset()} for {timestamp!r}. "
            "See validation.normalize_timezone."
        )


class Timeframe(str, Enum):
    """Closed set of bar granularities this system understands."""

    MIN_1 = "1Min"
    MIN_5 = "5Min"
    MIN_15 = "15Min"
    HOUR_1 = "1Hour"
    DAY_1 = "1Day"


class CorporateActionType(str, Enum):
    SPLIT = "split"
    DIVIDEND = "dividend"
    MERGER = "merger"
    SPINOFF = "spinoff"


@dataclass(frozen=True)
class Bar:
    """One OHLCV bar for `symbol` covering `[timestamp, timestamp + timeframe)`.

    `timestamp` is the bar's **open** time, matching Alpaca's convention —
    a 5-minute bar timestamped `09:30:00` covers `[09:30:00, 09:35:00)`.
    """

    symbol: str
    timestamp: datetime
    timeframe: Timeframe
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int | None = None
    vwap: float | None = None

    def __post_init__(self) -> None:
        _require_utc(self.timestamp)
        if self.volume < 0:
            raise ValueError(f"volume must be >= 0, got {self.volume}")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError(
                f"high ({self.high}) must be >= max(open, close, low) for {self.symbol}"
                f" at {self.timestamp}"
            )
        if self.low > min(self.open, self.close, self.high):
            raise ValueError(
                f"low ({self.low}) must be <= min(open, close, high) for {self.symbol}"
                f" at {self.timestamp}"
            )


@dataclass(frozen=True)
class Trade:
    """One executed trade tick."""

    symbol: str
    timestamp: datetime
    price: float
    size: float
    exchange: str = ""
    trade_id: str = ""
    conditions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_utc(self.timestamp)
        if self.price <= 0:
            raise ValueError(f"price must be > 0, got {self.price}")
        if self.size <= 0:
            raise ValueError(f"size must be > 0, got {self.size}")


@dataclass(frozen=True)
class Quote:
    """One top-of-book bid/ask update.

    Deliberately does not validate `bid_price <= ask_price`: real venues
    produce transiently crossed quotes, and rejecting them at the model
    boundary would silently drop legitimate market data rather than let a
    consumer decide how to handle it.
    """

    symbol: str
    timestamp: datetime
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    bid_exchange: str = ""
    ask_exchange: str = ""

    def __post_init__(self) -> None:
        _require_utc(self.timestamp)
        for name, value in (
            ("bid_price", self.bid_price),
            ("bid_size", self.bid_size),
            ("ask_price", self.ask_price),
            ("ask_size", self.ask_size),
        ):
            if value < 0:
                raise ValueError(f"{name} must be >= 0, got {value}")


@dataclass(frozen=True)
class PriceLevel:
    """One price/size level in an `OrderBook`."""

    price: float
    size: float

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError(f"price must be > 0, got {self.price}")
        if self.size <= 0:
            raise ValueError(f"size must be > 0, got {self.size}")


@dataclass(frozen=True)
class OrderBook:
    """A depth-of-book snapshot. `bids`/`asks` are ordered best-price-first."""

    symbol: str
    timestamp: datetime
    bids: tuple[PriceLevel, ...]
    asks: tuple[PriceLevel, ...]

    def __post_init__(self) -> None:
        _require_utc(self.timestamp)

    @property
    def best_bid(self) -> PriceLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> PriceLevel | None:
        return self.asks[0] if self.asks else None


@dataclass(frozen=True)
class Snapshot:
    """A consolidated point-in-time view of a symbol, mirroring what a
    single "give me the current state of this symbol" request returns —
    the pieces a fresh subscriber needs before incremental trade/quote
    updates alone are enough to reconstruct current state.
    """

    symbol: str
    timestamp: datetime
    latest_trade: Trade | None = None
    latest_quote: Quote | None = None
    daily_bar: Bar | None = None
    previous_daily_bar: Bar | None = None

    def __post_init__(self) -> None:
        _require_utc(self.timestamp)


@dataclass(frozen=True)
class CorporateAction:
    """A split, dividend, merger, or spinoff affecting `symbol`.

    `ex_date` is the ex-date (the first date the action is reflected in
    the price) — see `validation.apply_split_adjustment`, which uses it to
    decide which historical bars need back-adjustment.
    """

    symbol: str
    ex_date: datetime
    action_type: CorporateActionType
    ratio: float | None = None
    cash_amount: float | None = None
    description: str = ""

    def __post_init__(self) -> None:
        _require_utc(self.ex_date, field_name="ex_date")
        if self.action_type == CorporateActionType.SPLIT and not self.ratio:
            raise ValueError(f"SPLIT action for {self.symbol} requires a ratio")
        if self.action_type == CorporateActionType.DIVIDEND and self.cash_amount is None:
            raise ValueError(f"DIVIDEND action for {self.symbol} requires a cash_amount")
        if self.ratio is not None and self.ratio <= 0:
            raise ValueError(f"ratio must be > 0, got {self.ratio}")


__all__ = [
    "Bar",
    "CorporateAction",
    "CorporateActionType",
    "OrderBook",
    "PriceLevel",
    "Quote",
    "Snapshot",
    "Timeframe",
    "Trade",
]
