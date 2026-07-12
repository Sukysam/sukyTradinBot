"""Protective reference strategy, for whichever `regime_id`(s) the caller
configures as bear-like for a given trained model. Zero base allocation
by default -- fully flat regardless of regime confidence -- and the
shortest expected holding period, reflecting that a position isn't
expected to be held through a bear regime at all. See
`strategies/_base.py`'s module docstring for why `regime_id` semantics
are always caller-supplied, never hardcoded.
"""

from __future__ import annotations

from datetime import timedelta

from strategy.strategies._base import RegimeMappedStrategy

DEFAULT_BASE_ALLOCATION = 0.0
DEFAULT_EXPECTED_HOLDING_PERIOD = timedelta(days=5)


def create_bear_strategy(
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
        style="bear",
    )


__all__ = ["create_bear_strategy"]
