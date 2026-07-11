# SOP — Release Workflow

Governs deploying `regime-trader/` changes, and specifically the
paper-trading → live-trading gate. `ALPACA_PAPER` defaults to paper
(`true`) unless explicitly set to `"false"` in the environment — that
default is deliberate and should never be overridden casually.

## Every release (paper or live)

1. Full test suite green, per the priority order in
   [09_QA_ENGINEER.md](../09_QA_ENGINEER.md).
2. [Architecture/Known Gaps.md](../Architecture/Known%20Gaps.md) reviewed —
   confirm nothing the release depends on is still backed by a
   `_NotYetImplemented` placeholder. `main.py` will raise loudly if it is,
   but confirm before deploy rather than discovering it at 3am from a
   `NotImplementedError` in production logs.
3. Code Review Workflow completed for every change in the release
   (see [Code Review Workflow.md](Code%20Review%20Workflow.md)).
4. Secrets (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`) confirmed present in the
   target environment and scoped to the correct Alpaca account (paper vs.
   live keys are different credentials, not just a flag).

## Paper trading deploy

Standard release. No additional sign-off beyond the steps above. This is
the default and expected state of any running instance.

## Live trading deploy — additional gate

Flipping `ALPACA_PAPER=false` moves real capital. Per
[00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md)
and [12_DEVOPS_ENGINEER.md](../12_DEVOPS_ENGINEER.md),
this is never a unilateral config change. Before it happens:

1. **Sustained paper-trading track record.** The system has run against the
   full three-pipeline loop (structural, news, weekend cron) on paper for
   long enough to observe at least one full weekly learning-engine cycle
   and, ideally, at least one circuit-breaker-relevant drawdown event
   (even a minor daily-size-cut trigger) to confirm the veto layer actually
   fires correctly under real market conditions, not just unit tests.
2. **Every Known Gap that blocks correct operation is closed.** In
   particular: `broker/alpaca_client.py`, the model store, and
   `core/signal_generator.py` must all be real implementations, not
   placeholders — a live deploy running on `_NotYetImplemented` stubs isn't
   a partially-working system, it's a system that will throw on its first
   real tick.
3. **`config/settings.yaml` (or its equivalent) is real**, with correct
   per-ticker sector metadata — the risk manager's sector exposure cap is
   silently a no-op while `sectors={}` in `main.py`, which is acceptable in
   paper (low stakes) but not in live.
4. **The emergency-halt runbook is written and the on-call person knows
   it.** Per [08_RISK_MANAGER.md](../08_RISK_MANAGER.md) and
   [SOPs/Incident Response Runbook.md](Incident%20Response%20Runbook.md),
   clearing `risk_manager.EMERGENCY_HALT.lock` is a manual, human action —
   confirm someone knows where that file lives on the deployed host and
   under what conditions it's appropriate to delete it.
5. **If the Adaptive Strategy Allocation model is in the release**, it has
   a model card per [11_DOCUMENTATION_ENGINEER.md](../11_DOCUMENTATION_ENGINEER.md)
   and a reviewed SHAP attribution summary per
   [Standards/Model Explainability Standard.md](../Standards/Model%20Explainability%20Standard.md),
   even if SHAP integration itself is still in progress — a model with no
   attribution and no other explainability review does not go live.
6. **State backups verified restorable**, per
   [12_DEVOPS_ENGINEER.md](../12_DEVOPS_ENGINEER.md) — a live deployment's
   `trade_context_db.json` and `learning_weights.json` represent real
   accumulated trading history and RL memory-loop state that cannot be
   reconstructed if lost.
7. **Explicit human sign-off**, separate from code review approval, from
   whoever owns capital-allocation decisions for this system. This kit does
   not authorize live trading on its own — no role file's "can decide
   unilaterally" section includes this.

## Rollback

Reverting to paper (`ALPACA_PAPER=true`) is always the safe direction and
requires no special gate — treat "when in doubt, go back to paper" as the
default response to any live-trading anomaly, ahead of debugging in place.
