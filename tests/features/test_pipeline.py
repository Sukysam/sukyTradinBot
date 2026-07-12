from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from features.errors import InsufficientHistoryError
from features.pipeline import FeaturePipeline
from market_data.models import Bar, CorporateAction, CorporateActionType, Timeframe
from tests.features.conftest import make_bars

UTC = timezone.utc


class TestCompute:
    def test_returns_latest_vector(self, daily_bars: list[Bar]) -> None:
        pipeline = FeaturePipeline()
        vec = pipeline.compute(daily_bars, "TEST")
        assert vec.timestamp == daily_bars[-1].timestamp
        assert vec.symbol == "TEST"

    def test_full_history_has_no_flagged_features(self, daily_bars: list[Bar]) -> None:
        pipeline = FeaturePipeline()
        vec = pipeline.compute(daily_bars, "TEST")
        assert vec.has_any_flag is False

    def test_strict_mode_raises_when_any_feature_flagged(self) -> None:
        pipeline = FeaturePipeline()
        short_history = make_bars(5)  # far short of the longest lookback (100)
        with pytest.raises(InsufficientHistoryError):
            pipeline.compute(short_history, "TEST", strict=True)

    def test_non_strict_mode_returns_flagged_vector(self) -> None:
        pipeline = FeaturePipeline()
        short_history = make_bars(5)
        vec = pipeline.compute(short_history, "TEST")
        assert vec.has_any_flag is True

    def test_empty_bars_raises(self) -> None:
        pipeline = FeaturePipeline()
        with pytest.raises(InsufficientHistoryError, match="empty"):
            pipeline.compute([], "TEST")

    def test_feature_names_subset_restricts_output(self, daily_bars: list[Bar]) -> None:
        pipeline = FeaturePipeline()
        vec = pipeline.compute(daily_bars, "TEST", feature_names=["atr_14", "rsi_14"])
        assert set(vec.feature_names) == {"atr_14", "rsi_14"}

    def test_metadata_records_source_and_bar_count(self, daily_bars: list[Bar]) -> None:
        pipeline = FeaturePipeline()
        vec = pipeline.compute(daily_bars, "TEST", source="historical")
        assert vec.metadata["source"] == "historical"
        assert vec.metadata["n_bars_used"] == len(daily_bars)


class TestComputeSeries:
    def test_one_vector_per_bar(self, daily_bars: list[Bar]) -> None:
        pipeline = FeaturePipeline()
        vectors, _ = pipeline.compute_series(daily_bars, "TEST")
        assert len(vectors) == len(daily_bars)

    def test_ascending_timestamp_order(self, daily_bars: list[Bar]) -> None:
        pipeline = FeaturePipeline()
        vectors, _ = pipeline.compute_series(daily_bars, "TEST")
        timestamps = [v.timestamp for v in vectors]
        assert timestamps == sorted(timestamps)

    def test_early_rows_flagged_late_rows_clean(self, daily_bars: list[Bar]) -> None:
        pipeline = FeaturePipeline()
        vectors, _ = pipeline.compute_series(daily_bars, "TEST")
        assert vectors[0].has_any_flag is True
        assert vectors[-1].has_any_flag is False

    def test_out_of_order_input_is_sorted(self) -> None:
        bars = make_bars(30)
        shuffled = [bars[10], bars[0], bars[20], *bars[1:10], *bars[11:20], *bars[21:]]
        pipeline = FeaturePipeline()
        vectors, _ = pipeline.compute_series(shuffled, "TEST")
        timestamps = [v.timestamp for v in vectors]
        assert timestamps == sorted(timestamps)


class TestDiagnostics:
    def test_no_duplicates_reports_zero(self, daily_bars: list[Bar]) -> None:
        pipeline = FeaturePipeline()
        _, diagnostics = pipeline.compute_series(daily_bars, "TEST")
        assert diagnostics.duplicate_bar_count == 0

    def test_duplicate_timestamps_are_deduplicated_and_reported(self) -> None:
        bars = make_bars(30)
        with_duplicate = [*bars, bars[-1]]  # same timestamp as the last bar, appended
        pipeline = FeaturePipeline()
        vectors, diagnostics = pipeline.compute_series(with_duplicate, "TEST")
        assert diagnostics.duplicate_bar_count == 1
        assert len(vectors) == len(bars)  # deduplicated before feature computation

    def test_missing_bars_reported_not_fatal(self) -> None:
        bars = make_bars(30)
        with_gap = bars[:10] + bars[15:]  # calendar bars 10-14 missing
        pipeline = FeaturePipeline()
        vectors, diagnostics = pipeline.compute_series(with_gap, "TEST")
        # 5 calendar days removed (2024-01-11..15), but market_data's
        # validate_bars is business-day-aware for DAY_1 -- Jan 13/14 2024
        # are Sat/Sun and aren't expected bars, so only 3 count as missing.
        assert diagnostics.missing_bar_count == 3
        assert len(vectors) == len(with_gap)  # still computes, doesn't refuse


class TestCorporateActionAdjustment:
    def test_split_adjustment_removes_the_artificial_price_jump(self) -> None:
        """Realistic raw data for a 2-for-1 split: the exchange-reported
        price level is ~400 before the ex_date and ~200 after (the actual
        post-split trading price) -- an un-adjusted `log_return_1` would
        show a huge, spurious -50% return right at the split. After
        adjustment, that jump must disappear.
        """
        start = datetime(2024, 1, 1, tzinfo=UTC)
        pre_split_price = 400.0
        post_split_price = 200.0
        bars = [
            Bar(
                symbol="TEST",
                timestamp=start + timedelta(days=i),
                timeframe=Timeframe.DAY_1,
                open=pre_split_price,
                high=pre_split_price + 1,
                low=pre_split_price - 1,
                close=pre_split_price,
                volume=1000.0,
            )
            for i in range(3)
        ] + [
            Bar(
                symbol="TEST",
                timestamp=start + timedelta(days=i),
                timeframe=Timeframe.DAY_1,
                open=post_split_price,
                high=post_split_price + 1,
                low=post_split_price - 1,
                close=post_split_price,
                volume=1000.0,
            )
            for i in range(3, 6)
        ]
        split = CorporateAction(
            symbol="TEST",
            ex_date=start + timedelta(days=3),
            action_type=CorporateActionType.SPLIT,
            ratio=2.0,
        )
        pipeline = FeaturePipeline()

        unadjusted_vectors, _ = pipeline.compute_series(
            bars, "TEST", feature_names=["log_return_1"]
        )
        adjusted_vectors, _ = pipeline.compute_series(
            bars, "TEST", corporate_actions=[split], feature_names=["log_return_1"]
        )

        # Without adjustment: a huge spurious jump in log_return_1 at the split boundary.
        assert unadjusted_vectors[3].get("log_return_1") == pytest.approx(-0.6931, abs=1e-3)
        # With adjustment: the jump is gone -- both sides are ~200, so return ~0.
        assert adjusted_vectors[3].get("log_return_1") == pytest.approx(0.0, abs=1e-6)
