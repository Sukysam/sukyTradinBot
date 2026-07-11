# Architecture — Production Deployment

Status: **Implemented** (process lifecycle) / **Planned** (orchestration,
model serving, drift monitoring). Owner:
[12_DEVOPS_ENGINEER.md](../12_DEVOPS_ENGINEER.md).

## What exists today

A single supervised process (`python -m regime-trader.main`, or equivalent
entrypoint) running `RegimeTraderApp.run()`:

- Reads secrets and configuration from environment variables at startup
  (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER`,
  `REGIME_TRADER_TICKERS`).
- Constructs a `TradingClient` and wires all dependencies, including
  `_NotYetImplemented` placeholders for the three Known Gaps that don't
  exist yet (`alpaca_client.py`, the model store, `signal_generator.py`).
- Runs three concurrent `asyncio` tasks (structural loop, news listener,
  weekend cron) under `asyncio.gather`.
- Handles `SIGINT`/`SIGTERM` for graceful shutdown where the platform
  supports `asyncio` signal handlers.
- Persists state (`data/trade_context_db.json`, `data/learning_weights.json`,
  `data/equity_tracker_state.json`) to relative paths on local disk.

This is a minimal but coherent single-process deployment model. It has no
built-in redundancy, no orchestration layer, and no separate model-serving
tier — all model inference (HMM forward filter, FinBERT, and eventually
the allocation model + SHAP explainer) runs in-process.

## What "production-grade" adds (planned)

| Concern | Current state | Target |
|---|---|---|
| Process supervision | Manual / whatever the host provides | systemd/supervisord/container orchestrator with automatic restart and alerting on crash-loop |
| Secrets | Environment variables | Secret manager injection (never committed, never logged) — see [12_DEVOPS_ENGINEER.md](../12_DEVOPS_ENGINEER.md) |
| State durability | Local disk, relative paths | Backed up on a schedule with tested restore; ideally off-host replication |
| Model deployment | In-process construction at startup | Versioned, rollback-capable artifact deployment for HMM fits, the allocation model, and the SHAP explainer |
| Monitoring | Python `logging` to stdout/file | `CRITICAL` log lines wired to paging; dashboards for exposure, drawdown, circuit-breaker state |
| Drift detection | None | Scheduled comparison of live regime classifications against a held-out validation window, flagging when a model refresh may be warranted |
| Working directory contract | Assumed, unenforced | Explicit, validated at startup — a wrong cwd currently fails silently (see pitfall below) |

## Deployment topology (target)

```
                     ┌─────────────────────────┐
                     │   Secret manager          │
                     │  (ALPACA_API_KEY, etc.)   │
                     └────────────┬───────────────┘
                                  │ injected at start
                     ┌────────────▼───────────────┐
                     │  Supervised process          │
                     │  RegimeTraderApp             │──── stdout/structured logs ──► log aggregation
                     └────────────┬───────────────┘                                        │
                                  │ reads/writes                                            ▼
                     ┌────────────▼───────────────┐                              CRITICAL-level alerts
                     │  Durable state volume         │                              → paging
                     │  (trade_context_db.json,      │
                     │   learning_weights.json,      │
                     │   equity_tracker_state.json,  │
                     │   EMERGENCY_HALT.lock)         │
                     └────────────┬───────────────┘
                                  │ backed up on schedule
                     ┌────────────▼───────────────┐
                     │  Backup store (tested restore)│
                     └─────────────────────────────┘
```

## Paper vs. live environments

Two logically separate deployments — different Alpaca credentials
(paper vs. live keys are different, not just a flag), and ideally
physically separate process instances rather than one process toggled by
an environment variable at runtime, to reduce the chance of a
configuration error silently flipping a live deployment to paper-like
behavior or vice versa. See
[SOPs/Release Workflow.md](../SOPs/Release%20Workflow.md) for the gate
between them.

## Known operational pitfalls (see also [12_DEVOPS_ENGINEER.md](../12_DEVOPS_ENGINEER.md))

- All three durable-state paths are relative to process working directory.
  A deployment that starts the process from the wrong directory doesn't
  error — it silently starts with empty state, which is indistinguishable
  from a genuine cold start without deliberate monitoring for this
  specific condition.
- The weekend cron has no catch-up logic — if the process is down during
  the Saturday optimization window, that week's online learning update is
  simply skipped.
- `SIGTERM` grace period must exceed the time needed for in-flight order
  submission and state writes to complete; this should be measured, not
  assumed, on the actual deploy target.
