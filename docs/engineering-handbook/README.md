# Engineering Handbook

This is the engineering handbook for **Regime Trader**: a Gaussian-HMM
volatility-regime equity trading platform (`regime-trader/`) plus a
standalone crypto backtesting sandbox (`backtest/`). It is the single,
canonical source of engineering documentation for this repository —
vision, principles, standards, process, and role-specific guidance — for
both human contributors and AI coding agents.

## Start here

Read [00_MASTER_CHARTER.md](00_MASTER_CHARTER.md) first, in full, before
any other document in this handbook. It is the constitution of the
repository: every other document here operates within the principles and
standards it sets out, and defers to it if the two ever conflict.

After the Master Charter, load only the one or two role charters (`01`–`12`)
relevant to the task at hand — you rarely need the whole handbook in
context at once.

## Structure

```
docs/engineering-handbook/
├── 00_MASTER_CHARTER.md      the constitution — read this first
├── README.md                 this file
├── 01–12_*.md                role charters (System Architect, Backend Engineer,
│                             Quant Researcher, Risk Manager, and 8 others —
│                             see the Master Charter's Roles Overview)
├── SOPs/                     standard operating procedures
├── Prompt Templates/         reusable prompts for common engineering tasks
├── Knowledge Base/           spec references, glossary, capability maps
├── Standards/                detailed coding/testing/documentation/risk standards
├── Architecture/             system design, data flow, known gaps
└── _archive/                 superseded documentation, kept for historical reference only
```

This is the complete, current structure — nothing here is a stub or
placeholder. If a linked document doesn't exist, that's a bug in the
handbook; report it rather than assuming the gap is intentional.

## History: the `Claude AI Development Kit/` merge

This handbook was built in two passes. The first pass produced a
role-by-role, Claude-session-oriented guide at the repository root,
`Claude AI Development Kit/`, with its own Master Charter and a complete
set of 01–12 role charters. The second pass produced a more
process-oriented handbook here, at `docs/engineering-handbook/`, starting
from just a Master Charter and README.

Those two efforts have since been **merged into this single tree**:

- The role charters, SOPs, Prompt Templates, Knowledge Base, Standards,
  and Architecture documents from `Claude AI Development Kit/` were moved
  here unchanged in substance (only "Kit" → "handbook" terminology and
  internal cross-references were updated).
- `00_MASTER_CHARTER.md` was rewritten to combine both charters' unique
  content: the process-oriented sections required of this handbook
  (vision, branching strategy, definition of done, review process, and
  the rest) plus the original Kit charter's Capability Ownership Map and
  numbered Non-Negotiable System Invariants, which are referenced by
  number throughout the role charters and were preserved exactly.
- The original `Claude AI Development Kit/` directory has been archived
  to [`_archive/claude-ai-development-kit/`](_archive/claude-ai-development-kit/)
  for historical reference. It is not maintained and should not be linked
  to from any current document — treat it as a frozen snapshot, not a
  second source of truth.

There is now exactly one documentation system for this repository:
`docs/engineering-handbook/`.
