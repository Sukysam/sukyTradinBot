"""Regression tests for the `NewsSignal` contract itself (Standards/
NewsSignal Contract.md), distinct from `tests/nlp/`'s own unit tests --
these exist to catch an accidental breaking change to the contract's
*shape*, not to test ingestion/sentiment/evaluation logic. If a change
here forces an edit to this file, that's a signal the change needs a new
ADR per that Standards document's own versioning policy.
"""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone

from nlp.models import NewsSignal

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


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


class TestRequiredFields:
    def test_news_signal_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(NewsSignal)}
        assert field_names == {
            "signal_id",
            "source_id",
            "source",
            "symbols",
            "entities",
            "headline",
            "published_at",
            "processed_at",
            "sentiment_positive",
            "sentiment_negative",
            "sentiment_neutral",
            "sentiment_label",
            "model_version",
            "metadata",
        }


class TestSerializationRoundTrip:
    def test_signal_round_trips_through_dict(self) -> None:
        signal = _signal(metadata={"note": "value"})
        assert NewsSignal.from_dict(signal.to_dict()) == signal

    def test_signal_with_empty_symbols_and_entities_round_trips(self) -> None:
        signal = _signal(symbols=(), entities=())
        assert NewsSignal.from_dict(signal.to_dict()) == signal

    def test_to_dict_is_json_serializable(self) -> None:
        json.dumps(_signal().to_dict())


class TestBackwardCompatibility:
    def test_construction_tolerates_unknown_metadata_keys(self) -> None:
        _signal(metadata={"anything": "goes", "here": 123})
