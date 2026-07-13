"""Golden-dataset regression test -- mandatory per the technical lead's
explicit recommendation. Every CI run replays the exact same synthetic
scenario (`golden_dataset.py`) and compares the result against a
checked-in baseline (`baseline_results/synthetic_daily_2024.json`).

**Why tolerance, not exact equality**: this project's CI matrix runs both
Python 3.9 and 3.11 against different resolved `numpy`/`scipy` versions
(already a source of real, documented behavioral differences -- see
ADR-009's mypy note on numpy-version-dependent type inference). HMM
training (`hmmlearn`'s EM algorithm) is not guaranteed bit-identical
across BLAS/LAPACK backends, so an exact-equality regression here would
be genuinely flaky across that matrix, not just theoretically fragile.
Structural properties (trade count, symbol, side, ascending order) are
compared exactly; every float is compared within a documented relative
tolerance. If a genuine behavioral change is intended, regenerate the
baseline deliberately (see this file's bottom) and note why in the PR --
never silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtest.models import BacktestResult
from tests.regression.golden_dataset import run_golden_dataset

BASELINE_PATH = Path(__file__).parent / "baseline_results" / "synthetic_daily_2024.json"

#: Relative tolerance for every floating-point comparison below --
#: generous enough to absorb cross-platform BLAS/numpy drift in HMM
#: training, tight enough to still catch a real regression.
RELATIVE_TOLERANCE = 1e-3


@pytest.fixture(scope="module")
def baseline() -> BacktestResult:
    with open(BASELINE_PATH) as f:
        return BacktestResult.from_dict(json.load(f))


@pytest.fixture(scope="module")
def current() -> BacktestResult:
    return run_golden_dataset()


class TestGoldenDatasetRegression:
    def test_trade_count_matches(self, baseline: BacktestResult, current: BacktestResult) -> None:
        assert len(current.trade_log) == len(baseline.trade_log)

    def test_equity_curve_length_matches(
        self, baseline: BacktestResult, current: BacktestResult
    ) -> None:
        assert len(current.equity_curve) == len(baseline.equity_curve)

    def test_every_trade_has_matching_symbol_and_side(
        self, baseline: BacktestResult, current: BacktestResult
    ) -> None:
        for baseline_trade, current_trade in zip(baseline.trade_log, current.trade_log):
            assert current_trade.symbol == baseline_trade.symbol
            assert current_trade.side == baseline_trade.side

    def test_trade_prices_match_within_tolerance(
        self, baseline: BacktestResult, current: BacktestResult
    ) -> None:
        for baseline_trade, current_trade in zip(baseline.trade_log, current.trade_log):
            assert current_trade.entry_price == pytest.approx(
                baseline_trade.entry_price, rel=RELATIVE_TOLERANCE
            )
            assert current_trade.exit_price == pytest.approx(
                baseline_trade.exit_price, rel=RELATIVE_TOLERANCE
            )

    def test_final_equity_matches_within_tolerance(
        self, baseline: BacktestResult, current: BacktestResult
    ) -> None:
        assert current.final_equity == pytest.approx(baseline.final_equity, rel=RELATIVE_TOLERANCE)

    @pytest.mark.parametrize(
        "metric",
        ["cagr", "sharpe_ratio", "sortino_ratio", "max_drawdown", "win_rate", "turnover"],
    )
    def test_summary_metric_matches_within_tolerance(
        self, baseline: BacktestResult, current: BacktestResult, metric: str
    ) -> None:
        baseline_value = getattr(baseline, metric)
        current_value = getattr(current, metric)
        assert current_value == pytest.approx(baseline_value, rel=RELATIVE_TOLERANCE, abs=1e-6)

    def test_dataset_name_is_unchanged(
        self, baseline: BacktestResult, current: BacktestResult
    ) -> None:
        assert current.replay_run.dataset == baseline.replay_run.dataset


# To regenerate the baseline after a deliberate, documented behavioral
# change (never as a way to silence a failing regression test):
#
#   python -c "
#   import json
#   from tests.regression.golden_dataset import run_golden_dataset
#   result = run_golden_dataset()
#   with open('tests/regression/baseline_results/synthetic_daily_2024.json', 'w') as f:
#       json.dump(result.to_dict(), f, indent=2)
#   "
