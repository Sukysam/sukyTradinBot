"""Alpaca historical bars and corporate actions provider.

Satisfies `market_data.interfaces.HistoricalDataProvider` and
`CorporateActionsProvider`. Every method the underlying `alpaca-py` SDK
client needs is confirmed against the actually-installed SDK
(`alpaca-py==0.43.5` at the time this was written — `StockHistoricalDataClient
.get_stock_bars(StockBarsRequest(...)) -> BarSet` with `BarSet.data:
dict[str, list[alpaca.data.models.bars.Bar]]`, and
`CorporateActionsClient.get_corporate_actions(CorporateActionsRequest(...))
-> CorporateActionsSet` with `CorporateActionsSet.data: dict[str, list[...]]`
grouped by action type). Exercised against a live Alpaca paper account
during the runtime Phase A build (see
docs/engineering-handbook/Architecture/ADR/ADR-027-Runtime-Market-Data-Loop-Design.md)
— confirmed working end to end, which is also how the `feed` gap below
was found: querying without an explicit `feed` defaults to Alpaca's SIP
feed, which a free-tier account cannot query for recent data (`403
subscription does not permit querying recent SIP data`).

Per docs/engineering-handbook/03_BACKEND_ENGINEER.md's coding standards:
the Alpaca SDK client is always injected, never constructed inside
business logic other than this module's own default-construction helper;
every SDK call site converts the vendor's exception into this package's
own (`market_data.errors.ProviderConnectionError`), so no caller of this
provider needs to know `alpaca-py` exists.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Protocol

from alpaca.data.enums import DataFeed
from alpaca.data.historical.corporate_actions import CorporateActionsClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.models.corporate_actions import CashDividend, ForwardSplit, ReverseSplit
from alpaca.data.requests import CorporateActionsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from common.retry import RetryPolicy, call_with_retry
from market_data.auth import AlpacaCredentials, load_alpaca_credentials
from market_data.errors import ProviderConnectionError
from market_data.models import Bar, CorporateAction, CorporateActionType, Timeframe
from market_data.rate_limit import ALPACA_DEFAULT_REQUESTS_PER_MINUTE, RateLimiter
from market_data.validation import deduplicate_bars, normalize_timezone

logger = logging.getLogger(__name__)

_TIMEFRAME_MAP: dict[Timeframe, TimeFrame] = {
    Timeframe.MIN_1: TimeFrame(1, TimeFrameUnit.Minute),
    Timeframe.MIN_5: TimeFrame(5, TimeFrameUnit.Minute),
    Timeframe.MIN_15: TimeFrame(15, TimeFrameUnit.Minute),
    Timeframe.HOUR_1: TimeFrame(1, TimeFrameUnit.Hour),
    Timeframe.DAY_1: TimeFrame(1, TimeFrameUnit.Day),
}


class _BarsClient(Protocol):
    """The narrow slice of `StockHistoricalDataClient` this provider
    actually calls — deliberately smaller than the SDK client's full
    surface, so a test fake only needs one method, not the whole client.
    """

    def get_stock_bars(self, request_params: StockBarsRequest) -> object: ...


class _CorporateActionsClient(Protocol):
    def get_corporate_actions(self, request_params: CorporateActionsRequest) -> object: ...


def _default_bars_client(credentials: AlpacaCredentials) -> StockHistoricalDataClient:
    return StockHistoricalDataClient(api_key=credentials.api_key, secret_key=credentials.secret_key)


def _default_corporate_actions_client(
    credentials: AlpacaCredentials,
) -> CorporateActionsClient:
    return CorporateActionsClient(api_key=credentials.api_key, secret_key=credentials.secret_key)


class AlpacaHistoricalProvider:
    """Satisfies `HistoricalDataProvider` and `CorporateActionsProvider`
    using Alpaca's historical market data REST API.

    Pagination across Alpaca's `next_page_token` is handled internally by
    the SDK client's `get_stock_bars` call — this provider adds retry
    (via `common.retry`), rate limiting, and conversion into this
    package's provider-agnostic models on top.

    `feed` defaults to `DataFeed.IEX` -- matching
    `AlpacaStreamingProvider._default_stream_client`'s existing default
    -- rather than the SDK's own default (`DataFeed.SIP`), which a
    free-tier account cannot query for data less than ~15 minutes old.
    Pass `feed=DataFeed.SIP` explicitly for a paid market-data
    subscription; never assume one is available.
    """

    def __init__(
        self,
        bars_client: _BarsClient | None = None,
        corporate_actions_client: _CorporateActionsClient | None = None,
        *,
        credentials: AlpacaCredentials | None = None,
        rate_limiter: RateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
        feed: DataFeed = DataFeed.IEX,
    ) -> None:
        if bars_client is None:
            bars_client = _default_bars_client(credentials or load_alpaca_credentials())
        if corporate_actions_client is None:
            corporate_actions_client = _default_corporate_actions_client(
                credentials or load_alpaca_credentials()
            )
        self._bars_client = bars_client
        self._corporate_actions_client = corporate_actions_client
        self._rate_limiter = rate_limiter or RateLimiter.per_minute(
            ALPACA_DEFAULT_REQUESTS_PER_MINUTE
        )
        self._retry_policy = retry_policy or RetryPolicy(exceptions=(ProviderConnectionError,))
        self._feed = feed

    def get_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: Timeframe
    ) -> list[Bar]:
        if timeframe not in _TIMEFRAME_MAP:
            raise ValueError(f"Unsupported timeframe {timeframe!r}")

        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=_TIMEFRAME_MAP[timeframe],
            start=start,
            end=end,
            feed=self._feed,
        )

        def _fetch() -> object:
            self._rate_limiter.acquire()
            try:
                return self._bars_client.get_stock_bars(request)
            except Exception as exc:
                # Broad catch is deliberate: this is the one boundary where
                # a raw SDK/network exception is converted into this
                # package's own exception type, matching main.py's
                # existing precedent of a documented exception to the
                # "catch specific exceptions" rule at an external-call
                # boundary. Nothing downstream of this method ever sees a
                # raw alpaca-py or requests exception.
                raise ProviderConnectionError(f"Failed to fetch bars for {symbol}: {exc}") from exc

        response = call_with_retry(_fetch, self._retry_policy)
        raw_bars = _extract_symbol_bars(response, symbol)
        bars = [_to_bar(symbol, timeframe, raw) for raw in raw_bars]
        return deduplicate_bars(bars)

    def get_corporate_actions(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[CorporateAction]:
        request = CorporateActionsRequest(symbols=[symbol], start=start, end=end)

        def _fetch() -> object:
            self._rate_limiter.acquire()
            try:
                return self._corporate_actions_client.get_corporate_actions(request)
            except Exception as exc:
                raise ProviderConnectionError(
                    f"Failed to fetch corporate actions for {symbol}: {exc}"
                ) from exc

        response = call_with_retry(_fetch, self._retry_policy)
        actions = _extract_corporate_actions(response, symbol)
        return sorted(actions, key=lambda a: a.ex_date)


def _extract_symbol_bars(response: object, symbol: str) -> list[object]:
    """Extract the raw per-symbol bar objects from a `BarSet`-shaped
    response (`.data: dict[symbol, list[Bar]]`). The single place this
    assumption lives — an SDK response-shape change only needs a fix here.
    """
    data = getattr(response, "data", None)
    if data is None:
        raise ProviderConnectionError(
            f"Unexpected response shape from Alpaca historical bars API: {type(response)!r}"
        )
    return list(data.get(symbol, []))


def _to_bar(symbol: str, timeframe: Timeframe, raw: object) -> Bar:
    timestamp = normalize_timezone(raw.timestamp)  # type: ignore[attr-defined]
    return Bar(
        symbol=symbol,
        timestamp=timestamp,
        timeframe=timeframe,
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


def _extract_corporate_actions(response: object, symbol: str) -> list[CorporateAction]:
    """Flatten every action list in a `CorporateActionsSet`-shaped
    response (`.data: dict[action_type_str, list[...]]`) and convert the
    handled types (forward/reverse splits, cash dividends) into this
    package's `CorporateAction`. Other action types (mergers, spinoffs,
    name changes, ...) are skipped with a debug log line rather than
    raised on — an unhandled long-tail corporate action type is an
    expected gap to fill later, not a bug to fail loudly on today.
    """
    data = getattr(response, "data", None)
    if data is None:
        raise ProviderConnectionError(
            f"Unexpected response shape from Alpaca corporate actions API: {type(response)!r}"
        )

    actions: list[CorporateAction] = []
    for raw_action in (item for items in data.values() for item in items):
        if raw_action.symbol != symbol:
            continue
        converted = _to_corporate_action(raw_action)
        if converted is not None:
            actions.append(converted)
        else:
            logger.debug(
                "Skipping unhandled corporate action type %s for %s",
                type(raw_action).__name__,
                symbol,
            )
    return actions


def _to_corporate_action(raw: object) -> CorporateAction | None:
    if isinstance(raw, (ForwardSplit, ReverseSplit)):
        ratio = float(raw.new_rate) / float(raw.old_rate)
        return CorporateAction(
            symbol=raw.symbol,
            ex_date=_ex_date_to_utc_datetime(raw.ex_date),
            action_type=CorporateActionType.SPLIT,
            ratio=ratio,
            description=f"{type(raw).__name__}: {raw.old_rate}-for-{raw.new_rate}",
        )
    if isinstance(raw, CashDividend):
        return CorporateAction(
            symbol=raw.symbol,
            ex_date=_ex_date_to_utc_datetime(raw.ex_date),
            action_type=CorporateActionType.DIVIDEND,
            cash_amount=float(raw.rate),
            description="CashDividend",
        )
    return None


def _ex_date_to_utc_datetime(ex_date: datetime | date) -> datetime:
    """Alpaca's corporate-actions models return `ex_date` as a plain
    `datetime.date` (confirmed by SDK inspection), not a `datetime` —
    unlike every other timestamp this provider handles. Convert to a
    UTC-midnight `datetime` before it reaches `normalize_timezone` (which
    assumes a `datetime` with a `.tzinfo` attribute) or `CorporateAction`
    (whose `__post_init__` requires a timezone-aware `datetime`).
    """
    if isinstance(ex_date, datetime):
        return normalize_timezone(ex_date)
    return datetime(ex_date.year, ex_date.month, ex_date.day, tzinfo=timezone.utc)


__all__ = ["AlpacaHistoricalProvider"]
