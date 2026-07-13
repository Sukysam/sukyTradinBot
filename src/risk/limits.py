"""Named risk-limit constants.

Ported 1:1 from `regime-trader/core/risk_manager.py`'s module-level
constants and documented in
[Standards/Risk Limits Reference.md](../../docs/engineering-handbook/Standards/Risk%20Limits%20Reference.md).
Kept in their own module, separate from `validators.py`'s logic, so this
file alone is the audit trail for "what are the actual limit values today"
-- per [08_RISK_MANAGER.md](../../docs/engineering-handbook/08_RISK_MANAGER.md),
changing any of these is an escalation, not a routine edit.
"""

from __future__ import annotations

# --- Exposure / concentration / leverage / per-trade risk ---
MAX_GROSS_EXPOSURE_PCT = 0.80
MAX_SINGLE_TICKER_PCT = 0.15
MAX_SECTOR_EXPOSURE_PCT = 0.30
MAX_PORTFOLIO_LEVERAGE = 1.25

# --- Circuit breakers (most severe first when evaluated) ---
DAILY_DRAWDOWN_SIZE_CUT_PCT = 0.02
DAILY_DRAWDOWN_HALT_PCT = 0.03
WEEKLY_DRAWDOWN_HALT_PCT = 0.07
PEAK_DRAWDOWN_EMERGENCY_PCT = 0.10
DAILY_DRAWDOWN_SIZE_CUT_MULTIPLIER = 0.50

__all__ = [
    "DAILY_DRAWDOWN_HALT_PCT",
    "DAILY_DRAWDOWN_SIZE_CUT_MULTIPLIER",
    "DAILY_DRAWDOWN_SIZE_CUT_PCT",
    "MAX_GROSS_EXPOSURE_PCT",
    "MAX_PORTFOLIO_LEVERAGE",
    "MAX_SECTOR_EXPOSURE_PCT",
    "MAX_SINGLE_TICKER_PCT",
    "PEAK_DRAWDOWN_EMERGENCY_PCT",
    "WEEKLY_DRAWDOWN_HALT_PCT",
]
