"""`BarBuffer` -- bounded per-symbol bar history for Phase B's feature
computation. See
docs/engineering-handbook/Architecture/ADR/ADR-028-Runtime-Feature-Pipeline-Design.md.

A `collections.deque(maxlen=...)` per symbol keeps memory bounded no
matter how long the runtime stays up -- the "run for an extended period
without memory growth" success criterion depends on this being
structural, not on any downstream code remembering to trim anything.
"""

from __future__ import annotations

from collections import deque

from market_data.models import Bar


class BarBuffer:
    """Keeps the most recent `max_bars` bars per symbol, oldest first.

    Symbols are created on first `add()`; a symbol never queried isn't
    allocated, so this scales with however many symbols are actually
    polled, not some fixed universe.
    """

    def __init__(self, max_bars: int) -> None:
        if max_bars <= 0:
            raise ValueError("max_bars must be positive")
        self._max_bars = max_bars
        self._bars: dict[str, deque[Bar]] = {}

    def add(self, bar: Bar) -> None:
        symbol_bars = self._bars.setdefault(bar.symbol, deque(maxlen=self._max_bars))
        symbol_bars.append(bar)

    def get(self, symbol: str) -> list[Bar]:
        """Oldest-first snapshot of whatever history is held for
        `symbol` -- empty if `add()` was never called for it."""
        return list(self._bars.get(symbol, ()))

    def __len__(self) -> int:
        """Total bars held across every symbol -- a bounded-memory sanity
        check, not a meaningful business quantity on its own."""
        return sum(len(symbol_bars) for symbol_bars in self._bars.values())


__all__ = ["BarBuffer"]
