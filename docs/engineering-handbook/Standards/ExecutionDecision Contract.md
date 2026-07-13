# Standard — ExecutionDecision Contract

Governs `risk.models.ExecutionDecision`, the single output type the Risk
Manager (Milestone 6) is expected to produce. See
[Architecture/ADR/ADR-010-ExecutionDecision-Contract.md](../Architecture/ADR/ADR-010-ExecutionDecision-Contract.md)
for why this type is frozen *before* `src/risk/` exists — the same
"freeze interfaces before implementation" discipline
[ADR-008](../Architecture/ADR/ADR-008-StrategyDecision-Contract.md)
established for `StrategyDecision`, one milestone later. This document is
the binding contract for whoever implements the Risk Manager against it,
and for every future consumer (Execution, Adaptive Learning, Signal
Orchestration) that reads an `ExecutionDecision`.

## Why this exists, and why now

Milestone 6's mandate is narrow on purpose: convert a `StrategyDecision`
(plus a portfolio/account snapshot) into a sizing/approval verdict — an
answer to "is this trade allowed, and at what size" — not an order.
Nothing about broker connectivity, order type, stop placement, or fill
handling belongs in this milestone or this contract; that's Milestone 7
(Execution)'s job, consuming `ExecutionDecision` the same way Milestone 6
consumes `StrategyDecision`. Freezing the contract now, before a single
limit check is ported into `src/risk/`, means the Risk Manager's internals
(which limits exist, how they're checked, what order they're evaluated
in) can be built and iterated on freely without ever being confused with
the one thing every downstream consumer is allowed to depend on.

This contract is not designed from a blank page. `regime-trader/core/
risk_manager.py` already implements a real, tested veto layer —
`VetoDecision(approved, reasons, size_multiplier)` and
`CircuitBreakerDecision(action, size_multiplier, liquidate, reasons)` —
against the limits in
[Risk Limits Reference.md](Risk%20Limits%20Reference.md). `ExecutionDecision`
is grounded in what that module actually returns today, the same way
[ADR-007](../Architecture/ADR/ADR-007-HMM-Design.md) grounded `hmm`'s
causal algorithms in `core/hmm_engine.py` rather than inventing a shape
from scratch. Where this contract's fields don't map 1:1 onto the legacy
types, that's called out explicitly below and in ADR-010's Alternatives
Considered — not a silent divergence.

## Scope

Applies to `risk.models.ExecutionDecision` and whatever public method the
eventual `risk.service` module exposes to produce it (signature not yet
fixed — that's implementation, not contract). Does **not** freeze:

- The shape of the portfolio/account snapshot types consumed to produce a
  decision (`PortfolioState`, and the not-yet-designed `AccountState`) —
  implementation detail, the same way `StrategyDecision`'s freeze didn't
  fix `RegimeState`'s or `FeatureVector`'s internal representation beyond
  what those contracts already froze independently.
- Which limits exist, their threshold values, or the order they're
  checked in. [Risk Limits Reference.md](Risk%20Limits%20Reference.md)
  documents today's values as implemented in `core/risk_manager.py`;
  porting, extending, or re-tuning them in `src/risk/` is Milestone 6
  implementation work, escalated per
  [08_RISK_MANAGER.md](../08_RISK_MANAGER.md)'s "Must escalate" list where
  that document requires it — not fixed by this freeze.
- Whole-book actions (liquidating existing positions, halting all new
  trades) triggered by a circuit breaker. `ExecutionDecision` answers "is
  *this* `StrategyDecision` allowed to execute, and at what size" for one
  symbol — a portfolio-wide liquidate/halt action is a distinct concern
  with its own shape, deliberately not designed here. See ADR-010's
  Consequences for why this is an accepted gap, not an oversight.

## Required fields

| Field | Type | Guarantee |
|---|---|---|
| `timestamp` | `datetime` | Timezone-aware, normalized to UTC. The `StrategyDecision.timestamp` this decision was evaluated against — the causal "as of" time, not when the `ExecutionDecision` object was constructed. Must equal `strategy_reference.timestamp` (enforced at construction — see below). |
| `symbol` | `str` | Never empty. Must equal `strategy_reference.symbol` (enforced at construction). |
| `approved` | `bool` | Whether any position at all is permitted. `False` means reject outright — the strategy's intent does not get executed in any size this cycle. |
| `approved_allocation` | `float` | The allocation actually cleared for execution, as the same fraction-of-allocatable-capital unit as `StrategyDecision.allocation`. **Bounded `[0.0, strategy_reference.allocation]` — risk can only hold size steady or reduce it, never increase what the strategy asked for.** This is the risk layer's equivalent of invariant #5 ("every strategy is long-only"): the veto layer is a size-reducing filter by construction, not a sizing-up one. When `approved` is `False`, `approved_allocation` must be `0.0`. |
| `risk_adjustments` | `tuple[str, ...]` | Human-readable, one entry per limit or circuit breaker that shaped this decision — mirrors `VetoDecision.reasons`/`CircuitBreakerDecision.reasons` in the legacy module. **Empty tuple means a clean, full-size approval with nothing to note.** Non-empty whenever `approved` is `False` (enforced at construction — a rejection always cites at least one concrete reason, matching every real code path in `core/risk_manager.py::evaluate_trade`) **and** whenever `approved_allocation < strategy_reference.allocation` even while `approved` is `True` — this closes a real gap in the legacy `VetoDecision`, which silently drops the circuit-breaker reason when a trade is approved-but-size-cut (`CUT_SIZE_50`'s `size_multiplier=0.5` reaches the caller with no accompanying reason today). |
| `reasoning` | `str` | Never empty. A single human-readable synthesis of the decision, present even for a clean full-size approval (e.g. `"Approved at full size; no limits binding."`) — the same "never submit an order with no reconstructable rationale" principle [00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md) invariant #6 already requires of `StrategyDecision.reasoning`, applied one step downstream. Distinct from `risk_adjustments`: `reasoning` is always present and prose; `risk_adjustments` is structured and only present when something bound. |
| `strategy_reference` | `strategy.models.StrategyDecision` | The exact `StrategyDecision` this `ExecutionDecision` evaluates, embedded in full rather than referenced by ID — gives every consumer full traceability (`strategy_id`, `regime_id`, the strategy's own requested `allocation`, `confidence`, `reasoning`, `expected_holding_period`) without a separate lookup. See ADR-010's Alternatives Considered for why a full embed was chosen over a lightweight reference. |
| `metadata` | `Mapping[str, Any]` | Free-form. **No guaranteed keys yet** — same reasoning as `StrategyDecision.metadata`: no `src/risk/` implementation exists yet to honestly commit to specific keys. The first real implementation documents and freezes its actual guaranteed keys in the same change, following the same discipline as `StrategyDecision`. |

`ExecutionDecision` must be an immutable (`frozen=True`) dataclass,
matching `FeatureVector`, `RegimeState`, and `StrategyDecision`.

### Invariants enforced at construction

In addition to the per-field guarantees above, `__post_init__` enforces:

1. `symbol == strategy_reference.symbol` and `timestamp == strategy_reference.timestamp` — a mismatch means the decision was evaluated against the wrong `StrategyDecision`, a caller bug worth failing loudly on rather than silently trusting.
2. `0.0 <= approved_allocation <= strategy_reference.allocation`.
3. `not approved` implies `approved_allocation == 0.0`.
4. `not approved` implies `len(risk_adjustments) > 0`.
5. `approved_allocation < strategy_reference.allocation` implies `len(risk_adjustments) > 0` (covers the approved-but-reduced case).
6. `reasoning` is non-empty after stripping whitespace.

## Versioning policy

Follows the same three-tier pattern as
[StrategyDecision Contract.md](StrategyDecision%20Contract.md#versioning-policy):
a contract-shape version (this document's own "Contract history" below) is
independent of whatever internal versioning the eventual risk-limits
configuration defines. Currently **v1** (this freeze, ADR-010) — no
implementation exists yet to have driven a v2.

## Backward compatibility expectations

Same allowed/requires-a-new-ADR/never-permitted structure as
[StrategyDecision Contract.md](StrategyDecision%20Contract.md#backward-compatibility-expectations),
applied to `ExecutionDecision`. Notably: adding guaranteed `metadata` keys
once a real implementation exists is additive and doesn't require a new
ADR; loosening `approved_allocation`'s upper bound past
`strategy_reference.allocation` would — that bound is the risk layer's
core promise (it only ever reduces size, never increases it), and
weakening it is exactly the kind of decision
[08_RISK_MANAGER.md](../08_RISK_MANAGER.md)'s "Must escalate" list and
[01_SYSTEM_ARCHITECT.md](../01_SYSTEM_ARCHITECT.md) must sign off on
explicitly.

## Contract history

- **v1** ([ADR-010](../Architecture/ADR/ADR-010-ExecutionDecision-Contract.md)):
  initial freeze — `timestamp`, `symbol`, `approved`, `approved_allocation`,
  `risk_adjustments`, `reasoning`, `strategy_reference`, `metadata`. No
  implementation exists yet; this is the contract Milestone 6 is built
  against, not a retrofit onto existing code.

## Enforcement

Not yet mechanically enforced — there is no `risk.models` module yet. The
first implementation ships `tests/risk/test_models.py` enforcing every
constraint in the Required Fields table and the Invariants list above, in
the same change that adds the module, matching every other contract in
this handbook. `tests/contracts/test_executiondecision_contract.py` (or
equivalent, added to the existing `tests/contracts/` suite) verifies the
frozen field set, version metadata, and serialization round-trip the same
way the `FeatureVector`/`RegimeState`/`StrategyDecision` contract tests
already do.

## Ownership

Build and maintain: [Risk Manager](../08_RISK_MANAGER.md) — full ownership
of `src/risk/`, per that role charter's existing mandate over
`core/risk_manager.py`. Binding on every consumer: Execution (Milestone 7,
the next real consumer of `ExecutionDecision`), Adaptive Learning
(Milestone 9, evaluating realized outcomes against what was actually
approved, not just what the strategy requested), and Signal Orchestration
(Milestone 11). A consumer that needs a capability this contract doesn't
provide raises it against this document — it doesn't reach into Risk
Manager internals to work around it.
