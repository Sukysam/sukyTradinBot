"""Market data validation: gap detection, deduplication, timezone
normalization, and corporate-action split adjustment.

Every `Bar`/`Trade`/`Quote`/etc. already refuses construction with a
non-UTC timestamp (see `models._require_utc`), so `normalize_timezone`
here operates one layer *before* that — on raw timestamps a provider has
just parsed off the wire, before a domain model is built from them. The
other functions operate on already-constructed, already-UTC `Bar`
sequences.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo

from market_data.models import Bar, CorporateAction, CorporateActionType, Timeframe

# Fixed cadence per intraday timeframe. DAY_1 is deliberately absent: daily
# bars don't have a fixed inter-bar delta once weekends and market
# holidays are considered, and this module does not implement a trading
# calendar. `find_missing_bars` falls back to weekday-only gap detection
# for DAY_1 — a reasonable approximation, not a substitute for a real
# holiday calendar. See the function's docstring.
_INTRADAY_DELTAS: dict[Timeframe, timedelta] = {
    Timeframe.MIN_1: timedelta(minutes=1),
    Timeframe.MIN_5: timedelta(minutes=5),
    Timeframe.MIN_15: timedelta(minutes=15),
    Timeframe.HOUR_1: timedelta(hours=1),
}


def normalize_timezone(timestamp: datetime, *, assume_tz: tzinfo = timezone.utc) -> datetime:
    """Return `timestamp` as a UTC-aware `datetime`.

    A naive `timestamp` is assumed to already be in `assume_tz` (default:
    UTC) and localized accordingly — callers dealing with a provider that
    returns naive local-exchange time must pass the correct `assume_tz`
    explicitly rather than relying on the default, since silently
    guessing wrong here produces bars shifted by a fixed offset with no
    error anywhere downstream.
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=assume_tz)
    return timestamp.astimezone(timezone.utc)


def deduplicate_bars(bars: list[Bar]) -> list[Bar]:
    """Return `bars` with one entry per `timestamp`, ascending order.

    When the same timestamp appears more than once, the *last* occurrence
    in input order wins — later entries are treated as corrections
    superseding earlier ones, matching how a provider typically emits a
    revised bar (same timestamp, updated values) rather than a true
    duplicate.
    """
    by_timestamp: dict[datetime, Bar] = {}
    for bar in bars:
        by_timestamp[bar.timestamp] = bar
    return [by_timestamp[ts] for ts in sorted(by_timestamp)]


def find_duplicate_timestamps(bars: list[Bar]) -> list[Bar]:
    """Return every bar beyond the first for any repeated `timestamp`, in
    input order. An empty result means `bars` has no duplicates. Does not
    mutate or reorder `bars` — pair with `deduplicate_bars` to also
    resolve them.
    """
    seen: set[datetime] = set()
    duplicates: list[Bar] = []
    for bar in bars:
        if bar.timestamp in seen:
            duplicates.append(bar)
        else:
            seen.add(bar.timestamp)
    return duplicates


def _expected_timestamps(start: datetime, end: datetime, timeframe: Timeframe) -> list[datetime]:
    if timeframe in _INTRADAY_DELTAS:
        delta = _INTRADAY_DELTAS[timeframe]
        expected = []
        current = start
        while current < end:
            expected.append(current)
            current += delta
        return expected

    # DAY_1: one expected bar per weekday, ignoring market holidays (see
    # module docstring — no trading calendar here).
    expected = []
    current = start
    one_day = timedelta(days=1)
    while current < end:
        if current.weekday() < 5:  # Monday=0 .. Sunday=6
            expected.append(current)
        current += one_day
    return expected


def find_missing_bars(
    bars: list[Bar], timeframe: Timeframe, start: datetime, end: datetime
) -> list[datetime]:
    """Return the timestamps in `[start, end)` at `timeframe`'s expected
    cadence that `bars` does not cover.

    For `Timeframe.DAY_1` this only accounts for weekends, not market
    holidays — a holiday will be reported as a false-positive gap. This is
    a known, accepted limitation (see module docstring) rather than a bug;
    treat `DAY_1` results as a starting point for investigation, not a
    ground-truth gap list.
    """
    present = {bar.timestamp for bar in bars}
    return [ts for ts in _expected_timestamps(start, end, timeframe) if ts not in present]


def apply_split_adjustment(bars: list[Bar], actions: list[CorporateAction]) -> list[Bar]:
    """Back-adjust `bars` for every `SPLIT` action in `actions`.

    Standard back-adjustment: for a split with `ex_date` and `ratio` (e.g.
    `2.0` for a 2-for-1 split), every bar strictly before `ex_date` has
    open/high/low/close divided by `ratio` and volume multiplied by
    `ratio`, so the pre-split price series is comparable to the
    post-split one. Bars at or after `ex_date` are unchanged by that
    split. Multiple splits are applied oldest-`ex_date`-first, each only
    to bars before its own `ex_date`, so an older split's adjustment
    compounds correctly under a later one.

    Non-`SPLIT` actions in `actions` (dividends, mergers, spinoffs) are
    ignored by this function — dividend/total-return adjustment is a
    distinct, not-yet-implemented calculation or backtesting to consume
    from `CorporateAction` directly rather than folded into this function
    silently.
    """
    splits = sorted(
        (a for a in actions if a.action_type == CorporateActionType.SPLIT),
        key=lambda a: a.ex_date,
    )
    if not splits:
        return list(bars)

    adjusted = list(bars)
    for split in splits:
        assert split.ratio is not None  # enforced by CorporateAction.__post_init__
        ratio = split.ratio
        ex_date = split.ex_date
        adjusted = [
            (
                Bar(
                    symbol=bar.symbol,
                    timestamp=bar.timestamp,
                    timeframe=bar.timeframe,
                    open=bar.open / ratio,
                    high=bar.high / ratio,
                    low=bar.low / ratio,
                    close=bar.close / ratio,
                    volume=bar.volume * ratio,
                    trade_count=bar.trade_count,
                    vwap=(bar.vwap / ratio) if bar.vwap is not None else None,
                )
                if bar.timestamp < ex_date
                else bar
            )
            for bar in adjusted
        ]
    return adjusted


@dataclass(frozen=True)
class ValidationReport:
    """Summary of a validation pass over one symbol/timeframe/window."""

    symbol: str
    timeframe: Timeframe
    missing_bar_timestamps: tuple[datetime, ...]
    duplicate_bars: tuple[Bar, ...]

    @property
    def is_clean(self) -> bool:
        return not self.missing_bar_timestamps and not self.duplicate_bars


def validate_bars(
    bars: list[Bar], symbol: str, timeframe: Timeframe, start: datetime, end: datetime
) -> ValidationReport:
    """Run the standard validation pass (missing bars + duplicates) and
    return a single report. Does not mutate `bars` or resolve findings —
    see `deduplicate_bars` to act on `duplicate_bars`.
    """
    return ValidationReport(
        symbol=symbol,
        timeframe=timeframe,
        missing_bar_timestamps=tuple(find_missing_bars(bars, timeframe, start, end)),
        duplicate_bars=tuple(find_duplicate_timestamps(bars)),
    )


__all__ = [
    "ValidationReport",
    "apply_split_adjustment",
    "deduplicate_bars",
    "find_duplicate_timestamps",
    "find_missing_bars",
    "normalize_timezone",
    "validate_bars",
]
