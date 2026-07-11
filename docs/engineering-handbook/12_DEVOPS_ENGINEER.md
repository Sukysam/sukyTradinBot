# 12 — DevOps Engineer

## Mandate

Own everything about how this system actually runs in production: secrets,
process supervision, the paper/live toggle, model deployment for the RL
memory loop and (once built) the allocation/attribution models, and
monitoring the signals that mean something is wrong.

## Capability ownership

| Capability | This role's responsibility |
|---|---|
| Production Deployment | Full ownership |
| Online Learning | Owns the operational safety of the weekly cron and, once built, any HMM refresh job — deployment/rollback mechanics, not the learning logic itself |
| Reinforcement Learning Memory Loop | Owns backup/restore of `learning_weights.json` and `trade_context_db.json` as production data assets |

## Owns

- Environment/secrets contract: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`,
  `ALPACA_PAPER`, `REGIME_TRADER_TICKERS`.
- Process lifecycle: `main.py`'s `SIGINT`/`SIGTERM` handling.
- Monitoring for every condition this codebase logs at `CRITICAL`:
  circuit-breaker liquidations, emergency hard stop, `liquidate_all_positions`
  failures — these page a human, not just sit in a log file.
- Backup/restore procedures for `data/trade_context_db.json`,
  `data/learning_weights.json`, `data/equity_tracker_state.json` — the
  system's entire memory of its own trading history; losing these resets
  the RL memory loop to a cold start.
- Deploy target for `backtest/`'s scripts — one-off/ad hoc, not a service.
- Once built: model artifact deployment for fitted HMMs, the allocation
  model, and the SHAP explainer — versioned, rollback-capable delivery of
  each.

## Core responsibilities & workflows

1. **Secrets management.** Store credentials outside the repo, never
   logged; confirm no logging statement could accidentally echo
   `secret_key`.
2. **Process supervision.** Ensure `SIGTERM` is delivered with enough grace
   period for in-flight order submission and state-file writes to
   complete before a hard kill.
3. **Monitoring & alerting.** Wire every `CRITICAL`-level log line to page,
   not just log — this includes future model-deployment failures (a bad
   HMM refit that fails validation, an allocation-model rollback).
4. **State backup.** Regularly back up the three durable state files above;
   test restoration, not just backup creation — an untested backup is not
   a backup.
5. **Model deployment** (once in scope). Every model artifact
   (HMM, allocation model, SHAP explainer) ships through the same
   versioned, auditable deployment path — no ad hoc "copy the pickle file
   to the server" deployments for capital-affecting models.

## Acceptance criteria

- Every `CRITICAL`-level log condition in the codebase has a corresponding
  alert rule verified to actually fire in a staging/paper environment
  before it's trusted in production.
- State-file backups are restored in a drill at least once before being
  relied upon operationally, with the restore procedure documented in
  [SOPs/Incident Response Runbook.md](SOPs/Incident%20Response%20Runbook.md).
- `SIGTERM`-to-clean-shutdown timing is measured empirically (not assumed)
  and the deployment's stop-timeout is configured with margin above that
  measurement.
- No deployment configuration hardcodes `ALPACA_PAPER=false` by default —
  the safe default (paper) is preserved at every layer of the deployment
  stack, not just in application code.
- Model deployments (once in scope) are rollback-capable within a defined,
  tested time bound — stated explicitly in the deployment runbook.

## Coding standards

Follow [Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md)
and [Standards/Coding Standards.md](Standards/Coding%20Standards.md) for
any operational tooling code (deploy scripts, monitoring glue). Additional:

- No operational script performs a destructive action (delete state,
  force-restart, clear the emergency lock) without an explicit
  confirmation step or a documented `--yes`-style opt-in flag — never a
  silent default.
- Deployment configuration is version-controlled alongside the
  application code it deploys, not maintained out-of-band in a dashboard
  with no history.

## Communication protocols

- Every `CRITICAL` log event that pages is followed by an incident write-up
  per [SOPs/Incident Response Runbook.md](SOPs/Incident%20Response%20Runbook.md),
  even if the system self-recovered (e.g. a daily size-cut that resolved
  itself the next trading day still gets a brief note).
- Planned maintenance affecting the weekend cron's optimization window is
  announced in advance to [Memory Engineer](05_MEMORY_ENGINEER.md) — a
  missed weekly optimization run has no catch-up logic and silently skips
  that week's online learning update.
- Model deployment/rollback actions are logged with the model version,
  deploying operator, and rationale, in the same audit trail
  [Documentation Engineer](11_DOCUMENTATION_ENGINEER.md) maintains for
  model cards.

## Must escalate

- **Flipping `ALPACA_PAPER` to live trading** — gated on
  [SOPs/Release Workflow.md](SOPs/Release%20Workflow.md), never a
  unilateral config change.
- Any change to signal-handling or shutdown behavior in `main.py` —
  overlaps [System Architect](01_SYSTEM_ARCHITECT.md)'s territory.
- Deleting `risk_manager.EMERGENCY_HALT.lock` as part of any automated
  recovery/restart tooling — must survive a restart; clearing it is a
  manual, human action, never a side effect of a redeploy script.
- Any model deployment to a live-trading environment without a completed
  model card and QA sign-off.

## Pitfalls specific to this seam

- `loop.add_signal_handler` is wrapped in `try/except NotImplementedError`
  because signal handlers aren't available on all platforms — don't
  assume `Ctrl+C` or `SIGTERM` cleanly drains in-flight state everywhere
  without verifying on the actual deploy target.
- `EQUITY_STATE_PATH`, `LEARNING_WEIGHTS_PATH`, and `TRADE_CONTEXT_DB_PATH`
  are relative paths (`Path("data/...")`) — confirm the deployed process's
  working directory matches what's assumed, or these read/write to the
  wrong location silently (auto-created parent directories mean a
  wrong-cwd deployment won't even error, it'll just start with empty
  state — indistinguishable from a real cold start without careful
  monitoring).
- The weekend cron is polled hourly inside the same process, not a
  separate scheduled job — there is no external cron to configure. If the
  main process is down during the Saturday window, that week's online
  learning update is simply skipped with no catch-up logic; monitoring
  should treat "no weekly optimization log line by Sunday" as a signal.
