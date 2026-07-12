from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_data.models import Bar, Timeframe
from market_data.storage.duckdb_query import DuckDBBarQuery
from market_data.storage.parquet_store import ParquetBarStore

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


def test_bars_in_range_returns_empty_dataframe_for_unknown_symbol(tmp_path: Path) -> None:
    query = DuckDBBarQuery(tmp_path)
    start = datetime(2026, 6, 1, tzinfo=UTC)

    df = query.bars_in_range("AAPL", Timeframe.MIN_1, start, start + timedelta(days=1))

    assert df.empty
    assert "timestamp" in df.columns


def test_bars_in_range_matches_parquet_store_contents(tmp_path: Path) -> None:
    store = ParquetBarStore(tmp_path)
    start = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
    bars = [_bar("AAPL", start + timedelta(minutes=i)) for i in range(5)]
    store.write_bars(bars)

    query = DuckDBBarQuery(tmp_path)
    df = query.bars_in_range("AAPL", Timeframe.MIN_1, start, start + timedelta(minutes=5))

    assert len(df) == 5
    assert list(df["close"]) == [b.close for b in bars]


def test_bars_in_range_respects_window_bounds(tmp_path: Path) -> None:
    store = ParquetBarStore(tmp_path)
    start = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
    store.write_bars([_bar("AAPL", start + timedelta(minutes=i)) for i in range(10)])

    query = DuckDBBarQuery(tmp_path)
    df = query.bars_in_range(
        "AAPL", Timeframe.MIN_1, start + timedelta(minutes=2), start + timedelta(minutes=4)
    )

    assert len(df) == 2


def test_query_across_multiple_symbols_via_glob(tmp_path: Path) -> None:
    store = ParquetBarStore(tmp_path)
    ts = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
    store.write_bars([_bar("AAPL", ts, close=100.0)])
    store.write_bars([_bar("MSFT", ts, close=200.0)])

    query = DuckDBBarQuery(tmp_path)
    pattern = query.parquet_glob(Timeframe.MIN_1)
    df = query.query(f"SELECT * FROM read_parquet('{pattern}') ORDER BY close")

    assert len(df) == 2
    assert list(df["close"]) == [100.0, 200.0]


def test_parquet_glob_matches_store_layout(tmp_path: Path) -> None:
    query = DuckDBBarQuery(tmp_path)
    pattern = query.parquet_glob(Timeframe.DAY_1)
    assert pattern == str(tmp_path / "*" / "1Day.parquet")
