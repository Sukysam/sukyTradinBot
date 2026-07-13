"""Tests for `execution.execution_service.ExecutionService`."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from execution.execution_service import ExecutionService
from execution.models import ExecutionContext, FeatureSnapshot, OrderSide
from execution.order_builder import OrderBuilder
from execution.providers import BarSnapshotProvider, FeaturePipelineSnapshotProvider
from execution.stop_loss import ATRStopPolicy
from risk.models import Position
from tests.execution.conftest import (
    make_execution_context,
    make_execution_decision,
    make_feature_snapshot,
    make_portfolio_state,
)


@dataclass(frozen=True)
class _FakeMarketSnapshotProvider:
    context: ExecutionContext

    def get_snapshot(self, symbol: str) -> ExecutionContext:
        assert symbol == self.context.symbol
        return self.context


@dataclass(frozen=True)
class _FakeFeatureSnapshotProvider:
    snapshot: FeatureSnapshot

    def get_latest(self, symbol: str) -> FeatureSnapshot:
        assert symbol == self.snapshot.symbol
        return self.snapshot


class TestDecide:
    def test_returns_none_for_a_rejected_decision_without_touching_providers(self) -> None:
        market_provider = _FakeMarketSnapshotProvider(make_execution_context())
        feature_provider = _FakeFeatureSnapshotProvider(make_feature_snapshot())
        service = ExecutionService(
            market_snapshot_provider=market_provider,
            feature_snapshot_provider=feature_provider,
            order_builder=OrderBuilder(stop_loss_policy=ATRStopPolicy()),
        )
        rejected = make_execution_decision(approved=False)
        portfolio = make_portfolio_state()

        assert service.decide(rejected, portfolio) is None

    def test_builds_an_order_intent_end_to_end(self) -> None:
        market_provider = _FakeMarketSnapshotProvider(make_execution_context(reference_price=100.0))
        feature_provider = _FakeFeatureSnapshotProvider(make_feature_snapshot(atr_14=2.0))
        service = ExecutionService(
            market_snapshot_provider=market_provider,
            feature_snapshot_provider=feature_provider,
            order_builder=OrderBuilder(stop_loss_policy=ATRStopPolicy(atr_multiplier=2.0)),
        )
        decision = make_execution_decision(approved_allocation=0.5)
        portfolio = make_portfolio_state(equity=100_000.0, positions=())

        intent = service.decide(decision, portfolio)

        assert intent is not None
        assert intent.side is OrderSide.BUY
        assert intent.stop_loss == 96.0  # 100 - 2*2

    def test_returns_none_when_target_already_matches_position(self) -> None:
        market_provider = _FakeMarketSnapshotProvider(make_execution_context(reference_price=100.0))
        feature_provider = _FakeFeatureSnapshotProvider(make_feature_snapshot())
        service = ExecutionService(
            market_snapshot_provider=market_provider,
            feature_snapshot_provider=feature_provider,
            order_builder=OrderBuilder(stop_loss_policy=ATRStopPolicy()),
        )
        decision = make_execution_decision(approved_allocation=0.1)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="TEST", sector="Tech", market_value=10_000.0),),
        )

        assert service.decide(decision, portfolio) is None


class TestDefault:
    def test_wires_a_sensible_default_pipeline(self) -> None:
        historical_provider = MagicMock()
        service = ExecutionService.default(historical_provider)

        assert isinstance(service.market_snapshot_provider, BarSnapshotProvider)
        assert isinstance(service.feature_snapshot_provider, FeaturePipelineSnapshotProvider)
        assert isinstance(service.order_builder, OrderBuilder)
        assert isinstance(service.order_builder.stop_loss_policy, ATRStopPolicy)
