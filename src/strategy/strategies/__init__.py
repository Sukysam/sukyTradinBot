"""Reference strategies, each a thin, named factory over the shared
`RegimeMappedStrategy` implementation (`_base.py`) -- see that module's
docstring for why the allocation formula is identical across styles in
this deliberately-simple milestone, and why `regime_id` semantics are
always caller-supplied, never hardcoded into any of these files.
"""

from __future__ import annotations

from strategy.strategies._base import RegimeMappedStrategy
from strategy.strategies.bear import create_bear_strategy
from strategy.strategies.bull import create_growth_strategy
from strategy.strategies.defensive import create_defensive_strategy
from strategy.strategies.sideways import create_mean_reversion_strategy

__all__ = [
    "RegimeMappedStrategy",
    "create_bear_strategy",
    "create_defensive_strategy",
    "create_growth_strategy",
    "create_mean_reversion_strategy",
]
