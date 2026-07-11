"""Isolated, state-free validation interceptor (Spec Sec. 5).

Every function here is a pure function of its explicit inputs -- a portfolio
snapshot, a proposed trade, and a price history -- with one deliberate
exception: the emergency hard-stop halt is read from and written to a lock
file on disk rather than held in memory. That is not an accident; it is the
whole point of the "requires manual file lock deletion" requirement -- the
halt must survive a process restart and can only be cleared by a human.

This module never talks to the broker and never mutates a portfolio. It
answers "is this trade allowed" or "what should happen to open positions right
now" and returns a decision; `signal_generator.py` / `order_executor.py` act
on it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd

from data.feature_engineering import log_returns

logger = logging.getLogger(__name__)

# --- Limits (Spec Sec. 5) ---
MAX_GROSS_EXPOSURE_PCT = 0.80
MAX_SINGLE_TICKER_PCT = 0.15
MAX_SECTOR_EXPOSURE_PCT = 0.30
MAX_PORTFOLIO_LEVERAGE = 1.25
MAX_RISK_PER_TRADE_PCT = 0.01

CORRELATION_WINDOW_DAYS = 60
CORRELATION_LIMIT = 0.85

DAILY_DRAWDOWN_SIZE_CUT_PCT = 0.02
DAILY_DRAWDOWN_HALT_PCT = 0.03
WEEKLY_DRAWDOWN_HALT_PCT = 0.07
PEAK_DRAWDOWN_EMERGENCY_PCT = 0.10
DAILY_DRAWDOWN_SIZE_CUT_MULTIPLIER = 0.50

DEFAULT_EMERGENCY_LOCK_PATH = Path("risk_manager.EMERGENCY_HALT.lock")


# --------------------------------------------------------------------------
# Snapshot inputs
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Position:
    ticker: str
    sector: str
    market_value: float


@dataclass(frozen=True)
class PortfolioState:
    equity: float
    positions: tuple[Position, ...]
    equity_start_of_day: float
    equity_start_of_week: float
    equity_peak: float

    @property
    def gross_exposure(self) -> float:
        return sum(p.market_value for p in self.positions)

    @property
    def gross_exposure_pct(self) -> float:
        """Also used as portfolio leverage -- see note in check_exposure_limits."""
        return self.gross_exposure / self.equity if self.equity > 0 else float("inf")

    @property
    def daily_drawdown_pct(self) -> float:
        return _drawdown_pct(self.equity_start_of_day, self.equity)

    @property
    def weekly_drawdown_pct(self) -> float:
        return _drawdown_pct(self.equity_start_of_week, self.equity)

    @property
    def peak_drawdown_pct(self) -> float:
        return _drawdown_pct(self.equity_peak, self.equity)


def _drawdown_pct(reference_equity: float, current_equity: float) -> float:
    if reference_equity <= 0:
        return 0.0
    return max(0.0, (reference_equity - current_equity) / reference_equity)


@dataclass(frozen=True)
class ProposedTrade:
    ticker: str
    sector: str
    notional_value: float
    entry_price: float
    stop_price: float

    @property
    def quantity(self) -> float:
        return self.notional_value / self.entry_price if self.entry_price > 0 else 0.0

    @property
    def dollar_risk(self) -> float:
        """$ lost if stopped out at stop_price, assuming the full notional
        fills at entry_price."""
        return self.quantity * abs(self.entry_price - self.stop_price)


# --------------------------------------------------------------------------
# Decisions
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class VetoDecision:
    approved: bool
    reasons: tuple[str, ...] = ()
    size_multiplier: float = 1.0


class CircuitBreakerAction(str, Enum):
    NONE = "none"
    CUT_SIZE_50 = "cut_size_50"
    HALT_DAY = "halt_day"
    HALT_WEEK = "halt_week"
    EMERGENCY_HARD_STOP = "emergency_hard_stop"


@dataclass(frozen=True)
class CircuitBreakerDecision:
    action: CircuitBreakerAction
    size_multiplier: float
    liquidate: bool
    reasons: tuple[str, ...] = ()


# --------------------------------------------------------------------------
# Emergency hard stop (disk-backed, deliberately not in-memory)
# --------------------------------------------------------------------------

def is_emergency_halted(lock_path: Path = DEFAULT_EMERGENCY_LOCK_PATH) -> bool:
    return lock_path.exists()


def trigger_emergency_hard_stop(
    portfolio: PortfolioState, lock_path: Path = DEFAULT_EMERGENCY_LOCK_PATH
) -> None:
    """Write the emergency halt lock file. Idempotent, and never overwrites or
    deletes an existing lock -- clearing it is a manual, human action by
    design (Spec Sec. 5).
    """
    if lock_path.exists():
        return
    lock_path.write_text(
        "EMERGENCY HARD STOP\n"
        f"peak_drawdown_pct={portfolio.peak_drawdown_pct:.4f}\n"
        f"equity_peak={portfolio.equity_peak:.2f}\n"
        f"equity={portfolio.equity:.2f}\n"
        "Delete this file manually to resume trading.\n"
    )
    logger.critical(
        "EMERGENCY HARD STOP triggered: peak drawdown %.2f%%. Lock written to %s",
        portfolio.peak_drawdown_pct * 100,
        lock_path,
    )


# --------------------------------------------------------------------------
# Circuit breakers
# --------------------------------------------------------------------------

def evaluate_circuit_breakers(
    portfolio: PortfolioState,
    lock_path: Path = DEFAULT_EMERGENCY_LOCK_PATH,
) -> CircuitBreakerDecision:
    """Evaluate PnL-based circuit breakers against the current snapshot.

    Checked most-severe first: the thresholds are not mutually exclusive (a
    >10% peak drawdown almost always also breaches the daily and weekly
    thresholds), and only the single most severe applicable action should be
    returned to the caller.
    """
    if is_emergency_halted(lock_path):
        return CircuitBreakerDecision(
            action=CircuitBreakerAction.EMERGENCY_HARD_STOP,
            size_multiplier=0.0,
            liquidate=True,
            reasons=("Emergency hard stop lock file present; manual deletion required to resume.",),
        )

    if portfolio.peak_drawdown_pct > PEAK_DRAWDOWN_EMERGENCY_PCT:
        trigger_emergency_hard_stop(portfolio, lock_path)
        return CircuitBreakerDecision(
            action=CircuitBreakerAction.EMERGENCY_HARD_STOP,
            size_multiplier=0.0,
            liquidate=True,
            reasons=(
                f"Peak drawdown {portfolio.peak_drawdown_pct:.2%} > "
                f"{PEAK_DRAWDOWN_EMERGENCY_PCT:.0%} emergency threshold.",
            ),
        )

    if portfolio.weekly_drawdown_pct > WEEKLY_DRAWDOWN_HALT_PCT:
        return CircuitBreakerDecision(
            action=CircuitBreakerAction.HALT_WEEK,
            size_multiplier=0.0,
            liquidate=True,
            reasons=(
                f"Weekly drawdown {portfolio.weekly_drawdown_pct:.2%} > "
                f"{WEEKLY_DRAWDOWN_HALT_PCT:.0%} weekly halt threshold.",
            ),
        )

    if portfolio.daily_drawdown_pct > DAILY_DRAWDOWN_HALT_PCT:
        return CircuitBreakerDecision(
            action=CircuitBreakerAction.HALT_DAY,
            size_multiplier=0.0,
            liquidate=True,
            reasons=(
                f"Daily drawdown {portfolio.daily_drawdown_pct:.2%} > "
                f"{DAILY_DRAWDOWN_HALT_PCT:.0%} daily halt threshold.",
            ),
        )

    if portfolio.daily_drawdown_pct > DAILY_DRAWDOWN_SIZE_CUT_PCT:
        return CircuitBreakerDecision(
            action=CircuitBreakerAction.CUT_SIZE_50,
            size_multiplier=DAILY_DRAWDOWN_SIZE_CUT_MULTIPLIER,
            liquidate=False,
            reasons=(
                f"Daily drawdown {portfolio.daily_drawdown_pct:.2%} > "
                f"{DAILY_DRAWDOWN_SIZE_CUT_PCT:.0%} size-cut threshold.",
            ),
        )

    return CircuitBreakerDecision(action=CircuitBreakerAction.NONE, size_multiplier=1.0, liquidate=False)


# --------------------------------------------------------------------------
# Exposure / concentration / per-trade risk limits
# --------------------------------------------------------------------------

def check_exposure_limits(trade: ProposedTrade, portfolio: PortfolioState) -> list[str]:
    """Gross exposure, single-ticker, sector, leverage, and per-trade risk caps.

    Gross exposure and portfolio leverage are computed from the same ratio
    (total position market value / equity) since the spec gives no separate
    formula for either. Because 80% < 125%, the gross-exposure cap is always
    the binding one of the two in practice.
    """
    equity = portfolio.equity
    if equity <= 0:
        return [f"Portfolio equity is non-positive ({equity}); rejecting all trades."]

    violations: list[str] = []

    projected_gross_pct = (portfolio.gross_exposure + trade.notional_value) / equity
    if projected_gross_pct > MAX_GROSS_EXPOSURE_PCT:
        violations.append(
            f"Projected gross exposure {projected_gross_pct:.2%} > {MAX_GROSS_EXPOSURE_PCT:.0%} limit."
        )
    if projected_gross_pct > MAX_PORTFOLIO_LEVERAGE:
        violations.append(
            f"Projected portfolio leverage {projected_gross_pct:.2f}x > {MAX_PORTFOLIO_LEVERAGE:.2f}x limit."
        )

    existing_ticker_value = sum(p.market_value for p in portfolio.positions if p.ticker == trade.ticker)
    projected_ticker_pct = (existing_ticker_value + trade.notional_value) / equity
    if projected_ticker_pct > MAX_SINGLE_TICKER_PCT:
        violations.append(
            f"Projected {trade.ticker} exposure {projected_ticker_pct:.2%} > "
            f"{MAX_SINGLE_TICKER_PCT:.0%} single-ticker limit."
        )

    existing_sector_value = sum(p.market_value for p in portfolio.positions if p.sector == trade.sector)
    projected_sector_pct = (existing_sector_value + trade.notional_value) / equity
    if projected_sector_pct > MAX_SECTOR_EXPOSURE_PCT:
        violations.append(
            f"Projected {trade.sector} sector exposure {projected_sector_pct:.2%} > "
            f"{MAX_SECTOR_EXPOSURE_PCT:.0%} sector limit."
        )

    if trade.stop_price != trade.entry_price:
        projected_risk_pct = trade.dollar_risk / equity
        if projected_risk_pct > MAX_RISK_PER_TRADE_PCT:
            violations.append(
                f"Trade risk {projected_risk_pct:.2%} of equity > "
                f"{MAX_RISK_PER_TRADE_PCT:.0%} max risk per trade."
            )

    return violations


def _trailing_correlation(a: pd.Series, b: pd.Series, window: int = CORRELATION_WINDOW_DAYS) -> float:
    """Pearson correlation of trailing `window`-day log returns. Reuses
    `feature_engineering.log_returns` so the correlation filter and the HMM
    feature matrix compute returns identically.
    """
    common_index = a.index.intersection(b.index)
    a, b = a.loc[common_index], b.loc[common_index]
    ra = log_returns(a, 1).tail(window)
    rb = log_returns(b, 1).tail(window)
    aligned = pd.concat([ra, rb], axis=1).dropna()

    if len(aligned) < window:
        logger.warning(
            "Correlation window has only %d/%d observations after alignment; result may be unstable",
            len(aligned), window,
        )
    if len(aligned) < 2:
        return 0.0
    return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))


def check_correlation_filter(
    trade: ProposedTrade,
    portfolio: PortfolioState,
    price_history: dict[str, pd.Series],
) -> list[str]:
    """Blocks the trade if 60-day rolling correlation with any existing
    position's returns exceeds CORRELATION_LIMIT."""
    if trade.ticker not in price_history:
        raise ValueError(f"No price history supplied for proposed ticker {trade.ticker!r}")

    violations: list[str] = []
    for position in portfolio.positions:
        if position.ticker == trade.ticker:
            continue
        if position.ticker not in price_history:
            logger.warning(
                "No price history for existing position %s; skipping correlation check", position.ticker
            )
            continue
        corr = _trailing_correlation(price_history[trade.ticker], price_history[position.ticker])
        if corr > CORRELATION_LIMIT:
            violations.append(
                f"{CORRELATION_WINDOW_DAYS}d correlation with existing position {position.ticker} "
                f"is {corr:.2f} > {CORRELATION_LIMIT:.2f} limit."
            )
    return violations


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def evaluate_trade(
    trade: ProposedTrade,
    portfolio: PortfolioState,
    price_history: dict[str, pd.Series],
    lock_path: Path = DEFAULT_EMERGENCY_LOCK_PATH,
) -> VetoDecision:
    """Single entry point for the veto layer.

    Pure given its inputs: the same trade + portfolio + price_history (and the
    same lock-file state on disk) always yields the same decision. Circuit
    breakers are checked first and short-circuit exposure/correlation checks
    entirely when they halt trading, since there is no point evaluating limits
    for a trade that will be rejected regardless.
    """
    breaker = evaluate_circuit_breakers(portfolio, lock_path)
    if breaker.action in (
        CircuitBreakerAction.EMERGENCY_HARD_STOP,
        CircuitBreakerAction.HALT_DAY,
        CircuitBreakerAction.HALT_WEEK,
    ):
        return VetoDecision(approved=False, reasons=breaker.reasons, size_multiplier=0.0)

    reasons = check_exposure_limits(trade, portfolio) + check_correlation_filter(trade, portfolio, price_history)
    if reasons:
        return VetoDecision(approved=False, reasons=tuple(reasons), size_multiplier=0.0)

    return VetoDecision(approved=True, reasons=(), size_multiplier=breaker.size_multiplier)
