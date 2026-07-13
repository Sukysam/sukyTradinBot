"""Tests for `risk.validators` -- boundary tests (just under / at / just
over) for every threshold, per 08_RISK_MANAGER.md's acceptance criteria.
"""

from __future__ import annotations

import pytest

from risk.models import Position
from risk.validators import (
    BuyingPowerValidator,
    GrossExposureValidator,
    LeverageValidator,
    LiquidityValidator,
    SectorExposureValidator,
    SingleTickerExposureValidator,
)
from tests.risk.conftest import make_account_state, make_portfolio_state, make_strategy_decision


class TestGrossExposureValidator:
    def test_just_under_limit_passes(self) -> None:
        # 79% projected, limit 80%
        decision = make_strategy_decision(allocation=0.09)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="X", sector="Tech", market_value=70_000.0),),
        )
        assert GrossExposureValidator().validate(decision, portfolio, make_account_state()) == ()

    def test_at_limit_passes(self) -> None:
        # exactly 80%
        decision = make_strategy_decision(allocation=0.10)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="X", sector="Tech", market_value=70_000.0),),
        )
        assert GrossExposureValidator().validate(decision, portfolio, make_account_state()) == ()

    def test_just_over_limit_rejects(self) -> None:
        decision = make_strategy_decision(allocation=0.11)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="X", sector="Tech", market_value=70_000.0),),
        )
        violations = GrossExposureValidator().validate(decision, portfolio, make_account_state())
        assert len(violations) == 1
        assert "gross exposure" in violations[0]

    def test_custom_threshold(self) -> None:
        decision = make_strategy_decision(allocation=0.5)
        portfolio = make_portfolio_state(equity=100_000.0)
        validator = GrossExposureValidator(max_gross_exposure_pct=0.40)
        assert validator.validate(decision, portfolio, make_account_state()) != ()

    def test_non_positive_equity_always_rejects(self) -> None:
        decision = make_strategy_decision(allocation=0.0)
        portfolio = make_portfolio_state(equity=0.0)
        assert GrossExposureValidator().validate(decision, portfolio, make_account_state()) != ()

    def test_name(self) -> None:
        assert GrossExposureValidator().name == "gross_exposure"


class TestLeverageValidator:
    def test_just_under_limit_passes(self) -> None:
        decision = make_strategy_decision(allocation=0.20)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="X", sector="Tech", market_value=104_000.0),),
        )
        assert LeverageValidator().validate(decision, portfolio, make_account_state()) == ()

    def test_just_over_limit_rejects(self) -> None:
        decision = make_strategy_decision(allocation=0.20)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="X", sector="Tech", market_value=106_000.0),),
        )
        violations = LeverageValidator().validate(decision, portfolio, make_account_state())
        assert len(violations) == 1
        assert "leverage" in violations[0]

    def test_name(self) -> None:
        assert LeverageValidator().name == "leverage"


class TestSingleTickerExposureValidator:
    def test_just_under_limit_passes(self) -> None:
        decision = make_strategy_decision(symbol="AAPL", allocation=0.04)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="AAPL", sector="Tech", market_value=10_000.0),),
        )
        validator = SingleTickerExposureValidator()
        assert validator.validate(decision, portfolio, make_account_state()) == ()

    def test_just_over_limit_rejects(self) -> None:
        decision = make_strategy_decision(symbol="AAPL", allocation=0.06)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="AAPL", sector="Tech", market_value=10_000.0),),
        )
        violations = SingleTickerExposureValidator().validate(
            decision, portfolio, make_account_state()
        )
        assert len(violations) == 1
        assert "AAPL" in violations[0]

    def test_ignores_other_tickers(self) -> None:
        decision = make_strategy_decision(symbol="AAPL", allocation=0.05)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="MSFT", sector="Tech", market_value=90_000.0),),
        )
        validator = SingleTickerExposureValidator()
        assert validator.validate(decision, portfolio, make_account_state()) == ()


class TestSectorExposureValidator:
    def test_just_under_limit_passes(self) -> None:
        decision = make_strategy_decision(symbol="AAPL", allocation=0.09)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="MSFT", sector="Tech", market_value=20_000.0),),
        )
        validator = SectorExposureValidator(sector_map={"AAPL": "Tech", "MSFT": "Tech"})
        assert validator.validate(decision, portfolio, make_account_state()) == ()

    def test_just_over_limit_rejects(self) -> None:
        decision = make_strategy_decision(symbol="AAPL", allocation=0.11)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="MSFT", sector="Tech", market_value=20_000.0),),
        )
        validator = SectorExposureValidator(sector_map={"AAPL": "Tech", "MSFT": "Tech"})
        violations = validator.validate(decision, portfolio, make_account_state())
        assert len(violations) == 1
        assert "Tech" in violations[0]

    def test_unmapped_symbol_skips_check(self) -> None:
        decision = make_strategy_decision(symbol="ZZZZ", allocation=0.9)
        portfolio = make_portfolio_state(equity=100_000.0)
        validator = SectorExposureValidator(sector_map={})
        assert validator.validate(decision, portfolio, make_account_state()) == ()


class TestBuyingPowerValidator:
    def test_just_under_available_passes(self) -> None:
        decision = make_strategy_decision(allocation=0.4)
        portfolio = make_portfolio_state(equity=100_000.0)
        account = make_account_state(buying_power=40_001.0)
        assert BuyingPowerValidator().validate(decision, portfolio, account) == ()

    def test_just_over_available_rejects(self) -> None:
        decision = make_strategy_decision(allocation=0.4)
        portfolio = make_portfolio_state(equity=100_000.0)
        account = make_account_state(buying_power=39_999.0)
        violations = BuyingPowerValidator().validate(decision, portfolio, account)
        assert len(violations) == 1
        assert "buying power" in violations[0]

    def test_exactly_at_limit_passes(self) -> None:
        decision = make_strategy_decision(allocation=0.4)
        portfolio = make_portfolio_state(equity=100_000.0)
        account = make_account_state(buying_power=40_000.0)
        assert BuyingPowerValidator().validate(decision, portfolio, account) == ()


class TestLiquidityValidatorPlaceholder:
    def test_raises_not_implemented(self) -> None:
        decision = make_strategy_decision()
        portfolio = make_portfolio_state()
        with pytest.raises(NotImplementedError):
            LiquidityValidator().validate(decision, portfolio, make_account_state())

    def test_name(self) -> None:
        assert LiquidityValidator().name == "liquidity"
