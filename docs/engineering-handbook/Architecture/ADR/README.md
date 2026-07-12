# Architecture Decision Records (ADRs)

This folder records *why* a significant, hard-to-reverse engineering
decision was made — not what the code does (docstrings do that per
[Standards/Python Style Guide.md](../../Standards/Python%20Style%20Guide.md))
and not current status (that's [PROJECT_STATUS.md](../../../../PROJECT_STATUS.md)).
An ADR exists so that months from now, when someone asks "why did we do
it this way," the answer is a document, not a half-remembered Slack
thread or a git-blame archaeology session.

## When to write one

Write an ADR for a decision that is:

- **Significant** — it shapes how future code gets written, not a local
  implementation detail.
- **Hard to reverse** — changing it later means touching many call sites,
  not one function.
- **Non-obvious** — a reasonable engineer could have made a different
  choice, and the reasoning for this one isn't self-evident from the code.

Don't write one for routine implementation choices already covered by
[Standards/Coding Standards.md](../../Standards/Coding%20Standards.md) or
[Standards/Python Style Guide.md](../../Standards/Python%20Style%20Guide.md)
— those are the default; an ADR is for a deliberate departure from a
default, or a foundational choice those standards themselves rest on.

## Numbering and naming

`ADR-NNN-Short-Title.md`, zero-padded to three digits, numbered
**sequentially and never reused**, even if a later ADR supersedes an
earlier one. The initial convention is one ADR per milestone (matching
[PROJECT_STATUS.md](../../../../PROJECT_STATUS.md)'s numbering —
`ADR-001-Foundation.md` for Milestone 1, `ADR-002-Market-Data.md` for
Milestone 2, and so on), bundling every significant decision made during
that milestone into one record. A milestone with no significant
architectural decisions doesn't need an ADR just to keep the count
matching — the sequence only needs to stay monotonically increasing, not
gapless-and-1:1-with-milestones forever. If a decision significant enough
to warrant its own record comes up between milestones, give it the next
number regardless of milestone boundaries.

## Status lifecycle

Each ADR (and, since ADRs in this repo bundle multiple decisions, each
decision within one) carries a status:

| Status | Meaning |
|---|---|
| Proposed | Under discussion, not yet acted on |
| Accepted | Decided and reflected in the current codebase |
| Superseded by ADR-NNN | No longer current; the linked ADR replaces it |
| Deprecated | No longer current, with no direct replacement |

**Never edit or delete an accepted decision to reflect a later change of
mind.** Write a new ADR that supersedes it, and mark the old one
`Superseded by ADR-NNN`. The old ADR's reasoning is still valuable
historical context — it usually explains why the *original* choice looked
right at the time, which is exactly the information most likely to matter
the next time someone reconsiders it.

## Format

Use [TEMPLATE.md](TEMPLATE.md) for each decision. At minimum: Context
(what problem/tension prompted a choice), Decision (what was chosen,
stated plainly), Consequences (both the benefit and the accepted
trade-off — an ADR that lists no downside wasn't looking hard enough),
and Alternatives Considered (what else was on the table and why it lost).

## Relationship to the rest of the handbook

- [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md) is *prescriptive* —
  the standards every decision must operate within.
- ADRs are *explanatory* — why a specific decision satisfies (or, rarely,
  deliberately deviates from and amends) those standards.
- [Architecture/Known Gaps.md](../Known%20Gaps.md) is *status* — what
  isn't built yet.
- [PROJECT_STATUS.md](../../../../PROJECT_STATUS.md) is *progress* — which
  milestone is done.

An ADR that reveals a standard needs to change updates the Master Charter
in the same change, per Definition of Done — it doesn't just sit here
contradicting it.
