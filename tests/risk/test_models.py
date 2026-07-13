"""Tests for `risk.models`: `Position`, `PortfolioState`, `AccountState`,
`DecisionType`, and `ExecutionDecision`'s construction-time invariants."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from risk.models import AccountState, DecisionType, ExecutionDecision, Position
from strategy.models import StrategyDecision
from tests.risk.conftest import make_portfolio_state, make_strategy_decision

UTC = timezone.utc


def _decision(**overrides: object) -> ExecutionDecision:
    strategy_decision = overrides.pop("strategy_reference", None) or make_strategy_decision(
        allocation=0.5
    )
    assert isinstance(strategy_decision, StrategyDecision)
    defaults: dict[str, object] = {
        "timestamp": strategy_decision.timestamp,
        "symbol": strategy_decision.symbol,
        "approved": True,
        "approved_allocation": strategy_decision.allocation,
        "decision_type": DecisionType.APPROVED,
        "risk_adjustments": (),
        "reasoning": "Approved at full size; no limits binding.",
        "strategy_reference": strategy_decision,
        "metadata": {},
    }
    defaults.update(overrides)
    return ExecutionDecision(**defaults)  # type: ignore[arg-type]


class TestPosition:
    def test_rejects_empty_ticker(self) -> None:
        with pytest.raises(ValueError, match="ticker"):
            Position(ticker="", sector="Tech", market_value=100.0)

    def test_rejects_negative_market_value(self) -> None:
        with pytest.raises(ValueError, match="market_value"):
            Position(ticker="AAPL", sector="Tech", market_value=-1.0)


class TestPortfolioState:
    def test_gross_exposure_sums_positions(self) -> None:
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(
                Position(ticker="AAPL", sector="Tech", market_value=10_000.0),
                Position(ticker="MSFT", sector="Tech", market_value=5_000.0),
            ),
        )
        assert portfolio.gross_exposure == 15_000.0
        assert portfolio.gross_exposure_pct == pytest.approx(0.15)

    def test_gross_exposure_pct_is_inf_for_non_positive_equity(self) -> None:
        portfolio = make_portfolio_state(equity=0.0)
        assert portfolio.gross_exposure_pct == float("inf")

    def test_daily_drawdown_pct(self) -> None:
        portfolio = make_portfolio_state(equity=95_000.0, equity_start_of_day=100_000.0)
        assert portfolio.daily_drawdown_pct == pytest.approx(0.05)

    def test_drawdown_pct_never_negative_on_gains(self) -> None:
        portfolio = make_portfolio_state(equity=110_000.0, equity_start_of_day=100_000.0)
        assert portfolio.daily_drawdown_pct == 0.0

    def test_peak_drawdown_pct(self) -> None:
        portfolio = make_portfolio_state(equity=90_000.0, equity_peak=100_000.0)
        assert portfolio.peak_drawdown_pct == pytest.approx(0.10)

    def test_drawdown_pct_is_zero_for_non_positive_reference_equity(self) -> None:
        portfolio = make_portfolio_state(equity=50_000.0, equity_start_of_day=0.0)
        assert portfolio.daily_drawdown_pct == 0.0


class TestAccountState:
    def test_rejects_negative_buying_power(self) -> None:
        with pytest.raises(ValueError, match="buying_power"):
            AccountState(buying_power=-1.0)

    def test_accepts_zero_buying_power(self) -> None:
        AccountState(buying_power=0.0)


class TestExecutionDecisionRequiredFields:
    def test_construction_succeeds_with_defaults(self) -> None:
        decision = _decision()
        assert decision.approved is True
        assert decision.decision_type is DecisionType.APPROVED

    def test_timestamp_must_be_utc(self) -> None:
        strategy_decision = make_strategy_decision()
        naive = strategy_decision.timestamp.replace(tzinfo=None)
        with pytest.raises(ValueError, match="timezone-aware"):
            _decision(
                timestamp=naive,
                strategy_reference=strategy_decision,
            )

    def test_symbol_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="symbol"):
            _decision(symbol="")

    def test_symbol_must_match_strategy_reference(self) -> None:
        with pytest.raises(ValueError, match="symbol"):
            _decision(symbol="OTHER")

    def test_timestamp_must_match_strategy_reference(self) -> None:
        with pytest.raises(ValueError, match="timestamp"):
            _decision(timestamp=datetime(2025, 1, 1, tzinfo=UTC))


class TestApprovedAllocationBound:
    def test_cannot_exceed_strategy_reference_allocation(self) -> None:
        strategy_decision = make_strategy_decision(allocation=0.5)
        with pytest.raises(ValueError, match="approved_allocation"):
            _decision(
                strategy_reference=strategy_decision,
                approved_allocation=0.6,
                decision_type=DecisionType.APPROVED,
            )

    def test_cannot_be_negative(self) -> None:
        strategy_decision = make_strategy_decision(allocation=0.5)
        with pytest.raises(ValueError, match="approved_allocation"):
            _decision(
                strategy_reference=strategy_decision,
                approved_allocation=-0.1,
                decision_type=DecisionType.REJECTED,
                approved=False,
                risk_adjustments=("x",),
            )

    def test_equal_to_strategy_reference_allocation_is_valid(self) -> None:
        strategy_decision = make_strategy_decision(allocation=0.5)
        decision = _decision(
            strategy_reference=strategy_decision,
            approved_allocation=0.5,
            decision_type=DecisionType.APPROVED,
        )
        assert decision.approved_allocation == 0.5


class TestRejectionInvariants:
    def test_not_approved_requires_zero_allocation(self) -> None:
        with pytest.raises(ValueError, match=r"approved_allocation must be 0\.0"):
            _decision(
                approved=False,
                approved_allocation=0.1,
                decision_type=DecisionType.REJECTED,
                risk_adjustments=("some violation",),
            )

    def test_not_approved_requires_non_empty_risk_adjustments(self) -> None:
        with pytest.raises(ValueError, match="risk_adjustments"):
            _decision(
                approved=False,
                approved_allocation=0.0,
                decision_type=DecisionType.REJECTED,
                risk_adjustments=(),
            )

    def test_rejected_with_reasons_is_valid(self) -> None:
        decision = _decision(
            approved=False,
            approved_allocation=0.0,
            decision_type=DecisionType.REJECTED,
            risk_adjustments=("gross_exposure: too big",),
            reasoning="Rejected: gross_exposure: too big",
        )
        assert decision.decision_type is DecisionType.REJECTED


class TestReducedInvariants:
    def test_reduced_allocation_requires_non_empty_risk_adjustments(self) -> None:
        strategy_decision = make_strategy_decision(allocation=0.5)
        with pytest.raises(ValueError, match="risk_adjustments"):
            _decision(
                strategy_reference=strategy_decision,
                approved_allocation=0.3,
                decision_type=DecisionType.REDUCED,
                risk_adjustments=(),
            )

    def test_reduced_with_reasons_is_valid(self) -> None:
        strategy_decision = make_strategy_decision(allocation=0.5)
        decision = _decision(
            strategy_reference=strategy_decision,
            approved_allocation=0.3,
            decision_type=DecisionType.REDUCED,
            risk_adjustments=("sizing: reduced",),
            reasoning="Approved at reduced size (0.3 of 0.5 requested) due to: sizing: reduced",
        )
        assert decision.decision_type is DecisionType.REDUCED


class TestReasoning:
    def test_cannot_be_empty(self) -> None:
        with pytest.raises(ValueError, match="reasoning"):
            _decision(reasoning="")

    def test_cannot_be_whitespace_only(self) -> None:
        with pytest.raises(ValueError, match="reasoning"):
            _decision(reasoning="   \n\t")


class TestDecisionTypeConsistency:
    def test_approved_requires_decision_type_approved_or_reduced(self) -> None:
        with pytest.raises(ValueError, match="decision_type"):
            _decision(approved=True, decision_type=DecisionType.REJECTED)

    def test_rejected_requires_decision_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="decision_type"):
            _decision(
                approved=False,
                approved_allocation=0.0,
                decision_type=DecisionType.APPROVED,
                risk_adjustments=("x",),
            )

    def test_reduced_requires_decision_type_reduced_not_approved(self) -> None:
        strategy_decision = make_strategy_decision(allocation=0.5)
        with pytest.raises(ValueError, match="decision_type"):
            _decision(
                strategy_reference=strategy_decision,
                approved_allocation=0.3,
                decision_type=DecisionType.APPROVED,
                risk_adjustments=("sizing: reduced",),
            )

    def test_clean_approval_forbids_risk_adjustments(self) -> None:
        with pytest.raises(ValueError, match="risk_adjustments must be empty"):
            _decision(
                decision_type=DecisionType.APPROVED,
                risk_adjustments=("unexpected note",),
            )


class TestSerializationRoundTrip:
    def test_decision_round_trips_through_dict(self) -> None:
        decision = _decision(metadata={"note": "value"})
        assert ExecutionDecision.from_dict(decision.to_dict()) == decision

    def test_to_dict_is_json_serializable(self) -> None:
        import json

        json.dumps(_decision().to_dict())

    def test_rejected_decision_round_trips(self) -> None:
        decision = _decision(
            approved=False,
            approved_allocation=0.0,
            decision_type=DecisionType.REJECTED,
            risk_adjustments=("gross_exposure: too big",),
            reasoning="Rejected: gross_exposure: too big",
        )
        assert ExecutionDecision.from_dict(decision.to_dict()) == decision
