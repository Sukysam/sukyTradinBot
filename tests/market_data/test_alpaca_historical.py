from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Callable

import pytest
from alpaca.data.models.corporate_actions import CashDividend, ForwardSplit, ReverseSplit

from common.errors import RetryExhaustedError
from common.retry import RetryPolicy
from market_data.errors import ProviderConnectionError
from market_data.models import CorporateActionType, Timeframe
from market_data.providers.alpaca_historical import AlpacaHistoricalProvider
from market_data.rate_limit import RateLimiter

UTC = timezone.utc


def _raw_bar(
    ts: datetime, close: float = 100.0, trade_count: int | None = 10, vwap: float | None = 100.1
) -> object:
    return SimpleNamespace(
        timestamp=ts,
        open=close - 0.5,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
        trade_count=trade_count,
        vwap=vwap,
    )


class _FakeBarsClient:
    def __init__(self, response: object | None = None, fail_times: int = 0) -> None:
        self.response = response
        self.fail_times = fail_times
        self.calls = 0

    def get_stock_bars(self, request_params: object) -> object:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("simulated transient failure")
        return self.response


class _FakeCorporateActionsClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls = 0

    def get_corporate_actions(self, request_params: object) -> object:
        self.calls += 1
        return self.response


def _no_wait_rate_limiter() -> RateLimiter:
    return RateLimiter(rate=1_000_000, capacity=1_000_000)


def _fast_retry_policy(**overrides: object) -> RetryPolicy:
    defaults: dict[str, object] = {
        "max_attempts": 3,
        "initial_delay_seconds": 0.0,
        "exceptions": (ProviderConnectionError,),
    }
    defaults.update(overrides)
    return RetryPolicy(**defaults)  # type: ignore[arg-type]


def _make_provider(
    bars_response: object | None = None,
    bars_fail_times: int = 0,
    corporate_actions_response: object | None = None,
) -> tuple[AlpacaHistoricalProvider, _FakeBarsClient, _FakeCorporateActionsClient]:
    bars_client = _FakeBarsClient(bars_response, fail_times=bars_fail_times)
    ca_client = _FakeCorporateActionsClient(corporate_actions_response or SimpleNamespace(data={}))
    provider = AlpacaHistoricalProvider(
        bars_client=bars_client,
        corporate_actions_client=ca_client,
        rate_limiter=_no_wait_rate_limiter(),
        retry_policy=_fast_retry_policy(),
    )
    return provider, bars_client, ca_client


class TestGetBars:
    def test_converts_response_to_our_bar_model(self) -> None:
        ts = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        response = SimpleNamespace(data={"AAPL": [_raw_bar(ts, close=100.0)]})
        provider, _, _ = _make_provider(bars_response=response)

        bars = provider.get_bars("AAPL", ts, ts, Timeframe.MIN_1)

        assert len(bars) == 1
        assert bars[0].symbol == "AAPL"
        assert bars[0].close == 100.0
        assert bars[0].trade_count == 10
        assert bars[0].timeframe == Timeframe.MIN_1

    def test_ignores_other_symbols_in_response(self) -> None:
        ts = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        response = SimpleNamespace(data={"AAPL": [_raw_bar(ts)], "MSFT": [_raw_bar(ts)]})
        provider, _, _ = _make_provider(bars_response=response)

        bars = provider.get_bars("AAPL", ts, ts, Timeframe.MIN_1)

        assert all(b.symbol == "AAPL" for b in bars)

    def test_missing_symbol_in_response_returns_empty(self) -> None:
        response = SimpleNamespace(data={})
        provider, _, _ = _make_provider(bars_response=response)

        assert (
            provider.get_bars(
                "AAPL",
                datetime(2026, 6, 1, tzinfo=UTC),
                datetime(2026, 6, 1, tzinfo=UTC),
                Timeframe.MIN_1,
            )
            == []
        )

    def test_deduplicates_bars_from_response(self) -> None:
        ts = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        response = SimpleNamespace(
            data={"AAPL": [_raw_bar(ts, close=100.0), _raw_bar(ts, close=101.0)]}
        )
        provider, _, _ = _make_provider(bars_response=response)

        bars = provider.get_bars("AAPL", ts, ts, Timeframe.MIN_1)

        assert len(bars) == 1
        assert bars[0].close == 101.0  # last wins, per validation.deduplicate_bars

    def test_rejects_unsupported_timeframe(self) -> None:
        provider, _, _ = _make_provider(bars_response=SimpleNamespace(data={}))
        with pytest.raises(ValueError, match="timeframe"):
            provider.get_bars("AAPL", datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 6, 1, tzinfo=UTC), "not-a-timeframe")  # type: ignore[arg-type]

    def test_retries_then_succeeds(self) -> None:
        ts = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        response = SimpleNamespace(data={"AAPL": [_raw_bar(ts)]})
        provider, bars_client, _ = _make_provider(bars_response=response, bars_fail_times=2)

        bars = provider.get_bars("AAPL", ts, ts, Timeframe.MIN_1)

        assert len(bars) == 1
        assert bars_client.calls == 3

    def test_raises_retry_exhausted_after_persistent_failure(self) -> None:
        provider, bars_client, _ = _make_provider(
            bars_response=SimpleNamespace(data={}), bars_fail_times=99
        )

        with pytest.raises(RetryExhaustedError):
            provider.get_bars(
                "AAPL",
                datetime(2026, 6, 1, tzinfo=UTC),
                datetime(2026, 6, 1, tzinfo=UTC),
                Timeframe.MIN_1,
            )
        assert bars_client.calls == 3  # bounded by the injected retry policy's max_attempts

    def test_sdk_exception_is_converted_to_provider_connection_error(self) -> None:
        provider, _, _ = _make_provider(bars_response=SimpleNamespace(data={}), bars_fail_times=99)
        with pytest.raises(RetryExhaustedError) as exc_info:
            provider.get_bars(
                "AAPL",
                datetime(2026, 6, 1, tzinfo=UTC),
                datetime(2026, 6, 1, tzinfo=UTC),
                Timeframe.MIN_1,
            )
        assert isinstance(exc_info.value.__cause__, ProviderConnectionError)

    def test_rate_limiter_is_consulted_before_each_call(self) -> None:
        ts = datetime(2026, 6, 1, tzinfo=UTC)
        response = SimpleNamespace(data={"AAPL": [_raw_bar(ts)]})
        bars_client = _FakeBarsClient(response)
        ca_client = _FakeCorporateActionsClient(SimpleNamespace(data={}))

        class _SpyRateLimiter(RateLimiter):
            def __init__(self) -> None:
                super().__init__(rate=1_000_000, capacity=1_000_000)
                self.acquire_calls = 0

            def acquire(
                self, tokens: float = 1.0, *, sleep: Callable[[float], None] = time.sleep
            ) -> None:
                self.acquire_calls += 1

        spy = _SpyRateLimiter()
        provider = AlpacaHistoricalProvider(
            bars_client=bars_client,
            corporate_actions_client=ca_client,
            rate_limiter=spy,
            retry_policy=_fast_retry_policy(),
        )

        provider.get_bars("AAPL", ts, ts, Timeframe.MIN_1)

        assert spy.acquire_calls == 1


def _real_split(
    new_rate: float, old_rate: float, ex_date: str, symbol: str = "AAPL"
) -> ForwardSplit:
    parsed_date = date.fromisoformat(ex_date)
    return ForwardSplit(
        id=uuid.uuid4(),
        corporate_action_type="forward_split",
        symbol=symbol,
        cusip="000000000",
        new_rate=new_rate,
        old_rate=old_rate,
        process_date=parsed_date,
        ex_date=parsed_date,
    )


def _real_reverse_split(
    new_rate: float, old_rate: float, ex_date: str, symbol: str = "AAPL"
) -> ReverseSplit:
    parsed_date = date.fromisoformat(ex_date)
    return ReverseSplit(
        id=uuid.uuid4(),
        corporate_action_type="reverse_split",
        symbol=symbol,
        old_cusip="000000000",
        new_cusip="111111111",
        new_rate=new_rate,
        old_rate=old_rate,
        process_date=parsed_date,
        ex_date=parsed_date,
    )


def _real_dividend(rate: float, ex_date: str, symbol: str = "AAPL") -> CashDividend:
    parsed_date = date.fromisoformat(ex_date)
    return CashDividend(
        id=uuid.uuid4(),
        corporate_action_type="cash_dividend",
        symbol=symbol,
        cusip="000000000",
        rate=rate,
        special=False,
        foreign=False,
        process_date=parsed_date,
        ex_date=parsed_date,
    )


class TestGetCorporateActions:
    def test_converts_forward_split(self) -> None:
        response = SimpleNamespace(data={"forward_splits": [_real_split(4.0, 1.0, "2026-06-15")]})
        provider, _, _ = _make_provider(
            bars_response=SimpleNamespace(data={}), corporate_actions_response=response
        )

        actions = provider.get_corporate_actions(
            "AAPL", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC)
        )

        assert len(actions) == 1
        assert actions[0].action_type == CorporateActionType.SPLIT
        assert actions[0].ratio == 4.0
        # ex_date came back from the SDK as a plain `date`, not `datetime` --
        # this is the exact conversion bug caught during verification.
        assert actions[0].ex_date == datetime(2026, 6, 15, tzinfo=UTC)

    def test_converts_reverse_split_ratio_below_one(self) -> None:
        response = SimpleNamespace(
            data={"reverse_splits": [_real_reverse_split(1.0, 4.0, "2026-06-15")]}
        )
        provider, _, _ = _make_provider(
            bars_response=SimpleNamespace(data={}), corporate_actions_response=response
        )

        actions = provider.get_corporate_actions(
            "AAPL", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC)
        )

        assert actions[0].ratio == 0.25

    def test_converts_cash_dividend(self) -> None:
        response = SimpleNamespace(data={"cash_dividends": [_real_dividend(0.25, "2026-06-15")]})
        provider, _, _ = _make_provider(
            bars_response=SimpleNamespace(data={}), corporate_actions_response=response
        )

        actions = provider.get_corporate_actions(
            "AAPL", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC)
        )

        assert actions[0].action_type == CorporateActionType.DIVIDEND
        assert actions[0].cash_amount == 0.25

    def test_filters_out_other_symbols(self) -> None:
        response = SimpleNamespace(
            data={"forward_splits": [_real_split(2.0, 1.0, "2026-06-15", symbol="MSFT")]}
        )
        provider, _, _ = _make_provider(
            bars_response=SimpleNamespace(data={}), corporate_actions_response=response
        )

        actions = provider.get_corporate_actions(
            "AAPL", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC)
        )

        assert actions == []

    def test_results_sorted_by_ex_date(self) -> None:
        response = SimpleNamespace(
            data={
                "forward_splits": [_real_split(2.0, 1.0, "2026-09-01")],
                "cash_dividends": [_real_dividend(0.1, "2026-03-01")],
            }
        )
        provider, _, _ = _make_provider(
            bars_response=SimpleNamespace(data={}), corporate_actions_response=response
        )

        actions = provider.get_corporate_actions(
            "AAPL", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC)
        )

        assert [a.ex_date.month for a in actions] == [3, 9]
