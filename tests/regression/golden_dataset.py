"""The one canonical scenario `test_golden_dataset.py` regresses
against.

Per the technical lead's explicit recommendation ("choose one canonical
dataset... every CI run should reproduce the same trades, equity curve,
and summary metrics within documented tolerances"). Named `SYNTH`, not a
real ticker like `SPY` -- this repository has no live market-data
credentials (see Architecture/Known Gaps.md), so every golden dataset in
this codebase is deterministic synthetic data, matching the honesty
convention every prior milestone's own test fixtures already established.
Never mistake `SYNTH` for real historical SPY data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine
from backtest.models import BacktestResult
from common.time import FixedClock
from tests.backtest.conftest import (
    DEFAULT_START,
    make_bars,
    make_risk_service,
    make_strategy_service,
    train_regime_service,
)

GOLDEN_SYMBOL = "SYNTH"
GOLDEN_DATASET_NAME = "synthetic-daily-2024"
GOLDEN_RUN_ID = "golden-dataset-baseline"
GOLDEN_GIT_COMMIT = "0" * 40
GOLDEN_GENERATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def run_golden_dataset() -> BacktestResult:
    bars = make_bars(300, start=DEFAULT_START, symbol=GOLDEN_SYMBOL, seed=7)
    regime_service = train_regime_service(bars, symbol=GOLDEN_SYMBOL, model_version="golden_v1")

    config = BacktestConfig(
        symbols=(GOLDEN_SYMBOL,),
        start_date=DEFAULT_START + timedelta(days=100),
        end_date=DEFAULT_START + timedelta(days=299),
        initial_equity=100_000.0,
        feature_lookback_bars=60,
        dataset=GOLDEN_DATASET_NAME,
    )

    engine = BacktestEngine(clock=FixedClock(GOLDEN_GENERATED_AT))
    return engine.run(
        config=config,
        bars={GOLDEN_SYMBOL: bars},
        regime_services={GOLDEN_SYMBOL: regime_service},
        strategy_service=make_strategy_service(),
        risk_service=make_risk_service(),
        run_id=GOLDEN_RUN_ID,
        git_commit=GOLDEN_GIT_COMMIT,
    )


__all__ = [
    "GOLDEN_DATASET_NAME",
    "GOLDEN_GENERATED_AT",
    "GOLDEN_GIT_COMMIT",
    "GOLDEN_RUN_ID",
    "GOLDEN_SYMBOL",
    "run_golden_dataset",
]
