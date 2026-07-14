"""Tests for `nlp.service.NlpService` -- Phase B's batch signal-assembly
orchestration, using `DeterministicSentimentScorer` so these tests never
touch a real model."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from nlp.exceptions import NlpError
from nlp.models import NewsItem, SentimentResult
from nlp.sentiment import DeterministicSentimentScorer
from nlp.service import NlpService

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _item(**overrides: object) -> NewsItem:
    defaults: dict[str, object] = {
        "source_id": "12345",
        "source": "alpaca_news",
        "headline": "Fed holds rates steady",
        "summary": "",
        "symbols": ("AAPL",),
        "published_at": T0,
    }
    defaults.update(overrides)
    return NewsItem(**defaults)  # type: ignore[arg-type]


class TestNlpServiceBuildSignals:
    def test_empty_items_returns_empty_list(self) -> None:
        service = NlpService(scorer=DeterministicSentimentScorer())
        assert service.build_signals([], processed_at=T0) == []

    def test_produces_one_signal_per_item(self) -> None:
        service = NlpService(scorer=DeterministicSentimentScorer())
        items = [_item(source_id="1"), _item(source_id="2")]
        signals = service.build_signals(items, processed_at=T0 + timedelta(seconds=1))
        assert len(signals) == 2

    def test_signal_carries_over_item_fields(self) -> None:
        service = NlpService(scorer=DeterministicSentimentScorer())
        item = _item(source_id="42", source="alpaca_news", symbols=("AAPL", "MSFT"))
        [signal] = service.build_signals([item], processed_at=T0 + timedelta(seconds=1))
        assert signal.source_id == "42"
        assert signal.source == "alpaca_news"
        assert signal.symbols == ("AAPL", "MSFT")
        assert signal.headline == item.headline
        assert signal.published_at == item.published_at

    def test_entities_are_always_empty_in_this_milestone(self) -> None:
        service = NlpService(scorer=DeterministicSentimentScorer())
        [signal] = service.build_signals([_item()], processed_at=T0 + timedelta(seconds=1))
        assert signal.entities == ()

    def test_signal_id_derived_from_source_and_source_id(self) -> None:
        service = NlpService(scorer=DeterministicSentimentScorer())
        item = _item(source="alpaca_news", source_id="999")
        [signal] = service.build_signals([item], processed_at=T0 + timedelta(seconds=1))
        assert signal.signal_id == "alpaca_news:999"

    def test_sentiment_fields_come_from_scorer(self) -> None:
        bullish = SentimentResult(positive=0.9, negative=0.05, neutral=0.05, label="positive")
        scorer = DeterministicSentimentScorer(overrides={"Stocks rally": bullish})
        service = NlpService(scorer=scorer)
        item = _item(headline="Stocks rally")
        [signal] = service.build_signals([item], processed_at=T0 + timedelta(seconds=1))
        assert signal.sentiment_positive == 0.9
        assert signal.sentiment_label == "positive"

    def test_model_version_comes_from_scorer(self) -> None:
        scorer = DeterministicSentimentScorer(model_version="custom-v3")
        service = NlpService(scorer=scorer)
        [signal] = service.build_signals([_item()], processed_at=T0 + timedelta(seconds=1))
        assert signal.model_version == "custom-v3"

    def test_scores_all_headlines_in_a_single_batch_call(self) -> None:
        calls: list[list[str]] = []

        class RecordingScorer:
            model_version = "recording-v1"

            def score_batch(self, headlines):  # type: ignore[no-untyped-def]
                calls.append(list(headlines))
                return [
                    SentimentResult(positive=0.0, negative=0.0, neutral=1.0, label="neutral")
                    for _ in headlines
                ]

        service = NlpService(scorer=RecordingScorer())
        items = [_item(source_id=str(i), headline=f"Headline {i}") for i in range(5)]
        service.build_signals(items, processed_at=T0 + timedelta(seconds=1))
        assert len(calls) == 1
        assert len(calls[0]) == 5

    def test_raises_if_scorer_returns_mismatched_count(self) -> None:
        class BrokenScorer:
            model_version = "broken-v1"

            def score_batch(self, headlines):  # type: ignore[no-untyped-def]
                return []

        service = NlpService(scorer=BrokenScorer())
        with pytest.raises(NlpError, match="scorer returned"):
            service.build_signals([_item()], processed_at=T0 + timedelta(seconds=1))

    def test_propagates_processed_at_before_published_at_as_signal_error(self) -> None:
        service = NlpService(scorer=DeterministicSentimentScorer())
        item = _item(published_at=T0)
        with pytest.raises(ValueError, match="processed_at must be >= published_at"):
            service.build_signals([item], processed_at=T0 - timedelta(seconds=1))
