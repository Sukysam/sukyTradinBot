# Standard — Communication Protocols

How roles talk to each other, escalate, and report status, across both
human-only teams and Claude sessions acting under this Kit. The goal is
that nothing load-bearing lives only in someone's head or in a chat
message that scrolls away — every role file's "Communication Protocols"
section points back here for the shared conventions.

## Severity language

Used consistently in PR descriptions, incident reports, and escalations so
severity is unambiguous across roles:

| Severity | Meaning | Response expectation |
|---|---|---|
| **Blocking** | Violates a non-negotiable invariant ([00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md)) | Do not merge/deploy. Fix before proceeding. |
| **Incident** | A `CRITICAL`-logged production event (circuit breaker, emergency halt, liquidation failure) | Page per [SOPs/Incident Response Runbook.md](../SOPs/Incident%20Response%20Runbook.md); write-up required regardless of self-recovery. |
| **Needs discussion** | A "must escalate" item from a role charter | Route to the named owning role; get explicit sign-off before merge. |
| **Non-blocking** | Style, naming, missing docstring rationale, test gaps outside priority-1/2 areas | Note in review; does not block merge. |

## Escalation format

When raising a "must escalate" or "blocking" item, state:

1. **What** — the specific change or finding.
2. **Which invariant/rule** — cite the Kit section (e.g. "Master Charter
   invariant #2: risk veto is the only gate").
3. **Owning role** — who must sign off, by role name from the Master
   Charter's table.
4. **Blast radius** — what breaks if this ships unresolved.

Address escalations to the owning role explicitly (by role name), in the
PR thread or task conversation — never leave an escalation implicit for a
reviewer to infer from a diff.

## Status updates on multi-step work

For any task spanning more than a couple of tool calls or commits:

- State what you're about to do before doing it (one sentence).
- Report at meaningful checkpoints: a finding, a direction change, a
  blocker — not after every individual action.
- End with a concise summary: what changed, what's left, what needs
  another role's input.

This mirrors how a Claude session should narrate its own work to a human
overseeing it, and how one role should narrate handoffs to another.

## Handoffs between roles

A handoff is complete only when the receiving role has everything needed
to act without re-deriving context:

- The relevant files/modules named explicitly.
- The specific question or decision needed.
- Links to the Kit sections that frame the decision (the receiving role's
  own charter almost always has a relevant "Acceptance Criteria" or "Must
  Escalate" section — point to it rather than re-explaining it).

Example, System Architect → Backend Engineer:
> "The `MarketDataProvider` Protocol contract is finalized in `main.py`
> (see [01_SYSTEM_ARCHITECT.md](../01_SYSTEM_ARCHITECT.md)'s import
> direction section). `broker/alpaca_client.py` needs an implementation
> satisfying it — see [03_BACKEND_ENGINEER.md](../03_BACKEND_ENGINEER.md)'s
> acceptance criteria for the contract test it needs."

## Reporting model/data findings

Quantitative findings (backtest results, SHAP summaries, BIC scores, drift
detections) are reported with:

- The full methodology (train/test split, data window, seed), never just
  a headline number.
- Both favorable and unfavorable results — a backtest that underperforms
  buy-and-hold is reported as clearly as one that outperforms.
- An explicit statement of what would change the finding's confidence
  (more data, a longer out-of-sample window, a different market regime).

## Documentation currency

Any communication that establishes a new fact about the system (a
capability's status changed, a threshold was revised, a gap was closed) is
followed by a Kit update in the same PR — a decision communicated only in
chat/PR comments and never written into the Kit is, for this project's
purposes, not yet decided. See
[11_DOCUMENTATION_ENGINEER.md](../11_DOCUMENTATION_ENGINEER.md).
