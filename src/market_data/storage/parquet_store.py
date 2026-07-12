"""Parquet-backed implementation of `market_data.interfaces.MarketDataStorage`.

This is both "the local cache" and "incremental updates" from Milestone
2's deliverables in one class, deliberately — see
docs/engineering-handbook/Architecture/ADR/ADR-002-Market-Data.md's
storage section for why a separate cache abstraction on top of this would
have been redundant: every `write_bars` call already merges into whatever
is on disk, deduplicating on timestamp, so calling this store repeatedly
with overlapping fetches *is* the incremental-update / local-cache
behavior, not a separate concern layered on top.

One Parquet file per `(symbol, timeframe)` pair, at
`{root}/{symbol}/{timeframe}.parquet`. Not safe for concurrent writers to
the same file — this repository has no more than one writer process per
state file anywhere else either (see
docs/engineering-handbook/05_MEMORY_ENGINEER.md), and this store follows
the same convention.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from market_data.models import Bar, Timeframe

_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "trade_count", "vwap"]


def _bars_to_dataframe(bars: Sequence[Bar]) -> pd.DataFrame:
    rows = [
        {
            "timestamp": bar.timestamp,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "trade_count": bar.trade_count,
            "vwap": bar.vwap,
        }
        for bar in bars
    ]
    df = pd.DataFrame(rows, columns=_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def _dataframe_to_bars(df: pd.DataFrame, symbol: str, timeframe: Timeframe) -> list[Bar]:
    bars = []
    for row in df.itertuples(index=False):
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=row.timestamp.to_pydatetime(),
                timeframe=timeframe,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
                trade_count=(None if pd.isna(row.trade_count) else int(row.trade_count)),
                vwap=(None if pd.isna(row.vwap) else float(row.vwap)),
            )
        )
    return bars


class ParquetBarStore:
    """Satisfies `market_data.interfaces.MarketDataStorage`."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, symbol: str, timeframe: Timeframe) -> Path:
        return self.root / symbol / f"{timeframe.value}.parquet"

    def write_bars(self, bars: Sequence[Bar]) -> None:
        """Merge `bars` into whatever is already stored for each
        `(symbol, timeframe)` pair present in `bars`, deduplicating on
        timestamp (last write wins — matching
        `validation.deduplicate_bars`) and keeping the file sorted
        ascending by timestamp.
        """
        if not bars:
            return

        by_key: dict[tuple[str, Timeframe], list[Bar]] = {}
        for bar in bars:
            by_key.setdefault((bar.symbol, bar.timeframe), []).append(bar)

        for (symbol, timeframe), symbol_bars in by_key.items():
            path = self._path(symbol, timeframe)
            new_df = _bars_to_dataframe(symbol_bars)

            if path.exists():
                existing_df = pd.read_parquet(path)
                combined = pd.concat([existing_df, new_df], ignore_index=True)
            else:
                combined = new_df

            combined = (
                combined.drop_duplicates(subset="timestamp", keep="last")
                .sort_values("timestamp")
                .reset_index(drop=True)
            )

            path.parent.mkdir(parents=True, exist_ok=True)
            combined.to_parquet(path, engine="pyarrow", index=False)

    def read_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: Timeframe
    ) -> list[Bar]:
        path = self._path(symbol, timeframe)
        if not path.exists():
            return []

        df = pd.read_parquet(path)
        mask = (df["timestamp"] >= start) & (df["timestamp"] < end)
        return _dataframe_to_bars(df.loc[mask], symbol, timeframe)

    def latest_timestamp(self, symbol: str, timeframe: Timeframe) -> datetime | None:
        path = self._path(symbol, timeframe)
        if not path.exists():
            return None

        df = pd.read_parquet(path, columns=["timestamp"])
        if df.empty:
            return None
        latest = df["timestamp"].max()
        result: datetime = latest.to_pydatetime()
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result


__all__ = ["ParquetBarStore"]
