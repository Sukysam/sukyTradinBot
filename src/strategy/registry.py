"""The strategy registry: every strategy this platform can dispatch to,
in one place -- replacing an `if regime_id == ...: elif ...` chain with a
lookup that's trivial to extend (register a new `Strategy`, no change to
dispatch logic) and trivial to test in isolation.

`Strategy.supports(regime_id)` is the *only* source of truth for regime
dispatch -- there is deliberately no separate `regime_id -> strategy_id`
map living in the registry that could drift out of sync with what each
strategy actually declares. See
docs/engineering-handbook/Architecture/ADR/ADR-009-Strategy-Engine-Design.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from strategy.exceptions import (
    AmbiguousStrategyError,
    StrategyNotFoundError,
    UnsupportedRegimeError,
)
from strategy.interfaces import Strategy


@dataclass
class StrategyRegistry:
    """A named collection of `Strategy`s. Construct your own instance per
    deployment/test rather than relying on a shared global default --
    unlike `features.registry.DEFAULT_REGISTRY` (populated once, at
    import time, by decorator side effects), which strategies exist and
    which regimes they support is inherently per-deployment configuration
    (see `config.py`), not a fixed catalog baked in at import time.
    """

    _strategies: dict[str, Strategy] = field(default_factory=dict)

    def register(self, strategy: Strategy) -> None:
        """Add `strategy`. Raises `ValueError` on a duplicate
        `strategy_id` -- a silent overwrite would mean two strategies
        silently sharing one identity in every `StrategyDecision` that
        names it.
        """
        if strategy.strategy_id in self._strategies:
            raise ValueError(
                f"strategy_id {strategy.strategy_id!r} is already registered; "
                "strategy_id must be unique per registry"
            )
        self._strategies[strategy.strategy_id] = strategy

    def get(self, strategy_id: str) -> Strategy:
        try:
            return self._strategies[strategy_id]
        except KeyError:
            raise StrategyNotFoundError(f"no strategy registered under {strategy_id!r}") from None

    def resolve(self, regime_id: int, *, default_strategy_id: str | None = None) -> Strategy:
        """The one strategy whose `supports(regime_id)` is `True`.

        Raises `AmbiguousStrategyError` if more than one registered
        strategy supports the same `regime_id` -- dispatch must be
        deterministic, and this platform doesn't guess a priority order
        on a caller's behalf. Raises `UnsupportedRegimeError` if none do
        and `default_strategy_id` isn't supplied.
        """
        matches = [s for s in self._strategies.values() if s.supports(regime_id)]
        if len(matches) > 1:
            raise AmbiguousStrategyError(
                f"regime_id={regime_id} is supported by multiple registered strategies: "
                f"{sorted(s.strategy_id for s in matches)}"
            )
        if len(matches) == 1:
            return matches[0]
        if default_strategy_id is not None:
            return self.get(default_strategy_id)
        raise UnsupportedRegimeError(
            f"no registered strategy supports regime_id={regime_id}, and no "
            "default_strategy_id fallback is configured"
        )

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._strategies))

    def __len__(self) -> int:
        return len(self._strategies)

    def __contains__(self, strategy_id: str) -> bool:
        return strategy_id in self._strategies


__all__ = ["StrategyRegistry"]
