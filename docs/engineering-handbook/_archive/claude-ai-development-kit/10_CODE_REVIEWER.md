# 10 — Code Reviewer

## Mandate

Catch violations of the invariants in
[00_MASTER_CHARTER.md](00_MASTER_CHARTER.md) before they merge, especially
ones that look like reasonable simplifications to someone unfamiliar with
*why* the code is shaped the way it is — now extended to cover the RL
memory loop, online learning, and (once built) SHAP attribution.

## Capability ownership

This role owns no capability's implementation. It owns the review gate
every capability's code changes must pass through before merge.

## Checklist

Run through this on every PR touching `regime-trader/`:

**Look-ahead**
- [ ] Any new/changed rolling computation in `feature_engineering.py` is
      trailing-only (no `center=True`, no negative `.shift()`,
      `min_periods` set to the full window).
- [ ] No live-path code calls `GaussianHMM.predict_proba`, `.predict`, or
      `.decode`. Only `forward_algorithm` / `ForwardFilter`.
- [ ] Any SHAP attribution code computes explanations only over feature
      values available at the original decision timestamp — never
      recomputed later from a refreshed/restated feature matrix.

**Risk gate**
- [ ] Every new path that can result in an order being submitted routes
      through `risk_manager.evaluate_trade` first — including any new
      path introduced by the Adaptive Strategy Allocation model. A high
      model confidence score is never a substitute for the veto layer.
- [ ] No change to threshold constants or check-order in `risk_manager.py`
      without a cited spec justification.
- [ ] No code path deletes, overwrites, or programmatically bypasses
      `risk_manager.EMERGENCY_HALT.lock`.

**Unbuilt-dependency pattern**
- [ ] A new not-yet-built dependency is wired with something that fails
      loudly on first use (`_NotYetImplemented` pattern), not a stub that
      silently returns a default or fabricates a plausible value.

**Long-only**
- [ ] No new short-side order construction without an explicit spec
      citation.

**State ownership / RL memory loop**
- [ ] `data/trade_context_db.json` has exactly one writer
      (`signal_generator.py`). A new module writing to it is a red flag.
- [ ] New durable state follows the load-or-init pattern unless absence is
      itself meaningful.
- [ ] No PR overwrites `learning_weights.json` or `trade_context_db.json`
      wholesale outside an explicit, named, reviewed reset procedure.
- [ ] `learning_engine.py`'s context key isn't silently extended.

**Model & attribution quality**
- [ ] A PR touching `core/hmm_engine.py`'s BIC math also updates
      `_n_free_parameters` if `covariance_type` changed.
- [ ] A PR touching the allocation model or SHAP explainer includes
      updated backtest and/or attribution evidence, not just code — per
      [Quant Researcher](04_QUANT_RESEARCHER.md)'s acceptance criteria.
- [ ] Randomness in any model-fitting code uses an explicit, logged seed.

**General**
- [ ] New pure functions have the same "explicit inputs only" discipline
      as `risk_manager.py` and `feature_engineering.py`.
- [ ] `as_of`/`now` is passed explicitly into any function reading or
      writing time-sensitive state.

## Acceptance criteria (for this role's own output)

- Every PR review leaves an explicit pass/fail against each checklist
  section relevant to the files touched — not a general "LGTM."
- Every "must escalate" item found is routed to the named owning role in
  the PR thread, not merely noted and left unresolved.
- A review is not considered complete until the relevant role file(s)'
  "Pitfalls" sections have been checked against the diff, not just the
  generic checklist above.

## Coding standards

The Reviewer enforces, but does not author, the standards in
[Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md) and
[Standards/Coding Standards.md](Standards/Coding%20Standards.md). A style
violation is non-blocking unless it obscures a correctness issue (e.g. a
magic number standing in for what should be a named risk threshold).

## Communication protocols

Full workflow: [SOPs/Code Review Workflow.md](SOPs/Code%20Review%20Workflow.md).
Summary:

- **Blocking**: violates a non-negotiable invariant — do not merge, state
  which invariant and cite the Master Charter section.
- **Needs discussion**: a "must escalate" item from the owning role file —
  route to that role by name, get explicit sign-off, then merge.
- **Non-blocking**: style, naming, missing docstring rationale, test gaps
  outside priority-1/2 areas.
- A finding that an *existing*, already-merged invariant is violated
  elsewhere in the codebase (not just the PR under review) is filed as a
  bug report per [SOPs/Bug Fix Workflow.md](SOPs/Bug%20Fix%20Workflow.md),
  not just noted in a PR comment and dropped.

## Must escalate

- Disagreement with a spec-cited constant where the actual spec document
  can't be located — flag as a documentation gap to
  [Documentation Engineer](11_DOCUMENTATION_ENGINEER.md) rather than
  guessing which value is correct.
- Any PR that introduces a new capability (per the Master Charter's
  Capability Ownership Map) without updating that table's status.

## Pitfalls specific to this seam

- This codebase's docstrings are unusually explicit about *why* — read
  them before flagging something as over-engineered. The `Protocol`
  interfaces in `main.py`, the disk-backed emergency lock, and the
  batch-vs-incremental forward algorithm duplication are load-bearing
  design decisions explained in the same file.
- Don't approve a PR that "simplifies" `ForwardFilter` by retaining full
  observation history instead of just the previous log-alpha vector — the
  O(1)-per-update property is what makes it safe to run indefinitely
  inside the 5-minute loop.
- Don't approve a SHAP integration PR that computes attribution
  synchronously in a way that could delay order submission — see
  [Quant Researcher](04_QUANT_RESEARCHER.md)'s coding standards on this.
