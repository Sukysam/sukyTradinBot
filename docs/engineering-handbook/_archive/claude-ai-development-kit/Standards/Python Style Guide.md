# Standard — Python Style Guide

Describes the conventions already consistently followed across
`regime-trader/`, so new code matches without needing a separate style
discussion each time.

## Module structure

- `from __future__ import annotations` at the top of every module.
- Module-level docstring explains **why**, not just what — cite the Spec
  Sec. N this module implements if applicable, and call out any
  non-obvious design decision explicitly (see `hmm_engine.py`'s docstring
  on Viterbi/smoothing exclusion as the reference example). A docstring
  that only restates the function/class names below it isn't pulling its
  weight.
- `logger = logging.getLogger(__name__)` per module; no `print()` in
  library code (scripts under `backtest/` are the exception — they're CLI
  tools that print results directly).

## Types and data structures

- `@dataclass(frozen=True)` for value objects with no mutation need
  (`Position`, `PortfolioState`, `ProposedTrade`, `VetoDecision`,
  `TradeDecision`, `NewsItem`, `SentimentScore`). Plain `@dataclass` only
  when the object is genuinely mutated in place (`EquityTracker`,
  `BetaArm`).
- `Enum` (string-valued) for closed sets of named outcomes
  (`CircuitBreakerAction`, `OrderClass`/`OrderSide`/`TimeInForce` from
  `alpaca-py`).
- `typing.Protocol` for a dependency that has more than one real or
  potential implementation, or that doesn't exist yet and needs a stable
  contract to build against (`MarketDataProvider`, `ModelStore`,
  `SignalGenerator` in `main.py`). Don't reach for `Protocol` for something
  with exactly one implementation and no test double need — that's just
  indirection.
- Computed values that are cheap and always re-derivable belong as
  `@property` on the dataclass (`PortfolioState.gross_exposure_pct`,
  `ProposedTrade.dollar_risk`), not precomputed fields that could drift out
  of sync with their inputs.

## Function design

- Prefer pure functions with explicit parameters over methods with hidden
  state, especially anywhere financial correctness matters
  (`risk_manager.py`, `feature_engineering.py` are the reference examples —
  every function's output is fully determined by its arguments).
- Pass "now"/"as of" timestamps as an explicit parameter
  (`as_of: datetime`) rather than calling `datetime.now()` inside a
  function that's supposed to be deterministic and testable — see
  `EquityTracker.update`, `LearningEngine.run_weekly_optimization`.
- Validate at the boundary, fail loudly with a specific message: functions
  that receive malformed input (`fit_with_bic_selection` on NaN input,
  `SentimentEngine._validate_text` on empty strings,
  `order_executor.size_to_shares` on non-positive price) raise
  `ValueError` with a message that includes the actual bad value, not a
  generic "invalid input."

## Constants

- Named module-level constants in `UPPER_SNAKE_CASE` for every tunable
  threshold, never inline magic numbers — see `risk_manager.py`'s limit
  constants or `hmm_engine.MIN_COMPONENTS`/`MAX_COMPONENTS`. This is what
  makes [Standards/Risk Limits Reference.md](Risk%20Limits%20Reference.md)
  possible to keep accurate by grepping the source.

## Async code

- Blocking calls inside an async function go through
  `asyncio.to_thread(...)`, never called directly — see every
  `market_data.get_ohlcv_history` call site in `main.py`, and
  `NewsStreamer.start()` wrapping the SDK's blocking `.run()`.
- Long-lived background loops (`_structural_loop`, `_weekend_cron_loop`)
  check a shared `asyncio.Event` for shutdown rather than being cancelled
  externally, and use `asyncio.wait_for(event.wait(), timeout=...)` instead
  of bare `asyncio.sleep(...)` so shutdown is responsive rather than
  waiting out the full interval.

## Docstrings on "why", comments sparingly

This codebase leans heavily on module/class/function docstrings to explain
rationale, and uses inline comments only for something a docstring can't
easily carry (e.g. the one-line note in `main.py` on why
`asyncio.Event()` isn't constructed in `__init__`). Match that balance —
don't add comments restating what the next line of code already makes
obvious.
