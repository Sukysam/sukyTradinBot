"""Tests for `app.frame.RuntimeFrame`'s enrichment-order invariant and
`with_*` helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.frame import RuntimeFrame
from features.feature_vector import FeatureVector, Provenance
from hmm.models import RegimeState
from market_data.models import Bar, Timeframe
from strategy.models import StrategyDecision

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _bar() -> Bar:
    return Bar(
        symbol="AAPL",
        timestamp=T0,
        timeframe=Timeframe.DAY_1,
        open=99.0,
        high=101.0,
        low=98.0,
        close=100.0,
        volume=1000.0,
    )


def _feature_vector() -> FeatureVector:
    return FeatureVector(
        timestamp=T0,
        symbol="AAPL",
        feature_values=(1.0,),
        feature_names=("f1",),
        metadata={},
        quality_flags={},
        provenance=Provenance(
            pipeline_version="2",
            manifest_version="1",
            feature_versions={"f1": 1},
            generated_at=T0,
            source_dataset="test",
        ),
    )


def _regime_state() -> RegimeState:
    return RegimeState(
        timestamp=T0,
        symbol="AAPL",
        regime_id=0,
        confidence=0.8,
        transition_probability=0.9,
        model_version="v1",
        feature_pipeline_version="2",
        metadata={},
    )


def _strategy_decision() -> StrategyDecision:
    return StrategyDecision(
        timestamp=T0,
        symbol="AAPL",
        strategy_id="growth",
        regime_id=0,
        allocation=0.5,
        confidence=0.8,
        expected_holding_period=timedelta(days=20),
        reasoning="test",
        metadata={},
    )


class TestRuntimeFrame:
    def test_bar_only_frame_constructs(self) -> None:
        frame = RuntimeFrame(bar=_bar())
        assert frame.feature_vector is None
        assert frame.regime_state is None
        assert frame.strategy_decision is None

    def test_rejects_regime_state_without_feature_vector(self) -> None:
        with pytest.raises(ValueError, match="feature_vector"):
            RuntimeFrame(bar=_bar(), regime_state=_regime_state())

    def test_rejects_strategy_decision_without_regime_state(self) -> None:
        with pytest.raises(ValueError, match="regime_state"):
            RuntimeFrame(
                bar=_bar(), feature_vector=_feature_vector(), strategy_decision=_strategy_decision()
            )

    def test_with_feature_vector_enriches_without_mutating_original(self) -> None:
        frame = RuntimeFrame(bar=_bar())
        vector = _feature_vector()
        enriched = frame.with_feature_vector(vector)

        assert frame.feature_vector is None
        assert enriched.feature_vector is vector
        assert enriched.bar == frame.bar

    def test_with_regime_state_enriches_without_mutating_original(self) -> None:
        frame = RuntimeFrame(bar=_bar(), feature_vector=_feature_vector())
        state = _regime_state()
        enriched = frame.with_regime_state(state)

        assert frame.regime_state is None
        assert enriched.regime_state is state
        assert enriched.feature_vector == frame.feature_vector

    def test_with_strategy_decision_enriches_without_mutating_original(self) -> None:
        frame = RuntimeFrame(
            bar=_bar(), feature_vector=_feature_vector(), regime_state=_regime_state()
        )
        decision = _strategy_decision()
        enriched = frame.with_strategy_decision(decision)

        assert frame.strategy_decision is None
        assert enriched.strategy_decision is decision
        assert enriched.regime_state == frame.regime_state
