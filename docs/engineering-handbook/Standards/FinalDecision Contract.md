# Standard — FinalDecision Contract

Governs `orchestration.models.FinalDecision` and `orchestration.models.
SignalInput`, the output types the Signal Orchestration layer (Milestone
11) is expected to produce. See
[Architecture/ADR/ADR-020-FinalDecision-Contract.md](../Architecture/ADR/ADR-020-FinalDecision-Contract.md)
for why these types are frozen *before* `src/orchestration/` exists at
all — following the same "freeze interfaces before implementation"
discipline every milestone since Milestone 5 has used. This document is
the binding contract for whoever implements the orchestrator against it,
and for every future consumer.

## Why this exists, and why now

Milestones 5, 9, and 10 each answer one question in isolation:
`StrategyDecision` ("what does the Strategy Engine think, given the
current regime?"), `LearningDecision` ("what would the learner have
recommended, in shadow?"), and `NewsSignal` ("what does the current
headline sentiment look like?"). Milestone 11 is the first milestone
that *reconciles* them — per direct product-owner review, the question
`FinalDecision` answers is different in kind, not just a fourth instance
of the same pattern: "given everything the platform currently believes,
what should the platform actually do?"

That reconciliation is deliberately conservative in its first version.
`StrategyDecision` remains the **primary** signal — `LearningDecision`
and `NewsSignal` are **advisory only**: the orchestrator may reduce
confidence, adjust the final allocation downward, or suppress a decision
outright when advisory signals disagree strongly with the primary one,
but nothing in this contract permits an advisory signal to increase the
allocation beyond what the Strategy Engine itself proposed, or to
substitute its own recommendation as the final answer. This mirrors
[ADR-010](../Architecture/ADR/ADR-010-ExecutionDecision-Contract.md)'s
`approved_allocation` bound (`[0.0, strategy_reference.allocation]`,
"risk only ever reduces size, never increases it") applied one layer
earlier in the pipeline, and for the same reason: a downstream layer
built to arbitrate advisory input should not be able to silently
manufacture conviction the upstream primary signal never had.

## Scope

Applies to `orchestration.models.FinalDecision` and `orchestration.
models.SignalInput`, and whatever public method the eventual
`orchestration.service` module exposes to produce them (signature not
yet fixed — that's implementation, not contract). Does **not** freeze:
the arbitration algorithm itself (policy-based — e.g. weighted-vote,
confidence-threshold, consensus, safety-first — is the expected shape
per product-owner direction, but no specific policy is mandated by this
contract), how `LearningDecision`/`NewsSignal` are retrieved or paired
with the `StrategyDecision` they advise, or whether/when `FinalDecision`
is actually wired into `risk.RiskService` as a replacement input for
`StrategyDecision` — see this document's "Wiring is not yet authorized"
section below.

## Required fields — `SignalInput`

One `SignalInput` per advisory source (`memory`, `nlp`), always present
on a `FinalDecision` even when that source had nothing to contribute —
`considered=False` in that case, rather than omitting the field, so a
consumer never has to handle an `Optional` sub-schema.

| Field | Type | Guarantee |
|---|---|---|
| `source` | `str` | Never empty. Identifies which advisory subsystem this input came from (e.g. `"memory"`, `"nlp"`). |
| `considered` | `bool` | Whether this source had a real signal available to factor in (e.g. a `LearningDecision` existed for this `(symbol, strategy_id, regime_id)` context, or a `NewsSignal` existed for this symbol within the relevant window). `False` means the orchestrator had nothing from this source, not that it disagreed. |
| `agrees` | `bool` | Whether this source's signal aligned with the primary `StrategyDecision`'s direction. Must be `False` when `considered` is `False` — a source that contributed nothing cannot be recorded as agreeing with anything, enforced at construction, not left to a call site's discipline. |
| `weight` | `float` | `[0.0, 1.0]`. How much this source actually influenced `FinalDecision.final_allocation`, as the orchestrator's own policy computed it. Must be `0.0` when `considered` is `False`, for the same reason `agrees` must be `False`. |

`SignalInput` must be an immutable (`frozen=True`) dataclass.

## Required fields — `FinalDecision`

| Field | Type | Guarantee |
|---|---|---|
| `timestamp` | `datetime` | Timezone-aware, normalized to UTC. The `StrategyDecision.timestamp` this arbitration was performed against — the causal "as of" time. |
| `symbol` | `str` | Never empty. |
| `strategy_id` | `str` | Never empty. Copied from the primary `StrategyDecision.strategy_id`. |
| `regime_id` | `int` | Copied from the `RegimeState` in force when the primary `StrategyDecision` was made. `>= 0`. |
| `primary_allocation` | `float` | The primary `StrategyDecision.allocation`, unmodified. `[0.0, 1.0]`. Recorded here (not just derivable by joining back to the original `StrategyDecision`) so `FinalDecision` is self-contained and auditable without needing state that may no longer exist by the time anyone reviews it — the same reasoning [Standards/LearningDecision Contract.md](LearningDecision%20Contract.md) already gives for `production_allocation`. |
| `final_allocation` | `float` | The orchestrator's actual decision. `[0.0, primary_allocation]` — **never greater than the primary signal's own allocation.** This is the type-level enforcement of "Memory and NLP are advisory, not authoritative" described above; a future decision to let an advisory signal increase allocation beyond the primary would be a deliberate, reviewed contract change, not something achievable by tuning a policy's weights within today's bound. |
| `confidence` | `float` | `[0.0, 1.0]`. The orchestrator's own aggregate confidence in `final_allocation` — distinct from `StrategyDecision.confidence`, `LearningDecision.confidence`, and any sentiment-derived confidence from a `NewsSignal`. How it's computed from those inputs is implementation detail (per Scope), not fixed by this field's existence. |
| `outcome` | `ArbitrationOutcome` (`str, Enum`: `CONFIRMED`, `ADJUSTED`, `SUPPRESSED`) | Explicit tri-state classification of what the orchestrator actually did, validated at construction against `primary_allocation`/`final_allocation` so a caller cannot construct a self-contradictory `FinalDecision` — the same discipline `ExecutionDecision.decision_type` already established. `CONFIRMED` iff `final_allocation == primary_allocation`. `SUPPRESSED` iff `final_allocation == 0.0` and `primary_allocation > 0.0` (a real suppression event caused by arbitration — distinct from the primary strategy itself proposing `0.0`, which is `CONFIRMED`). `ADJUSTED` iff `0.0 < final_allocation < primary_allocation`. |
| `learner_input` | `SignalInput` | The Memory / `LearningDecision` advisory input. |
| `news_input` | `SignalInput` | The NLP / `NewsSignal` advisory input. |
| `rationale` | `str` | Human-readable explanation of the arbitration outcome. Never empty — the same "never produce an unexplained decision" principle every prior decision-shaped contract in this handbook already carries (`StrategyDecision.reasoning`, `ExecutionDecision.reasoning`, `LearningDecision.rationale`). |
| `metadata` | `Mapping[str, Any]` | Free-form. No guaranteed keys yet — first real implementation documents and freezes whatever it needs, same discipline every fresh contract in this handbook follows. Per-subsystem version traceability (which HMM/strategy/memory/nlp model versions contributed) belongs here rather than as a dedicated required field, matching [ADR-008](../Architecture/ADR/ADR-008-StrategyDecision-Contract.md)'s explicit reasoning for `StrategyDecision.metadata`. |

`FinalDecision` must be an immutable (`frozen=True`) dataclass, matching
every other decision-shaped contract in this handbook.

## Wiring is not yet authorized

Stated explicitly, the same way [ADR-016](../Architecture/ADR/ADR-016-LearningDecision-Contract.md)'s
Standards document states the shadow-mode guarantee for `LearningDecision`:
**this contract freeze does not authorize replacing `StrategyDecision`
with `FinalDecision` as `risk.RiskService`'s actual input.** `FinalDecision`
is a real, constructible, potentially-computed-in-production artifact —
unlike Milestone 9/10's fully shadow-only outputs, nothing here forbids
an implementation from running the orchestrator against live decisions —
but wiring its output into the execution path so that `final_allocation`
(not `StrategyDecision.allocation`) is what `risk.RiskService` actually
evaluates is a separate, later, explicitly-authorized decision. Per
[00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md) invariant #2 ("the risk
veto is the only gate on order submission"), *something* must reach
`RiskService` for every trade; until wiring is explicitly authorized,
that something remains the unarbitrated `StrategyDecision`, exactly as
every milestone before this one has produced it.

## Versioning policy

Follows the same three-tier pattern as every prior contract in this
handbook. Currently **v1** (this freeze, ADR-020) — no implementation
exists yet to have driven a v2.

## Backward compatibility expectations

Same allowed/requires-a-new-ADR/never-permitted structure as
[RegimeState Contract.md](RegimeState%20Contract.md#backward-compatibility-expectations),
applied to `FinalDecision`/`SignalInput`. Notably: adding guaranteed
`metadata` keys once a real implementation exists is additive; widening
`final_allocation`'s bound beyond `[0.0, primary_allocation]` (letting an
advisory signal increase allocation) or actually wiring `FinalDecision`
into `RiskService` would each require a new ADR and explicit
[01_SYSTEM_ARCHITECT.md](../01_SYSTEM_ARCHITECT.md) sign-off — both are
exactly the kind of decision this contract's conservative-by-construction
design exists to make deliberate, not incidental.

## Contract history

- **v1** ([ADR-020](../Architecture/ADR/ADR-020-FinalDecision-Contract.md)):
  initial freeze — `SignalInput` (`source`, `considered`, `agrees`,
  `weight`) and `FinalDecision` (`timestamp`, `symbol`, `strategy_id`,
  `regime_id`, `primary_allocation`, `final_allocation`, `confidence`,
  `outcome`, `learner_input`, `news_input`, `rationale`, `metadata`). No
  implementation exists yet; this is the contract Milestone 11 is built
  against, not a retrofit onto existing code.

## Enforcement

Not yet mechanically enforced — there is no `orchestration.models` module
yet. The first implementation ships `tests/orchestration/test_models.py`
enforcing every constraint in the Required Fields tables above (frozen
dataclasses, UTC timestamp, non-empty string fields, `regime_id >= 0`,
every allocation/confidence/weight field in its documented bound,
`final_allocation <= primary_allocation`, `outcome` consistent with the
allocation fields per the rule above, `SignalInput.agrees`/`weight`
forced when `considered` is `False`), in the same change that adds the
module, matching every other contract in this handbook.

## Ownership

Build and maintain: [07 Signal Orchestrator](../07_SIGNAL_ORCHESTRATOR.md),
per that role's existing mandate over cross-source arbitration. A
consumer that needs a capability this contract doesn't provide — in
particular, anything that would let `FinalDecision` actually replace
`StrategyDecision` at the `RiskService` boundary — raises it against this
document and [01_SYSTEM_ARCHITECT.md](../01_SYSTEM_ARCHITECT.md)
explicitly. It does not reach into `orchestration` internals, or into
`risk`/`execution`, to wire that up unreviewed.
