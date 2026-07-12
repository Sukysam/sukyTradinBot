"""The one path from raw bars to `FeatureVector` — see
docs/engineering-handbook/Architecture/ADR/ADR-003-Feature-Engineering.md
for why this exists: every subsystem that needs features (HMM,
backtesting, adaptive learning, NLP, risk) is meant to call
`FeaturePipeline`, never recompute an indicator itself.

Fixed sequence, always the same order:

    Bars -> validation -> cleaning -> corporate-action adjustment ->
    feature calculation -> validation -> FeatureVector(s)

Stages 1-3 reuse `market_data.validation` directly rather than
reimplementing bar-level cleaning — this pipeline's own `validation.py`
only handles what's new at this layer: feature *output* validation and
quality-flag computation.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from features.errors import InsufficientHistoryError
from features.feature_vector import FeatureVector
from features.registry import DEFAULT_REGISTRY, FeatureRegistry
from features.validation import compute_quality_flags, validate_feature_output
from market_data.models import Bar, CorporateAction
from market_data.validation import apply_split_adjustment, deduplicate_bars, validate_bars

PIPELINE_VERSION = "1"

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def _bars_to_dataframe(bars: Sequence[Bar]) -> pd.DataFrame:
    rows = [
        {
            "timestamp": bar.timestamp,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in bars
    ]
    df = pd.DataFrame(rows, columns=["timestamp", *_OHLCV_COLUMNS])
    return df.sort_values("timestamp").reset_index(drop=True)


@dataclass(frozen=True)
class PipelineDiagnostics:
    """What `market_data.validation.validate_bars` found in the input,
    surfaced to the caller via `FeaturePipeline`'s return value rather
    than silently discarded — a caller building a backtest or a live
    signal may care that gaps existed even though the pipeline didn't
    refuse to run because of them (see `FeaturePipeline`'s docstring on
    why missing bars don't hard-fail by default).
    """

    missing_bar_count: int
    duplicate_bar_count: int


class FeaturePipeline:
    """Computes `FeatureVector`s for one symbol from its bar history.

    Missing bars are reported (see `PipelineDiagnostics`) but do not stop
    computation by default — real market data has minor gaps (trading
    halts, thin liquidity) that would make this pipeline unusable if
    treated as fatal. Duplicate timestamps *are* resolved automatically
    (last write wins, via `market_data.validation.deduplicate_bars`)
    before any feature touches the data, since a duplicate is a data
    integrity problem, not a market condition.
    """

    def __init__(self, registry: FeatureRegistry | None = None) -> None:
        self.registry = registry or DEFAULT_REGISTRY

    def _prepare(
        self, bars: Sequence[Bar], corporate_actions: Sequence[CorporateAction]
    ) -> tuple[pd.DataFrame, PipelineDiagnostics]:
        if not bars:
            raise InsufficientHistoryError("Cannot compute features from an empty bar history")

        symbol = bars[0].symbol
        timeframe = bars[0].timeframe
        ordered = sorted(bars, key=lambda b: b.timestamp)
        start, end = ordered[0].timestamp, ordered[-1].timestamp

        report = validate_bars(list(ordered), symbol, timeframe, start, end)
        deduplicated = deduplicate_bars(list(ordered))
        if corporate_actions:
            deduplicated = apply_split_adjustment(deduplicated, list(corporate_actions))

        diagnostics = PipelineDiagnostics(
            missing_bar_count=len(report.missing_bar_timestamps),
            duplicate_bar_count=len(report.duplicate_bars),
        )
        return _bars_to_dataframe(deduplicated), diagnostics

    def _compute_feature_matrix(
        self, df: pd.DataFrame, feature_names: Sequence[str] | None
    ) -> pd.DataFrame:
        specs = (
            [self.registry.get(name) for name in feature_names]
            if feature_names is not None
            else list(self.registry.all())
        )
        columns: dict[str, pd.Series] = {}
        for spec in specs:
            output = spec.compute(df)
            validate_feature_output(spec, output, df.index)
            columns[spec.name] = output
        return pd.DataFrame(columns, index=df.index)

    def compute_series(
        self,
        bars: Sequence[Bar],
        symbol: str,
        *,
        corporate_actions: Sequence[CorporateAction] = (),
        feature_names: Sequence[str] | None = None,
        source: str = "unspecified",
    ) -> tuple[list[FeatureVector], PipelineDiagnostics]:
        """One `FeatureVector` per input bar (after cleaning/dedup), in
        ascending timestamp order. Early rows will have flagged/`NaN`
        values for any feature whose `lookback` exceeds their position —
        that's expected, not an error; see `validation.compute_quality_flags`.
        """
        df, diagnostics = self._prepare(bars, corporate_actions)
        feature_df = self._compute_feature_matrix(df, feature_names)
        flags_df = compute_quality_flags(feature_df)

        # Per-row `.iloc[i]` on a DataFrame builds a fresh Series each call
        # -- fine at daily-bar row counts, but O(n) Series-construction
        # overhead dominates at 1-minute-bar counts (~8k rows). Pulling the
        # whole matrix to numpy once, and timestamps to a plain list once,
        # turns that into cheap positional indexing per row instead.
        values_matrix = feature_df.to_numpy(dtype="float64")
        flags_matrix = flags_df.to_numpy(dtype="bool")
        timestamps = df["timestamp"].tolist()
        metadata_base = {
            "pipeline_version": PIPELINE_VERSION,
            "source": source,
            "n_bars_used": len(df),
        }

        feature_name_tuple = tuple(feature_df.columns)
        vectors = []
        for i in range(len(df)):
            flags = {
                name: True
                for name, is_flagged in zip(feature_name_tuple, flags_matrix[i])
                if is_flagged
            }
            vectors.append(
                FeatureVector(
                    timestamp=timestamps[i].to_pydatetime(),
                    symbol=symbol,
                    feature_values=tuple(values_matrix[i].tolist()),
                    feature_names=feature_name_tuple,
                    metadata=dict(metadata_base),
                    quality_flags=flags,
                    version=PIPELINE_VERSION,
                )
            )
        return vectors, diagnostics

    def compute(
        self,
        bars: Sequence[Bar],
        symbol: str,
        *,
        corporate_actions: Sequence[CorporateAction] = (),
        feature_names: Sequence[str] | None = None,
        source: str = "unspecified",
        strict: bool = False,
    ) -> FeatureVector:
        """The single most recent `FeatureVector` — the live-trading
        entry point. `strict=True` raises `InsufficientHistoryError`
        instead of returning a vector with any flagged feature, for
        callers (e.g. a future live signal path) that must not act on
        partially-warmed-up features.
        """
        vectors, _ = self.compute_series(
            bars,
            symbol,
            corporate_actions=corporate_actions,
            feature_names=feature_names,
            source=source,
        )
        latest = vectors[-1]
        if strict and latest.has_any_flag:
            flagged = sorted(
                name for name, is_flagged in latest.quality_flags.items() if is_flagged
            )
            raise InsufficientHistoryError(
                f"{symbol}: {len(flagged)} feature(s) lack sufficient history at "
                f"{latest.timestamp.isoformat()}: {flagged}"
            )
        return latest


def timed_compute_series(
    pipeline: FeaturePipeline, bars: Sequence[Bar], symbol: str
) -> tuple[list[FeatureVector], float]:
    """Convenience wrapper used by `tests/features/test_performance.py` —
    not part of the platform's production API, just avoids duplicating
    timing boilerplate across performance test cases.
    """
    start = time.perf_counter()
    vectors, _ = pipeline.compute_series(bars, symbol)
    elapsed = time.perf_counter() - start
    return vectors, elapsed


__all__ = ["PIPELINE_VERSION", "FeaturePipeline", "PipelineDiagnostics", "timed_compute_series"]
