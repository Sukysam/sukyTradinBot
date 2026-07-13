"""Tests for `backtest.replay.run_replay` -- Phase A: deterministic
replay through the entire real decision pipeline to a trade log. No
metrics, no `BacktestResult` involved here; see `test_engine.py` for
Phase B."""

from __future__ import annotations

from datetime import timedelta

import pytest

from backtest.config import BacktestConfig
from backtest.exceptions import InsufficientReplayHistoryError
from backtest.replay import NextBarOpenFillModel, run_replay
from execution.models import OrderSide
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


def _config(**overrides: object) -> BacktestConfig:
    defaults: dict[str, object] = {
        "symbols": (SYMBOL,),
        "start_date": DEFAULT_START + timedelta(days=110),
        "end_date": DEFAULT_START + timedelta(days=149),
        "initial_equity": 100_000.0,
        "feature_lookback_bars": 60,
        "dataset": "test",
    }
    defaults.update(overrides)
    return BacktestConfig(**defaults)  # type: ignore[arg-type]


class TestDeterminism:
    """The single most important property Phase A must prove, per the
    technical lead's explicit two-phase instruction: replay first,
    metrics later, and replay must be deterministic before anything is
    built on top of it."""

    def test_two_identical_runs_produce_identical_trade_logs_and_equity_curves(
        self, bars: list[Bar], regime_service: RegimeService
    ) -> None:
        strategy_service = make_strategy_service()
        risk_service = make_risk_service()
        config = _config()

        first = run_replay(
            config=config,
            bars={SYMBOL: bars},
            regime_services={SYMBOL: regime_service},
            strategy_service=strategy_service,
            risk_service=risk_service,
        )
        second = run_replay(
            config=config,
            bars={SYMBOL: bars},
            regime_services={SYMBOL: regime_service},
            strategy_service=strategy_service,
            risk_service=risk_service,
        )

        assert first.trade_log == second.trade_log
        assert first.equity_curve == second.equity_curve


class TestReplayBasics:
    def test_equity_curve_starts_at_initial_equity(
        self, bars: list[Bar], regime_service: RegimeService
    ) -> None:
        config = _config(initial_equity=50_000.0)

        result = run_replay(
            config=config,
            bars={SYMBOL: bars},
            regime_services={SYMBOL: regime_service},
            strategy_service=make_strategy_service(),
            risk_service=make_risk_service(),
        )

        # Seeded before any fill happens -- required by
        # Standards/BacktestResult Contract.md's equity_curve[0].equity
        # == initial_equity invariant, which a trade filling on the very
        # first replayed bar would otherwise violate.
        assert result.equity_curve[0].equity == config.initial_equity
        assert result.equity_curve[0].timestamp < config.start_date

    def test_equity_curve_is_strictly_ascending_by_timestamp(
        self, bars: list[Bar], regime_service: RegimeService
    ) -> None:
        result = run_replay(
            config=_config(),
            bars={SYMBOL: bars},
            regime_services={SYMBOL: regime_service},
            strategy_service=make_strategy_service(),
            risk_service=make_risk_service(),
        )
        timestamps = [p.timestamp for p in result.equity_curve]
        assert timestamps == sorted(set(timestamps))

    def test_trade_log_is_ascending_by_exit_timestamp(
        self, bars: list[Bar], regime_service: RegimeService
    ) -> None:
        result = run_replay(
            config=_config(),
            bars={SYMBOL: bars},
            regime_services={SYMBOL: regime_service},
            strategy_service=make_strategy_service(),
            risk_service=make_risk_service(),
        )
        exits = [t.exit_timestamp for t in result.trade_log]
        assert exits == sorted(exits)

    def test_every_trade_side_is_buy(self, bars: list[Bar], regime_service: RegimeService) -> None:
        # TradeRecord.side always records the entry side -- long-only
        # (invariant #5), matching Standards/BacktestResult Contract.md.
        result = run_replay(
            config=_config(),
            bars={SYMBOL: bars},
            regime_services={SYMBOL: regime_service},
            strategy_service=make_strategy_service(),
            risk_service=make_risk_service(),
        )
        assert all(t.side is OrderSide.BUY for t in result.trade_log)


class TestInsufficientHistory:
    def test_raises_when_not_enough_bars_before_start_date(
        self, bars: list[Bar], regime_service: RegimeService
    ) -> None:
        config = _config(
            start_date=DEFAULT_START + timedelta(days=10),
            end_date=DEFAULT_START + timedelta(days=20),
            feature_lookback_bars=60,
        )
        with pytest.raises(InsufficientReplayHistoryError, match="bars of history"):
            run_replay(
                config=config,
                bars={SYMBOL: bars},
                regime_services={SYMBOL: regime_service},
                strategy_service=make_strategy_service(),
                risk_service=make_risk_service(),
            )

    def test_raises_when_symbols_bars_are_misaligned(
        self, bars: list[Bar], regime_service: RegimeService
    ) -> None:
        bars_b = make_bars(140, symbol="B")  # different length -> misaligned timestamps
        config = _config(symbols=("A", "B"))
        with pytest.raises(InsufficientReplayHistoryError, match="do not match"):
            run_replay(
                config=config,
                bars={"A": bars, "B": bars_b},
                regime_services={"A": regime_service, "B": regime_service},
                strategy_service=make_strategy_service(),
                risk_service=make_risk_service(),
            )


class TestNextBarOpenFillModel:
    def test_fill_price_is_the_bars_open(self, bars: list[Bar]) -> None:
        model = NextBarOpenFillModel()
        assert model.fill_price(intent=object(), next_bar=bars[1]) == bars[1].open  # type: ignore[arg-type]

    def test_name_is_stable(self) -> None:
        assert NextBarOpenFillModel().name == "next_bar_open"
