"""Tests for `backtest.metrics` -- one class per grouped module, plus
`compute_metrics`'s aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backtest.metrics import compute_metrics, exposure, returns, risk, trade_quality
from backtest.models import EquityPoint, TradeRecord
from execution.models import OrderSide

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _curve(
    values: list[float], *, start: datetime = T0, step: timedelta = timedelta(days=1)
) -> tuple[EquityPoint, ...]:
    return tuple(EquityPoint(timestamp=start + i * step, equity=v) for i, v in enumerate(values))


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


class TestCagr:
    def test_doubling_in_one_year_is_100_pct(self) -> None:
        value = returns.cagr(100_000.0, 200_000.0, T0, T0 + timedelta(days=365))
        assert value == pytest.approx(1.0, abs=0.01)

    def test_zero_duration_returns_zero(self) -> None:
        assert returns.cagr(100_000.0, 200_000.0, T0, T0) == 0.0

    def test_loss_produces_negative_cagr(self) -> None:
        value = returns.cagr(100_000.0, 50_000.0, T0, T0 + timedelta(days=365))
        assert value < 0.0


class TestSharpeAndSortino:
    def test_flat_curve_has_zero_sharpe(self) -> None:
        curve = _curve([100_000.0] * 10)
        assert returns.sharpe_ratio(curve) == 0.0

    def test_flat_curve_has_zero_sortino(self) -> None:
        curve = _curve([100_000.0] * 10)
        assert returns.sortino_ratio(curve) == 0.0

    def test_single_point_curve_has_zero_sharpe(self) -> None:
        assert returns.sharpe_ratio(_curve([100_000.0])) == 0.0

    def test_rising_curve_has_positive_sharpe(self) -> None:
        curve = _curve([100_000.0 * (1.01**i) for i in range(20)])
        assert returns.sharpe_ratio(curve) > 0.0

    def test_sortino_ignores_upside_volatility(self) -> None:
        # All-positive returns of varying size -- no downside deviation
        # at all, so sortino's denominator is the degenerate 0.0 case.
        curve = _curve([100_000.0, 101_000.0, 105_000.0, 106_000.0, 112_000.0])
        assert returns.sortino_ratio(curve) == 0.0


class TestCalmarRatio:
    def test_zero_drawdown_is_infinite(self) -> None:
        assert returns.calmar_ratio(0.1, 0.0) == float("inf")

    def test_normal_case_divides_cagr_by_drawdown(self) -> None:
        assert returns.calmar_ratio(0.2, 0.1) == pytest.approx(2.0)


class TestMaxDrawdown:
    def test_no_decline_is_zero(self) -> None:
        curve = _curve([100.0, 110.0, 120.0])
        assert risk.max_drawdown(curve) == 0.0

    def test_simple_decline(self) -> None:
        curve = _curve([100.0, 50.0])
        assert risk.max_drawdown(curve) == pytest.approx(0.5)

    def test_recovers_after_decline_but_reports_the_worst_point(self) -> None:
        curve = _curve([100.0, 50.0, 200.0])
        assert risk.max_drawdown(curve) == pytest.approx(0.5)

    def test_empty_curve_is_zero(self) -> None:
        assert risk.max_drawdown(()) == 0.0


class TestWinRate:
    def test_no_trades_is_zero(self) -> None:
        assert trade_quality.win_rate(()) == 0.0

    def test_all_wins_is_one(self) -> None:
        trades = (_trade(pnl=10.0), _trade(pnl=20.0))
        assert trade_quality.win_rate(trades) == 1.0

    def test_mixed(self) -> None:
        trades = (_trade(pnl=10.0), _trade(pnl=-5.0), _trade(pnl=-1.0), _trade(pnl=1.0))
        assert trade_quality.win_rate(trades) == pytest.approx(0.5)


class TestProfitFactor:
    def test_no_trades_is_zero(self) -> None:
        assert trade_quality.profit_factor(()) == 0.0

    def test_no_losses_with_wins_is_infinite(self) -> None:
        trades = (_trade(pnl=10.0), _trade(pnl=20.0))
        assert trade_quality.profit_factor(trades) == float("inf")

    def test_normal_case(self) -> None:
        trades = (_trade(pnl=100.0), _trade(pnl=-50.0))
        assert trade_quality.profit_factor(trades) == pytest.approx(2.0)

    def test_all_losses_is_zero(self) -> None:
        trades = (_trade(pnl=-10.0), _trade(pnl=-20.0))
        assert trade_quality.profit_factor(trades) == 0.0


class TestAverageHoldingPeriod:
    def test_no_trades_is_zero(self) -> None:
        assert trade_quality.average_holding_period(()) == timedelta(0)

    def test_averages_across_trades(self) -> None:
        trades = (
            _trade(entry_timestamp=T0, exit_timestamp=T0 + timedelta(days=2)),
            _trade(entry_timestamp=T0, exit_timestamp=T0 + timedelta(days=8)),
        )
        assert trade_quality.average_holding_period(trades) == timedelta(days=5)


class TestExposure:
    def test_no_trades_is_zero(self) -> None:
        curve = _curve([100.0, 100.0, 100.0])
        assert exposure.exposure(curve, ()) == 0.0

    def test_fully_covered_period_is_one(self) -> None:
        curve = _curve([100.0, 101.0, 102.0])
        trades = (_trade(entry_timestamp=T0, exit_timestamp=T0 + timedelta(days=2)),)
        assert exposure.exposure(curve, trades) == pytest.approx(1.0)

    def test_partially_covered_period(self) -> None:
        curve = _curve([100.0, 101.0, 102.0, 103.0])  # T0..T0+3d
        trades = (_trade(entry_timestamp=T0, exit_timestamp=T0 + timedelta(days=1)),)
        assert exposure.exposure(curve, trades) == pytest.approx(0.5)


class TestTurnover:
    def test_no_trades_is_zero(self) -> None:
        curve = _curve([100_000.0, 100_000.0])
        assert exposure.turnover((), curve) == 0.0

    def test_computes_ratio_of_traded_notional_to_average_equity(self) -> None:
        curve = _curve([100_000.0, 100_000.0])
        trades = (_trade(entry_price=100.0, exit_price=110.0, quantity=100),)
        # traded notional = 100*100 + 110*100 = 21,000; avg equity = 100,000
        assert exposure.turnover(trades, curve) == pytest.approx(0.21)


class TestComputeMetrics:
    def test_returns_every_documented_key(self) -> None:
        curve = _curve([100_000.0, 101_000.0, 99_000.0, 105_000.0])
        trades = (_trade(),)
        result = compute_metrics(
            equity_curve=curve,
            trade_log=trades,
            initial_equity=100_000.0,
            start_date=T0,
            end_date=T0 + timedelta(days=365),
        )
        assert set(result) == {
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
        }
