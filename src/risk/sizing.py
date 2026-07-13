"""Reduce-only `SizingRule` implementations.

Distinct from `validators.py`: a validator either passes a decision
unchanged or rejects it outright; a `SizingRule` instead reduces how much
of a decision's requested allocation actually fits within remaining
capacity, without rejecting anything itself. `risk.service.RiskService`
only runs sizing rules against decisions that already passed every
`RiskValidator` -- sizing never has to decide whether to reject, only how
much room is left.

`ExposureCapacitySizing` has no equivalent in the legacy
`core/risk_manager.py`, which only ever binary-rejects a trade that
breaches a cap. This is a genuine, new design contribution for this
milestone -- see ADR-011.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from risk.limits import (
    MAX_GROSS_EXPOSURE_PCT,
    MAX_SECTOR_EXPOSURE_PCT,
    MAX_SINGLE_TICKER_PCT,
)
from risk.models import AccountState, PortfolioState
from strategy.models import StrategyDecision


def _headroom(cap_pct: float, existing_value: float, equity: float) -> float:
    """Remaining allocation-fraction headroom under `cap_pct`, given how
    much of that cap is already used by `existing_value`. `0.0` (never
    negative) if the cap is already met or breached, and `cap_pct` itself
    if nothing is committed against it yet. Non-positive equity has no
    usable headroom."""
    if equity <= 0:
        return 0.0
    return max(0.0, cap_pct - existing_value / equity)


@dataclass(frozen=True)
class ExposureCapacitySizing:
    """Reduces (never increases) a decision's allocation to fit within
    remaining headroom under the gross-exposure, single-ticker, and (when
    `sector_map` provides one) sector caps -- computed independently of
    whether a `RiskValidator` would also reject the unsized request, so a
    decision that would breach a cap at full size can still execute at
    whatever size actually fits.
    """

    sector_map: Mapping[str, str] = field(default_factory=dict)
    max_gross_exposure_pct: float = MAX_GROSS_EXPOSURE_PCT
    max_single_ticker_pct: float = MAX_SINGLE_TICKER_PCT
    max_sector_exposure_pct: float = MAX_SECTOR_EXPOSURE_PCT

    @property
    def name(self) -> str:
        return "exposure_capacity_sizing"

    def apply(
        self,
        decision: StrategyDecision,
        requested_allocation: float,
        portfolio: PortfolioState,
        account: AccountState,
    ) -> float:
        headrooms = [
            requested_allocation,
            _headroom(self.max_gross_exposure_pct, portfolio.gross_exposure, portfolio.equity),
            _headroom(
                self.max_single_ticker_pct,
                sum(p.market_value for p in portfolio.positions if p.ticker == decision.symbol),
                portfolio.equity,
            ),
        ]
        sector = self.sector_map.get(decision.symbol)
        if sector is not None:
            headrooms.append(
                _headroom(
                    self.max_sector_exposure_pct,
                    sum(p.market_value for p in portfolio.positions if p.sector == sector),
                    portfolio.equity,
                )
            )
        return min(headrooms)


__all__ = ["ExposureCapacitySizing"]
