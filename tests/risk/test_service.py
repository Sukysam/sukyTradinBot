"""Tests for `risk.service.RiskService` -- the full validators -> sizing ->
circuit breakers -> `ExecutionDecision` pipeline."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from risk.circuit_breakers import DrawdownCircuitBreaker
from risk.config import RiskServiceConfig
from risk.exceptions import InvalidSizingResultError
from risk.models import DecisionType, Position
from risk.service import RiskService
from risk.validators import (
    BuyingPowerValidator,
    GrossExposureValidator,
    LeverageValidator,
    SectorExposureValidator,
    SingleTickerExposureValidator,
)
from tests.risk.conftest import make_account_state, make_portfolio_state, make_strategy_decision


def _with_lock_path(service: RiskService, tmp_path: Path) -> RiskService:
    """`RiskService.default()` uses the real default lock-file path;
    tests need an isolated one per test so they never touch a real
    filesystem lock file (see Standards/Coding Standards.md's "any test
    touching a filesystem path uses a temp-directory override")."""
    return replace(service, circuit_breaker=DrawdownCircuitBreaker(lock_path=tmp_path / "lock"))


class TestApprovalPath:
    def test_clean_decision_is_approved_at_full_size(self, tmp_path: Path) -> None:
        service = _with_lock_path(RiskService.default(), tmp_path)
        decision = make_strategy_decision(allocation=0.1)
        portfolio = make_portfolio_state(equity=100_000.0)
        result = service.decide(decision, portfolio, make_account_state())

        assert result.approved is True
        assert result.decision_type is DecisionType.APPROVED
        assert result.approved_allocation == decision.allocation
        assert result.risk_adjustments == ()
        assert "full size" in result.reasoning

    def test_zero_allocation_decision_is_a_clean_approval(self, tmp_path: Path) -> None:
        service = _with_lock_path(RiskService.default(), tmp_path)
        decision = make_strategy_decision(allocation=0.0)
        portfolio = make_portfolio_state(equity=100_000.0)
        result = service.decide(decision, portfolio, make_account_state())

        assert result.approved is True
        assert result.decision_type is DecisionType.APPROVED
        assert result.approved_allocation == 0.0


class TestRejectionPath:
    def test_gross_exposure_violation_rejects_under_a_strict_validator_policy(
        self, tmp_path: Path
    ) -> None:
        # RiskService.default() prefers ExposureCapacitySizing's graceful
        # reduction for this concern (see RiskService.default's docstring)
        # -- a caller wanting a hard zero-tolerance policy instead wires
        # GrossExposureValidator in explicitly.
        service = RiskService(
            validators=(GrossExposureValidator(),),
            sizing_rules=(),
            circuit_breaker=DrawdownCircuitBreaker(lock_path=tmp_path / "lock"),
        )
        decision = make_strategy_decision(allocation=0.9)
        portfolio = make_portfolio_state(equity=100_000.0)
        result = service.decide(decision, portfolio, make_account_state())

        assert result.approved is False
        assert result.decision_type is DecisionType.REJECTED
        assert result.approved_allocation == 0.0
        assert any("gross_exposure" in r for r in result.risk_adjustments)
        assert result.reasoning.startswith("Rejected:")

    def test_buying_power_violation_rejects(self, tmp_path: Path) -> None:
        service = _with_lock_path(RiskService.default(), tmp_path)
        decision = make_strategy_decision(allocation=0.5)
        portfolio = make_portfolio_state(equity=100_000.0)
        account = make_account_state(buying_power=1_000.0)
        result = service.decide(decision, portfolio, account)

        assert result.approved is False
        assert any("buying_power" in r for r in result.risk_adjustments)


class TestMultipleSimultaneousViolations:
    def test_all_violated_validators_are_reported(self, tmp_path: Path) -> None:
        # Explicitly wires every validator (the strict, zero-tolerance
        # policy) to demonstrate a single proposed decision can breach
        # several independent concerns at once, and every one is reported
        # -- not just the first found.
        service = RiskService(
            validators=(
                GrossExposureValidator(),
                LeverageValidator(),
                SingleTickerExposureValidator(),
                SectorExposureValidator(sector_map={"AAPL": "Tech"}),
                BuyingPowerValidator(),
            ),
            sizing_rules=(),
            circuit_breaker=DrawdownCircuitBreaker(lock_path=tmp_path / "lock"),
        )
        decision = make_strategy_decision(symbol="AAPL", allocation=0.9)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="AAPL", sector="Tech", market_value=5_000.0),),
        )
        account = make_account_state(buying_power=1_000.0)
        result = service.decide(decision, portfolio, account)

        assert result.approved is False
        fired = {adj.split(":")[0] for adj in result.risk_adjustments}
        assert "gross_exposure" in fired
        assert "leverage" not in fired  # 95% > 80% but < 125%, doesn't fire independently
        assert "single_ticker_exposure" in fired
        assert "sector_exposure" in fired
        assert "buying_power" in fired
        assert len(result.risk_adjustments) >= 4


class TestAllocationReduction:
    def test_sizing_reduces_allocation_and_records_adjustment(self, tmp_path: Path) -> None:
        service = _with_lock_path(RiskService.default(), tmp_path)
        decision = make_strategy_decision(allocation=0.5)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="X", sector="Tech", market_value=75_000.0),),
        )
        result = service.decide(decision, portfolio, make_account_state())

        assert result.approved is True
        assert result.decision_type is DecisionType.REDUCED
        assert result.approved_allocation == pytest.approx(0.05)
        assert any("exposure_capacity_sizing" in r for r in result.risk_adjustments)
        assert "reduced size" in result.reasoning

    def test_reduced_allocation_never_exceeds_requested(self, tmp_path: Path) -> None:
        service = _with_lock_path(RiskService.default(), tmp_path)
        decision = make_strategy_decision(allocation=1.0)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="X", sector="Tech", market_value=50_000.0),),
        )
        result = service.decide(decision, portfolio, make_account_state())
        assert result.approved_allocation <= decision.allocation


class TestCircuitBreakerActivation:
    def test_size_cut_breaker_reduces_an_otherwise_clean_approval(self, tmp_path: Path) -> None:
        service = _with_lock_path(RiskService.default(), tmp_path)
        decision = make_strategy_decision(allocation=0.1)
        portfolio = make_portfolio_state(equity=97_990.0, equity_start_of_day=100_000.0)
        result = service.decide(decision, portfolio, make_account_state())

        assert result.approved is True
        assert result.decision_type is DecisionType.REDUCED
        assert result.approved_allocation == pytest.approx(0.05)
        assert any("drawdown_circuit_breaker" in r for r in result.risk_adjustments)

    def test_halt_breaker_rejects_an_otherwise_clean_decision(self, tmp_path: Path) -> None:
        service = _with_lock_path(RiskService.default(), tmp_path)
        decision = make_strategy_decision(allocation=0.1)
        portfolio = make_portfolio_state(equity=96_990.0, equity_start_of_day=100_000.0)
        result = service.decide(decision, portfolio, make_account_state())

        assert result.approved is False
        assert result.decision_type is DecisionType.REJECTED
        assert any("drawdown_circuit_breaker" in r for r in result.risk_adjustments)

    def test_emergency_halt_overrides_validator_rejection_reasons_too(self, tmp_path: Path) -> None:
        service = RiskService(
            validators=(GrossExposureValidator(),),
            sizing_rules=(),
            circuit_breaker=DrawdownCircuitBreaker(lock_path=tmp_path / "lock"),
        )
        # A decision that would also fail gross exposure on its own.
        decision = make_strategy_decision(allocation=0.9)
        portfolio = make_portfolio_state(
            equity=89_990.0,
            equity_start_of_day=100_000.0,
            equity_start_of_week=100_000.0,
            equity_peak=100_000.0,
        )
        result = service.decide(decision, portfolio, make_account_state())

        assert result.approved is False
        assert result.approved_allocation == 0.0
        assert any("gross_exposure" in r for r in result.risk_adjustments)
        assert any("drawdown_circuit_breaker" in r for r in result.risk_adjustments)


class TestDeterminism:
    def test_identical_inputs_produce_identical_output(self, tmp_path: Path) -> None:
        service = _with_lock_path(RiskService.default(), tmp_path)
        decision = make_strategy_decision(allocation=0.3)
        portfolio = make_portfolio_state(equity=100_000.0)
        account = make_account_state()

        results = [service.decide(decision, portfolio, account) for _ in range(5)]
        assert all(r == results[0] for r in results)


class TestValidatorComposition:
    def test_custom_validator_set_is_respected(self, tmp_path: Path) -> None:
        service = RiskService(
            validators=(GrossExposureValidator(max_gross_exposure_pct=0.10),),
            sizing_rules=(),
            circuit_breaker=DrawdownCircuitBreaker(lock_path=tmp_path / "lock"),
        )
        decision = make_strategy_decision(allocation=0.2)
        portfolio = make_portfolio_state(equity=100_000.0)
        result = service.decide(decision, portfolio, make_account_state())
        assert result.approved is False

    def test_empty_validator_set_never_rejects_on_exposure(self, tmp_path: Path) -> None:
        service = RiskService(
            validators=(),
            sizing_rules=(),
            circuit_breaker=DrawdownCircuitBreaker(lock_path=tmp_path / "lock"),
        )
        decision = make_strategy_decision(allocation=1.0)
        portfolio = make_portfolio_state(equity=100_000.0)
        result = service.decide(decision, portfolio, make_account_state())
        assert result.approved is True
        assert result.approved_allocation == 1.0

    def test_default_factory_wires_buying_power_validator_and_exposure_sizing(
        self, tmp_path: Path
    ) -> None:
        # See RiskService.default's docstring: the four exposure/leverage/
        # concentration validators are deliberately excluded from the
        # default policy since ExposureCapacitySizing already covers the
        # same concerns via graceful reduction.
        service = _with_lock_path(RiskService.default(), tmp_path)
        assert {v.name for v in service.validators} == {"buying_power"}
        assert {r.name for r in service.sizing_rules} == {"exposure_capacity_sizing"}


class TestInvalidSizingResult:
    def test_sizing_rule_that_increases_allocation_raises(self, tmp_path: Path) -> None:
        @dataclass(frozen=True)
        class _BrokenSizing:
            @property
            def name(self) -> str:
                return "broken"

            def apply(
                self,
                decision: object,
                requested_allocation: float,
                portfolio: object,
                account: object,
            ) -> float:
                return requested_allocation + 0.5

        service = RiskService(
            validators=(),
            sizing_rules=(_BrokenSizing(),),
            circuit_breaker=DrawdownCircuitBreaker(lock_path=tmp_path / "lock"),
        )
        decision = make_strategy_decision(allocation=0.1)
        portfolio = make_portfolio_state(equity=100_000.0)
        with pytest.raises(InvalidSizingResultError):
            service.decide(decision, portfolio, make_account_state())


class TestSectorHeadroomIntegration:
    def test_sector_map_flows_through_default_factory(self, tmp_path: Path) -> None:
        service = _with_lock_path(
            RiskService.default(RiskServiceConfig(sector_map={"AAPL": "Tech"})), tmp_path
        )
        decision = make_strategy_decision(symbol="AAPL", allocation=0.5)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="MSFT", sector="Tech", market_value=25_000.0),),
        )
        result = service.decide(decision, portfolio, make_account_state())
        assert result.decision_type is DecisionType.REDUCED
        assert result.approved_allocation == pytest.approx(0.05)
