"""Settings shared across `ExecutionService.default`'s assembly of a
sensible default pipeline. Individual providers/policies still take their
own parameters directly -- this only holds what that default assembly
itself needs, mirroring `risk.config.RiskServiceConfig`'s "one real knob,
not a speculative grab-bag" precedent.
"""

from __future__ import annotations

from dataclasses import dataclass

from execution.models import TimeInForce
from execution.providers import DEFAULT_TICK_SIZE


@dataclass(frozen=True)
class ExecutionServiceConfig:
    time_in_force: TimeInForce = TimeInForce.DAY
    tick_size: float = DEFAULT_TICK_SIZE


__all__ = ["ExecutionServiceConfig"]
