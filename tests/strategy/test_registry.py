from __future__ import annotations

import pytest

from strategy.exceptions import (
    AmbiguousStrategyError,
    StrategyNotFoundError,
    UnsupportedRegimeError,
)
from strategy.registry import StrategyRegistry
from strategy.strategies import (
    create_bear_strategy,
    create_defensive_strategy,
    create_growth_strategy,
)


class TestRegister:
    def test_register_and_get(self) -> None:
        registry = StrategyRegistry()
        strategy = create_growth_strategy("growth_v1", frozenset({0}))
        registry.register(strategy)
        assert registry.get("growth_v1") is strategy

    def test_rejects_duplicate_strategy_id(self) -> None:
        registry = StrategyRegistry()
        registry.register(create_growth_strategy("growth_v1", frozenset({0})))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(create_bear_strategy("growth_v1", frozenset({1})))

    def test_len_and_contains(self) -> None:
        registry = StrategyRegistry()
        assert len(registry) == 0
        registry.register(create_growth_strategy("growth_v1", frozenset({0})))
        assert len(registry) == 1
        assert "growth_v1" in registry
        assert "bear_v1" not in registry

    def test_names_returns_sorted_tuple(self) -> None:
        registry = StrategyRegistry()
        registry.register(create_bear_strategy("bear_v1", frozenset({1})))
        registry.register(create_growth_strategy("growth_v1", frozenset({0})))
        assert registry.names() == ("bear_v1", "growth_v1")


class TestGet:
    def test_unregistered_strategy_id_raises(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(StrategyNotFoundError):
            registry.get("nope")


class TestResolve:
    def test_resolves_unique_matching_strategy(self) -> None:
        registry = StrategyRegistry()
        growth = create_growth_strategy("growth_v1", frozenset({0}))
        bear = create_bear_strategy("bear_v1", frozenset({1}))
        registry.register(growth)
        registry.register(bear)
        assert registry.resolve(0) is growth
        assert registry.resolve(1) is bear

    def test_unsupported_regime_raises_without_default(self) -> None:
        registry = StrategyRegistry()
        registry.register(create_growth_strategy("growth_v1", frozenset({0})))
        with pytest.raises(UnsupportedRegimeError):
            registry.resolve(99)

    def test_unsupported_regime_falls_back_to_default(self) -> None:
        registry = StrategyRegistry()
        registry.register(create_growth_strategy("growth_v1", frozenset({0})))
        defensive = create_defensive_strategy("defensive_v1", frozenset())
        registry.register(defensive)
        assert registry.resolve(99, default_strategy_id="defensive_v1") is defensive

    def test_default_strategy_id_pointing_at_unregistered_id_raises(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(StrategyNotFoundError):
            registry.resolve(99, default_strategy_id="nope")

    def test_ambiguous_when_two_strategies_support_the_same_regime(self) -> None:
        registry = StrategyRegistry()
        registry.register(create_growth_strategy("growth_a", frozenset({0})))
        registry.register(create_growth_strategy("growth_b", frozenset({0})))
        with pytest.raises(AmbiguousStrategyError):
            registry.resolve(0)

    def test_deterministic_mapping_is_stable_across_calls(self) -> None:
        registry = StrategyRegistry()
        growth = create_growth_strategy("growth_v1", frozenset({0, 2}))
        registry.register(growth)
        assert registry.resolve(0) is growth
        assert registry.resolve(0) is growth
        assert registry.resolve(2) is growth

    def test_configuration_override_changes_which_regime_ids_a_strategy_supports(self) -> None:
        # "Configuration override": the same strategy factory, constructed
        # with a different supported_regime_ids, dispatches differently --
        # no code change to registry.py or service.py required.
        default_registry = StrategyRegistry()
        default_registry.register(create_growth_strategy("growth_v1", frozenset({0})))

        overridden_registry = StrategyRegistry()
        overridden_registry.register(create_growth_strategy("growth_v1", frozenset({5})))

        with pytest.raises(UnsupportedRegimeError):
            default_registry.resolve(5)
        assert overridden_registry.resolve(5).strategy_id == "growth_v1"
