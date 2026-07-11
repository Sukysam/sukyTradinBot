# SOP — Incident Response Runbook

Governs response to any `CRITICAL`-level event this system logs, and to
any operational failure that puts capital at risk. Severity language
follows [Standards/Communication Protocols.md](../Standards/Communication%20Protocols.md).

## Incident classes

### 1. Circuit breaker: size cut (`CUT_SIZE_50`)

- **Signal**: `logger` at `WARNING`/`INFO` from `evaluate_circuit_breakers`
  (daily drawdown > 2%).
- **Immediate action**: none required — this is the system self-correcting.
  Confirm the next tick applies the 0.5x size multiplier as expected.
- **Follow-up**: a brief note in the incident log even though this
  self-recovers, per
  [12_DEVOPS_ENGINEER.md](../12_DEVOPS_ENGINEER.md)'s communication
  protocol — patterns of frequent size cuts are worth trending over time.

### 2. Circuit breaker: daily or weekly halt (`HALT_DAY` / `HALT_WEEK`)

- **Signal**: `logger.critical` from `evaluate_circuit_breakers`; all
  positions liquidated via `OrderExecutor.liquidate_all_positions`.
- **Immediate action**: page on-call. Confirm `liquidate_all_positions`
  actually succeeded (check the returned bool and Alpaca account state
  directly) — a failed liquidation during a halt is a more severe incident
  (see class 4 below).
- **Follow-up**: written incident report within 24 hours covering: what
  triggered the halt, portfolio state at trigger time, whether
  liquidation completed cleanly, and — once SHAP attribution exists —
  attribution records for the trades that contributed most to the
  drawdown.
- **Resolution**: trading resumes automatically at the next eligible
  period (next day / next week) — no manual lock-clearing needed for
  these two tiers, only for emergency hard stop (class 3).

### 3. Emergency hard stop (`EMERGENCY_HARD_STOP`)

- **Signal**: `logger.critical`, `risk_manager.EMERGENCY_HALT.lock`
  written to disk. Peak drawdown > 10%.
- **Immediate action**: page on-call immediately, highest severity. Confirm
  liquidation completed. **Do not delete the lock file** as part of
  incident triage — it is intentionally the one piece of state in
  `risk_manager.py` that only a human clears, and only after the
  investigation below is complete.
- **Investigation required before clearing the lock**:
  1. Reconstruct the sequence of trades leading to the drawdown from
     `trade_context_db.json` (and, once available, their
     `AttributionRecord`s).
  2. Determine whether the drawdown reflects a genuine adverse market move,
     a modeling/allocation defect, or a risk-limit configuration issue.
  3. Get explicit sign-off from [Risk Manager](../08_RISK_MANAGER.md) and
     whoever owns capital-allocation decisions before resuming.
  4. Only then, a human manually deletes
     `risk_manager.EMERGENCY_HALT.lock`.
- **Follow-up**: full written post-mortem, filed regardless of root cause.

### 4. Liquidation failure

- **Signal**: `logger.critical("Liquidate-all failed: %s", exc)` from
  `OrderExecutor.liquidate_all_positions`, or a `False` return.
- **Immediate action**: highest-severity page — the system attempted to
  reduce risk and failed, meaning the portfolio is now in an unmanaged
  state relative to what the risk layer intended. Check Alpaca account
  state directly and manually intervene (manual position closure via
  Alpaca's dashboard/API) if the automated retry doesn't succeed quickly.
- **Follow-up**: root-cause the failure (API outage, auth issue, rate
  limit) and file with [Backend Engineer](../03_BACKEND_ENGINEER.md).

### 5. Missed weekly optimization

- **Signal**: absence of a weekly optimization log line by Sunday.
- **Immediate action**: none urgent — see
  [SOPs/Model Retraining and Online Learning.md](Model%20Retraining%20and%20Online%20Learning.md)
  section A.
- **Follow-up**: confirm the process was healthy during the missed window;
  if it was down, that's a separate process-supervision incident to
  investigate under [12_DEVOPS_ENGINEER.md](../12_DEVOPS_ENGINEER.md).

### 6. Unbuilt-dependency `NotImplementedError` in production

- **Signal**: `NotImplementedError` citing a component listed in
  [Architecture/Known Gaps.md](../Architecture/Known%20Gaps.md).
- **Immediate action**: this should never reach a live-trading deployment
  — per [SOPs/Release Workflow.md](Release%20Workflow.md), every Known Gap
  blocking live operation must be closed before go-live. If it happens
  anyway, treat as a release-process failure, not just a code bug: page,
  confirm the process is safely idle (not silently retrying into a bad
  state), and escalate to [Technical Planner](../02_TECHNICAL_PLANNER.md).
- **Follow-up**: post-mortem on how an unclosed Known Gap reached a live
  environment.

## General incident write-up template

```
## Incident: <one line>
Detected: <timestamp> via <log line / alert>
Severity: <class from above>
Portfolio state at detection: <equity, drawdown%, open positions>
Timeline: <what happened, in order>
Root cause: <or "investigation ongoing">
Resolution: <what was done>
Follow-up actions: <owner, due date>
```

File every incident write-up regardless of whether the system
self-recovered — a pattern only becomes visible across multiple
lightweight write-ups, never from a single unrecorded event.
