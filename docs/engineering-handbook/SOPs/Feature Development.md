# SOP — Feature Development

Applies to any new capability inside `regime-trader/` (a new strategy, a new
feature column, a new risk check, a new pipeline). For `backtest/` changes,
steps 1–2 and 6 still apply; skip the risk/spec-gate steps, since that
sandbox trades no real capital.

## 1. Locate the owning role

Check [00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md)'s
role table. If the feature spans multiple roles' territory (e.g. a new
strategy touches both Signal Orchestrator and Risk Manager), identify each
seam explicitly before writing code.

## 2. Check the spec citation

Every non-trivial behavioral choice in this codebase traces to a "Spec Sec.
N" citation in a docstring. Before implementing, find the nearest existing
citation for the area you're touching in
[Knowledge Base/Spec Section Index.md](../Knowledge%20Base/Spec%20Section%20Index.md).
If none exists and the feature isn't purely internal refactoring, say so —
don't invent spec-sounding justification for a design choice that's
actually just convenient.

## 3. Check Known Gaps first

If the feature depends on something in
[Architecture/Known Gaps.md](../Architecture/Known%20Gaps.md) (e.g. anything
needing `config/settings.yaml` or the model store), that dependency should
usually be built first, or the new feature should be built against the
`Protocol` interface the way `main.py` already does — not against a
guessed-at concrete implementation.

## 4. Implement against the invariants

Re-check [00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md)'s
non-negotiable invariants list before writing code that touches feature
computation, order submission, or state files. The
[Standards/](../Standards/) directory has concrete checklists for the two
highest-stakes ones (anti-look-ahead, risk limits).

## 5. Test at the priority level the change deserves

See [09_QA_ENGINEER.md](../09_QA_ENGINEER.md)'s
priority order. A change to `risk_manager.py` or `feature_engineering.py`
needs boundary/regression tests before merge, not after.

## 6. Update the kit in the same PR

- New module → add it to the owning role file's "Owns" section.
- Closed a Known Gap → remove it from
  [Architecture/Known Gaps.md](../Architecture/Known%20Gaps.md) in this PR,
  not a follow-up (see
  [11_DOCUMENTATION_ENGINEER.md](../11_DOCUMENTATION_ENGINEER.md)).
- New spec-cited constant or behavior → add it to
  [Knowledge Base/Spec Section Index.md](../Knowledge%20Base/Spec%20Section%20Index.md).

## 7. Route through Code Review

See [Code Review Workflow.md](Code%20Review%20Workflow.md).
