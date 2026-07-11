# Template — PR Description

Use for any PR touching `regime-trader/`, to make Code Review Workflow
faster for the reviewer.

```
## What
<one or two sentences>

## Why
<spec citation from Knowledge Base/Spec Section Index.md, linked bug report,
or "internal refactor, no behavior change">

## Role(s) / files touched
<from 00_MASTER_CHARTER.md's table — e.g.
"08_RISK_MANAGER.md territory: core/risk_manager.py">

## Invariant checklist (10_CODE_REVIEWER.md)
- [ ] No new look-ahead in feature/inference path
- [ ] Every new order-submission path routes through risk_manager.evaluate_trade
- [ ] No threshold/check-order change in risk_manager.py without spec citation
- [ ] Emergency-halt lock file untouched by any new code path
- [ ] New unbuilt dependencies fail loudly (_NotYetImplemented pattern), not silently
- [ ] No new short-side order construction
- [ ] trade_context_db.json still has exactly one writer
- [ ] learning_engine.py's context key not silently extended

## Kit updates included
- [ ] Architecture/Known Gaps.md updated (if a gap was closed)
- [ ] 00_MASTER_CHARTER.md Capability Ownership Map updated (if a
      capability's implementation status changed)
- [ ] Owning role file's "Owns" section updated (if a new module was added)
- [ ] Knowledge Base/Spec Section Index.md updated (if a new spec-cited
      constant/behavior was introduced)
- [ ] Model card added/updated (if this PR changes the HMM fit, the
      allocation model, or the SHAP explainer — see
      11_DOCUMENTATION_ENGINEER.md)

## Tests
<what's covered, referencing the priority order in
09_QA_ENGINEER.md>

## Paper vs. live impact
<does this change anything relevant to the live-trading gate in
SOPs/Release Workflow.md? Usually "no, paper-only impact.">
```
