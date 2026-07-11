# Template — Close a Known Gap

Use when asking Claude to implement one of the components listed in
[Architecture/Known Gaps.md](../Architecture/Known%20Gaps.md).

```
Implement <component name> to close the gap tracked in
Architecture/Known Gaps.md item <N>.

Contract it must satisfy: <paste the relevant Protocol from main.py, e.g.
MarketDataProvider.get_ohlcv_history's signature and docstring>

Read first:
- 00_MASTER_CHARTER.md (non-negotiable invariants)
- <relevant role file>.md
- Architecture/Known Gaps.md item <N> (open questions, if any)
- Architecture/Data Flow.md (where this component sits in the pipeline)

Constraints:
- Match the Protocol signature exactly — don't change main.py's interface
  as part of this change; if the interface itself needs to change, stop and
  flag that separately (it's a System Architect decision).
- <any component-specific constraints, e.g. "must not call
  ForwardFilter.predict_proba/predict/decode" for anything HMM-adjacent>

When done:
- Update Architecture/Known Gaps.md: move this item from "Open gaps" to
  "Resolved gaps" with today's date.
- Update the owning role file's "Owns" section if this introduces a new
  module.
- Add or update tests per 09_QA_ENGINEER.md's
  priority guidance for this module.
```
