"""Protocol interfaces for the NLP layer's two pluggable stages: Phase
A's deduplicated news storage and Phase B's sentiment scoring. `nlp.store`
and `nlp.sentiment` each ship implementations; these Protocols are what
make a caller swappable between them without depending on either
concretely -- per explicit product-owner direction to "keep the model
behind a simple interface so you can swap implementations later."
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from nlp.models import NewsItem, SentimentResult


class NewsItemStore(Protocol):
    """A deduplicating store of `NewsItem`s, keyed on `(source,
    source_id)`. Unlike `memory.interfaces.ExperienceStore`, this store's
    `add` is idempotent by design -- redelivering the same raw event
    (e.g. a WebSocket reconnect replay) must not create a second entry."""

    def add(self, item: NewsItem) -> bool:
        """Store `item` unless a prior item with the same `(source,
        source_id)` already exists. Returns `True` if this call actually
        stored a new item, `False` if it was a duplicate no-op."""
        ...

    def all(self) -> Sequence[NewsItem]:
        """Every stored `NewsItem`, in the order they were first added."""
        ...

    def __len__(self) -> int: ...


class SentimentScorer(Protocol):
    """Scores headlines into `SentimentResult`s. Batch-only by design --
    no single-headline `score` method exists on this Protocol, so a
    caller physically cannot fall into the "loop calling score() per
    headline" anti-pattern `06_NLP_ENGINEER.md` explicitly warns against
    for burst-scoring workloads."""

    @property
    def model_version(self) -> str:
        """Identifies this scorer's model version -- copied directly
        into every `NewsSignal.model_version` it produces."""
        ...

    def score_batch(self, headlines: Sequence[str]) -> Sequence[SentimentResult]:
        """One `SentimentResult` per input headline, same order. Must
        return `[]` for empty input without any model invocation --
        matches `regime-trader/core/sentiment_engine.py::SentimentEngine.
        score_batch`'s existing contract."""
        ...


__all__ = ["NewsItemStore", "SentimentScorer"]
