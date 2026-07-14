"""Tests for `nlp.models`: `NewsItem`'s construction-time invariants,
`NewsSignal`'s construction-time invariants and serialization, and
`SentimentResult`'s shared sentiment-validation invariants."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from nlp.models import NewsItem, NewsSignal, SentimentResult

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _news_item(**overrides: object) -> NewsItem:
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


def _signal(**overrides: object) -> NewsSignal:
    defaults: dict[str, object] = {
        "signal_id": "sig-1",
        "source_id": "12345",
        "source": "alpaca_news",
        "symbols": ("AAPL",),
        "entities": ("Apple Inc.",),
        "headline": "Fed holds rates steady",
        "published_at": T0,
        "processed_at": T0 + timedelta(seconds=5),
        "sentiment_positive": 0.1,
        "sentiment_negative": 0.1,
        "sentiment_neutral": 0.8,
        "sentiment_label": "neutral",
        "model_version": "finbert-v1",
        "metadata": {},
    }
    defaults.update(overrides)
    return NewsSignal(**defaults)  # type: ignore[arg-type]


class TestNewsItem:
    def test_valid_item_constructs(self) -> None:
        item = _news_item()
        assert item.source_id == "12345"

    def test_rejects_naive_published_at(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _news_item(published_at=datetime(2024, 1, 1))

    def test_rejects_empty_source_id(self) -> None:
        with pytest.raises(ValueError, match="source_id"):
            _news_item(source_id="")

    def test_rejects_empty_source(self) -> None:
        with pytest.raises(ValueError, match="source"):
            _news_item(source="")

    def test_rejects_empty_headline(self) -> None:
        with pytest.raises(ValueError, match="headline"):
            _news_item(headline="")

    def test_allows_empty_summary(self) -> None:
        item = _news_item(summary="")
        assert item.summary == ""

    def test_rejects_blank_symbol_entry(self) -> None:
        with pytest.raises(ValueError, match="symbols"):
            _news_item(symbols=("AAPL", ""))

    def test_allows_empty_symbols(self) -> None:
        item = _news_item(symbols=())
        assert item.symbols == ()

    def test_round_trips_through_dict(self) -> None:
        item = _news_item(summary="Some detail.")
        assert NewsItem.from_dict(item.to_dict()) == item

    def test_is_frozen(self) -> None:
        item = _news_item()
        with pytest.raises(AttributeError):
            item.headline = "Other"  # type: ignore[misc]


class TestNewsSignal:
    def test_valid_signal_constructs(self) -> None:
        signal = _signal()
        assert signal.sentiment_label == "neutral"

    def test_rejects_naive_published_at(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _signal(published_at=datetime(2024, 1, 1))

    def test_rejects_naive_processed_at(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _signal(processed_at=datetime(2024, 1, 1))

    def test_rejects_empty_signal_id(self) -> None:
        with pytest.raises(ValueError, match="signal_id"):
            _signal(signal_id="")

    def test_rejects_empty_source_id(self) -> None:
        with pytest.raises(ValueError, match="source_id"):
            _signal(source_id="")

    def test_rejects_empty_source(self) -> None:
        with pytest.raises(ValueError, match="source"):
            _signal(source="")

    def test_rejects_empty_headline(self) -> None:
        with pytest.raises(ValueError, match="headline"):
            _signal(headline="")

    def test_rejects_blank_symbol_entry(self) -> None:
        with pytest.raises(ValueError, match="symbols"):
            _signal(symbols=("AAPL", ""))

    def test_rejects_blank_entity_entry(self) -> None:
        with pytest.raises(ValueError, match="entities"):
            _signal(entities=("Apple", ""))

    def test_allows_empty_symbols_and_entities(self) -> None:
        signal = _signal(symbols=(), entities=())
        assert signal.symbols == ()
        assert signal.entities == ()

    def test_rejects_processed_at_before_published_at(self) -> None:
        with pytest.raises(ValueError, match="processed_at must be >= published_at"):
            _signal(published_at=T0, processed_at=T0 - timedelta(seconds=1))

    def test_allows_processed_at_equal_to_published_at(self) -> None:
        signal = _signal(published_at=T0, processed_at=T0)
        assert signal.processed_at == signal.published_at

    @pytest.mark.parametrize(
        "field", ["sentiment_positive", "sentiment_negative", "sentiment_neutral"]
    )
    def test_rejects_sentiment_score_out_of_bounds(self, field: str) -> None:
        with pytest.raises(ValueError, match=field):
            _signal(**{field: 1.5})

    def test_rejects_sentiment_scores_not_summing_to_one(self) -> None:
        with pytest.raises(ValueError, match="must be in"):
            _signal(sentiment_positive=0.5, sentiment_negative=0.5, sentiment_neutral=0.5)

    def test_rejects_unknown_sentiment_label(self) -> None:
        with pytest.raises(ValueError, match="sentiment_label"):
            _signal(sentiment_label="mixed")

    def test_rejects_label_not_matching_argmax(self) -> None:
        with pytest.raises(ValueError, match="does not match the argmax"):
            _signal(
                sentiment_positive=0.1,
                sentiment_negative=0.1,
                sentiment_neutral=0.8,
                sentiment_label="positive",
            )

    def test_accepts_label_matching_argmax(self) -> None:
        signal = _signal(
            sentiment_positive=0.7,
            sentiment_negative=0.1,
            sentiment_neutral=0.2,
            sentiment_label="positive",
        )
        assert signal.sentiment_label == "positive"

    def test_rejects_empty_model_version(self) -> None:
        with pytest.raises(ValueError, match="model_version"):
            _signal(model_version="")

    def test_round_trips_through_dict(self) -> None:
        signal = _signal(metadata={"summary": "value"})
        assert NewsSignal.from_dict(signal.to_dict()) == signal

    def test_is_frozen(self) -> None:
        signal = _signal()
        with pytest.raises(AttributeError):
            signal.sentiment_label = "positive"  # type: ignore[misc]

    def test_backward_compatible_with_unknown_metadata_keys(self) -> None:
        signal = _signal(metadata={"unexpected_future_key": 123})
        assert NewsSignal.from_dict(signal.to_dict()) == signal


class TestSentimentResult:
    def test_valid_result_constructs(self) -> None:
        result = SentimentResult(positive=0.7, negative=0.1, neutral=0.2, label="positive")
        assert result.label == "positive"

    def test_rejects_score_out_of_bounds(self) -> None:
        with pytest.raises(ValueError, match="must be in"):
            SentimentResult(positive=1.5, negative=0.1, neutral=0.2, label="positive")

    def test_rejects_scores_not_summing_to_one(self) -> None:
        with pytest.raises(ValueError, match="must be in"):
            SentimentResult(positive=0.5, negative=0.5, neutral=0.5, label="neutral")

    def test_rejects_unknown_label(self) -> None:
        with pytest.raises(ValueError, match="sentiment_label"):
            SentimentResult(positive=0.7, negative=0.1, neutral=0.2, label="mixed")

    def test_rejects_label_not_matching_argmax(self) -> None:
        with pytest.raises(ValueError, match="does not match the argmax"):
            SentimentResult(positive=0.1, negative=0.1, neutral=0.8, label="positive")

    def test_is_frozen(self) -> None:
        result = SentimentResult(positive=0.7, negative=0.1, neutral=0.2, label="positive")
        with pytest.raises(AttributeError):
            result.label = "negative"  # type: ignore[misc]
