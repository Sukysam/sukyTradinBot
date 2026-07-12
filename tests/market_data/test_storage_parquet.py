from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_data.models import Bar, Timeframe
from market_data.storage.parquet_store import ParquetBarStore

UTC = timezone.utc


def _bar(
    symbol: str, ts: datetime, close: float = 100.0, timeframe: Timeframe = Timeframe.MIN_1
) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=ts,
        timeframe=timeframe,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
        trade_count=10,
        vwap=close + 0.1,
    )


class TestWriteAndReadRoundTrip:
    def test_round_trip_preserves_bar_fields(self, tmp_path: Path) -> None:
        store = ParquetBarStore(tmp_path)
        ts = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        bar = _bar("AAPL", ts)

        store.write_bars([bar])
        result = store.read_bars("AAPL", ts, ts + timedelta(minutes=1), Timeframe.MIN_1)

        assert len(result) == 1
        assert result[0] == bar

    def test_read_bars_filters_by_range(self, tmp_path: Path) -> None:
        store = ParquetBarStore(tmp_path)
        start = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        bars = [_bar("AAPL", start + timedelta(minutes=i)) for i in range(10)]
        store.write_bars(bars)

        result = store.read_bars(
            "AAPL", start + timedelta(minutes=2), start + timedelta(minutes=5), Timeframe.MIN_1
        )

        assert [b.timestamp for b in result] == [
            start + timedelta(minutes=2),
            start + timedelta(minutes=3),
            start + timedelta(minutes=4),
        ]

    def test_read_bars_returns_empty_list_for_unknown_symbol(self, tmp_path: Path) -> None:
        store = ParquetBarStore(tmp_path)
        start = datetime(2026, 6, 1, tzinfo=UTC)
        assert store.read_bars("MSFT", start, start + timedelta(days=1), Timeframe.MIN_1) == []

    def test_separate_files_per_symbol_and_timeframe(self, tmp_path: Path) -> None:
        store = ParquetBarStore(tmp_path)
        ts = datetime(2026, 6, 1, tzinfo=UTC)
        store.write_bars([_bar("AAPL", ts, timeframe=Timeframe.MIN_1)])
        store.write_bars([_bar("AAPL", ts, timeframe=Timeframe.DAY_1)])
        store.write_bars([_bar("MSFT", ts, timeframe=Timeframe.MIN_1)])

        assert (tmp_path / "AAPL" / "1Min.parquet").exists()
        assert (tmp_path / "AAPL" / "1Day.parquet").exists()
        assert (tmp_path / "MSFT" / "1Min.parquet").exists()


class TestIncrementalUpdates:
    def test_second_write_merges_with_first(self, tmp_path: Path) -> None:
        store = ParquetBarStore(tmp_path)
        start = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)

        store.write_bars([_bar("AAPL", start)])
        store.write_bars([_bar("AAPL", start + timedelta(minutes=1))])

        result = store.read_bars("AAPL", start, start + timedelta(minutes=2), Timeframe.MIN_1)
        assert len(result) == 2

    def test_overlapping_write_deduplicates_keeping_latest(self, tmp_path: Path) -> None:
        store = ParquetBarStore(tmp_path)
        ts = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)

        store.write_bars([_bar("AAPL", ts, close=100.0)])
        store.write_bars([_bar("AAPL", ts, close=105.0)])  # revision of the same bar

        result = store.read_bars("AAPL", ts, ts + timedelta(minutes=1), Timeframe.MIN_1)
        assert len(result) == 1
        assert result[0].close == 105.0

    def test_write_empty_list_is_a_no_op(self, tmp_path: Path) -> None:
        store = ParquetBarStore(tmp_path)
        store.write_bars([])
        assert list(tmp_path.iterdir()) == []


class TestLatestTimestamp:
    def test_none_when_nothing_stored(self, tmp_path: Path) -> None:
        store = ParquetBarStore(tmp_path)
        assert store.latest_timestamp("AAPL", Timeframe.MIN_1) is None

    def test_returns_max_timestamp(self, tmp_path: Path) -> None:
        store = ParquetBarStore(tmp_path)
        start = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        bars = [_bar("AAPL", start + timedelta(minutes=i)) for i in range(5)]
        store.write_bars(bars)

        latest = store.latest_timestamp("AAPL", Timeframe.MIN_1)

        assert latest == start + timedelta(minutes=4)
        assert latest.tzinfo is not None

    def test_incremental_update_pattern(self, tmp_path: Path) -> None:
        """The exact pattern a provider uses to fetch only new data:
        check latest_timestamp, fetch (latest, now], write_bars."""
        store = ParquetBarStore(tmp_path)
        start = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
        store.write_bars([_bar("AAPL", start + timedelta(minutes=i)) for i in range(3)])

        latest = store.latest_timestamp("AAPL", Timeframe.MIN_1)
        assert latest is not None
        new_bars = [_bar("AAPL", latest + timedelta(minutes=i)) for i in range(1, 4)]
        store.write_bars(new_bars)

        all_bars = store.read_bars("AAPL", start, start + timedelta(minutes=10), Timeframe.MIN_1)
        assert len(all_bars) == 6  # 3 original + 3 new, no duplicate at the boundary
