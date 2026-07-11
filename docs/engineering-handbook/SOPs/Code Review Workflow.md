# SOP — Code Review Workflow

## 1. Author: self-check before requesting review

Run the full checklist in
[10_CODE_REVIEWER.md](../10_CODE_REVIEWER.md)
yourself first. Most of it is mechanical (grep for new order-submission call
sites, check rolling-window `min_periods`) and cheaper to catch before a
reviewer's time is spent.

## 2. Reviewer: read the relevant role file(s) before the diff

Identify which of the 13 roles in
[00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md)
own the changed files, and re-read their "Must escalate" and "Pitfalls"
sections before reading the diff — context that makes an otherwise-plausible
change look wrong (e.g. "simplifying" `ForwardFilter` to keep full history)
is easy to miss without it.

## 3. Apply the checklist

Work through [10_CODE_REVIEWER.md](../10_CODE_REVIEWER.md)
section by section: look-ahead, risk gate, unbuilt-dependency pattern,
long-only, state ownership, scope discipline.

## 4. Severity triage

- **Blocking**: violates a non-negotiable invariant from
  [00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md)
  (look-ahead, risk-gate bypass, emergency-lock tampering, short-side order,
  silent stub for a missing dependency). Do not merge.
- **Needs discussion**: a "must escalate" item from the owning role file —
  changing a threshold, extending a scope explicitly marked as deliberate
  and future, altering a `Protocol` contract. Route to the role that owns
  the escalation, get explicit sign-off, then merge.
- **Non-blocking**: style, naming, missing docstring rationale, test gaps
  outside the priority-1/2 areas in
  [09_QA_ENGINEER.md](../09_QA_ENGINEER.md).

## 5. If the review surfaces a pre-existing bug, not just a PR issue

Don't fold an unrelated fix into this PR. File it per
[Bug Fix Workflow.md](Bug%20Fix%20Workflow.md) instead, so the review of
*this* diff stays scoped and the bug fix gets its own regression test and
history.

## 6. Kit currency check

Confirm the PR updated the kit per step 6 of
[Feature Development.md](Feature%20Development.md) if applicable (new
module ownership, closed gap, new spec citation). A PR that changes
behavior without updating the kit is incomplete, not just under-documented.
