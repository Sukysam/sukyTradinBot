from __future__ import annotations

import pytest

from strategy.config import StrategyEngineConfig
from strategy.exceptions import ContractViolationError, UnsupportedRegimeError
from strategy.registry import StrategyRegistry
from strategy.service import StrategyService
from strategy.strategies import (
    create_bear_strategy,
    create_defensive_strategy,
    create_growth_strategy,
)
from tests.strategy.conftest import make_feature_vector, make_regime_state


def _service(*, default_strategy_id: str | None = None) -> StrategyService:
    registry = StrategyRegistry()
    registry.register(create_growth_strategy("growth_v1", frozenset({0})))
    registry.register(create_bear_strategy("bear_v1", frozenset({1})))
    registry.register(create_defensive_strategy("defensive_v1", frozenset()))
    return StrategyService(registry, StrategyEngineConfig(default_strategy_id=default_strategy_id))


class TestDecide:
    def test_dispatches_to_the_resolved_strategy(self) -> None:
        service = _service()
        fv = make_feature_vector()
        rs = make_regime_state(regime_id=0)
        decision = service.decide(fv, rs)
        assert decision.strategy_id == "growth_v1"

    def test_unsupported_regime_raises_without_default(self) -> None:
        service = _service()
        fv = make_feature_vector()
        rs = make_regime_state(regime_id=99)
        with pytest.raises(UnsupportedRegimeError):
            service.decide(fv, rs)

    def test_unsupported_regime_falls_back_to_configured_default(self) -> None:
        service = _service(default_strategy_id="defensive_v1")
        fv = make_feature_vector()
        rs = make_regime_state(regime_id=99, confidence=0.4)
        decision = service.decide(fv, rs)
        assert decision.strategy_id == "defensive_v1"
        assert decision.regime_id == 99

    def test_rejects_mismatched_symbol(self) -> None:
        service = _service()
        fv = make_feature_vector(symbol="AAPL")
        rs = make_regime_state(symbol="MSFT", regime_id=0)
        with pytest.raises(ContractViolationError, match="symbol"):
            service.decide(fv, rs)

    def test_rejects_mismatched_timestamp(self) -> None:
        from datetime import datetime, timedelta, timezone

        service = _service()
        fv = make_feature_vector(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc))
        rs = make_regime_state(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=1), regime_id=0
        )
        with pytest.raises(ContractViolationError, match="timestamp"):
            service.decide(fv, rs)

    def test_default_config_used_when_none_supplied(self) -> None:
        registry = StrategyRegistry()
        registry.register(create_growth_strategy("growth_v1", frozenset({0})))
        service = StrategyService(registry)  # no config -- StrategyEngineConfig() default
        fv = make_feature_vector()
        rs = make_regime_state(regime_id=0)
        decision = service.decide(fv, rs)
        assert decision.strategy_id == "growth_v1"
        with pytest.raises(UnsupportedRegimeError):
            service.decide(fv, make_regime_state(regime_id=99))

    def test_deterministic_output_for_identical_inputs(self) -> None:
        service = _service()
        fv = make_feature_vector()
        rs = make_regime_state(regime_id=1, confidence=0.5)
        first = service.decide(fv, rs)
        second = service.decide(fv, rs)
        assert first == second
