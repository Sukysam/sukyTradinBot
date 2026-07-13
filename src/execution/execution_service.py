"""`ExecutionService` -- the single public entry point for this package.

Pipeline: `ExecutionDecision` -> `MarketSnapshotProvider` ->
`FeatureSnapshotProvider` -> `OrderBuilder` -> `OrderIntent` (or `None`).
Never touches a broker -- submitting the resulting `OrderIntent` is a
`BrokerAdapter`'s job, called separately by whatever process owns the
actual submission step (see ADR-013).
"""

from __future__ import annotations

from dataclasses import dataclass

from execution.config import ExecutionServiceConfig
from execution.interfaces import FeatureSnapshotProvider, MarketSnapshotProvider
from execution.models import OrderIntent
from execution.order_builder import OrderBuilder
from execution.providers import BarSnapshotProvider, FeaturePipelineSnapshotProvider
from execution.stop_loss import ATRStopPolicy
from market_data.interfaces import HistoricalDataProvider
from risk.models import ExecutionDecision, PortfolioState


@dataclass(frozen=True)
class ExecutionService:
    market_snapshot_provider: MarketSnapshotProvider
    feature_snapshot_provider: FeatureSnapshotProvider
    order_builder: OrderBuilder

    @classmethod
    def default(
        cls,
        historical_provider: HistoricalDataProvider,
        config: ExecutionServiceConfig | None = None,
    ) -> ExecutionService:
        """A sensible default pipeline: bar-close market snapshots,
        `FeaturePipeline`-computed feature snapshots, and `ATRStopPolicy`
        -- all sourced from one injected `HistoricalDataProvider`.
        Callers needing live quotes, a different stop policy, or a
        different data source construct `ExecutionService` directly
        instead.
        """
        cfg = config or ExecutionServiceConfig()
        return cls(
            market_snapshot_provider=BarSnapshotProvider(
                historical_provider=historical_provider, tick_size=cfg.tick_size
            ),
            feature_snapshot_provider=FeaturePipelineSnapshotProvider(
                historical_provider=historical_provider
            ),
            order_builder=OrderBuilder(
                stop_loss_policy=ATRStopPolicy(), time_in_force=cfg.time_in_force
            ),
        )

    def decide(
        self, execution_decision: ExecutionDecision, portfolio: PortfolioState
    ) -> OrderIntent | None:
        if not execution_decision.approved:
            return None

        context = self.market_snapshot_provider.get_snapshot(execution_decision.symbol)
        feature_snapshot = self.feature_snapshot_provider.get_latest(execution_decision.symbol)
        return self.order_builder.build(execution_decision, portfolio, context, feature_snapshot)


__all__ = ["ExecutionService"]
