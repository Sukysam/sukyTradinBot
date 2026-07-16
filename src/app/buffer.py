"""`BarBuffer`/`FeatureVectorBuffer` -- bounded per-symbol history for
Phase B's feature computation and Phase C's regime inference. See
docs/engineering-handbook/Architecture/ADR/ADR-028-Runtime-Feature-Pipeline-Design.md
and
docs/engineering-handbook/Architecture/ADR/ADR-029-Runtime-Regime-Detection-Design.md.

A `collections.deque(maxlen=...)` per symbol keeps memory bounded no
matter how long the runtime stays up -- the "run for an extended period
without memory growth" success criterion depends on this being
structural, not on any downstream code remembering to trim anything.

The two buffers are deliberately separate, near-identical classes
rather than one generic `SymbolBuffer[T]` -- each emitter (Phase B's
`FeatureVectorEmitter`, Phase C's `RegimeEmitter`) owns exactly one
buffer of exactly one item type, and the duplication between them is a
handful of lines. Generalizing now would mean touching Phase B's
already-shipped, tested `BarBuffer` for a saving that isn't worth the
churn.
"""

from __future__ import annotations

from collections import deque

from features.feature_vector import FeatureVector
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


class FeatureVectorBuffer:
    """Keeps the most recent `max_vectors` `FeatureVector`s per symbol,
    oldest first -- `RegimeService.infer`'s input window. Sized well
    above the largest feature lookback so a full buffer eventually
    evicts every NaN-flagged (still-warming-up) vector, letting
    inference succeed on its own once enough clean history has
    accumulated -- see `RegimeEmitter`.
    """

    def __init__(self, max_vectors: int) -> None:
        if max_vectors <= 0:
            raise ValueError("max_vectors must be positive")
        self._max_vectors = max_vectors
        self._vectors: dict[str, deque[FeatureVector]] = {}

    def add(self, vector: FeatureVector) -> None:
        symbol_vectors = self._vectors.setdefault(vector.symbol, deque(maxlen=self._max_vectors))
        symbol_vectors.append(vector)

    def get(self, symbol: str) -> list[FeatureVector]:
        """Oldest-first snapshot of whatever history is held for
        `symbol` -- empty if `add()` was never called for it."""
        return list(self._vectors.get(symbol, ()))

    def __len__(self) -> int:
        """Total vectors held across every symbol -- a bounded-memory
        sanity check, not a meaningful business quantity on its own."""
        return sum(len(symbol_vectors) for symbol_vectors in self._vectors.values())


__all__ = ["BarBuffer", "FeatureVectorBuffer"]
