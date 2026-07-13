"""`run_replay` -- Phase A of Milestone 8: deterministic replay of
historical bars through the *entire* real decision pipeline (Features ->
HMM -> Strategy -> Risk -> Execution), producing a trade log and equity
curve. No metrics, no `BacktestResult` -- see `engine.py` for Phase B,
which layers those on top.

Causality (invariant #1, no look-ahead): at replay step `t`, every
decision is made using only feature/regime data computed from bars
strictly before `t` (indices `< t`). The resulting `OrderIntent` fills
at bar `t`'s own open -- the next real price after the information the
decision was based on, never the same bar's close. Equity is marked at
bar `t`'s close, after that step's fills. See ADR-015.

All symbols are replayed in lockstep, one calendar timestamp at a time,
so portfolio-level risk checks (gross exposure, sector concentration)
see every symbol's current state together -- never one symbol fully
replayed before the next begins. This requires every symbol's bars to
share exactly the same timestamps; `InsufficientReplayHistoryError` is
raised otherwise, not silently misaligned.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from backtest.config import BacktestConfig
from backtest.exceptions import InsufficientReplayHistoryError
from backtest.interfaces import FillModel
from backtest.models import EquityPoint, TradeRecord
from backtest.portfolio import PortfolioEngine
from execution.models import ExecutionContext, FeatureSnapshot, OrderIntent, OrderSide
from execution.order_builder import OrderBuilder
from execution.stop_loss import ATRStopPolicy
from features.pipeline import FeaturePipeline
from hmm.service import RegimeService
from market_data.models import Bar
from risk.service import RiskService
from strategy.service import StrategyService

DEFAULT_TICK_SIZE = 0.01
_EXECUTION_FEATURE_NAMES = ("atr_14", "realized_volatility_20")


@dataclass(frozen=True)
class NextBarOpenFillModel:
    """The only `FillModel` this milestone ships: fills exactly at the
    bar's own open, no slippage. See module docstring for why this bar
    (not the one the decision was based on) is the correct one."""

    @property
    def name(self) -> str:
        return "next_bar_open"

    def fill_price(self, intent: OrderIntent, next_bar: Bar) -> float:
        del intent  # unused: this model always fills at the bar's open
        return next_bar.open


@dataclass(frozen=True)
class ReplayResult:
    """Internal, unfrozen Phase A output -- `engine.py` consumes this to
    build the frozen `BacktestResult` (Phase B)."""

    trade_log: tuple[TradeRecord, ...]
    equity_curve: tuple[EquityPoint, ...]


def _aligned_timestamps(bars: Mapping[str, Sequence[Bar]]) -> list[datetime]:
    timestamp_sets = {symbol: [b.timestamp for b in series] for symbol, series in bars.items()}
    reference_symbol = next(iter(timestamp_sets))
    reference = timestamp_sets[reference_symbol]
    for symbol, timestamps in timestamp_sets.items():
        if timestamps != reference:
            raise InsufficientReplayHistoryError(
                f"{symbol!r}'s bar timestamps do not match {reference_symbol!r}'s -- "
                "lockstep multi-symbol replay requires every symbol's bars to share "
                "exactly the same timestamps"
            )
    return reference


def run_replay(
    config: BacktestConfig,
    bars: Mapping[str, Sequence[Bar]],
    regime_services: Mapping[str, RegimeService],
    strategy_service: StrategyService,
    risk_service: RiskService,
    fill_model: FillModel | None = None,
) -> ReplayResult:
    fill_model = fill_model or NextBarOpenFillModel()
    pipeline = FeaturePipeline()
    portfolio = PortfolioEngine(cash=config.initial_equity)
    order_builder = OrderBuilder(stop_loss_policy=ATRStopPolicy())

    timestamps = _aligned_timestamps(bars)
    try:
        replay_start_index = next(i for i, ts in enumerate(timestamps) if ts >= config.start_date)
    except StopIteration as exc:
        raise InsufficientReplayHistoryError(
            f"no bars at or after start_date {config.start_date.isoformat()}"
        ) from exc
    if replay_start_index < config.feature_lookback_bars:
        raise InsufficientReplayHistoryError(
            f"need >= {config.feature_lookback_bars} bars of history before start_date, "
            f"got {replay_start_index}"
        )

    trade_log: list[TradeRecord] = []
    # Seeded with equity as of the close just before any replay decision
    # is made -- no fills have happened yet, so this is exactly
    # `config.initial_equity`. Required so `BacktestResult.equity_curve[0]
    # .equity == initial_equity` (Standards/BacktestResult Contract.md)
    # holds even when a trade fills on the very first replayed bar.
    equity_curve: list[EquityPoint] = [
        EquityPoint(timestamp=timestamps[replay_start_index - 1], equity=config.initial_equity)
    ]

    for t in range(replay_start_index, len(timestamps)):
        timestamp = timestamps[t]
        if timestamp > config.end_date:
            break

        prior_close_prices = {symbol: series[t - 1].close for symbol, series in bars.items()}
        portfolio.on_new_bar(timestamp, prior_close_prices)

        for symbol in config.symbols:
            series = bars[symbol]
            window = series[max(0, t - config.feature_lookback_bars) : t]
            regime_service = regime_services[symbol]
            feature_names = tuple(set(regime_service.feature_names) | set(_EXECUTION_FEATURE_NAMES))

            raw_vectors, _diagnostics = pipeline.compute_series(
                window, symbol, feature_names=feature_names, source_dataset=config.dataset
            )
            # `compute_series` restarts each feature's own lookback warm-up
            # from this window's first bar, not the underlying series'
            # true start -- the leading rows are expected to carry NaN
            # until warm-up completes. `infer_series` requires every row
            # it's given to be complete (see its docstring), so only the
            # warmed-up suffix is passed through, never the whole window.
            vectors = [v for v in raw_vectors if not any(math.isnan(x) for x in v.feature_values)]
            if not vectors:
                continue
            latest_vector = vectors[-1]
            regime_state = regime_service.infer(vectors)
            strategy_decision = strategy_service.decide(latest_vector, regime_state)

            portfolio_snapshot = portfolio.snapshot(
                prior_close_prices, sector_map=config.sector_map
            )
            account_state = portfolio.account_state()
            execution_decision = risk_service.decide(
                strategy_decision, portfolio_snapshot, account_state
            )
            if not execution_decision.approved:
                continue

            context = ExecutionContext(
                symbol=symbol,
                timestamp=series[t - 1].timestamp,
                reference_price=series[t - 1].close,
                bid=None,
                ask=None,
                spread=None,
                tick_size=DEFAULT_TICK_SIZE,
                price_source="bar_close",
            )
            feature_snapshot = FeatureSnapshot(
                symbol=symbol,
                timestamp=series[t - 1].timestamp,
                atr_14=latest_vector.get("atr_14"),
                realized_volatility_20=latest_vector.get("realized_volatility_20"),
            )
            intent = order_builder.build(
                execution_decision, portfolio_snapshot, context, feature_snapshot
            )
            if intent is None:
                continue

            fill_price = fill_model.fill_price(intent, series[t])
            if intent.side is OrderSide.BUY:
                portfolio.open_or_add(
                    symbol=symbol,
                    sector=config.sector_map.get(symbol, ""),
                    strategy_id=strategy_decision.strategy_id,
                    regime_id=regime_state.regime_id,
                    timestamp=timestamp,
                    fill_price=fill_price,
                    quantity=intent.quantity,
                )
            else:
                trade = portfolio.reduce_or_close(
                    symbol=symbol,
                    timestamp=timestamp,
                    fill_price=fill_price,
                    quantity=intent.quantity,
                )
                trade_log.append(trade)

        closing_prices = {symbol: series[t].close for symbol, series in bars.items()}
        equity_curve.append(
            EquityPoint(timestamp=timestamp, equity=portfolio.equity(closing_prices))
        )

    return ReplayResult(trade_log=tuple(trade_log), equity_curve=tuple(equity_curve))


__all__ = ["NextBarOpenFillModel", "ReplayResult", "run_replay"]
