"""`NewsSignal` -- the single contract `nlp.service`'s eventual public
method is meant to produce, and the only thing about this package any
downstream consumer (Milestone 11's Signal Orchestration) is meant to
depend on. Frozen per
docs/engineering-handbook/Architecture/ADR/ADR-018-NewsSignal-Contract.md
*before* this package existed at all; full detail in
"docs/engineering-handbook/Standards/NewsSignal Contract.md".

Also defines `NewsItem` -- an internal, *unfrozen* value object
representing one cleaned, deduplicated news event, ready for sentiment
scoring but not yet scored. It is Phase A's own deliverable, never part
of the frozen `NewsSignal` contract -- the same "execution contracts
describe trading intent, not market observations" split
docs/engineering-handbook/Architecture/ADR/ADR-013-Execution-Layer-Design.md
established for `ExecutionContext`/`FeatureSnapshot`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from common.time import require_utc

REQUIRED_SENTIMENT_LABELS = frozenset({"positive", "negative", "neutral"})


def _require_no_blank_entries(values: tuple[str, ...], field_name: str) -> None:
    for value in values:
        if not value:
            raise ValueError(f"{field_name} must not contain empty strings")


def _validate_sentiment(positive: float, negative: float, neutral: float, label: str) -> None:
    """Shared by `SentimentResult` and `NewsSignal` -- both carry the same
    three-probability-plus-label shape (see `nlp.sentiment.SentimentResult`
    docstring), and duplicating this validation between them would risk
    the two silently drifting apart."""
    for name, value in (
        ("sentiment_positive", positive),
        ("sentiment_negative", negative),
        ("sentiment_neutral", neutral),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0.0, 1.0], got {value}")
    total = positive + negative + neutral
    if not 0.99 <= total <= 1.01:
        raise ValueError(
            "sentiment_positive + sentiment_negative + sentiment_neutral must be in "
            f"[0.99, 1.01], got {total}"
        )
    if label not in REQUIRED_SENTIMENT_LABELS:
        raise ValueError(
            f"sentiment_label must be one of {sorted(REQUIRED_SENTIMENT_LABELS)}, got {label!r}"
        )
    scores = {"positive": positive, "negative": negative, "neutral": neutral}
    if scores[label] != max(scores.values()):
        raise ValueError(
            f"sentiment_label {label!r} does not match the argmax of the sentiment scores "
            f"{scores}"
        )


@dataclass(frozen=True)
class NewsItem:
    """One cleaned, de-duplicated news event -- Phase A's output. Adapts
    `regime-trader/broker/news_streamer.py`'s `NewsItem` shape (`id` ->
    `source_id`, `created_at` -> `published_at`), kept as an internal
    value object rather than a frozen contract since nothing outside
    this package is meant to depend on it directly."""

    source_id: str
    source: str
    headline: str
    summary: str
    symbols: tuple[str, ...]
    published_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.published_at, "published_at")
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        if not self.source:
            raise ValueError("source must not be empty")
        if not self.headline:
            raise ValueError("headline must not be empty")
        _require_no_blank_entries(self.symbols, "symbols")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source": self.source,
            "headline": self.headline,
            "summary": self.summary,
            "symbols": list(self.symbols),
            "published_at": self.published_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NewsItem:
        return cls(
            source_id=data["source_id"],
            source=data["source"],
            headline=data["headline"],
            summary=data["summary"],
            symbols=tuple(data["symbols"]),
            published_at=datetime.fromisoformat(data["published_at"]),
        )


@dataclass(frozen=True)
class NewsSignal:
    signal_id: str
    source_id: str
    source: str
    symbols: tuple[str, ...]
    entities: tuple[str, ...]
    headline: str
    published_at: datetime
    processed_at: datetime
    sentiment_positive: float
    sentiment_negative: float
    sentiment_neutral: float
    sentiment_label: str
    model_version: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_utc(self.published_at, "published_at")
        require_utc(self.processed_at, "processed_at")
        if not self.signal_id:
            raise ValueError("signal_id must not be empty")
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        if not self.source:
            raise ValueError("source must not be empty")
        if not self.headline:
            raise ValueError("headline must not be empty")
        _require_no_blank_entries(self.symbols, "symbols")
        _require_no_blank_entries(self.entities, "entities")
        if self.processed_at < self.published_at:
            raise ValueError("processed_at must be >= published_at")
        _validate_sentiment(
            self.sentiment_positive,
            self.sentiment_negative,
            self.sentiment_neutral,
            self.sentiment_label,
        )
        if not self.model_version:
            raise ValueError("model_version must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "source_id": self.source_id,
            "source": self.source,
            "symbols": list(self.symbols),
            "entities": list(self.entities),
            "headline": self.headline,
            "published_at": self.published_at.isoformat(),
            "processed_at": self.processed_at.isoformat(),
            "sentiment_positive": self.sentiment_positive,
            "sentiment_negative": self.sentiment_negative,
            "sentiment_neutral": self.sentiment_neutral,
            "sentiment_label": self.sentiment_label,
            "model_version": self.model_version,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NewsSignal:
        return cls(
            signal_id=data["signal_id"],
            source_id=data["source_id"],
            source=data["source"],
            symbols=tuple(data["symbols"]),
            entities=tuple(data["entities"]),
            headline=data["headline"],
            published_at=datetime.fromisoformat(data["published_at"]),
            processed_at=datetime.fromisoformat(data["processed_at"]),
            sentiment_positive=data["sentiment_positive"],
            sentiment_negative=data["sentiment_negative"],
            sentiment_neutral=data["sentiment_neutral"],
            sentiment_label=data["sentiment_label"],
            model_version=data["model_version"],
            metadata=dict(data["metadata"]),
        )


@dataclass(frozen=True)
class SentimentResult:
    """One `SentimentScorer.score_batch` output for a single headline --
    Phase B's internal handoff between scoring and `NewsSignal` assembly,
    never itself the frozen contract. Adapts
    `regime-trader/core/sentiment_engine.py`'s `SentimentScore` shape
    (`text` dropped -- the caller already has the headline it passed in)."""

    positive: float
    negative: float
    neutral: float
    label: str

    def __post_init__(self) -> None:
        _validate_sentiment(self.positive, self.negative, self.neutral, self.label)


__all__ = ["REQUIRED_SENTIMENT_LABELS", "NewsItem", "NewsSignal", "SentimentResult"]
