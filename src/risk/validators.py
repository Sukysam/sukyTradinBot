"""Small, composable `RiskValidator` implementations -- each evaluates
exactly one concern against a single proposed `StrategyDecision`.

Grounded in `regime-trader/core/risk_manager.py::check_exposure_limits`
where a legacy equivalent exists (gross exposure, leverage, single-ticker,
sector); `BuyingPowerValidator` is net new, since `AccountState` has no
legacy precedent. `check_exposure_limits`'s per-trade dollar-risk check
and `check_correlation_filter` are deliberately not ported here -- both
need data (`entry_price`/`stop_price`, a rolling return history) that
isn't part of any input `RiskService.decide` receives in this milestone
(`StrategyDecision` carries an allocation fraction, not prices; no price
history is threaded through the pipeline). See ADR-011's Consequences for
why this is a scoped deferral, not an oversight.

`StrategyDecision.allocation` is a fraction of the strategy's allocatable
capital (see `Standards/StrategyDecision Contract.md`); every validator
here treats `PortfolioState.equity` as that allocatable capital, so a
decision's projected notional is `decision.allocation * portfolio.equity`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from risk.limits import (
    MAX_GROSS_EXPOSURE_PCT,
    MAX_PORTFOLIO_LEVERAGE,
    MAX_SECTOR_EXPOSURE_PCT,
    MAX_SINGLE_TICKER_PCT,
)
from risk.models import AccountState, PortfolioState
from strategy.models import StrategyDecision


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Mirrors `PortfolioState.gross_exposure_pct`'s own non-positive-
    equity convention: a ratio against non-positive equity is `inf`, so it
    always fails whatever limit it's compared against rather than raising
    or silently passing."""
    return numerator / denominator if denominator > 0 else float("inf")


def _projected_notional(decision: StrategyDecision, portfolio: PortfolioState) -> float:
    return decision.allocation * portfolio.equity


@dataclass(frozen=True)
class GrossExposureValidator:
    """Total book exposure after this decision, vs. equity."""

    max_gross_exposure_pct: float = MAX_GROSS_EXPOSURE_PCT

    @property
    def name(self) -> str:
        return "gross_exposure"

    def validate(
        self, decision: StrategyDecision, portfolio: PortfolioState, account: AccountState
    ) -> tuple[str, ...]:
        notional = _projected_notional(decision, portfolio)
        projected_pct = _safe_ratio(portfolio.gross_exposure + notional, portfolio.equity)
        if projected_pct > self.max_gross_exposure_pct:
            return (
                f"Projected gross exposure {projected_pct:.2%} > "
                f"{self.max_gross_exposure_pct:.0%} limit.",
            )
        return ()


@dataclass(frozen=True)
class LeverageValidator:
    """Same ratio `GrossExposureValidator` computes, checked against the
    portfolio leverage cap -- a distinct concern with its own limit, per
    `08_RISK_MANAGER.md`'s "Must escalate" note that gross exposure and
    leverage must stay two independently configurable limits even though
    they share a formula today."""

    max_leverage: float = MAX_PORTFOLIO_LEVERAGE

    @property
    def name(self) -> str:
        return "leverage"

    def validate(
        self, decision: StrategyDecision, portfolio: PortfolioState, account: AccountState
    ) -> tuple[str, ...]:
        notional = _projected_notional(decision, portfolio)
        projected_ratio = _safe_ratio(portfolio.gross_exposure + notional, portfolio.equity)
        if projected_ratio > self.max_leverage:
            return (
                f"Projected portfolio leverage {projected_ratio:.2f}x > "
                f"{self.max_leverage:.2f}x limit.",
            )
        return ()


@dataclass(frozen=True)
class SingleTickerExposureValidator:
    """Concentration in the specific symbol this decision proposes."""

    max_single_ticker_pct: float = MAX_SINGLE_TICKER_PCT

    @property
    def name(self) -> str:
        return "single_ticker_exposure"

    def validate(
        self, decision: StrategyDecision, portfolio: PortfolioState, account: AccountState
    ) -> tuple[str, ...]:
        notional = _projected_notional(decision, portfolio)
        existing = sum(p.market_value for p in portfolio.positions if p.ticker == decision.symbol)
        projected_pct = _safe_ratio(existing + notional, portfolio.equity)
        if projected_pct > self.max_single_ticker_pct:
            return (
                f"Projected {decision.symbol} exposure {projected_pct:.2%} > "
                f"{self.max_single_ticker_pct:.0%} single-ticker limit.",
            )
        return ()


@dataclass(frozen=True)
class SectorExposureValidator:
    """Concentration in the proposed symbol's sector.

    `sector_map` is caller-supplied (there is no sector field anywhere in
    `StrategyDecision`/`PortfolioState`). A symbol missing from the map
    skips this check rather than fabricating a sector -- the same
    documented no-op behavior `Architecture/Known Gaps.md` item 1 already
    describes for `main.py`'s own empty `sectors={}` today, not new,
    undocumented behavior invented here.
    """

    sector_map: Mapping[str, str]
    max_sector_exposure_pct: float = MAX_SECTOR_EXPOSURE_PCT

    @property
    def name(self) -> str:
        return "sector_exposure"

    def validate(
        self, decision: StrategyDecision, portfolio: PortfolioState, account: AccountState
    ) -> tuple[str, ...]:
        sector = self.sector_map.get(decision.symbol)
        if sector is None:
            return ()
        notional = _projected_notional(decision, portfolio)
        existing = sum(p.market_value for p in portfolio.positions if p.sector == sector)
        projected_pct = _safe_ratio(existing + notional, portfolio.equity)
        if projected_pct > self.max_sector_exposure_pct:
            return (
                f"Projected {sector} sector exposure {projected_pct:.2%} > "
                f"{self.max_sector_exposure_pct:.0%} sector limit.",
            )
        return ()


@dataclass(frozen=True)
class BuyingPowerValidator:
    """Net new -- no legacy precedent, since `AccountState` didn't exist
    before this milestone. Rejects a decision whose projected notional
    exceeds the account's available buying power."""

    @property
    def name(self) -> str:
        return "buying_power"

    def validate(
        self, decision: StrategyDecision, portfolio: PortfolioState, account: AccountState
    ) -> tuple[str, ...]:
        notional = _projected_notional(decision, portfolio)
        if notional > account.buying_power:
            return (
                f"Projected notional ${notional:,.2f} > available buying power "
                f"${account.buying_power:,.2f}.",
            )
        return ()


@dataclass(frozen=True)
class LiquidityValidator:
    """Not yet implemented -- deliberately, not silently.

    A real liquidity check (average daily volume, bid-ask spread) needs
    market-depth data that isn't part of any input `RiskService.decide`
    receives today: `StrategyDecision`, `PortfolioState`, and
    `AccountState` carry no volume or spread information whatsoever.
    Wiring in a check without that data would mean fabricating a
    plausible-looking pass/fail from nothing -- exactly what
    [00_MASTER_CHARTER.md](../../docs/engineering-handbook/00_MASTER_CHARTER.md)
    invariant #4 rules out ("a stub that quietly no-ops or fabricates a
    plausible-looking result"). Raises `NotImplementedError` on first use
    instead, matching `main.py`'s own `_NotYetImplemented` placeholder
    pattern -- a caller that registers this validator gets a loud failure,
    not a false sense of coverage. Do not register it with `RiskService`
    until real market-depth data is threaded into this package's inputs.
    """

    @property
    def name(self) -> str:
        return "liquidity"

    def validate(
        self, decision: StrategyDecision, portfolio: PortfolioState, account: AccountState
    ) -> tuple[str, ...]:
        raise NotImplementedError(
            "LiquidityValidator has no real implementation yet -- no volume/spread "
            "data is available in RiskService.decide's inputs. Do not register this "
            "validator with RiskService until real market-depth data is wired in."
        )


__all__ = [
    "BuyingPowerValidator",
    "GrossExposureValidator",
    "LeverageValidator",
    "LiquidityValidator",
    "SectorExposureValidator",
    "SingleTickerExposureValidator",
]
