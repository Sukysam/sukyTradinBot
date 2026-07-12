"""Market Data Platform (Milestone 2).

Provider-agnostic market data: domain models, provider interfaces,
Alpaca-backed implementations, Parquet/DuckDB storage, validation, and a
historical replay harness. See
docs/engineering-handbook/Architecture/ADR/ADR-002-Market-Data.md for the
architecture and docs/engineering-handbook/PROJECT_STATUS.md for status.

This package intentionally does not import anything from
`regime-trader/` — see that ADR's Decision on the adapter pattern used to
wire this into `regime-trader/main.py`'s `MarketDataProvider` `Protocol`
(`regime-trader/broker/alpaca_client.py`) without this package depending
on `regime-trader/` or vice versa beyond that one, deliberately thin, file.
"""

from __future__ import annotations

from market_data.errors import (
    DataValidationError,
    MarketDataError,
    ProviderAuthenticationError,
    ProviderConnectionError,
    RateLimitExceededError,
)
from market_data.models import (
    Bar,
    CorporateAction,
    CorporateActionType,
    OrderBook,
    PriceLevel,
    Quote,
    Snapshot,
    Timeframe,
    Trade,
)

__version__ = "0.1.0"

__all__ = [
    "Bar",
    "CorporateAction",
    "CorporateActionType",
    "DataValidationError",
    "MarketDataError",
    "OrderBook",
    "PriceLevel",
    "ProviderAuthenticationError",
    "ProviderConnectionError",
    "Quote",
    "RateLimitExceededError",
    "Snapshot",
    "Timeframe",
    "Trade",
    "__version__",
]
