"""Tests for `risk.circuit_breakers.DrawdownCircuitBreaker` -- most-severe-
first ordering and the disk-backed emergency lock file, matching
`core/risk_manager.py::evaluate_circuit_breakers`'s own behavior."""

from __future__ import annotations

from pathlib import Path

from risk.circuit_breakers import (
    CircuitBreakerAction,
    DrawdownCircuitBreaker,
    is_emergency_halted,
    trigger_emergency_hard_stop,
)
from tests.risk.conftest import make_portfolio_state


class TestNoBreach:
    def test_returns_none_action(self, tmp_path: Path) -> None:
        portfolio = make_portfolio_state(equity=100_000.0)
        result = DrawdownCircuitBreaker(lock_path=tmp_path / "lock").evaluate(portfolio)
        assert result.action is CircuitBreakerAction.NONE
        assert result.size_multiplier == 1.0
        assert not result.liquidate
        assert not result.halts_new_trades


class TestDailyDrawdownSizeCut:
    def test_just_under_threshold_no_action(self, tmp_path: Path) -> None:
        portfolio = make_portfolio_state(equity=98_010.0, equity_start_of_day=100_000.0)
        result = DrawdownCircuitBreaker(lock_path=tmp_path / "lock").evaluate(portfolio)
        assert result.action is CircuitBreakerAction.NONE

    def test_just_over_threshold_cuts_size(self, tmp_path: Path) -> None:
        portfolio = make_portfolio_state(equity=97_990.0, equity_start_of_day=100_000.0)
        result = DrawdownCircuitBreaker(lock_path=tmp_path / "lock").evaluate(portfolio)
        assert result.action is CircuitBreakerAction.CUT_SIZE_50
        assert result.size_multiplier == 0.5
        assert not result.liquidate
        assert not result.halts_new_trades


class TestDailyDrawdownHalt:
    def test_just_over_threshold_halts_day(self, tmp_path: Path) -> None:
        portfolio = make_portfolio_state(equity=96_990.0, equity_start_of_day=100_000.0)
        result = DrawdownCircuitBreaker(lock_path=tmp_path / "lock").evaluate(portfolio)
        assert result.action is CircuitBreakerAction.HALT_DAY
        assert result.size_multiplier == 0.0
        assert result.liquidate
        assert result.halts_new_trades


class TestWeeklyDrawdownHalt:
    def test_just_over_threshold_halts_week(self, tmp_path: Path) -> None:
        portfolio = make_portfolio_state(
            equity=92_990.0, equity_start_of_day=100_000.0, equity_start_of_week=100_000.0
        )
        result = DrawdownCircuitBreaker(lock_path=tmp_path / "lock").evaluate(portfolio)
        assert result.action is CircuitBreakerAction.HALT_WEEK
        assert result.halts_new_trades


class TestPeakDrawdownEmergency:
    def test_just_over_threshold_triggers_emergency_and_writes_lock(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock"
        portfolio = make_portfolio_state(
            equity=89_990.0,
            equity_start_of_day=100_000.0,
            equity_start_of_week=100_000.0,
            equity_peak=100_000.0,
        )
        result = DrawdownCircuitBreaker(lock_path=lock_path).evaluate(portfolio)
        assert result.action is CircuitBreakerAction.EMERGENCY_HARD_STOP
        assert result.halts_new_trades
        assert lock_path.exists()


class TestMostSevereFirst:
    def test_breach_of_all_tiers_returns_emergency_only(self, tmp_path: Path) -> None:
        portfolio = make_portfolio_state(
            equity=85_000.0,
            equity_start_of_day=100_000.0,
            equity_start_of_week=100_000.0,
            equity_peak=100_000.0,
        )
        result = DrawdownCircuitBreaker(lock_path=tmp_path / "lock").evaluate(portfolio)
        assert result.action is CircuitBreakerAction.EMERGENCY_HARD_STOP
        assert len(result.reasons) == 1


class TestEmergencyLockFile:
    def test_is_emergency_halted_false_when_absent(self, tmp_path: Path) -> None:
        assert not is_emergency_halted(tmp_path / "lock")

    def test_is_emergency_halted_true_once_written(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock"
        portfolio = make_portfolio_state(equity=100_000.0, equity_peak=100_000.0)
        trigger_emergency_hard_stop(portfolio, lock_path)
        assert is_emergency_halted(lock_path)

    def test_trigger_is_idempotent_never_overwrites(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock"
        portfolio = make_portfolio_state(equity=100_000.0, equity_peak=100_000.0)
        trigger_emergency_hard_stop(portfolio, lock_path)
        original_content = lock_path.read_text()
        different_portfolio = make_portfolio_state(equity=1.0, equity_peak=100_000.0)
        trigger_emergency_hard_stop(different_portfolio, lock_path)
        assert lock_path.read_text() == original_content

    def test_present_lock_forces_emergency_regardless_of_drawdown(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "lock"
        lock_path.write_text("halted")
        portfolio = make_portfolio_state(equity=100_000.0)
        result = DrawdownCircuitBreaker(lock_path=lock_path).evaluate(portfolio)
        assert result.action is CircuitBreakerAction.EMERGENCY_HARD_STOP


class TestName:
    def test_name(self) -> None:
        assert DrawdownCircuitBreaker().name == "drawdown_circuit_breaker"
