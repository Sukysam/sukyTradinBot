"""`StrategyService` -- the only class outside this package anyone should
import. Coordinates `FeatureVector` + `RegimeState` -> `StrategyRegistry`
-> `Strategy` -> `StrategyDecision`. No broker, no risk, no memory, no
NLP -- see
docs/engineering-handbook/Architecture/ADR/ADR-009-Strategy-Engine-Design.md.
"""

from __future__ import annotations

from features.feature_vector import FeatureVector
from hmm.models import RegimeState
from strategy.config import StrategyEngineConfig
from strategy.exceptions import ContractViolationError
from strategy.models import StrategyDecision
from strategy.registry import StrategyRegistry


class StrategyService:
    """Stateless coordinator over a `StrategyRegistry`. Construct one per
    registry/config pair (cheap -- holds no fitted state of its own,
    unlike `hmm.service.RegimeService`).
    """

    def __init__(
        self, registry: StrategyRegistry, config: StrategyEngineConfig | None = None
    ) -> None:
        self._registry = registry
        self._config = config or StrategyEngineConfig()

    def decide(self, feature_vector: FeatureVector, regime_state: RegimeState) -> StrategyDecision:
        """Convert `regime_state` (with `feature_vector` as additional
        context available to the resolved strategy) into a
        `StrategyDecision`. Raises `ContractViolationError` if the two
        inputs disagree on `symbol`/`timestamp` -- a caller bug, not
        something to silently reconcile.
        """
        if feature_vector.symbol != regime_state.symbol:
            raise ContractViolationError(
                f"FeatureVector symbol {feature_vector.symbol!r} != "
                f"RegimeState symbol {regime_state.symbol!r}"
            )
        if feature_vector.timestamp != regime_state.timestamp:
            raise ContractViolationError(
                f"FeatureVector timestamp {feature_vector.timestamp.isoformat()} != "
                f"RegimeState timestamp {regime_state.timestamp.isoformat()}"
            )
        strategy = self._registry.resolve(
            regime_state.regime_id, default_strategy_id=self._config.default_strategy_id
        )
        return strategy.allocate(feature_vector, regime_state)


__all__ = ["StrategyService"]
