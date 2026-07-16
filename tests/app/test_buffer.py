"""Tests for `app.buffer.BarBuffer`/`FeatureVectorBuffer`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.buffer import BarBuffer, FeatureVectorBuffer
from features.feature_vector import FeatureVector, Provenance
from market_data.models import Bar, Timeframe

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _bar(symbol: str, ts: datetime) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=ts,
        timeframe=Timeframe.DAY_1,
        open=99.0,
        high=101.0,
        low=98.0,
        close=100.0,
        volume=1000.0,
    )


def _feature_vector(symbol: str, ts: datetime) -> FeatureVector:
    return FeatureVector(
        timestamp=ts,
        symbol=symbol,
        feature_values=(1.0,),
        feature_names=("f1",),
        metadata={},
        quality_flags={},
        provenance=Provenance(
            pipeline_version="2",
            manifest_version="1",
            feature_versions={"f1": 1},
            generated_at=ts,
            source_dataset="test",
        ),
    )


class TestBarBuffer:
    def test_rejects_non_positive_max_bars(self) -> None:
        with pytest.raises(ValueError, match="max_bars"):
            BarBuffer(max_bars=0)

    def test_get_on_unknown_symbol_returns_empty(self) -> None:
        buffer = BarBuffer(max_bars=10)
        assert buffer.get("AAPL") == []

    def test_add_then_get_returns_the_bar(self) -> None:
        buffer = BarBuffer(max_bars=10)
        bar = _bar("AAPL", T0)
        buffer.add(bar)
        assert buffer.get("AAPL") == [bar]

    def test_get_returns_oldest_first(self) -> None:
        buffer = BarBuffer(max_bars=10)
        first = _bar("AAPL", T0)
        second = _bar("AAPL", T0.replace(day=2))
        buffer.add(first)
        buffer.add(second)
        assert buffer.get("AAPL") == [first, second]

    def test_evicts_oldest_bar_once_max_bars_exceeded(self) -> None:
        buffer = BarBuffer(max_bars=2)
        bars = [_bar("AAPL", T0.replace(day=day)) for day in (1, 2, 3)]
        for bar in bars:
            buffer.add(bar)
        assert buffer.get("AAPL") == bars[1:]

    def test_symbols_are_independent(self) -> None:
        buffer = BarBuffer(max_bars=10)
        aapl = _bar("AAPL", T0)
        msft = _bar("MSFT", T0)
        buffer.add(aapl)
        buffer.add(msft)
        assert buffer.get("AAPL") == [aapl]
        assert buffer.get("MSFT") == [msft]

    def test_len_counts_bars_across_all_symbols(self) -> None:
        buffer = BarBuffer(max_bars=10)
        buffer.add(_bar("AAPL", T0))
        buffer.add(_bar("MSFT", T0))
        buffer.add(_bar("AAPL", T0.replace(day=2)))
        assert len(buffer) == 3

    def test_len_reflects_eviction(self) -> None:
        buffer = BarBuffer(max_bars=1)
        buffer.add(_bar("AAPL", T0))
        buffer.add(_bar("AAPL", T0.replace(day=2)))
        assert len(buffer) == 1


class TestFeatureVectorBuffer:
    def test_rejects_non_positive_max_vectors(self) -> None:
        with pytest.raises(ValueError, match="max_vectors"):
            FeatureVectorBuffer(max_vectors=0)

    def test_get_on_unknown_symbol_returns_empty(self) -> None:
        buffer = FeatureVectorBuffer(max_vectors=10)
        assert buffer.get("AAPL") == []

    def test_add_then_get_returns_the_vector(self) -> None:
        buffer = FeatureVectorBuffer(max_vectors=10)
        vector = _feature_vector("AAPL", T0)
        buffer.add(vector)
        assert buffer.get("AAPL") == [vector]

    def test_get_returns_oldest_first(self) -> None:
        buffer = FeatureVectorBuffer(max_vectors=10)
        first = _feature_vector("AAPL", T0)
        second = _feature_vector("AAPL", T0.replace(day=2))
        buffer.add(first)
        buffer.add(second)
        assert buffer.get("AAPL") == [first, second]

    def test_evicts_oldest_vector_once_max_vectors_exceeded(self) -> None:
        buffer = FeatureVectorBuffer(max_vectors=2)
        vectors = [_feature_vector("AAPL", T0.replace(day=day)) for day in (1, 2, 3)]
        for vector in vectors:
            buffer.add(vector)
        assert buffer.get("AAPL") == vectors[1:]

    def test_symbols_are_independent(self) -> None:
        buffer = FeatureVectorBuffer(max_vectors=10)
        aapl = _feature_vector("AAPL", T0)
        msft = _feature_vector("MSFT", T0)
        buffer.add(aapl)
        buffer.add(msft)
        assert buffer.get("AAPL") == [aapl]
        assert buffer.get("MSFT") == [msft]

    def test_len_counts_vectors_across_all_symbols(self) -> None:
        buffer = FeatureVectorBuffer(max_vectors=10)
        buffer.add(_feature_vector("AAPL", T0))
        buffer.add(_feature_vector("MSFT", T0))
        buffer.add(_feature_vector("AAPL", T0.replace(day=2)))
        assert len(buffer) == 3

    def test_len_reflects_eviction(self) -> None:
        buffer = FeatureVectorBuffer(max_vectors=1)
        buffer.add(_feature_vector("AAPL", T0))
        buffer.add(_feature_vector("AAPL", T0.replace(day=2)))
        assert len(buffer) == 1
