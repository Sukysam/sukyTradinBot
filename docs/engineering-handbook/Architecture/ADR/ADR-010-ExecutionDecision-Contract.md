# ADR-010: Freeze the ExecutionDecision Contract

**Status**: Accepted
**Date**: 2026-07-13
**Milestone**: [6 — Risk Management](../../../../PROJECT_STATUS.md) (contract only — no
implementation in this record; see Context)

## Context

ADR-008 established a stricter sequencing than Milestone 4's own contract
freeze: freeze the next milestone's output type *before* its package
exists at all, reviewed on its own, implementation only starting
afterward. This record applies that same discipline to Milestone 6:
`src/risk/` does not exist yet. `ExecutionDecision` is frozen first,
reviewed, and only then does implementation begin.

Unlike `RegimeState` and `StrategyDecision`, this is not a contract
invented for a wholly new capability — `regime-trader/core/risk_manager.py`
already implements a real, tested veto layer (`VetoDecision`,
`CircuitBreakerDecision`, `evaluate_trade`, `evaluate_circuit_breakers`)
against a documented set of limits
([Standards/Risk Limits Reference.md](../../Standards/Risk%20Limits%20Reference.md)).
Milestone 6's job is to package and hardened-port that logic under
`src/`, the same relationship Milestone 4 had to `core/hmm_engine.py`. The
contract below is grounded in what that legacy module actually returns
today, not designed from a blank page — deviations from its shape are
called out explicitly in Alternatives Considered.

Milestone 6's own scope is narrow by design: convert a `StrategyDecision`
(plus a portfolio/account snapshot) into an approval/sizing verdict, not
an order. That boundary needs to be a contract property, or a future
implementation detail (an order type, a broker call, a fill assumption)
could quietly creep into what `ExecutionDecision` promises — the same
concern ADR-008 raised about `StrategyDecision` not creeping toward
`ExecutionDecision`'s own concerns.

## Decision

`risk.models.ExecutionDecision` — `timestamp`, `symbol`, `approved`,
`approved_allocation`, `decision_type`, `risk_adjustments`, `reasoning`,
`strategy_reference`, `metadata` — is frozen as a binding contract,
documented in full at
[Standards/ExecutionDecision Contract.md](../../Standards/ExecutionDecision%20Contract.md),
*before* `src/risk/` is scaffolded. Several properties are enforced at
the type level, not left to documentation or a call site's discipline:

1. **`approved_allocation` is bounded to `[0.0, strategy_reference.
   allocation]`.** The risk layer can only hold a strategy's requested
   size steady or reduce it — never increase it. This gives the veto
   layer's entire reason for existing ("the last line of defense between
   a proposed trade and real money," per
   [08_RISK_MANAGER.md](../../08_RISK_MANAGER.md)) a concrete, unavoidable
   shape at the exact point a decision is constructed, the same way
   `StrategyDecision.allocation`'s `[0.0, 1.0]` bound enforces invariant #5
   at that layer.
2. **`not approved` requires `approved_allocation == 0.0` and a non-empty
   `risk_adjustments`.** A rejection is never silent or size-ambiguous —
   grounded directly in `core/risk_manager.py::evaluate_trade`, which
   never returns `approved=False` with an empty `reasons` tuple in any
   real code path today.
3. **A size-cut approval also requires a non-empty `risk_adjustments`.**
   This is a deliberate improvement over the legacy `VetoDecision`: under
   a `CUT_SIZE_50` circuit breaker, `evaluate_trade` today returns
   `VetoDecision(approved=True, reasons=(), size_multiplier=0.5)` — the
   *reason* for the 50% cut is logged at `CRITICAL` via a side channel
   (`logger.critical` inside `trigger_emergency_hard_stop`/the circuit
   breaker path) but never reaches the returned decision object itself.
   `ExecutionDecision` closes that gap: any daylight between
   `approved_allocation` and `strategy_reference.allocation` must be
   explained in the return value, not just in a log line.
4. **`reasoning` must be non-empty, always** — including a clean full-size
   approval. This extends
   [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md) invariant #6 one
   step downstream of `StrategyDecision.reasoning`, and is deliberately a
   stronger requirement than the legacy module has today (a clean
   `VetoDecision(approved=True, reasons=(), ...)` currently carries no
   prose explanation at all).
5. **`symbol`/`timestamp` must match `strategy_reference`'s.** Enforceable
   here — unlike `StrategyDecision`, which has no embedded reference to
   the `RegimeState`/`FeatureVector` it was built from and so cannot self-
   check consistency — because `strategy_reference` is a first-class field
   on `ExecutionDecision` itself.
6. **`decision_type` (`APPROVED`/`REDUCED`/`REJECTED`) is a stored,
   construction-time-validated classification**, not just a value a
   consumer could derive by comparing `approved`, `approved_allocation`,
   and `strategy_reference.allocation` itself. Added directly during
   contract review, before merge — see Alternatives Considered for why
   this complements rather than replaces the three fields it's checked
   against.

## Consequences

- Whoever implements Milestone 6 has one document to build against before
  writing `src/risk/`'s first line — which limits are ported, how they're
  checked, what order they're evaluated in, and the shape of the
  portfolio/account snapshot types are all free to be designed, because
  none of that is what this freeze constrains.
- Milestone 7 (Execution) has a stable contract to design against well
  before Milestone 6's implementation is even reviewed — the same
  "next milestone can start designing against a known shape" benefit
  `StrategyDecision`'s freeze gave this one.
- `approved_allocation`'s upper bound makes "risk increases a strategy's
  requested size" a structurally impossible state, not just an untested
  one — closing off an entire class of bug before a single limit check is
  written.
- The `risk_adjustments`-on-size-cut requirement is a real, if small,
  behavioral improvement over `core/risk_manager.py` — Milestone 6's
  implementation is a *hardened* port, not a byte-for-byte one, and this
  is the first concrete instance of that.
- `decision_type` removes an entire class of latent bug where two
  consumers independently reconstruct "was this reduced?" from
  `approved`/`approved_allocation`/`strategy_reference.allocation` and
  disagree on a floating-point edge case (e.g. one checks `approved_
  allocation < strategy_reference.allocation`, another checks `bool(
  risk_adjustments)`) — one construction-time-validated field means there
  is exactly one place that comparison is made.
- Trade-off, accepted: `ExecutionDecision` deliberately does not carry
  whole-book actions (liquidate-all, halt-all-new-trades) that
  `CircuitBreakerDecision.liquidate` and the `HALT_DAY`/`HALT_WEEK`/
  `EMERGENCY_HARD_STOP` actions represent in the legacy module. Those are
  portfolio-wide state transitions, not a property of one `StrategyDecision
  -> ExecutionDecision` conversion for one symbol — forcing them into this
  contract would either bloat every single-symbol decision with
  book-wide fields that are almost always irrelevant, or misrepresent a
  portfolio-wide halt as if it were scoped to one symbol. How Milestone 6
  surfaces a whole-book circuit-breaker action (a separate method on
  `risk.service`, a distinct return type, an event) is left to that
  milestone's implementation — this ADR only notes the gap so it isn't
  mistaken for an oversight.
- Trade-off, accepted: because no implementation exists yet, this freeze
  is more speculative than a freeze written against real code would be —
  same acknowledgment ADR-008 made about `StrategyDecision`. `metadata`'s
  empty guaranteed-key set is the explicit hedge against that, as it was
  there.

## Alternatives Considered

- **Use `rejection_reason: str` (singular), as originally sketched** —
  rejected: `core/risk_manager.py::check_exposure_limits` already returns
  a `list[str]` because a single proposed trade can violate multiple
  limits simultaneously (e.g. gross exposure *and* sector exposure at
  once) — collapsing that to one string would lose information the
  legacy pure functions already compute correctly. `risk_adjustments:
  tuple[str, ...]` preserves it, matching `VetoDecision.reasons`'s actual
  shape.
- **A separate `risk_adjustments: Mapping[str, Any]` field alongside
  `metadata`, as originally sketched** — rejected: every other frozen
  contract in this handbook (`FeatureVector`, `RegimeState`,
  `StrategyDecision`) has exactly one free-form dict field. A second one
  here would invite an ambiguous split ("does this go in `metadata` or
  `risk_adjustments`?") for no real benefit once `risk_adjustments` is
  typed as a structured reason list rather than a grab-bag dict.
- **Reference `strategy_reference` by ID (`strategy_id` + `regime_id`)
  instead of embedding the full `StrategyDecision`** — rejected: the
  whole `StrategyDecision` is already a small, frozen, serializable value
  object. Embedding it gives every consumer of an `ExecutionDecision`
  full traceability (what was requested, what the strategy's own
  reasoning/confidence/expected holding period were) without a second
  lookup against a store this milestone doesn't need to build. The
  redundancy with `ExecutionDecision.timestamp`/`.symbol` is deliberate —
  it's what makes the consistency check in Decision point 5 possible.
- **Carry a `size_multiplier: float` field mirroring
  `CircuitBreakerDecision.size_multiplier` directly, instead of deriving
  it from `approved_allocation / strategy_reference.allocation`** —
  rejected: it would be a redundant, derivable value with its own edge
  case (division by zero when `strategy_reference.allocation == 0.0`) for
  no information `approved_allocation` doesn't already carry more
  directly.
- **Wait until Milestone 6's implementation exists, then freeze the
  contract retroactively (matching how ADR-006 was done for
  `RegimeState`)** — rejected per the same reasoning ADR-008 gave: the
  stricter before-implementation sequencing is the adopted process going
  forward, not a one-off exception limited to Milestone 5.
- **Leave the approved/reduced/rejected classification implicit,
  derivable only from `approved`, `approved_allocation`, and
  `strategy_reference.allocation`** — this was the original design;
  changed during review. Every consumer that wants to branch on the
  three-way outcome (dashboards, audit logs, the future Adaptive Learning
  milestone) would otherwise reconstruct the same comparison
  independently. `decision_type` gives that classification exactly one
  authoritative definition, validated at construction, the same role
  `CircuitBreakerAction` already plays for the legacy module's own
  multi-way classification rather than leaving it to a raw multiplier/
  liquidate tuple.
