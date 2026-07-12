"""DuckDB query layer over `ParquetBarStore`'s files.

`ParquetBarStore` is the canonical write path and single-symbol read path
(implements `MarketDataStorage`). This class is a read-only, SQL-oriented
complement for the case `ParquetBarStore.read_bars` doesn't cover well:
answering a question across *many* symbols at once (e.g. "which symbols
had a bar with volume > X on this date") without loading every parquet
file into pandas by hand. DuckDB queries the parquet files directly — no
separate load/ETL step, no second copy of the data.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from market_data.models import Timeframe


class DuckDBBarQuery:
    """Read-only SQL access to a `ParquetBarStore`'s files at `root`."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def parquet_glob(self, timeframe: Timeframe) -> str:
        """The glob pattern matching every symbol's parquet file for
        `timeframe`, for use in a `read_parquet('...')` SQL clause passed
        to `query()`.
        """
        return str(self.root / "*" / f"{timeframe.value}.parquet")

    def bars_in_range(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> pd.DataFrame:
        """Single-symbol convenience query. Returns an empty (but
        correctly-columned) DataFrame if no file exists for `symbol`.
        """
        path = self.root / symbol / f"{timeframe.value}.parquet"
        if not path.exists():
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        with duckdb.connect(":memory:") as con:
            return con.execute(
                "SELECT * FROM read_parquet(?) WHERE timestamp >= ? AND timestamp < ? "
                "ORDER BY timestamp",
                [str(path), start, end],
            ).df()

    def query(self, sql: str) -> pd.DataFrame:
        """Run arbitrary read-only SQL, typically built with
        `parquet_glob()`'s output inside a `read_parquet(...)` clause, and
        return the result as a DataFrame. No write access is exposed —
        this class never opens a connection against the store's real
        files in write mode.
        """
        with duckdb.connect(":memory:") as con:
            return con.execute(sql).df()


__all__ = ["DuckDBBarQuery"]
