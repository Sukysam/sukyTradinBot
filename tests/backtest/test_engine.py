"""End-to-end tests for `backtest.engine.BacktestEngine` -- Phase B:
metrics and `ReplayRun` layered on top of Phase A's `run_replay`,
producing a real `BacktestResult`."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine, current_git_commit
from backtest.exceptions import BacktestError
from backtest.models import BacktestResult
from backtest.reporting import generate_report
from common.time import FixedClock
from hmm.service import RegimeService
from market_data.models import Bar
from tests.backtest.conftest import (
    DEFAULT_START,
    make_bars,
    make_risk_service,
    make_strategy_service,
    train_regime_service,
)

SYMBOL = "TEST"


@pytest.fixture(scope="module")
def bars() -> list[Bar]:
    return make_bars(150, symbol=SYMBOL)


@pytest.fixture(scope="module")
def regime_service(bars: list[Bar]) -> RegimeService:
    return train_regime_service(bars, symbol=SYMBOL)


@pytest.fixture()
def config() -> BacktestConfig:
    return BacktestConfig(
        symbols=(SYMBOL,),
        start_date=DEFAULT_START + timedelta(days=110),
        end_date=DEFAULT_START + timedelta(days=149),
        initial_equity=100_000.0,
        feature_lookback_bars=60,
        dataset="test-engine",
    )


class TestBacktestEngineRun:
    def test_produces_a_valid_backtest_result(
        self, bars: list[Bar], regime_service: RegimeService, config: BacktestConfig
    ) -> None:
        engine = BacktestEngine(clock=FixedClock(DEFAULT_START + timedelta(days=200)))
        result = engine.run(
            config=config,
            bars={SYMBOL: bars},
            regime_services={SYMBOL: regime_service},
            strategy_service=make_strategy_service(),
            risk_service=make_risk_service(),
            run_id="test-run-1",
            git_commit="deadbeef",
        )
        assert isinstance(result, BacktestResult)
        assert result.symbols == (SYMBOL,)
        assert result.replay_run.run_id == "test-run-1"
        assert result.replay_run.git_commit == "deadbeef"
        assert result.replay_run.dataset == "test-engine"

    def test_pipeline_versions_include_every_upstream_package(
        self, bars: list[Bar], regime_service: RegimeService, config: BacktestConfig
    ) -> None:
        engine = BacktestEngine()
        result = engine.run(
            config=config,
            bars={SYMBOL: bars},
            regime_services={SYMBOL: regime_service},
            strategy_service=make_strategy_service(),
            risk_service=make_risk_service(),
            run_id="test-run-2",
            git_commit="cafef00d",
        )
        versions = result.replay_run.pipeline_versions
        for key in ("backtest", "features", "hmm", "strategy", "risk", "execution"):
            assert key in versions
        assert f"hmm_model_{SYMBOL}" in versions
        assert versions[f"hmm_model_{SYMBOL}"] == regime_service.model_version

    def test_result_round_trips_through_dict(
        self, bars: list[Bar], regime_service: RegimeService, config: BacktestConfig
    ) -> None:
        engine = BacktestEngine()
        result = engine.run(
            config=config,
            bars={SYMBOL: bars},
            regime_services={SYMBOL: regime_service},
            strategy_service=make_strategy_service(),
            risk_service=make_risk_service(),
            run_id="test-run-3",
            git_commit="abc123",
        )
        assert BacktestResult.from_dict(result.to_dict()) == result

    def test_generate_report_produces_readable_text(
        self, bars: list[Bar], regime_service: RegimeService, config: BacktestConfig
    ) -> None:
        engine = BacktestEngine()
        result = engine.run(
            config=config,
            bars={SYMBOL: bars},
            regime_services={SYMBOL: regime_service},
            strategy_service=make_strategy_service(),
            risk_service=make_risk_service(),
            run_id="test-run-4",
            git_commit="abc123",
        )
        report = generate_report(result)
        assert "Backtest Report" in report
        assert "test-run-4" in report
        assert SYMBOL in report


class TestCurrentGitCommit:
    def test_returns_a_real_commit_hash_in_this_repository(self) -> None:
        commit = current_git_commit()
        assert len(commit) == 40
        assert all(c in "0123456789abcdef" for c in commit)

    def test_raises_backtest_error_when_git_is_unavailable(self) -> None:
        with (
            patch("subprocess.run", side_effect=OSError("git not found")),
            pytest.raises(BacktestError, match="git rev-parse HEAD"),
        ):
            current_git_commit()
