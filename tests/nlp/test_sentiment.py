"""Tests for `nlp.sentiment.DeterministicSentimentScorer` -- the
dependency-free `SentimentScorer` used for fast unit tests and as an
explicit fallback. `FinBertSentimentScorer` is exercised separately in
`tests/nlp/test_sentiment_integration.py`, gated on `torch`/`transformers`
actually being installed."""

from __future__ import annotations

from nlp.models import SentimentResult
from nlp.sentiment import DeterministicSentimentScorer


class TestDeterministicSentimentScorer:
    def test_empty_input_returns_empty_list(self) -> None:
        scorer = DeterministicSentimentScorer()
        assert scorer.score_batch([]) == []

    def test_unmapped_headline_returns_default(self) -> None:
        scorer = DeterministicSentimentScorer()
        results = scorer.score_batch(["Some headline"])
        assert results == [scorer.default]

    def test_default_is_neutral_unless_overridden(self) -> None:
        scorer = DeterministicSentimentScorer()
        assert scorer.default.label == "neutral"

    def test_overrides_take_precedence_over_default(self) -> None:
        bullish = SentimentResult(positive=0.9, negative=0.05, neutral=0.05, label="positive")
        scorer = DeterministicSentimentScorer(overrides={"Stocks rally": bullish})
        results = scorer.score_batch(["Stocks rally"])
        assert results == [bullish]

    def test_mixed_batch_uses_override_and_default_per_headline(self) -> None:
        bullish = SentimentResult(positive=0.9, negative=0.05, neutral=0.05, label="positive")
        scorer = DeterministicSentimentScorer(overrides={"Stocks rally": bullish})
        results = scorer.score_batch(["Stocks rally", "Unrelated headline"])
        assert results == [bullish, scorer.default]

    def test_preserves_input_order(self) -> None:
        a = SentimentResult(positive=0.8, negative=0.1, neutral=0.1, label="positive")
        b = SentimentResult(positive=0.1, negative=0.8, neutral=0.1, label="negative")
        scorer = DeterministicSentimentScorer(overrides={"A": a, "B": b})
        assert scorer.score_batch(["B", "A"]) == [b, a]

    def test_model_version_is_a_stable_string(self) -> None:
        scorer = DeterministicSentimentScorer()
        assert isinstance(scorer.model_version, str)
        assert scorer.model_version
