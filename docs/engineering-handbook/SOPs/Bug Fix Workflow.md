# SOP — Bug Fix Workflow

## 1. Classify the bug before touching code

- **Silent wrong behavior** (wrong number, wrong decision, no crash) — e.g.
  a look-ahead leak, a risk check computing the wrong ratio, a mislabeled
  regime. These are the most dangerous class in this codebase because
  nothing crashes to announce them. Treat with the highest urgency
  regardless of how it was reported.
- **Loud failure** (exception, `NotImplementedError`, `logger.critical`) —
  often *working as designed* (see the `_NotYetImplemented` pattern in
  [00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md)).
  Confirm it's actually a bug and not a Known Gap surfacing correctly before
  "fixing" it by suppressing the error.
- **Production incident** (a `CRITICAL`-logged event, a live-trading
  circuit breaker, a liquidation failure) — handle via
  [Incident Response Runbook.md](Incident%20Response%20Runbook.md) first;
  the bug fix that follows is a downstream artifact of that incident's
  root-cause investigation, not a substitute for it.
- **Sandbox bug** (`backtest/`) — no live-capital impact; fix at normal
  priority.

## 2. Reproduce with a test first

Especially for silent-wrong-behavior bugs in `risk_manager.py`,
`hmm_engine.py`, or `feature_engineering.py`: write the failing test before
the fix. These modules are pure functions of explicit inputs — there's no
excuse not to have a minimal, deterministic repro.

## 3. Check whether the bug is actually a known gap

Cross-reference [Architecture/Known Gaps.md](../Architecture/Known%20Gaps.md).
If the "bug" is `NotImplementedError: broker/alpaca_client.py (historical
bar fetching) is not implemented yet`, that's the system working correctly —
route to feature development, not a bug fix.

## 4. Fix at the root cause, in the owning module

Identify the owning role from
[00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md)'s
table. Don't patch a symptom in a downstream caller when the defect is in
the producing module — e.g. a bad regime label should be fixed in
`regime_strategies.py`, not papered over with a special case in
`learning_engine.py`'s context-key bucketing.

## 5. Check for the same bug pattern elsewhere

A look-ahead bug in one feature column is worth grepping
`feature_engineering.py` for the same mistake in every other column. A
check-order bug in one circuit breaker is worth re-reading the whole
severity ladder in `risk_manager.py`.

## 6. If the fix touches risk limits or the anti-look-ahead guarantee, escalate

Per [08_RISK_MANAGER.md](../08_RISK_MANAGER.md)
and [04_QUANT_RESEARCHER.md](../04_QUANT_RESEARCHER.md):
these aren't unilateral fixes even when the bug is clear-cut, because the
"fix" might reveal the threshold itself was wrong per spec, which is a
policy question, not just a code question.

## 7. Regression test + Code Review

Every bug fix ships with a regression test reproducing the original failure,
and goes through [Code Review Workflow.md](Code%20Review%20Workflow.md).
