"""Mean-reversion reference strategy, for whichever `regime_id`(s) the
caller configures as range-bound/sideways-like for a given trained model.
Moderate allocation ceiling, shorter expected holding period than the
growth strategy (mean-reversion positions are conventionally shorter-
lived than trend-following ones). See `strategies/_base.py`'s module
docstring for why `regime_id` semantics are always caller-supplied, never
hardcoded.
"""

from __future__ import annotations

from datetime import timedelta

from strategy.strategies._base import RegimeMappedStrategy

DEFAULT_BASE_ALLOCATION = 0.5
DEFAULT_EXPECTED_HOLDING_PERIOD = timedelta(days=3)


def create_mean_reversion_strategy(
    strategy_id: str,
    supported_regime_ids: frozenset[int],
    *,
    base_allocation: float = DEFAULT_BASE_ALLOCATION,
    expected_holding_period: timedelta = DEFAULT_EXPECTED_HOLDING_PERIOD,
) -> RegimeMappedStrategy:
    return RegimeMappedStrategy(
        strategy_id=strategy_id,
        supported_regime_ids=supported_regime_ids,
        base_allocation=base_allocation,
        expected_holding_period=expected_holding_period,
        style="mean_reversion",
    )


__all__ = ["create_mean_reversion_strategy"]
