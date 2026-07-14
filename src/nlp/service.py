"""`NlpService` -- Phase B's orchestration layer, turning a batch of
Phase A `NewsItem`s into frozen `NewsSignal`s via an injected
`SentimentScorer`. This is the sanctioned entry point for anything
outside this package that wants a `NewsSignal`; per the Standards doc's
shadow-mode guarantee, its output is recorded, never wired into
`strategy`, `risk`, or `execution`.

Entity extraction is deliberately deferred -- every `NewsSignal` produced
here has `entities=()`. The frozen contract explicitly allows this (see
Standards/NewsSignal Contract.md's `entities` row); adding a real
extractor is future work, not assumed by this milestone's own phased
build order (ingestion -> sentiment -> attribution).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from nlp.exceptions import NlpError
from nlp.interfaces import SentimentScorer
from nlp.models import NewsItem, NewsSignal


@dataclass
class NlpService:
    scorer: SentimentScorer

    def build_signals(
        self, items: Sequence[NewsItem], *, processed_at: datetime
    ) -> list[NewsSignal]:
        """Score every headline in `items` in a single batched call --
        deliberately no per-item overload exists on this class, so a
        caller cannot fall into scoring one headline at a time (see
        `SentimentScorer.score_batch`'s docstring)."""
        if not items:
            return []
        headlines = [item.headline for item in items]
        results = self.scorer.score_batch(headlines)
        if len(results) != len(items):
            raise NlpError(f"scorer returned {len(results)} results for {len(items)} headlines")
        return [
            NewsSignal(
                signal_id=f"{item.source}:{item.source_id}",
                source_id=item.source_id,
                source=item.source,
                symbols=item.symbols,
                entities=(),
                headline=item.headline,
                published_at=item.published_at,
                processed_at=processed_at,
                sentiment_positive=result.positive,
                sentiment_negative=result.negative,
                sentiment_neutral=result.neutral,
                sentiment_label=result.label,
                model_version=self.scorer.model_version,
                metadata={},
            )
            for item, result in zip(items, results)
        ]


__all__ = ["NlpService"]
