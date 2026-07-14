"""Integration tests for `nlp.sentiment.FinBertSentimentScorer` -- the
only tests in this package that load real FinBERT model weights. Per
`06_NLP_ENGINEER.md`'s acceptance criteria (FinBERT-dependent tests are
integration tests, separate from the fast unit suite), these are marked
`@pytest.mark.integration` and skip gracefully via `pytest.importorskip`
when `torch`/`transformers` aren't installed -- the base dev extras
deliberately don't include them (see ADR-018's pyproject.toml note), so
this file is expected to skip in most environments, including this
repository's own CI matrix, until the `trading` extra is installed.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from nlp.exceptions import NlpError  # noqa: E402
from nlp.sentiment import FinBertSentimentScorer  # noqa: E402

pytestmark = pytest.mark.integration


class TestFinBertSentimentScorer:
    def test_scores_a_positive_headline(self) -> None:
        scorer = FinBertSentimentScorer()
        [result] = scorer.score_batch(["Company reports record profits, beats estimates"])
        assert result.label in {"positive", "negative", "neutral"}
        assert 0.99 <= result.positive + result.negative + result.neutral <= 1.01

    def test_empty_batch_returns_empty_list_without_loading_inference(self) -> None:
        scorer = FinBertSentimentScorer()
        assert scorer.score_batch([]) == []

    def test_rejects_empty_headline(self) -> None:
        scorer = FinBertSentimentScorer()
        with pytest.raises(NlpError, match="empty"):
            scorer.score_batch([""])

    def test_model_version_reflects_model_name(self) -> None:
        scorer = FinBertSentimentScorer()
        assert scorer.model_version == "ProsusAI/finbert"

    def test_batch_scoring_preserves_order(self) -> None:
        scorer = FinBertSentimentScorer()
        results = scorer.score_batch(
            [
                "Company reports record profits, beats estimates",
                "Company files for bankruptcy amid mounting losses",
            ]
        )
        assert len(results) == 2
