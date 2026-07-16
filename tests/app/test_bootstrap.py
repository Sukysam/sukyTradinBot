"""Tests for `app.bootstrap.build_market_data_loop`/`current_git_commit`.

Never constructs a real `AlpacaHistoricalProvider` or hits the network
-- a fake `HistoricalDataProvider` is always injected via
`build_market_data_loop`'s `provider` parameter, matching this
codebase's DI convention throughout.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.bootstrap import build_market_data_loop, current_git_commit
from app.config import MarketDataLoopConfig
from app.exceptions import GitCommitUnavailableError
from app.runtime import MarketDataLoop
from market_data.errors import ProviderConnectionError
from market_data.models import Bar, Timeframe
from ops.exceptions import RuntimeValidationError, UnhealthyPlatformError
from ops.models import RuntimeContext

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _bar(symbol: str = "AAPL") -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=T0,
        timeframe=Timeframe.DAY_1,
        open=99.0,
        high=101.0,
        low=98.0,
        close=100.0,
        volume=1000.0,
    )


class _FakeProvider:
    def __init__(self, healthy: bool = True) -> None:
        self._healthy = healthy

    def get_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: Timeframe
    ) -> list[Bar]:
        if not self._healthy:
            raise ProviderConnectionError("simulated failure")
        return [_bar(symbol)]


def _config() -> MarketDataLoopConfig:
    return MarketDataLoopConfig(
        symbols=("AAPL",),
        timeframe=Timeframe.DAY_1,
        poll_interval_seconds=300.0,
        lookback=timedelta(days=5),
    )


@pytest.fixture(autouse=True)
def _alpaca_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")


class TestCurrentGitCommit:
    def test_returns_a_non_empty_string_in_a_real_repo(self) -> None:
        commit = current_git_commit()
        assert commit
        assert len(commit) == 40

    def test_raises_when_git_is_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        def _boom(*args: object, **kwargs: object) -> None:
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(subprocess, "run", _boom)
        with pytest.raises(GitCommitUnavailableError):
            current_git_commit()


class TestBuildMarketDataLoop:
    def test_builds_a_loop_and_runtime_context_when_healthy(self) -> None:
        loop, runtime_context = build_market_data_loop(_config(), provider=_FakeProvider())
        assert isinstance(loop, MarketDataLoop)
        assert isinstance(runtime_context, RuntimeContext)
        assert runtime_context.platform_info.version == "0.1.0"

    def test_raises_runtime_validation_error_when_secret_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        with pytest.raises(RuntimeValidationError):
            build_market_data_loop(_config(), provider=_FakeProvider())

    def test_raises_unhealthy_platform_error_when_connectivity_check_fails(self) -> None:
        with pytest.raises(UnhealthyPlatformError):
            build_market_data_loop(_config(), provider=_FakeProvider(healthy=False))
