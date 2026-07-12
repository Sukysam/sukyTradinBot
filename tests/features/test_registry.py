from __future__ import annotations

import pandas as pd
import pytest

from features.registry import FeatureCategory, FeatureRegistry, FeatureSpec, feature


def _dummy_compute(df: pd.DataFrame) -> pd.Series:
    return df["close"]


def _spec(name: str = "dummy", **overrides: object) -> FeatureSpec:
    defaults: dict[str, object] = {
        "name": name,
        "category": FeatureCategory.PRICE,
        "version": 1,
        "lookback": 1,
        "dtype": "float64",
        "compute": _dummy_compute,
    }
    defaults.update(overrides)
    return FeatureSpec(**defaults)  # type: ignore[arg-type]


class TestFeatureSpec:
    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            _spec(name="")

    def test_rejects_version_below_one(self) -> None:
        with pytest.raises(ValueError, match="version"):
            _spec(version=0)

    def test_rejects_lookback_below_one(self) -> None:
        with pytest.raises(ValueError, match="lookback"):
            _spec(lookback=0)

    def test_rejects_uses_future_data(self) -> None:
        with pytest.raises(ValueError, match="uses_future_data"):
            _spec(uses_future_data=True)

    def test_description_defaults_empty(self) -> None:
        assert _spec().description == ""


class TestFeatureRegistry:
    def test_register_and_get(self) -> None:
        registry = FeatureRegistry()
        spec = _spec()
        registry.register(spec)
        assert registry.get("dummy") is spec

    def test_get_unknown_raises_key_error(self) -> None:
        registry = FeatureRegistry()
        with pytest.raises(KeyError, match="dummy"):
            registry.get("dummy")

    def test_register_duplicate_name_raises(self) -> None:
        registry = FeatureRegistry()
        registry.register(_spec())
        with pytest.raises(ValueError, match="already registered"):
            registry.register(_spec())

    def test_all_returns_sorted_by_name(self) -> None:
        registry = FeatureRegistry()
        registry.register(_spec(name="zebra"))
        registry.register(_spec(name="alpha"))
        assert [s.name for s in registry.all()] == ["alpha", "zebra"]

    def test_by_category_filters(self) -> None:
        registry = FeatureRegistry()
        registry.register(_spec(name="a", category=FeatureCategory.PRICE))
        registry.register(_spec(name="b", category=FeatureCategory.VOLATILITY))
        assert [s.name for s in registry.by_category(FeatureCategory.PRICE)] == ["a"]

    def test_len_and_contains(self) -> None:
        registry = FeatureRegistry()
        assert len(registry) == 0
        assert "dummy" not in registry
        registry.register(_spec())
        assert len(registry) == 1
        assert "dummy" in registry

    def test_names(self) -> None:
        registry = FeatureRegistry()
        registry.register(_spec(name="b"))
        registry.register(_spec(name="a"))
        assert registry.names() == ("a", "b")


class TestFeatureDecorator:
    def test_decorator_registers_into_target_registry(self) -> None:
        registry = FeatureRegistry()

        @feature("custom", FeatureCategory.PRICE, lookback=5, registry=registry)
        def custom(df: pd.DataFrame) -> pd.Series:
            return df["close"]

        assert "custom" in registry
        assert registry.get("custom").lookback == 5

    def test_decorator_returns_original_function_unchanged(self) -> None:
        registry = FeatureRegistry()

        @feature("custom", FeatureCategory.PRICE, lookback=5, registry=registry)
        def custom(df: pd.DataFrame) -> pd.Series:
            return df["close"]

        df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
        pd.testing.assert_series_equal(custom(df), df["close"])

    def test_decorator_uses_docstring_as_default_description(self) -> None:
        registry = FeatureRegistry()

        @feature("custom", FeatureCategory.PRICE, lookback=5, registry=registry)
        def custom(df: pd.DataFrame) -> pd.Series:
            """First line of docstring."""
            return df["close"]

        assert registry.get("custom").description == "First line of docstring."

    def test_decorator_defaults_to_default_registry(self) -> None:
        from features.registry import DEFAULT_REGISTRY

        @feature("__test_only_feature__", FeatureCategory.PRICE, lookback=1)
        def temp(df: pd.DataFrame) -> pd.Series:
            return df["close"]

        try:
            assert "__test_only_feature__" in DEFAULT_REGISTRY
        finally:
            del DEFAULT_REGISTRY._specs["__test_only_feature__"]
