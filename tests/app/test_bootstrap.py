"""Tests for `app.bootstrap.build_market_data_loop`/`current_git_commit`.

Never constructs a real `AlpacaHistoricalProvider` or hits the network
-- a fake `HistoricalDataProvider` is always injected via
`build_market_data_loop`'s `provider` parameter, matching this
codebase's DI convention throughout.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.bootstrap import (
    build_feature_loop,
    build_market_data_loop,
    build_regime_loop,
    build_strategy_loop,
    current_git_commit,
)
from app.config import FeatureLoopConfig, MarketDataLoopConfig, RegimeLoopConfig
from app.exceptions import GitCommitUnavailableError
from app.features_loop import FeatureVectorEmitter
from app.regime_loop import RegimeEmitter
from app.runtime import MarketDataLoop
from app.strategy_loop import StrategyEmitter
from market_data.errors import ProviderConnectionError
from market_data.models import Bar, Timeframe
from ops.checks import CallableHealthCheck
from ops.exceptions import RuntimeValidationError, UnhealthyPlatformError
from ops.models import RuntimeContext
from strategy.registry import StrategyRegistry
from strategy.strategies import create_growth_strategy

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
        assert runtime_context.platform_info.version == "0.4.0"

    def test_raises_runtime_validation_error_when_secret_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        with pytest.raises(RuntimeValidationError):
            build_market_data_loop(_config(), provider=_FakeProvider())

    def test_raises_unhealthy_platform_error_when_connectivity_check_fails(self) -> None:
        with pytest.raises(UnhealthyPlatformError):
            build_market_data_loop(_config(), provider=_FakeProvider(healthy=False))

    def test_on_bar_is_passed_through_to_the_loop(self) -> None:
        received: list[Bar] = []
        callback = received.append
        loop, _ = build_market_data_loop(_config(), provider=_FakeProvider(), on_bar=callback)
        assert loop._on_bar is callback


def _feature_config() -> FeatureLoopConfig:
    return FeatureLoopConfig(market_data=_config())


class TestBuildFeatureLoop:
    def test_builds_a_loop_context_and_emitter_when_healthy(self) -> None:
        loop, runtime_context, emitter = build_feature_loop(
            _feature_config(), provider=_FakeProvider()
        )
        assert isinstance(loop, MarketDataLoop)
        assert isinstance(runtime_context, RuntimeContext)
        assert isinstance(emitter, FeatureVectorEmitter)
        assert runtime_context.platform_info.version == "0.4.0"

    def test_wires_the_emitter_as_the_loops_on_bar_callback(self) -> None:
        loop, _, emitter = build_feature_loop(_feature_config(), provider=_FakeProvider())
        assert loop._on_bar == emitter.handle_bar

    def test_emitter_metrics_start_empty(self) -> None:
        _, _, emitter = build_feature_loop(_feature_config(), provider=_FakeProvider())
        assert emitter.metrics.counters == ()
        assert emitter.metrics.gauges == ()

    def test_raises_runtime_validation_error_when_secret_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        with pytest.raises(RuntimeValidationError):
            build_feature_loop(_feature_config(), provider=_FakeProvider())

    def test_raises_unhealthy_platform_error_when_connectivity_check_fails(self) -> None:
        with pytest.raises(UnhealthyPlatformError):
            build_feature_loop(_feature_config(), provider=_FakeProvider(healthy=False))

    def test_on_frame_is_passed_through_to_the_emitter(self) -> None:
        received: list[object] = []
        callback = received.append
        _, _, emitter = build_feature_loop(
            _feature_config(), provider=_FakeProvider(), on_frame=callback
        )
        assert emitter._on_frame is callback

    def test_extra_checks_are_included_in_the_health_gate(self) -> None:
        failing_check = CallableHealthCheck("always_fails", lambda: False)
        with pytest.raises(UnhealthyPlatformError):
            build_feature_loop(
                _feature_config(), provider=_FakeProvider(), extra_checks=[failing_check]
            )


class _FakeRegimeService:
    def __init__(self, n_states: int = 3) -> None:
        self.n_states = n_states


def _regime_config() -> RegimeLoopConfig:
    return RegimeLoopConfig(feature_loop=_feature_config())


class TestBuildRegimeLoop:
    def test_builds_loop_context_and_both_emitters_when_healthy(self) -> None:
        loop, runtime_context, feature_emitter, regime_emitter = build_regime_loop(
            _regime_config(), _FakeRegimeService(), provider=_FakeProvider()  # type: ignore[arg-type]
        )
        assert isinstance(loop, MarketDataLoop)
        assert isinstance(runtime_context, RuntimeContext)
        assert isinstance(feature_emitter, FeatureVectorEmitter)
        assert isinstance(regime_emitter, RegimeEmitter)
        assert runtime_context.platform_info.version == "0.4.0"

    def test_wires_the_regime_emitter_as_the_feature_emitters_on_frame_callback(self) -> None:
        _, _, feature_emitter, regime_emitter = build_regime_loop(
            _regime_config(), _FakeRegimeService(), provider=_FakeProvider()  # type: ignore[arg-type]
        )
        assert feature_emitter._on_frame == regime_emitter.handle_frame

    def test_regime_emitter_metrics_start_empty(self) -> None:
        _, _, _, regime_emitter = build_regime_loop(
            _regime_config(), _FakeRegimeService(), provider=_FakeProvider()  # type: ignore[arg-type]
        )
        assert regime_emitter.metrics.counters == ()
        assert regime_emitter.metrics.gauges == ()

    def test_raises_runtime_validation_error_when_secret_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        with pytest.raises(RuntimeValidationError):
            build_regime_loop(
                _regime_config(), _FakeRegimeService(), provider=_FakeProvider()  # type: ignore[arg-type]
            )

    def test_raises_unhealthy_platform_error_when_connectivity_check_fails(self) -> None:
        with pytest.raises(UnhealthyPlatformError):
            build_regime_loop(
                _regime_config(),
                _FakeRegimeService(),  # type: ignore[arg-type]
                provider=_FakeProvider(healthy=False),
            )

    def test_raises_unhealthy_platform_error_when_regime_service_has_no_states(self) -> None:
        with pytest.raises(UnhealthyPlatformError):
            build_regime_loop(
                _regime_config(), _FakeRegimeService(n_states=0), provider=_FakeProvider()  # type: ignore[arg-type]
            )


def _strategy_registry(*, populated: bool = True) -> StrategyRegistry:
    registry = StrategyRegistry()
    if populated:
        registry.register(create_growth_strategy("growth", frozenset({0})))
    return registry


class TestBuildStrategyLoop:
    def test_builds_loop_context_and_all_three_emitters_when_healthy(self) -> None:
        loop, runtime_context, feature_emitter, regime_emitter, strategy_emitter = (
            build_strategy_loop(
                _regime_config(),
                _FakeRegimeService(),  # type: ignore[arg-type]
                _strategy_registry(),
                provider=_FakeProvider(),
            )
        )
        assert isinstance(loop, MarketDataLoop)
        assert isinstance(runtime_context, RuntimeContext)
        assert isinstance(feature_emitter, FeatureVectorEmitter)
        assert isinstance(regime_emitter, RegimeEmitter)
        assert isinstance(strategy_emitter, StrategyEmitter)
        assert runtime_context.platform_info.version == "0.4.0"

    def test_wires_the_strategy_emitter_as_the_regime_emitters_on_frame_callback(self) -> None:
        _, _, _, regime_emitter, strategy_emitter = build_strategy_loop(
            _regime_config(),
            _FakeRegimeService(),  # type: ignore[arg-type]
            _strategy_registry(),
            provider=_FakeProvider(),
        )
        assert regime_emitter._on_frame == strategy_emitter.handle_frame

    def test_strategy_emitter_metrics_start_empty(self) -> None:
        _, _, _, _, strategy_emitter = build_strategy_loop(
            _regime_config(),
            _FakeRegimeService(),  # type: ignore[arg-type]
            _strategy_registry(),
            provider=_FakeProvider(),
        )
        assert strategy_emitter.metrics.counters == ()
        assert strategy_emitter.metrics.gauges == ()

    def test_raises_runtime_validation_error_when_secret_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        with pytest.raises(RuntimeValidationError):
            build_strategy_loop(
                _regime_config(),
                _FakeRegimeService(),  # type: ignore[arg-type]
                _strategy_registry(),
                provider=_FakeProvider(),
            )

    def test_raises_unhealthy_platform_error_when_connectivity_check_fails(self) -> None:
        with pytest.raises(UnhealthyPlatformError):
            build_strategy_loop(
                _regime_config(),
                _FakeRegimeService(),  # type: ignore[arg-type]
                _strategy_registry(),
                provider=_FakeProvider(healthy=False),
            )

    def test_raises_unhealthy_platform_error_when_regime_service_has_no_states(self) -> None:
        with pytest.raises(UnhealthyPlatformError):
            build_strategy_loop(
                _regime_config(),
                _FakeRegimeService(n_states=0),  # type: ignore[arg-type]
                _strategy_registry(),
                provider=_FakeProvider(),
            )

    def test_raises_unhealthy_platform_error_when_strategy_registry_is_empty(self) -> None:
        with pytest.raises(UnhealthyPlatformError):
            build_strategy_loop(
                _regime_config(),
                _FakeRegimeService(),  # type: ignore[arg-type]
                _strategy_registry(populated=False),
                provider=_FakeProvider(),
            )
