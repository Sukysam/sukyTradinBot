"""Conservative reference strategy -- small, non-zero allocation ceiling
and the shortest expected holding period of the four reference
strategies. Intended as the natural candidate for `StrategyEngineConfig.
default_strategy_id` (an explicit, opt-in fallback for a `regime_id` no
other registered strategy supports), though nothing in this module
enforces that role -- it's registered and resolved the same way as any
other `Strategy`. See `strategies/_base.py`'s module docstring for why
`regime_id` semantics are always caller-supplied, never hardcoded.
"""

from __future__ import annotations

from datetime import timedelta

from strategy.strategies._base import RegimeMappedStrategy

DEFAULT_BASE_ALLOCATION = 0.1
DEFAULT_EXPECTED_HOLDING_PERIOD = timedelta(days=1)


def create_defensive_strategy(
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
        style="defensive",
    )


__all__ = ["create_defensive_strategy"]
