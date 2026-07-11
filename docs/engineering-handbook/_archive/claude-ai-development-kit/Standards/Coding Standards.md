# Standard — Coding Standards

Repository-wide engineering standards that apply across every role. This
complements [Python Style Guide.md](Python%20Style%20Guide.md) (which
covers language-level conventions already in use) with process-level
standards for how code is structured, reviewed, and shipped in a
capital-deploying system.

## Definition of Done (applies to every PR, every role)

A change is not done until:

1. It satisfies the acceptance criteria in the owning role's charter
   (`Claude AI Development Kit/NN_ROLE.md`).
2. It passes the relevant tier of testing per
   [09_QA_ENGINEER.md](../09_QA_ENGINEER.md)'s priority order.
3. It passes the checklist in
   [10_CODE_REVIEWER.md](../10_CODE_REVIEWER.md).
4. Any Kit documentation it invalidates (role file ownership, Known Gaps,
   Capability Ownership Map) is updated in the same PR.
5. It does not silently expand scope beyond its stated purpose — a bug fix
   fixes the bug; a feature adds the feature; refactors are scoped and
   labeled as such.

## Module and function design

- One module, one responsibility. If a module's docstring needs "and" to
  describe its purpose, consider whether it should be two modules.
- Pure functions by default. Reach for a class only when there's genuine
  state to hold across calls (`ForwardFilter`, `LearningEngine`,
  `EquityTracker`) — not as a default organizing structure.
- Dependency injection over hidden construction. Any component with an
  external dependency (a broker client, a model, a file path) receives it
  as a constructor/function parameter, never constructs it internally —
  this is what makes `OrderExecutor`, `SignalGenerator`, and `ModelStore`
  all independently testable with fakes.
- Fail at the boundary, fail loudly. Validate inputs where they enter the
  system (a `Protocol` implementation's return value, a user-facing
  config), not deep inside a call chain where the error message will be
  disconnected from its cause.

## Error handling

- Catch specific exceptions (`APIError`, `ValueError`), never bare
  `except Exception` unless the code explicitly intends to contain and log
  an unknown failure without crashing a long-running loop (see
  `_process_ticker`'s per-ticker exception handling in `main.py` — a
  deliberate exception to the specificity rule, because one ticker's
  failure must never take down the structural loop for every other
  ticker).
- Never swallow an exception silently. At minimum, log it with enough
  context (which ticker, which trade, which model version) to reconstruct
  what happened without re-running the system.
- Distinguish "this is a bug, fix the code" (`ValueError` on malformed
  input) from "this is an expected operational condition" (a rejected
  order, a missing file on first run) in both the exception type used and
  the log level.

## Testing

- Every pure function gets unit tests covering its documented edge cases,
  not just its happy path.
- Every function with a documented invariant (purity, idempotency,
  numerical equivalence between two implementations) gets a test that
  verifies that invariant directly, not just a test that happens to pass.
- Mocks/fakes stand in for external systems (Alpaca, FinBERT) in the fast
  suite; the real systems are exercised only in an explicitly separate,
  slower integration tier.

## Version control

- Commits are scoped to one logical change; a PR that mixes a bug fix with
  an unrelated refactor is split before merge.
- Commit messages and PR descriptions state *why*, not just *what* — the
  diff already shows what changed.
- No direct commits to the trunk branch for anything beyond trivial
  documentation fixes — all code changes go through
  [SOPs/Code Review Workflow.md](../SOPs/Code%20Review%20Workflow.md).

## Security & secrets

- No credential, API key, or secret is ever committed to the repository,
  logged, or included in an exception message.
- No code path constructs a broker/API client from a hardcoded credential
  — always sourced from environment/secret-manager injection, per
  [12_DEVOPS_ENGINEER.md](../12_DEVOPS_ENGINEER.md).

## Model and data code (HMM, allocation model, SHAP, sentiment)

- Every source of randomness takes an explicit, logged seed.
- Every model-input feature computation is unit-tested for the
  anti-look-ahead property per
  [Anti-Lookahead Checklist.md](Anti-Lookahead%20Checklist.md).
- Every persisted model artifact records the code version and data window
  used to produce it.
