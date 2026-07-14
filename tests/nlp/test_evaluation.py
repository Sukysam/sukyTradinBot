"""Tests for `nlp.evaluation` -- Phase C's read-only ingestion/sentiment
reporting. No production influence is exercised or possible here."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from nlp.evaluation import evaluate_ingestion, evaluate_sentiment, generate_evaluation_report
from nlp.models import NewsSignal

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _signal(**overrides: object) -> NewsSignal:
    defaults: dict[str, object] = {
        "signal_id": "sig-1",
        "source_id": "12345",
        "source": "alpaca_news",
        "symbols": ("AAPL",),
        "entities": (),
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


class TestEvaluateIngestion:
    def test_empty_input(self) -> None:
        report = evaluate_ingestion([], started_at=T0, completed_at=T0)
        assert report["n_items"] == 0
        assert report["deduplication_rate"] == 0.0

    def test_counts_stored_and_duplicates(self) -> None:
        report = evaluate_ingestion(
            [True, True, False, True, False], started_at=T0, completed_at=T0 + timedelta(seconds=1)
        )
        assert report["n_items"] == 5
        assert report["n_stored"] == 3
        assert report["n_duplicates"] == 2

    def test_deduplication_rate(self) -> None:
        report = evaluate_ingestion(
            [True, False, False, False], started_at=T0, completed_at=T0 + timedelta(seconds=1)
        )
        assert report["deduplication_rate"] == pytest.approx(0.75)

    def test_throughput(self) -> None:
        report = evaluate_ingestion(
            [True] * 10, started_at=T0, completed_at=T0 + timedelta(seconds=2)
        )
        assert report["throughput_items_per_second"] == pytest.approx(5.0)

    def test_zero_elapsed_time_gives_zero_throughput(self) -> None:
        report = evaluate_ingestion([True], started_at=T0, completed_at=T0)
        assert report["throughput_items_per_second"] == 0.0

    def test_rejects_completed_before_started(self) -> None:
        with pytest.raises(ValueError, match="completed_at must be >= started_at"):
            evaluate_ingestion([True], started_at=T0, completed_at=T0 - timedelta(seconds=1))

    def test_rejects_naive_started_at(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            evaluate_ingestion([True], started_at=datetime(2024, 1, 1), completed_at=T0)


class TestEvaluateSentiment:
    def test_empty_input(self) -> None:
        report = evaluate_sentiment([])
        assert report["n_signals"] == 0
        assert report["positive_rate"] == 0.0

    def test_label_distribution(self) -> None:
        signals = [
            _signal(
                sentiment_label="positive",
                sentiment_positive=0.8,
                sentiment_negative=0.1,
                sentiment_neutral=0.1,
            ),
            _signal(
                sentiment_label="negative",
                sentiment_positive=0.1,
                sentiment_negative=0.8,
                sentiment_neutral=0.1,
            ),
            _signal(
                sentiment_label="neutral",
                sentiment_positive=0.1,
                sentiment_negative=0.1,
                sentiment_neutral=0.8,
            ),
            _signal(
                sentiment_label="neutral",
                sentiment_positive=0.1,
                sentiment_negative=0.1,
                sentiment_neutral=0.8,
            ),
        ]
        report = evaluate_sentiment(signals)
        assert report["n_signals"] == 4
        assert report["positive_rate"] == pytest.approx(0.25)
        assert report["negative_rate"] == pytest.approx(0.25)
        assert report["neutral_rate"] == pytest.approx(0.5)

    def test_mean_scores(self) -> None:
        signals = [
            _signal(
                sentiment_positive=0.8,
                sentiment_negative=0.1,
                sentiment_neutral=0.1,
                sentiment_label="positive",
            ),
            _signal(
                sentiment_positive=0.2,
                sentiment_negative=0.1,
                sentiment_neutral=0.7,
                sentiment_label="neutral",
            ),
        ]
        report = evaluate_sentiment(signals)
        assert report["mean_positive"] == pytest.approx(0.5)

    def test_throughput_omitted_without_timestamps(self) -> None:
        report = evaluate_sentiment([_signal()])
        assert "throughput_signals_per_second" not in report

    def test_throughput_included_with_timestamps(self) -> None:
        report = evaluate_sentiment(
            [_signal(), _signal()], started_at=T0, completed_at=T0 + timedelta(seconds=1)
        )
        assert report["throughput_signals_per_second"] == pytest.approx(2.0)

    def test_rejects_completed_before_started(self) -> None:
        with pytest.raises(ValueError, match="completed_at must be >= started_at"):
            evaluate_sentiment([_signal()], started_at=T0, completed_at=T0 - timedelta(seconds=1))


class TestGenerateEvaluationReport:
    def test_report_with_both_sections(self) -> None:
        ingestion = evaluate_ingestion(
            [True, False], started_at=T0, completed_at=T0 + timedelta(seconds=1)
        )
        sentiment = evaluate_sentiment([_signal()])
        report = generate_evaluation_report(ingestion=ingestion, sentiment=sentiment)
        assert "NLP Pipeline Evaluation Report" in report
        assert "Ingestion" in report
        assert "Sentiment" in report

    def test_report_includes_sentiment_throughput_when_present(self) -> None:
        sentiment = evaluate_sentiment(
            [_signal()], started_at=T0, completed_at=T0 + timedelta(seconds=1)
        )
        report = generate_evaluation_report(sentiment=sentiment)
        assert "Throughput" in report

    def test_report_with_ingestion_only(self) -> None:
        ingestion = evaluate_ingestion(
            [True], started_at=T0, completed_at=T0 + timedelta(seconds=1)
        )
        report = generate_evaluation_report(ingestion=ingestion)
        assert "Ingestion" in report
        assert "Sentiment" not in report

    def test_report_with_neither_section(self) -> None:
        report = generate_evaluation_report()
        assert "NLP Pipeline Evaluation Report" in report
