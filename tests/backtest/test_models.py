"""Tests for `backtest.models`: `EquityPoint`, `TradeRecord`,
`ReplayRun`, `BacktestResult`'s construction-time invariants, and
`OpenPosition`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backtest.models import BacktestResult, EquityPoint, OpenPosition, ReplayRun, TradeRecord
from execution.models import OrderSide

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _trade(**overrides: object) -> TradeRecord:
    defaults: dict[str, object] = {
        "symbol": "TEST",
        "strategy_id": "growth_v1",
        "regime_id": 0,
        "side": OrderSide.BUY,
        "entry_timestamp": T0,
        "exit_timestamp": T0 + timedelta(days=5),
        "entry_price": 100.0,
        "exit_price": 110.0,
        "quantity": 10,
        "pnl": 100.0,
        "pnl_pct": 0.1,
    }
    defaults.update(overrides)
    if "holding_period" not in overrides:
        defaults["holding_period"] = defaults["exit_timestamp"] - defaults["entry_timestamp"]  # type: ignore[operator]
    return TradeRecord(**defaults)  # type: ignore[arg-type]


def _replay_run(**overrides: object) -> ReplayRun:
    defaults: dict[str, object] = {
        "run_id": "run-1",
        "dataset": "test-dataset",
        "pipeline_versions": {"features": "2"},
        "git_commit": "abc123",
        "timestamp": T0,
    }
    defaults.update(overrides)
    return ReplayRun(**defaults)  # type: ignore[arg-type]


def _result(**overrides: object) -> BacktestResult:
    defaults: dict[str, object] = {
        "start_date": T0,
        "end_date": T0 + timedelta(days=30),
        "symbols": ("TEST",),
        "initial_equity": 100_000.0,
        "final_equity": 105_000.0,
        "cagr": 0.1,
        "sharpe_ratio": 1.0,
        "sortino_ratio": 1.2,
        "calmar_ratio": 2.0,
        "max_drawdown": 0.05,
        "win_rate": 0.6,
        "profit_factor": 1.5,
        "average_holding_period": timedelta(days=5),
        "exposure": 0.4,
        "turnover": 0.8,
        "trade_log": (_trade(),),
        "equity_curve": (
            EquityPoint(timestamp=T0, equity=100_000.0),
            EquityPoint(timestamp=T0 + timedelta(days=30), equity=105_000.0),
        ),
        "replay_run": _replay_run(),
        "generated_at": T0 + timedelta(days=31),
        "metadata": {},
    }
    defaults.update(overrides)
    return BacktestResult(**defaults)  # type: ignore[arg-type]


class TestEquityPoint:
    def test_rejects_naive_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            EquityPoint(timestamp=datetime(2024, 1, 1), equity=100.0)

    def test_rejects_negative_equity(self) -> None:
        with pytest.raises(ValueError, match="equity"):
            EquityPoint(timestamp=T0, equity=-1.0)

    def test_round_trips_through_dict(self) -> None:
        point = EquityPoint(timestamp=T0, equity=1234.5)
        assert EquityPoint.from_dict(point.to_dict()) == point


class TestTradeRecord:
    def test_rejects_exit_before_entry(self) -> None:
        with pytest.raises(ValueError, match="exit_timestamp"):
            _trade(exit_timestamp=T0 - timedelta(days=1))

    def test_rejects_non_positive_entry_price(self) -> None:
        with pytest.raises(ValueError, match="entry_price"):
            _trade(entry_price=0.0)

    def test_rejects_non_positive_quantity(self) -> None:
        with pytest.raises(ValueError, match="quantity"):
            _trade(quantity=0)

    def test_holding_period_must_equal_exit_minus_entry(self) -> None:
        with pytest.raises(ValueError, match="holding_period"):
            _trade(holding_period=timedelta(days=999))

    def test_round_trips_through_dict(self) -> None:
        trade = _trade()
        assert TradeRecord.from_dict(trade.to_dict()) == trade


class TestReplayRun:
    def test_rejects_empty_run_id(self) -> None:
        with pytest.raises(ValueError, match="run_id"):
            _replay_run(run_id="")

    def test_rejects_empty_dataset(self) -> None:
        with pytest.raises(ValueError, match="dataset"):
            _replay_run(dataset="")

    def test_rejects_empty_git_commit(self) -> None:
        with pytest.raises(ValueError, match="git_commit"):
            _replay_run(git_commit="")

    def test_round_trips_through_dict(self) -> None:
        run = _replay_run()
        assert ReplayRun.from_dict(run.to_dict()) == run


class TestBacktestResultRequiredFields:
    def test_construction_succeeds_with_defaults(self) -> None:
        result = _result()
        assert result.symbols == ("TEST",)

    def test_end_date_must_be_after_start_date(self) -> None:
        with pytest.raises(ValueError, match="end_date"):
            _result(end_date=T0 - timedelta(days=1))

    def test_symbols_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="symbols"):
            _result(symbols=())

    def test_symbols_must_not_have_duplicates(self) -> None:
        with pytest.raises(ValueError, match="duplicates"):
            _result(symbols=("TEST", "TEST"))

    def test_initial_equity_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="initial_equity"):
            _result(initial_equity=0.0)


class TestBacktestResultMetricBounds:
    @pytest.mark.parametrize("bad_value", [-0.01, 1.01])
    def test_max_drawdown_bounded_to_zero_one(self, bad_value: float) -> None:
        with pytest.raises(ValueError, match="max_drawdown"):
            _result(max_drawdown=bad_value)

    @pytest.mark.parametrize("bad_value", [-0.01, 1.01])
    def test_win_rate_bounded_to_zero_one(self, bad_value: float) -> None:
        with pytest.raises(ValueError, match="win_rate"):
            _result(win_rate=bad_value)

    def test_profit_factor_cannot_be_negative(self) -> None:
        with pytest.raises(ValueError, match="profit_factor"):
            _result(profit_factor=-1.0)

    def test_profit_factor_accepts_inf(self) -> None:
        result = _result(profit_factor=float("inf"))
        assert result.profit_factor == float("inf")

    def test_calmar_ratio_accepts_inf(self) -> None:
        result = _result(calmar_ratio=float("inf"))
        assert result.calmar_ratio == float("inf")

    @pytest.mark.parametrize("bad_value", [-0.01, 1.01])
    def test_exposure_bounded_to_zero_one(self, bad_value: float) -> None:
        with pytest.raises(ValueError, match="exposure"):
            _result(exposure=bad_value)

    def test_turnover_cannot_be_negative(self) -> None:
        with pytest.raises(ValueError, match="turnover"):
            _result(turnover=-0.1)


class TestBacktestResultCurveAndLogInvariants:
    def test_equity_curve_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="equity_curve"):
            _result(equity_curve=())

    def test_equity_curve_must_be_strictly_ascending(self) -> None:
        with pytest.raises(ValueError, match="ascending"):
            _result(
                equity_curve=(
                    EquityPoint(timestamp=T0, equity=100_000.0),
                    EquityPoint(timestamp=T0, equity=101_000.0),
                )
            )

    def test_equity_curve_first_point_must_equal_initial_equity(self) -> None:
        with pytest.raises(ValueError, match="initial_equity"):
            _result(
                initial_equity=100_000.0,
                equity_curve=(EquityPoint(timestamp=T0, equity=99_000.0),),
            )

    def test_trade_log_must_be_ascending_by_exit_timestamp(self) -> None:
        with pytest.raises(ValueError, match="ascending"):
            _result(
                trade_log=(
                    _trade(exit_timestamp=T0 + timedelta(days=10)),
                    _trade(exit_timestamp=T0 + timedelta(days=5)),
                )
            )

    def test_empty_trade_log_is_valid(self) -> None:
        result = _result(trade_log=())
        assert result.trade_log == ()


class TestSerializationRoundTrip:
    def test_result_round_trips_through_dict(self) -> None:
        result = _result(metadata={"note": "value"})
        assert BacktestResult.from_dict(result.to_dict()) == result

    def test_to_dict_is_json_serializable(self) -> None:
        import json

        json.dumps(_result().to_dict())


class TestBackwardCompatibility:
    def test_construction_tolerates_unknown_metadata_keys(self) -> None:
        _result(metadata={"anything": "goes", "here": 123})


class TestOpenPosition:
    def test_rejects_non_positive_entry_price(self) -> None:
        with pytest.raises(ValueError, match="entry_price"):
            OpenPosition(
                symbol="TEST",
                sector="Tech",
                strategy_id="growth_v1",
                regime_id=0,
                entry_timestamp=T0,
                entry_price=0.0,
                quantity=10,
            )

    def test_market_value_uses_supplied_current_price(self) -> None:
        position = OpenPosition(
            symbol="TEST",
            sector="Tech",
            strategy_id="growth_v1",
            regime_id=0,
            entry_timestamp=T0,
            entry_price=100.0,
            quantity=10,
        )
        assert position.market_value(current_price=120.0) == 1200.0
