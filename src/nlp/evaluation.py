"""Phase C: read-only reporting on Phase A ingestion and Phase B
sentiment scoring. Measures ingestion latency/throughput, deduplication
rate, sentiment distribution, and scoring throughput -- never influences
`strategy`, `risk`, or `execution`, and never mutates an `NewsItemStore`
or a `SentimentScorer`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from common.time import require_utc
from nlp.models import NewsSignal


def _require_ordered(started_at: datetime, completed_at: datetime) -> float:
    require_utc(started_at, "started_at")
    require_utc(completed_at, "completed_at")
    if completed_at < started_at:
        raise ValueError("completed_at must be >= started_at")
    return (completed_at - started_at).total_seconds()


def evaluate_ingestion(
    add_results: Sequence[bool], *, started_at: datetime, completed_at: datetime
) -> dict[str, Any]:
    """Reads `NewsItemStore.add`'s boolean results (`True` = newly
    stored, `False` = duplicate no-op) from one ingestion run, plus the
    wall-clock window it ran in, to report deduplication rate and
    throughput. Does not itself call `add` -- the caller owns ingestion,
    this function only reports on it after the fact."""
    elapsed = _require_ordered(started_at, completed_at)
    n = len(add_results)
    duplicates = sum(1 for stored in add_results if not stored)
    return {
        "n_items": n,
        "n_stored": n - duplicates,
        "n_duplicates": duplicates,
        "deduplication_rate": duplicates / n if n else 0.0,
        "elapsed_seconds": elapsed,
        "throughput_items_per_second": n / elapsed if elapsed > 0 else 0.0,
    }


def evaluate_sentiment(
    signals: Sequence[NewsSignal],
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    """Sentiment-label distribution and mean scores across `signals`.
    `started_at`/`completed_at` are optional -- pass both to also report
    scoring throughput; omit either to get distribution-only."""
    n = len(signals)
    report: dict[str, Any] = {
        "n_signals": n,
        "positive_rate": 0.0,
        "negative_rate": 0.0,
        "neutral_rate": 0.0,
        "mean_positive": 0.0,
        "mean_negative": 0.0,
        "mean_neutral": 0.0,
    }
    if n:
        label_counts = Counter(signal.sentiment_label for signal in signals)
        report["positive_rate"] = label_counts.get("positive", 0) / n
        report["negative_rate"] = label_counts.get("negative", 0) / n
        report["neutral_rate"] = label_counts.get("neutral", 0) / n
        report["mean_positive"] = sum(signal.sentiment_positive for signal in signals) / n
        report["mean_negative"] = sum(signal.sentiment_negative for signal in signals) / n
        report["mean_neutral"] = sum(signal.sentiment_neutral for signal in signals) / n
    if started_at is not None and completed_at is not None:
        elapsed = _require_ordered(started_at, completed_at)
        report["elapsed_seconds"] = elapsed
        report["throughput_signals_per_second"] = n / elapsed if elapsed > 0 else 0.0
    return report


def generate_evaluation_report(
    *,
    ingestion: Mapping[str, Any] | None = None,
    sentiment: Mapping[str, Any] | None = None,
) -> str:
    """Human-readable summary of `evaluate_ingestion`/`evaluate_sentiment`'s
    output. Deliberately plain text, matching `backtest.reporting.
    generate_report` and `memory.evaluation.generate_evaluation_report`'s
    minimalism -- this is a comparison/monitoring report, not a
    production artifact."""
    lines = ["NLP Pipeline Evaluation Report", "=" * 31]
    if ingestion is not None:
        lines += [
            "-- Ingestion --",
            f"Items: {ingestion['n_items']} "
            f"({ingestion['n_stored']} stored, {ingestion['n_duplicates']} duplicates)",
            f"Deduplication rate: {ingestion['deduplication_rate']:.1%}",
            f"Throughput: {ingestion['throughput_items_per_second']:.1f} items/sec",
        ]
    if sentiment is not None:
        lines += [
            "-- Sentiment --",
            f"Signals: {sentiment['n_signals']}",
            f"Distribution: positive {sentiment['positive_rate']:.1%}, "
            f"negative {sentiment['negative_rate']:.1%}, "
            f"neutral {sentiment['neutral_rate']:.1%}",
        ]
        if "throughput_signals_per_second" in sentiment:
            lines.append(
                f"Throughput: {sentiment['throughput_signals_per_second']:.1f} signals/sec"
            )
    return "\n".join(lines)


__all__ = ["evaluate_ingestion", "evaluate_sentiment", "generate_evaluation_report"]
