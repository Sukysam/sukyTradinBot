"""Shared factories for `tests/orchestration/policies/` -- one
`StrategyDecision`/`LearningDecision`/`NewsSignal` triple, reused across
every policy's test file so their agreement/disagreement scenarios are
directly comparable."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from memory.models import LearningDecision
from nlp.models import NewsSignal
from strategy.models import StrategyDecision

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def strategy_decision(**overrides: object) -> StrategyDecision:
    defaults: dict[str, object] = {
        "timestamp": T0,
        "symbol": "TEST",
        "strategy_id": "growth_v1",
        "regime_id": 0,
        "allocation": 0.7,
        "confidence": 0.8,
        "expected_holding_period": timedelta(days=5),
        "reasoning": "regime favors growth",
        "metadata": {},
    }
    defaults.update(overrides)
    return StrategyDecision(**defaults)  # type: ignore[arg-type]


def learning_decision(**overrides: object) -> LearningDecision:
    defaults: dict[str, object] = {
        "timestamp": T0,
        "symbol": "TEST",
        "strategy_id": "growth_v1",
        "regime_id": 0,
        "production_allocation": 0.7,
        "recommended_allocation": 0.7,
        "confidence": 0.6,
        "sample_size": 20,
        "rationale": "posterior mean 0.9 across 20 samples",
        "model_version": "thompson-bandit-v1",
        "metadata": {},
    }
    defaults.update(overrides)
    return LearningDecision(**defaults)  # type: ignore[arg-type]


def news_signal(**overrides: object) -> NewsSignal:
    defaults: dict[str, object] = {
        "signal_id": "alpaca_news:1",
        "source_id": "1",
        "source": "alpaca_news",
        "symbols": ("TEST",),
        "entities": (),
        "headline": "Company reports strong earnings",
        "published_at": T0,
        "processed_at": T0 + timedelta(seconds=5),
        "sentiment_positive": 0.8,
        "sentiment_negative": 0.1,
        "sentiment_neutral": 0.1,
        "sentiment_label": "positive",
        "model_version": "finbert-v1",
        "metadata": {},
    }
    defaults.update(overrides)
    return NewsSignal(**defaults)  # type: ignore[arg-type]
