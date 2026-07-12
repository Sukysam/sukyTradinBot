"""Configuration for `StrategyService`/`StrategyRegistry`.

Per docs/engineering-handbook/Architecture/ADR/ADR-009-Strategy-Engine-Design.md's
"freeze interfaces, not implementation" framing: which strategies exist,
which `regime_id`s each one supports, and the allocation formula inside
each strategy are all implementation detail, not part of the frozen
`StrategyDecision` contract. This module is where that detail is
configured, not hardcoded into `registry.py`/`service.py`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyEngineConfig:
    """`default_strategy_id` is an explicit, opt-in fallback used only
    when no registered strategy's `supports(regime_id)` returns `True`
    for the regime being resolved -- e.g. point it at a conservative
    strategy so an unmapped regime still produces a (very small)
    allocation rather than blocking entirely. Leave it `None` (the
    default) to fail loudly (`UnsupportedRegimeError`) on any regime no
    strategy was explicitly configured for, rather than silently
    defaulting -- the safer choice until an operator has deliberately
    decided otherwise for a specific deployment.
    """

    default_strategy_id: str | None = None


__all__ = ["StrategyEngineConfig"]
