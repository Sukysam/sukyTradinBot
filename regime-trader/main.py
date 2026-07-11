"""Execution loop orchestration (Spec Sec. 6).

Runs three concurrent, independent pipelines under one asyncio event loop:

1. 5-Minute Structural Loop: OHLCV history -> features -> HMM forward pass ->
   3-bar stability filter -> strategy target -> risk veto -> order execution.
2. Event-Driven News Listener: Alpaca News WebSocket -> Sentiment Engine ->
   Catalyst Strategy evaluation, independent of the 5-minute cadence.
3. Weekend Cron: `learning_engine.py` runs weekly optimization over the past
   week's closed trades.

Known gaps, surfaced deliberately rather than papered over: this file depends
on three pieces that do not exist yet anywhere in this codebase --
`broker/alpaca_client.py` (historical bar fetching), `core/signal_generator.py`
+ `core/regime_strategies.py` (turning HMM probabilities into a trade
decision), and a trained-HMM-model store (persistence/refresh for
`hmm_engine.GaussianHMM` fits is not specified anywhere in the spec). Each is
represented below as a narrow injected interface (`MarketDataProvider`,
`SignalGenerator`, `ModelStore`) so wiring in the real implementation later
needs no changes to this file -- the same pattern `OrderExecutor` already
uses for `TradingClient`. Running `main()` today with the placeholder wiring
at the bottom will raise `NotImplementedError` loudly the moment the
structural loop actually needs one of them, rather than failing silently or
trading on fabricated logic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal as signal_module
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional, Protocol

import numpy as np
import pandas as pd
from alpaca.trading.client import TradingClient

from broker.news_streamer import NewsItem, NewsStreamer
from broker.order_executor import OrderExecutor
from core.hmm_engine import ForwardFilter
from core.learning_engine import LearningEngine
from core.risk_manager import PortfolioState, Position, ProposedTrade, evaluate_circuit_breakers, evaluate_trade
from core.sentiment_engine import SentimentEngine, SentimentScore
from data.feature_engineering import build_feature_matrix

logger = logging.getLogger(__name__)

STRUCTURAL_LOOP_INTERVAL_SECONDS = 5 * 60
STABILITY_PERSISTENCE_BARS = 3
WEEKEND_CRON_CHECK_INTERVAL_SECONDS = 3600
FEATURE_HISTORY_LOOKBACK_DAYS = 400  # >252 z-score window + warmup buffer
CORRELATION_HISTORY_LOOKBACK_DAYS = 90
Z_SCORE_SUFFIX = "_z"

TRADE_CONTEXT_DB_PATH = Path("data/trade_context_db.json")
LEARNING_WEIGHTS_PATH = Path("data/learning_weights.json")
EQUITY_STATE_PATH = Path("data/equity_tracker_state.json")


# --------------------------------------------------------------------------
# Interfaces for components not yet built. See module docstring.
# --------------------------------------------------------------------------

class MarketDataProvider(Protocol):
    """Satisfied by `broker/alpaca_client.py` once built."""

    def get_ohlcv_history(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        """Ascending-time-indexed OHLCV DataFrame with columns
        ['open','high','low','close','volume'], matching what
        `feature_engineering.build_feature_matrix` expects."""
        ...


class ModelStore(Protocol):
    """Satisfied by whatever owns training/persisting `hmm_engine` models --
    not specified anywhere in the spec's Sec. 6 pipelines, so this file
    cannot assume where a fitted model per ticker comes from."""

    def get_model(self, ticker: str):  # -> hmmlearn.hmm.GaussianHMM
        ...


@dataclass(frozen=True)
class TradeDecision:
    """What `signal_generator.py` must hand back for main.py to act on."""

    ticker: str
    sector: str
    strategy: str
    regime_label: str
    rsi_14: float
    notional_value: float
    entry_price: float
    stop_price: float
    take_profit_price: float | None = None


class SignalGenerator(Protocol):
    """Satisfied by `core/signal_generator.py` (+ `core/regime_strategies.py`),
    which owns the HMM-probabilities -> regime tier -> allocation logic of
    Spec Sec. 3, and the trade_context_db.json entry snapshot of Spec Sec. 4.
    """

    def evaluate_bar(
        self, ticker: str, filtered_probs: np.ndarray, feature_row: pd.Series
    ) -> Optional[TradeDecision]:
        ...

    def evaluate_catalyst(
        self, news: NewsItem, sentiment: SentimentScore, filtered_probs: Optional[np.ndarray]
    ) -> Optional[TradeDecision]:
        ...


# --------------------------------------------------------------------------
# Stability filter (Spec Sec. 6: "3-bar persistence")
# --------------------------------------------------------------------------

class StabilityFilter:
    """Only emits a regime state once the same argmax state has held for
    `persistence_bars` consecutive forward-filter updates, so a single noisy
    bar can't flip the strategy target back and forth.
    """

    def __init__(self, persistence_bars: int = STABILITY_PERSISTENCE_BARS):
        self._persistence_bars = persistence_bars
        self._recent_states: list[int] = []

    def update(self, filtered_probs: np.ndarray) -> Optional[int]:
        state = int(np.argmax(filtered_probs))
        self._recent_states = (self._recent_states + [state])[-self._persistence_bars:]
        if len(self._recent_states) < self._persistence_bars:
            return None
        if len(set(self._recent_states)) == 1:
            return state
        return None


# --------------------------------------------------------------------------
# Equity baseline tracking
#
# Alpaca's account object already gives us the daily baseline for free
# (`last_equity` = prior trading day's close), but weekly-start and
# all-time-peak equity aren't exposed anywhere by the API, so this app has to
# remember them itself, durably, across restarts.
# --------------------------------------------------------------------------

def _iso_week_marker(as_of: datetime) -> str:
    year, week, _ = as_of.isocalendar()
    return f"{year}-W{week:02d}"


@dataclass
class EquityTracker:
    state_path: Path
    equity_start_of_week: float
    equity_peak: float
    _week_marker: str

    @classmethod
    def load_or_init(cls, state_path: Path, current_equity: float, as_of: datetime) -> "EquityTracker":
        if state_path.exists():
            raw = json.loads(state_path.read_text())
            tracker = cls(
                state_path=state_path,
                equity_start_of_week=raw["equity_start_of_week"],
                equity_peak=raw["equity_peak"],
                _week_marker=raw["week_marker"],
            )
        else:
            tracker = cls(
                state_path=state_path,
                equity_start_of_week=current_equity,
                equity_peak=current_equity,
                _week_marker=_iso_week_marker(as_of),
            )
        tracker.update(current_equity, as_of)
        return tracker

    def update(self, current_equity: float, as_of: datetime) -> None:
        if current_equity > self.equity_peak:
            self.equity_peak = current_equity
        week_marker = _iso_week_marker(as_of)
        if week_marker != self._week_marker:
            self.equity_start_of_week = current_equity
            self._week_marker = week_marker
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({
            "equity_start_of_week": self.equity_start_of_week,
            "equity_peak": self.equity_peak,
            "week_marker": self._week_marker,
        }))


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------

class RegimeTraderApp:
    def __init__(
        self,
        tickers: list[str],
        sectors: dict[str, str],
        trading_client: TradingClient,
        market_data: MarketDataProvider,
        model_store: ModelStore,
        signal_generator: SignalGenerator,
        order_executor: OrderExecutor,
        sentiment_engine: SentimentEngine,
        learning_engine: LearningEngine,
        news_streamer_factory: Callable[[Callable[[NewsItem], Awaitable[None]]], NewsStreamer],
        trade_context_db_path: Path = TRADE_CONTEXT_DB_PATH,
        equity_state_path: Path = EQUITY_STATE_PATH,
        structural_loop_interval_seconds: int = STRUCTURAL_LOOP_INTERVAL_SECONDS,
    ):
        self.tickers = tickers
        self.sectors = sectors
        self.trading_client = trading_client
        self.market_data = market_data
        self.model_store = model_store
        self.signal_generator = signal_generator
        self.order_executor = order_executor
        self.sentiment_engine = sentiment_engine
        self.learning_engine = learning_engine
        self.news_streamer_factory = news_streamer_factory
        self.trade_context_db_path = trade_context_db_path
        self.equity_state_path = equity_state_path
        self.structural_loop_interval_seconds = structural_loop_interval_seconds

        self._forward_filters: dict[str, ForwardFilter] = {}
        self._stability_filters: dict[str, StabilityFilter] = {t: StabilityFilter() for t in tickers}
        self._last_filtered_probs: dict[str, np.ndarray] = {}
        self._equity_tracker: Optional[EquityTracker] = None
        self._last_weekly_run_marker: str = ""
        # Not constructed here: asyncio.Event() binds to the running loop at
        # creation time on some Python versions, and __init__ runs before
        # asyncio.run() starts one (confirmed by a RuntimeError on 3.9).
        # `run()` always executes inside asyncio.run(), so it's created there.
        self._shutdown_event: Optional[asyncio.Event] = None

    # ---- shared: portfolio snapshot ----------------------------------

    def _build_portfolio_state(self, as_of: datetime) -> PortfolioState:
        account = self.trading_client.get_account()
        equity = float(account.equity)
        equity_start_of_day = float(account.last_equity)

        if self._equity_tracker is None:
            self._equity_tracker = EquityTracker.load_or_init(self.equity_state_path, equity, as_of)
        else:
            self._equity_tracker.update(equity, as_of)

        raw_positions = self.trading_client.get_all_positions()
        positions = tuple(
            Position(
                ticker=p.symbol,
                sector=self.sectors.get(p.symbol, "UNKNOWN"),
                market_value=float(p.market_value or 0.0),
            )
            for p in raw_positions
        )

        return PortfolioState(
            equity=equity,
            positions=positions,
            equity_start_of_day=equity_start_of_day,
            equity_start_of_week=self._equity_tracker.equity_start_of_week,
            equity_peak=self._equity_tracker.equity_peak,
        )

    # ---- shared: veto + submit -----------------------------------------

    async def _evaluate_and_submit(
        self,
        decision: TradeDecision,
        portfolio: PortfolioState,
        price_history_cache: dict[str, pd.Series],
    ) -> None:
        for held in portfolio.positions:
            if held.ticker not in price_history_cache:
                history = await asyncio.to_thread(
                    self.market_data.get_ohlcv_history, held.ticker, CORRELATION_HISTORY_LOOKBACK_DAYS
                )
                price_history_cache[held.ticker] = history["close"]

        trade = ProposedTrade(
            ticker=decision.ticker,
            sector=decision.sector,
            notional_value=decision.notional_value,
            entry_price=decision.entry_price,
            stop_price=decision.stop_price,
        )
        veto = evaluate_trade(trade, portfolio, price_history_cache)
        if not veto.approved:
            logger.info("Trade for %s vetoed: %s", decision.ticker, veto.reasons)
            return

        sized_notional = decision.notional_value * veto.size_multiplier
        result = self.order_executor.submit_entry_order(
            ticker=decision.ticker,
            notional_value=sized_notional,
            entry_price=decision.entry_price,
            stop_price=decision.stop_price,
            take_profit_price=decision.take_profit_price,
        )
        if not result.submitted:
            logger.warning("Order submission failed for %s: %s", decision.ticker, result.error)
            return

        logger.info(
            "Entered %s: strategy=%s regime=%s notional=%.2f (size_multiplier=%.2f)",
            decision.ticker, decision.strategy, decision.regime_label, sized_notional, veto.size_multiplier,
        )
        # NOTE: writing this entry to trade_context_db.json for the learning
        # loop (Spec Sec. 4) is signal_generator.py's stated responsibility.
        # It isn't duplicated here to avoid two writers racing on that file.

    # ---- pipeline 1: 5-minute structural loop --------------------------

    async def _process_ticker(self, ticker: str, portfolio: PortfolioState, price_history_cache: dict[str, pd.Series]) -> None:
        history = await asyncio.to_thread(self.market_data.get_ohlcv_history, ticker, FEATURE_HISTORY_LOOKBACK_DAYS)
        if history.empty:
            logger.warning("No OHLCV history returned for %s; skipping", ticker)
            return
        price_history_cache[ticker] = history["close"]

        features = build_feature_matrix(history)
        latest = features.iloc[-1]
        z_cols = [c for c in features.columns if c.endswith(Z_SCORE_SUFFIX)]
        if latest[z_cols].isna().any():
            logger.debug("%s: feature warmup incomplete, skipping this tick", ticker)
            return

        forward_filter = self._forward_filters.get(ticker)
        if forward_filter is None:
            model = self.model_store.get_model(ticker)
            forward_filter = ForwardFilter(model)
            self._forward_filters[ticker] = forward_filter

        filtered_probs = forward_filter.update(latest[z_cols].to_numpy(dtype=float))
        self._last_filtered_probs[ticker] = filtered_probs

        stable_state = self._stability_filters[ticker].update(filtered_probs)
        if stable_state is None:
            return

        decision = self.signal_generator.evaluate_bar(ticker, filtered_probs, latest)
        if decision is None:
            return

        await self._evaluate_and_submit(decision, portfolio, price_history_cache)

    async def _run_structural_tick(self, as_of: datetime) -> None:
        portfolio = await asyncio.to_thread(self._build_portfolio_state, as_of)

        breaker = evaluate_circuit_breakers(portfolio)
        if breaker.liquidate:
            logger.critical("Circuit breaker: %s -- %s", breaker.action.value, breaker.reasons)
            await asyncio.to_thread(self.order_executor.liquidate_all_positions)
            return

        price_history_cache: dict[str, pd.Series] = {}
        for ticker in self.tickers:
            try:
                await self._process_ticker(ticker, portfolio, price_history_cache)
            except Exception:
                logger.exception("Failed processing ticker %s this tick", ticker)

    async def _structural_loop(self) -> None:
        while not self._shutdown_event.is_set():
            started = datetime.now(timezone.utc)
            try:
                await self._run_structural_tick(started)
            except Exception:
                logger.exception("Structural loop tick failed; will retry next interval")

            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            sleep_for = max(0.0, self.structural_loop_interval_seconds - elapsed)
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=sleep_for)
            except asyncio.TimeoutError:
                pass

    # ---- pipeline 2: event-driven news listener ------------------------

    async def _on_news(self, news: NewsItem) -> None:
        relevant = [s for s in news.symbols if s in self.tickers]
        if not relevant:
            return

        try:
            sentiment = self.sentiment_engine.score(news.headline)
        except Exception:
            logger.exception("Sentiment scoring failed for headline: %s", news.headline)
            return

        for ticker in relevant:
            filtered_probs = self._last_filtered_probs.get(ticker)
            decision = self.signal_generator.evaluate_catalyst(news, sentiment, filtered_probs)
            if decision is None:
                continue
            portfolio = await asyncio.to_thread(self._build_portfolio_state, datetime.now(timezone.utc))
            await self._evaluate_and_submit(decision, portfolio, {})

    # ---- pipeline 3: weekend cron ---------------------------------------

    def _is_weekend_optimization_due(self, now: datetime) -> bool:
        """Saturday, once per ISO week. Checked hourly rather than scheduled
        precisely; the week-marker guard makes repeated checks idempotent, so
        an hourly poll is simpler than a real cron dependency and just as
        correct.
        """
        if now.weekday() != 5:
            return False
        return _iso_week_marker(now) != self._last_weekly_run_marker

    async def _weekend_cron_loop(self) -> None:
        while not self._shutdown_event.is_set():
            now = datetime.now(timezone.utc)
            if self._is_weekend_optimization_due(now):
                try:
                    report = await asyncio.to_thread(
                        self.learning_engine.run_weekly_optimization, self.trade_context_db_path, now
                    )
                    logger.info(
                        "Weekly optimization complete: %d updated, %d skipped, %d arms tracked",
                        report.trades_updated, report.trades_skipped, len(report.arm_snapshot),
                    )
                    self._last_weekly_run_marker = _iso_week_marker(now)
                except FileNotFoundError:
                    logger.warning("trade_context_db.json not found yet; skipping this week's optimization")

            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=WEEKEND_CRON_CHECK_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass

    # ---- lifecycle -------------------------------------------------------

    async def run(self) -> None:
        self._shutdown_event = asyncio.Event()
        news_stream = self.news_streamer_factory(self._on_news)

        tasks = [
            asyncio.create_task(self._structural_loop(), name="structural_loop"),
            asyncio.create_task(news_stream.start(), name="news_listener"),
            asyncio.create_task(self._weekend_cron_loop(), name="weekend_cron"),
        ]

        loop = asyncio.get_running_loop()
        for sig in (signal_module.SIGINT, signal_module.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.ensure_future(self._shutdown(news_stream)))
            except NotImplementedError:
                pass  # signal handlers aren't available on some platforms (e.g. Windows)

        await asyncio.gather(*tasks)

    async def _shutdown(self, news_stream: NewsStreamer) -> None:
        logger.info("Shutdown signal received, stopping pipelines...")
        self._shutdown_event.set()
        news_stream.stop()


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------

class _NotYetImplemented:
    """Placeholder for a dependency this codebase hasn't built yet. Raises
    immediately and loudly the first time the structural loop actually
    touches it, instead of failing silently or trading on fabricated logic.
    """

    def __init__(self, missing_component: str):
        self._missing_component = missing_component

    def __getattr__(self, _name: str):
        raise NotImplementedError(f"{self._missing_component} is not implemented yet.")


def _load_tickers() -> list[str]:
    raw = os.environ.get("REGIME_TRADER_TICKERS", "")
    tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
    if not tickers:
        raise RuntimeError(
            "Set REGIME_TRADER_TICKERS (comma-separated tickers) -- config/settings.yaml doesn't exist yet."
        )
    return tickers


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    api_key = os.environ["ALPACA_API_KEY"]
    secret_key = os.environ["ALPACA_SECRET_KEY"]
    paper = os.environ.get("ALPACA_PAPER", "true").lower() != "false"
    tickers = _load_tickers()

    trading_client = TradingClient(api_key=api_key, secret_key=secret_key, paper=paper)

    app = RegimeTraderApp(
        tickers=tickers,
        sectors={},  # TODO: populate from config/settings.yaml once it exists
        trading_client=trading_client,
        market_data=_NotYetImplemented("broker/alpaca_client.py (historical bar fetching)"),
        model_store=_NotYetImplemented("a trained-HMM-model store (persistence isn't specified in the spec)"),
        signal_generator=_NotYetImplemented("core/signal_generator.py + core/regime_strategies.py"),
        order_executor=OrderExecutor(trading_client),
        sentiment_engine=SentimentEngine(),
        learning_engine=LearningEngine(weights_path=LEARNING_WEIGHTS_PATH),
        news_streamer_factory=lambda on_news: NewsStreamer(
            on_news=on_news, api_key=api_key, secret_key=secret_key, symbols=tuple(tickers)
        ),
    )

    asyncio.run(app.run())


if __name__ == "__main__":
    main()
