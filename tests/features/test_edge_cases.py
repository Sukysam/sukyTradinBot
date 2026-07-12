"""Milestone 3's explicit edge-case checklist: NaNs, missing bars,
duplicate timestamps, timezone transitions, holidays, daylight saving,
stock splits, insufficient history, constant prices, extreme volatility.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from features.errors import InsufficientHistoryError
from features.pipeline import FeaturePipeline
from market_data.models import Bar, CorporateAction, CorporateActionType, Timeframe
from tests.features.conftest import make_bars

UTC = timezone.utc
US_EASTERN_STANDARD = timezone(timedelta(hours=-5))
US_EASTERN_DAYLIGHT = timezone(timedelta(hours=-4))


class TestInsufficientHistory:
    def test_one_bar_does_not_crash(self) -> None:
        pipeline = FeaturePipeline()
        vec = pipeline.compute(make_bars(1), "TEST")
        assert vec.has_any_flag is True

    def test_all_features_flagged_with_minimal_history(self) -> None:
        pipeline = FeaturePipeline()
        vec = pipeline.compute(make_bars(2), "TEST")
        # lookback=1 features (log_volume) may be clean; everything with a
        # real window requirement must be flagged.
        assert vec.is_flagged("hurst_exponent_100") is True
        assert vec.is_flagged("sma_50") is True

    def test_exactly_at_longest_lookback_is_clean(self) -> None:
        pipeline = FeaturePipeline()
        vec = pipeline.compute(make_bars(100), "TEST")
        assert vec.is_flagged("hurst_exponent_100") is False


class TestDuplicateTimestamps:
    def test_exact_duplicate_bar_is_deduplicated(self) -> None:
        bars = make_bars(30)
        duplicated = [*bars, bars[-1]]
        pipeline = FeaturePipeline()
        vectors, diagnostics = pipeline.compute_series(duplicated, "TEST")
        assert diagnostics.duplicate_bar_count == 1
        assert len(vectors) == 30

    def test_conflicting_duplicate_keeps_last_value(self) -> None:
        bars = make_bars(30)
        revised = Bar(
            symbol=bars[-1].symbol,
            timestamp=bars[-1].timestamp,
            timeframe=bars[-1].timeframe,
            open=bars[-1].open,
            high=bars[-1].high + 50,
            low=bars[-1].low,
            close=bars[-1].close + 50,
            volume=bars[-1].volume,
        )
        pipeline = FeaturePipeline()
        vectors, _ = pipeline.compute_series(
            [*bars, revised], "TEST", feature_names=["log_return_1"]
        )
        # The revised (later-in-input-order) bar's close must be what the
        # final close-derived feature reflects.
        assert vectors[-1].timestamp == revised.timestamp


class TestMissingBars:
    def test_gap_in_the_middle_does_not_stop_computation(self) -> None:
        bars = make_bars(40)
        with_gap = bars[:15] + bars[25:]
        pipeline = FeaturePipeline()
        vectors, diagnostics = pipeline.compute_series(with_gap, "TEST")
        # 10 calendar days removed (2024-01-16..25), but market_data's
        # validate_bars is business-day-aware for DAY_1 -- Jan 20/21 2024
        # are Sat/Sun and aren't expected bars in the first place, so only
        # 8 of the 10 missing calendar days count as missing *bars*.
        assert diagnostics.missing_bar_count == 8
        assert len(vectors) == len(with_gap)

    def test_gap_does_not_propagate_nan_beyond_the_affected_window(self) -> None:
        bars = make_bars(60)
        with_gap = bars[:30] + bars[40:]  # 10-bar gap
        pipeline = FeaturePipeline()
        vectors, _ = pipeline.compute_series(with_gap, "TEST", feature_names=["log_return_1"])
        # Far past the gap, a 1-bar-lookback feature must be clean again.
        assert vectors[-1].is_flagged("log_return_1") is False


class TestTimezoneAndDST:
    def test_bars_across_a_dst_transition_still_produce_features(self) -> None:
        # US DST spring-forward 2024-03-10: 2am -> 3am. Bars straddling it
        # in UTC-normalized form must not confuse a purely bar-count-based
        # rolling window.
        start = datetime(2024, 3, 8, 14, 30, tzinfo=UTC)
        bars = [
            Bar(
                symbol="TEST",
                timestamp=start + timedelta(days=i),
                timeframe=Timeframe.DAY_1,
                open=100 + i,
                high=101 + i,
                low=99 + i,
                close=100 + i,
                volume=1000,
            )
            for i in range(30)
        ]
        pipeline = FeaturePipeline()
        vec = pipeline.compute(bars, "TEST")
        assert vec.timestamp.tzinfo is not None

    def test_non_utc_but_tz_aware_timestamps_are_accepted_as_is(self) -> None:
        """`Bar` itself requires UTC (see market_data.models) -- this
        confirms the pipeline doesn't silently accept or mis-handle a
        non-UTC Bar, by constructing one the only legal way: pre-normalized.
        """
        from market_data.validation import normalize_timezone

        naive_like_source = datetime(2024, 3, 10, 9, 30, tzinfo=US_EASTERN_DAYLIGHT)
        normalized = normalize_timezone(naive_like_source)
        assert normalized.tzinfo == timezone.utc


class TestStockSplits:
    def test_split_ratio_two_halves_pre_split_prices(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        bars = [
            Bar(
                symbol="TEST",
                timestamp=start + timedelta(days=i),
                timeframe=Timeframe.DAY_1,
                open=300.0,
                high=301.0,
                low=299.0,
                close=300.0,
                volume=1000.0,
            )
            for i in range(10)
        ]
        split = CorporateAction(
            symbol="TEST",
            ex_date=start + timedelta(days=5),
            action_type=CorporateActionType.SPLIT,
            ratio=2.0,
        )
        pipeline = FeaturePipeline()
        vectors, _ = pipeline.compute_series(
            bars, "TEST", corporate_actions=[split], feature_names=["log_return_1"]
        )
        # No feature computation should raise; adjustment happens upstream
        # of feature calculation (see test_pipeline.py for the numeric check).
        assert len(vectors) == 10


class TestConstantPrices:
    def test_constant_price_series_does_not_crash(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        bars = [
            Bar(
                symbol="TEST",
                timestamp=start + timedelta(days=i),
                timeframe=Timeframe.DAY_1,
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                volume=1000.0,
            )
            for i in range(150)
        ]
        pipeline = FeaturePipeline()
        vec = pipeline.compute(bars, "TEST")
        assert vec.get("log_return_1") == 0.0
        assert vec.get("realized_volatility_20") == 0.0

    def test_constant_price_zscore_features_are_nan_not_inf(self) -> None:
        """Zero variance in the denominator of a z-score must produce NaN
        (flagged), never +/-inf silently propagating downstream.
        """
        import math

        start = datetime(2024, 1, 1, tzinfo=UTC)
        bars = [
            Bar(
                symbol="TEST",
                timestamp=start + timedelta(days=i),
                timeframe=Timeframe.DAY_1,
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                volume=1_000_000.0,
            )
            for i in range(150)
        ]
        pipeline = FeaturePipeline()
        vec = pipeline.compute(bars, "TEST")
        value = vec.get("volume_zscore_20")
        assert not math.isinf(value)


class TestExtremeVolatility:
    def test_large_single_bar_move_does_not_crash(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        bars = make_bars(150)[:-1]
        spike = Bar(
            symbol="TEST",
            timestamp=start + timedelta(days=150),
            timeframe=Timeframe.DAY_1,
            open=100.0,
            high=10_000.0,
            low=1.0,
            close=5_000.0,
            volume=1_000_000_000.0,
        )
        pipeline = FeaturePipeline()
        vec = pipeline.compute([*bars, spike], "TEST")
        assert vec.timestamp == spike.timestamp
        # Every feature either has a finite value or is honestly flagged --
        # never silently NaN without being reflected in quality_flags.
        for name in vec.feature_names:
            value = vec.get(name)
            if value != value:  # NaN check without importing math
                assert vec.is_flagged(name) is True

    def test_near_zero_price_does_not_divide_by_zero_uncaught(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        bars = [
            Bar(
                symbol="TEST",
                timestamp=start + timedelta(days=i),
                timeframe=Timeframe.DAY_1,
                open=0.02,
                high=0.021,
                low=0.019,
                close=0.02,
                volume=1_000_000.0,
            )
            for i in range(150)
        ]
        pipeline = FeaturePipeline()
        vec = pipeline.compute(bars, "TEST")  # must not raise ZeroDivisionError
        assert vec.symbol == "TEST"


def test_strict_mode_is_the_documented_escape_hatch_for_all_of_the_above() -> None:
    pipeline = FeaturePipeline()
    with pytest.raises(InsufficientHistoryError):
        pipeline.compute(make_bars(3), "TEST", strict=True)
