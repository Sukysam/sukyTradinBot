"""Market-data-specific exception hierarchy.

Every exception here derives from `common.errors.AppError`, so calling
code outside this package can catch "something in first-party
infrastructure went wrong" without also catching unrelated third-party
exceptions — see `common.errors`'s own docstring. Per
docs/engineering-handbook/03_BACKEND_ENGINEER.md's coding standards,
provider implementations catch the underlying SDK's exceptions (e.g.
`alpaca.common.exceptions.APIError`) and re-raise as one of these — a
consumer in `core/` or a future strategy module should never need to know
`alpaca-py` exists.
"""

from __future__ import annotations

from common.errors import AppError


class MarketDataError(AppError):
    """Base class for all market-data package errors."""


class ProviderAuthenticationError(MarketDataError):
    """Raised when a provider rejects credentials or none are configured."""


class RateLimitExceededError(MarketDataError):
    """Raised when a provider's rate limit is exceeded and the caller has
    exhausted its retry budget (see `common.retry`). Distinct from a
    transient connection error: a rate limit is an expected operational
    condition under load, not a bug.
    """


class ProviderConnectionError(MarketDataError):
    """Raised when a provider's transport (REST or streaming) fails in a
    way that isn't a rate limit or an auth failure — network errors,
    unexpected disconnects, malformed responses.
    """


class DataValidationError(MarketDataError):
    """Raised when data returned by a provider fails validation (see
    `validation.py`) badly enough that it must not be used, rather than
    merely flagged. Most validation findings are reported, not raised —
    this is reserved for cases where continuing would be actively unsafe
    (e.g. constructing a `Bar` with a naive timestamp).
    """


__all__ = [
    "DataValidationError",
    "MarketDataError",
    "ProviderAuthenticationError",
    "ProviderConnectionError",
    "RateLimitExceededError",
]
