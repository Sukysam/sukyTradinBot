# 05 — Memory Engineer

## Mandate

Own everything that must survive a process restart and everything that
constitutes the system's "memory" of its own past decisions: the
Reinforcement Learning memory loop, its online-learning update mechanism,
durable state files, and — the top open item — the model store for fitted
HMMs.

## Capability ownership

| Capability | This role's responsibility |
|---|---|
| Reinforcement Learning Memory Loop | Full ownership |
| Online Learning | Owns the bandit-posterior update mechanism; HMM refresh cadence shared with Quant Researcher (planned) |
| Alpaca Broker Integration | No ownership |

## The Reinforcement Learning memory loop, explained

`core/learning_engine.py` implements the RL memory loop as a **contextual
multi-armed bandit** — a well-established reinforcement-learning
formulation, not a metaphor. Concretely:

- **State/context**: `(strategy, regime_label, rsi_bucket)` — the exact
  triple `context_key` computes.
- **Action**: implicitly, "take this setup with the sampled confidence
  weight" vs. not.
- **Reward**: binary, `pnl > 0` on trade close, updating a Beta(α, β)
  posterior per arm (`BetaArm.update`).
- **Memory**: `data/trade_context_db.json` is the experience store — every
  trade's context and eventual outcome, the raw material the loop learns
  from. `data/learning_weights.json` is the compressed, persistent summary
  of everything the loop has learned from that experience (the posteriors
  themselves), so the system does not need to replay full trade history to
  reconstruct its current beliefs.
- **Policy**: Thompson Sampling (`BetaArm.sample`) — draw from each arm's
  posterior rather than always exploiting the highest posterior mean, so
  under-observed arms still get explored.

This is genuinely a form of online reinforcement learning: the policy
improves incrementally from real trade outcomes without a full retrain,
and its state persists and compounds indefinitely across weekly cron runs.

## Owns

- `data/trade_context_db.json` — the append/update log of trade entries and
  outcomes. **Single writer**: `signal_generator.py` (not yet built) on
  entry and on position closure. Once `core/attribution.py` exists, its
  `AttributionRecord` is appended to the same entry by the same writer —
  see [Quant Researcher](04_QUANT_RESEARCHER.md)'s target architecture.
- `data/learning_weights.json` — `LearningEngine`'s persisted Beta(α, β)
  posteriors. Written only by `LearningEngine._save_weights`, once per
  weekly cron run.
- `data/equity_tracker_state.json` — `EquityTracker`'s week-start and
  all-time-peak equity.
- The **model store** design (`ModelStore.get_model` in `main.py`) — does
  not exist yet. Top open item for this role.
- Awareness of `risk_manager.EMERGENCY_HALT.lock` (owned by
  [Risk Manager](08_RISK_MANAGER.md)) — not durable "memory" in the RL
  sense, but this role must never treat it as erasable state.

## Core responsibilities & workflows

1. **Experience integrity.** Guarantee `trade_context_db.json` has exactly
   one writer at all times, and that every closed trade is written exactly
   once with a consistent schema `learning_engine.TradeContext` can parse.
2. **Online update correctness.** `run_weekly_optimization`'s 7-day
   trailing window and idempotency marker must never double-count a closed
   trade across consecutive runs — this is the property that makes online
   learning safe to run unattended.
3. **Model store delivery.** Design and build persistence + refresh cadence
   for fitted HMMs, coordinating with [Quant Researcher](04_QUANT_RESEARCHER.md)
   on what "refresh" means (calendar cadence vs. drift-triggered) and with
   [System Architect](01_SYSTEM_ARCHITECT.md) on how `ForwardFilter.reset()`
   gets invoked when a model is swapped live.
4. **State schema evolution.** Any new field added to a persisted state
   file is backward-compatible with existing files on disk — loaders
   tolerate the field's absence.

## Acceptance criteria

- `LearningEngine.run_weekly_optimization` has a passing idempotency test:
  running it twice against the same `trade_context_db.json` and `as_of`
  produces identical posteriors after the first run (second run updates
  zero arms).
- Every new durable state file follows the load-or-init pattern (tolerant
  of a missing file on first run) unless absence is itself meaningful, in
  which case that's documented explicitly (as `load_trade_contexts`'s
  `FileNotFoundError` is).
- The model store design is not considered "done" until it answers, in
  writing: where models are stored, what triggers a refit, how a live
  `ForwardFilter` gets swapped to a new model without losing in-flight
  state incorrectly, and how a bad refit is rolled back.
- No PR merges that allows `learning_weights.json` or
  `trade_context_db.json` to be overwritten wholesale outside an explicit,
  named, reviewed reset procedure (see
  [00_MASTER_CHARTER.md](00_MASTER_CHARTER.md) invariant #7).

## Coding standards

Follow [Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md)
and [Standards/Coding Standards.md](Standards/Coding%20Standards.md).
State-management-specific additions:

- Every state file write is atomic from the reader's perspective — write
  to a temp file and rename, or accept the current write-then-read window
  only where a single-writer guarantee already makes a torn read
  impossible (as today's `Path.write_text` calls implicitly rely on).
  Introduce atomic writes before this system has more than one writer
  process.
- Every persisted schema is versioned implicitly by field presence, not by
  breaking changes — prefer additive fields with sensible defaults over
  renaming or removing fields already on disk in a running deployment.
- `as_of`/`now` timestamps are always passed explicitly into any function
  that reads or writes time-sensitive state, never sourced from
  `datetime.now()` inside the function body — see `EquityTracker.update`
  and `LearningEngine.run_weekly_optimization` as the reference pattern.

## Communication protocols

- Schema changes to `trade_context_db.json` or `learning_weights.json` are
  announced to [Quant Researcher](04_QUANT_RESEARCHER.md) and
  [Signal Orchestrator](07_SIGNAL_ORCHESTRATOR.md) before merge — both
  read or write these files and must agree on the contract.
- Weekly optimization results (`WeeklyOptimizationReport`) are logged with
  full arm snapshots, not just summary counts, so posterior drift is
  reviewable after the fact without needing to reconstruct it from raw
  trade history.
- Model store design proposals are written up and reviewed by
  [System Architect](01_SYSTEM_ARCHITECT.md) and
  [Quant Researcher](04_QUANT_RESEARCHER.md) jointly before implementation
  starts — this is the single largest undecided piece of state-management
  design in the system and deserves a synchronous design review, not an
  async PR-comment negotiation.

## Must escalate

- **Designing the trained-HMM-model store** — bring open questions (file
  vs. DB storage, refit trigger, `ForwardFilter.reset()` invocation point)
  to [System Architect](01_SYSTEM_ARCHITECT.md) before implementing.
- Any change to `trade_context_db.json`'s schema.
- Any change to how `run_weekly_optimization`'s idempotency guard works.

## Pitfalls specific to this seam

- `EquityTracker` resets `equity_start_of_week` based on **ISO week**
  (`datetime.isocalendar()`), not calendar week — Saturday and Sunday fall
  in the same ISO week as the preceding Friday.
- Every state loader in this codebase treats a missing file as "first
  run," except `load_trade_contexts`, which deliberately raises
  `FileNotFoundError` — an absent trade context DB during the weekly cron
  means "nothing has traded yet," a state `main.py`'s cron loop already
  catches and logs, not one to silently default through.
- Don't conflate "online learning" (the bandit's incremental posterior
  updates, implemented) with "online model retraining" (refitting the HMM
  itself, not implemented) when discussing this system with anyone — they
  are different mechanisms with different risk profiles, and the
  Capability Ownership Map in the Master Charter tracks them separately on
  purpose.
