# Template — New Strategy Proposal

Use when proposing a new trading strategy or a change to regime-tier
allocation logic (`core/regime_strategies.py`, once built) — anything that
would change *what* trades get proposed, not how they're executed or
vetoed.

```
Proposed strategy: <name>

Trigger condition: <what regime/feature/sentiment state causes this
strategy to fire — be as precise as the existing catalyst strategy's
">0.90 positive FinBERT while HMM regime reads NEUTRAL">

Spec citation: <Spec Sec. N, or "none found — flagging as new policy, not
an implementation of existing spec" per Knowledge Base/Spec Section Index.md>

Position sizing logic: <how notional_value, entry_price, stop_price, and
optional take_profit_price are derived>

Expected interaction with existing systems:
- Risk veto: does this strategy's typical stop distance keep
  MAX_RISK_PER_TRADE_PCT (1%) satisfiable? (Standards/Risk Limits Reference.md)
- Learning loop: what (strategy, regime_label, rsi_bucket) context key(s)
  will this generate? Does it fragment existing arms or create sensible new
  ones? (core/learning_engine.py context_key)
- Correlation filter: is this strategy likely to concentrate in
  correlated names within a sector?

Backtesting plan: <how this will be validated before paper trading — see
09_QA_ENGINEER.md and SOPs/Release Workflow.md>

Read first:
- 07_SIGNAL_ORCHESTRATOR.md
- 08_RISK_MANAGER.md
- Architecture/Data Flow.md (entry path diagrams)
```

Do not implement position sizing or risk logic inline in the strategy
function — it must still pass through `risk_manager.evaluate_trade` via the
normal `TradeDecision` → `_evaluate_and_submit` path. A strategy proposal
that bypasses the veto layer is out of scope, full stop.
