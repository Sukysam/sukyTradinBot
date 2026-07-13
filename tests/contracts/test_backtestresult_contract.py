"""Regression tests for the `BacktestResult` contract itself (Standards/
BacktestResult Contract.md), distinct from `tests/backtest/`'s own unit
tests -- these exist to catch an accidental breaking change to the
contract's *shape*, not to test replay/metrics/portfolio logic. If a
change here forces an edit to this file, that's a signal the change
needs a new ADR per that Standards document's own versioning policy.
"""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone

from backtest.models import BacktestResult, EquityPoint, ReplayRun, TradeRecord
from execution.models import OrderSide

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


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
        "holding_period": timedelta(days=5),
    }
    defaults.update(overrides)
    return TradeRecord(**defaults)  # type: ignore[arg-type]


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


class TestRequiredFields:
    def test_backtest_result_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(BacktestResult)}
        assert field_names == {
            "start_date",
            "end_date",
            "symbols",
            "initial_equity",
            "final_equity",
            "cagr",
            "sharpe_ratio",
            "sortino_ratio",
            "calmar_ratio",
            "max_drawdown",
            "win_rate",
            "profit_factor",
            "average_holding_period",
            "exposure",
            "turnover",
            "trade_log",
            "equity_curve",
            "replay_run",
            "generated_at",
            "metadata",
        }

    def test_trade_record_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(TradeRecord)}
        assert field_names == {
            "symbol",
            "strategy_id",
            "regime_id",
            "side",
            "entry_timestamp",
            "exit_timestamp",
            "entry_price",
            "exit_price",
            "quantity",
            "pnl",
            "pnl_pct",
            "holding_period",
        }

    def test_equity_point_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(EquityPoint)}
        assert field_names == {"timestamp", "equity"}

    def test_replay_run_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(ReplayRun)}
        assert field_names == {"run_id", "dataset", "pipeline_versions", "git_commit", "timestamp"}


class TestSerializationRoundTrip:
    def test_result_round_trips_through_dict(self) -> None:
        result = _result(metadata={"note": "value"})
        assert BacktestResult.from_dict(result.to_dict()) == result

    def test_result_with_empty_trade_log_round_trips(self) -> None:
        result = _result(trade_log=())
        assert BacktestResult.from_dict(result.to_dict()) == result

    def test_result_with_inf_metrics_round_trips(self) -> None:
        result = _result(calmar_ratio=float("inf"), profit_factor=float("inf"))
        round_tripped = BacktestResult.from_dict(result.to_dict())
        assert round_tripped.calmar_ratio == float("inf")
        assert round_tripped.profit_factor == float("inf")

    def test_to_dict_is_json_serializable_except_for_inf(self) -> None:
        # json.dumps accepts Infinity by default (non-standard JSON, but
        # Python's json module permits it) -- confirms to_dict() doesn't
        # produce anything json.dumps chokes on for a normal (finite)
        # result.
        json.dumps(_result().to_dict())


class TestBackwardCompatibility:
    def test_construction_tolerates_unknown_metadata_keys(self) -> None:
        _result(metadata={"anything": "goes", "here": 123})

    def test_pipeline_versions_tolerates_arbitrary_keys(self) -> None:
        # ReplayRun.pipeline_versions ships with no guaranteed keys by
        # design -- any package/model version mapping must be accepted.
        _result(replay_run=_replay_run(pipeline_versions={"whatever": "1", "another": "2"}))
