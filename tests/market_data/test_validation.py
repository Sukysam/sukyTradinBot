from __future__ import annotations

from datetime import datetime, timedelta, timezone

from market_data.models import Bar, CorporateAction, CorporateActionType, Timeframe
from market_data.validation import (
    apply_split_adjustment,
    deduplicate_bars,
    find_duplicate_timestamps,
    find_missing_bars,
    normalize_timezone,
    validate_bars,
)

UTC = timezone.utc


def _bar(symbol: str, ts: datetime, close: float = 100.0) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=ts,
        timeframe=Timeframe.MIN_1,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
    )


class TestNormalizeTimezone:
    def test_naive_timestamp_assumed_utc_by_default(self) -> None:
        naive = datetime(2026, 6, 1, 9, 30, 0)
        result = normalize_timezone(naive)
        assert result.tzinfo is not None
        assert result == datetime(2026, 6, 1, 9, 30, 0, tzinfo=UTC)

    def test_naive_timestamp_with_explicit_source_tz(self) -> None:
        ny = timezone(timedelta(hours=-4))
        naive = datetime(2026, 6, 1, 9, 30, 0)
        result = normalize_timezone(naive, assume_tz=ny)
        assert result == datetime(2026, 6, 1, 13, 30, 0, tzinfo=UTC)

    def test_aware_non_utc_converted_to_utc(self) -> None:
        ny = timezone(timedelta(hours=-4))
        aware = datetime(2026, 6, 1, 9, 30, 0, tzinfo=ny)
        result = normalize_timezone(aware)
        assert result == datetime(2026, 6, 1, 13, 30, 0, tzinfo=UTC)
        assert result.utcoffset() == timedelta(0)

    def test_already_utc_is_unchanged(self) -> None:
        aware = datetime(2026, 6, 1, 9, 30, 0, tzinfo=UTC)
        assert normalize_timezone(aware) == aware


class TestDeduplication:
    def test_no_duplicates_returns_all(self) -> None:
        ts0 = datetime(2026, 6, 1, tzinfo=UTC)
        bars = [_bar("AAPL", ts0), _bar("AAPL", ts0 + timedelta(minutes=1))]
        assert find_duplicate_timestamps(bars) == []

    def test_finds_duplicate_after_first_occurrence(self) -> None:
        ts0 = datetime(2026, 6, 1, tzinfo=UTC)
        first = _bar("AAPL", ts0, close=100.0)
        duplicate = _bar("AAPL", ts0, close=101.0)
        result = find_duplicate_timestamps([first, duplicate])
        assert result == [duplicate]

    def test_deduplicate_bars_keeps_last_and_sorts(self) -> None:
        ts0 = datetime(2026, 6, 1, tzinfo=UTC)
        first = _bar("AAPL", ts0, close=100.0)
        revision = _bar("AAPL", ts0, close=105.0)
        later = _bar("AAPL", ts0 + timedelta(minutes=1), close=110.0)

        result = deduplicate_bars([later, first, revision])

        assert len(result) == 2
        assert result[0].timestamp == ts0
        assert result[0].close == 105.0  # revision wins
        assert result[1] == later


class TestMissingBars:
    def test_no_gaps_returns_empty(self) -> None:
        start = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        bars = [_bar("AAPL", start + timedelta(minutes=i)) for i in range(5)]
        end = start + timedelta(minutes=5)
        assert find_missing_bars(bars, Timeframe.MIN_1, start, end) == []

    def test_detects_single_gap(self) -> None:
        start = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        bars = [_bar("AAPL", start), _bar("AAPL", start + timedelta(minutes=2))]
        end = start + timedelta(minutes=3)

        missing = find_missing_bars(bars, Timeframe.MIN_1, start, end)

        assert missing == [start + timedelta(minutes=1)]

    def test_empty_bars_reports_every_expected_timestamp(self) -> None:
        start = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        end = start + timedelta(minutes=3)
        assert len(find_missing_bars([], Timeframe.MIN_1, start, end)) == 3

    def test_daily_timeframe_skips_weekends(self) -> None:
        # 2026-06-01 is a Monday; window covers Mon-Fri (5 weekdays) + the
        # following Sat/Sun, which must not be reported as missing.
        start = datetime(2026, 6, 1, tzinfo=UTC)
        end = start + timedelta(days=7)
        missing = find_missing_bars([], Timeframe.DAY_1, start, end)
        assert len(missing) == 5
        assert all(ts.weekday() < 5 for ts in missing)


class TestValidateBars:
    def test_clean_report(self) -> None:
        start = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        bars = [_bar("AAPL", start + timedelta(minutes=i)) for i in range(3)]
        end = start + timedelta(minutes=3)

        report = validate_bars(bars, "AAPL", Timeframe.MIN_1, start, end)

        assert report.is_clean is True
        assert report.missing_bar_timestamps == ()
        assert report.duplicate_bars == ()

    def test_dirty_report(self) -> None:
        start = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        bars = [_bar("AAPL", start), _bar("AAPL", start)]  # duplicate, and gap after
        end = start + timedelta(minutes=3)

        report = validate_bars(bars, "AAPL", Timeframe.MIN_1, start, end)

        assert report.is_clean is False
        assert len(report.duplicate_bars) == 1
        assert len(report.missing_bar_timestamps) == 2


class TestSplitAdjustment:
    def test_bars_before_ex_date_are_adjusted(self) -> None:
        ex_date = datetime(2026, 6, 15, tzinfo=UTC)
        before = _bar("AAPL", ex_date - timedelta(days=1), close=200.0)
        split = CorporateAction(
            symbol="AAPL", ex_date=ex_date, action_type=CorporateActionType.SPLIT, ratio=2.0
        )

        adjusted = apply_split_adjustment([before], [split])

        assert adjusted[0].close == 100.0
        assert adjusted[0].open == 100.0
        assert adjusted[0].volume == 2000.0

    def test_bars_on_or_after_ex_date_are_unchanged(self) -> None:
        ex_date = datetime(2026, 6, 15, tzinfo=UTC)
        on_date = _bar("AAPL", ex_date, close=100.0)

        adjusted = apply_split_adjustment(
            [on_date],
            [
                CorporateAction(
                    symbol="AAPL", ex_date=ex_date, action_type=CorporateActionType.SPLIT, ratio=2.0
                )
            ],
        )

        assert adjusted[0].close == 100.0

    def test_no_splits_returns_bars_unchanged(self, sample_bars: list[Bar]) -> None:
        assert apply_split_adjustment(sample_bars, []) == sample_bars

    def test_non_split_actions_are_ignored(self) -> None:
        ex_date = datetime(2026, 6, 15, tzinfo=UTC)
        before = _bar("AAPL", ex_date - timedelta(days=1), close=200.0)
        dividend = CorporateAction(
            symbol="AAPL",
            ex_date=ex_date,
            action_type=CorporateActionType.DIVIDEND,
            cash_amount=0.5,
        )

        adjusted = apply_split_adjustment([before], [dividend])

        assert adjusted[0].close == 200.0  # unchanged

    def test_two_splits_compound_correctly(self) -> None:
        first_split_date = datetime(2026, 3, 1, tzinfo=UTC)
        second_split_date = datetime(2026, 6, 1, tzinfo=UTC)
        bar_before_both = _bar("AAPL", first_split_date - timedelta(days=1), close=400.0)

        actions = [
            CorporateAction(
                symbol="AAPL",
                ex_date=first_split_date,
                action_type=CorporateActionType.SPLIT,
                ratio=2.0,
            ),
            CorporateAction(
                symbol="AAPL",
                ex_date=second_split_date,
                action_type=CorporateActionType.SPLIT,
                ratio=2.0,
            ),
        ]

        adjusted = apply_split_adjustment([bar_before_both], actions)

        # Both splits apply since the bar predates both ex_dates: 400 / 2 / 2 = 100
        assert adjusted[0].close == 100.0
