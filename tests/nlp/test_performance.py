"""Milestone 10's performance targets, measured -- not assumed.

| Metric                                            | Target  |
|-----------------------------------------------------|---------|
| Ingest (`InMemoryNewsItemStore.add`, new item)       | < 0.1ms |
| Dedup check (`InMemoryNewsItemStore.add`, duplicate) | < 0.1ms |
| Batch sentiment scoring (`DeterministicSentimentScorer.score_batch`, per headline) | < 0.1ms |

All three are pure in-memory, no I/O -- comparable in spirit to
`tests/memory/test_performance.py`'s insert/update/recommend measurements.
`FinBertSentimentScorer`'s real inference latency is deliberately not
benchmarked here -- it requires `torch`/`transformers` (not installed by
the base dev extras) and its cost is dominated by model inference, not
this package's own logic, the same reasoning that kept
`JsonlExperienceStore.append`'s file I/O out of Milestone 9's benchmark.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from nlp.models import NewsItem
from nlp.sentiment import DeterministicSentimentScorer
from nlp.store import InMemoryNewsItemStore

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)
ASSERT_SECONDS = 0.0005  # generous margin for shared/CI hardware variance


def _item(index: int) -> NewsItem:
    return NewsItem(
        source_id=str(index),
        source="alpaca_news",
        headline=f"Headline number {index}",
        summary="",
        symbols=("AAPL",),
        published_at=T0,
    )


@pytest.mark.performance
def test_ingest_latency_meets_target() -> None:
    store = InMemoryNewsItemStore()
    n_trials = 10_000
    items = [_item(i) for i in range(n_trials)]

    start = time.perf_counter()
    for item in items:
        store.add(item)
    elapsed_per_call = (time.perf_counter() - start) / n_trials

    print(f"\nIngest, per-call: {elapsed_per_call * 1000:.4f}ms")
    assert elapsed_per_call < ASSERT_SECONDS


@pytest.mark.performance
def test_dedup_check_latency_meets_target() -> None:
    store = InMemoryNewsItemStore()
    item = _item(0)
    store.add(item)

    n_trials = 10_000
    start = time.perf_counter()
    for _ in range(n_trials):
        store.add(item)
    elapsed_per_call = (time.perf_counter() - start) / n_trials

    print(f"\nDedup check, per-call: {elapsed_per_call * 1000:.4f}ms")
    assert elapsed_per_call < ASSERT_SECONDS


@pytest.mark.performance
def test_batch_sentiment_scoring_latency_meets_target() -> None:
    scorer = DeterministicSentimentScorer()
    n_trials = 10_000
    headlines = [f"Headline number {i}" for i in range(n_trials)]

    start = time.perf_counter()
    scorer.score_batch(headlines)
    elapsed_per_call = (time.perf_counter() - start) / n_trials

    print(f"\nBatch sentiment scoring, per-headline: {elapsed_per_call * 1000:.4f}ms")
    assert elapsed_per_call < ASSERT_SECONDS
