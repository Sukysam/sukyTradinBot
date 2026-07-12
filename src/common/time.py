"""Injectable time source.

Every timestamp-dependent piece of logic in this codebase is expected to
receive "now" as an explicit parameter rather than calling `datetime.now()`
internally — see docs/engineering-handbook/Standards/Python Style Guide.md,
"Pass 'now'/'as of' timestamps as an explicit parameter". `Clock` is the
`Protocol` that formalizes where that explicit "now" comes from in
production (`SystemClock`) versus in a test (`FixedClock`), so time-based
tests never depend on wall-clock timing or sleeping.
"""

from __future__ import annotations

from datetime import datetime, timezone

from common.interfaces import Clock


class SystemClock:
    """Real wall-clock time, always timezone-aware UTC.

    The only `Clock` implementation used in production. Naive datetimes
    are never returned — every consumer of `now()` can assume `tzinfo` is
    always set, so no call site needs to guess or normalize.
    """

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """A `Clock` that always returns the same instant.

    For tests that need deterministic, injectable time without sleeping or
    monkeypatching `datetime.now`. Construct with an explicit,
    timezone-aware `datetime`; raises if given a naive one, since a test
    silently running in "local time" is a common source of flaky,
    timezone-dependent test failures.
    """

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError(
                f"FixedClock requires a timezone-aware datetime, got naive value {instant!r}"
            )
        self._instant = instant

    def now(self) -> datetime:
        return self._instant

    def advance(self, *, seconds: float = 0.0) -> None:
        """Move this clock forward, for tests that exercise elapsed-time logic."""
        from datetime import timedelta

        self._instant = self._instant + timedelta(seconds=seconds)


def require_utc(value: datetime, field_name: str) -> None:
    """Raise `ValueError` unless `value` is timezone-aware and normalized to
    UTC exactly (not merely "has a tzinfo") -- e.g. `+00:00`, not `-05:00`.

    The same naive-datetime and wrong-offset check was independently
    written three times across this codebase (`market_data.models.Bar`,
    `features.feature_vector.FeatureVector`/`Provenance`, and
    `hmm.models.RegimeState`) before being promoted here — see
    docs/engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md.
    `field_name` is included in the error so a caller validating several
    datetime fields on one object gets a message pointing at the specific
    field, not just "a timestamp was wrong."
    """
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware, got naive datetime {value!r}")
    if value.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError(
            f"{field_name} must be normalized to UTC, got offset "
            f"{value.utcoffset()} for {value!r}"
        )


def utc_now() -> datetime:
    """Convenience free function equivalent to `SystemClock().now()`.

    Prefer injecting a `Clock` (see `common.interfaces.Clock`) into any
    function or class whose behavior depends on "now" and needs to be
    tested deterministically. Use this free function only at the outermost
    call site (e.g. constructing the default `Clock` for a long-lived
    service), never inside logic that should be testable with a
    `FixedClock`.
    """
    return datetime.now(timezone.utc)


__all__ = ["Clock", "FixedClock", "SystemClock", "require_utc", "utc_now"]
