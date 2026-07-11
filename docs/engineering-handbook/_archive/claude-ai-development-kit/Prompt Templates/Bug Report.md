# Template — Bug Report

Use when reporting or asking Claude to investigate a suspected defect.
Fill in as much as you know; leave the rest for investigation, but don't
skip the classification — it changes how urgently this should be handled.

```
Observed behavior: <what happened>
Expected behavior: <what should have happened, and why — cite a spec
section from Knowledge Base/Spec Section Index.md if applicable>

Classification (see SOPs/Bug Fix Workflow.md step 1):
[ ] Silent wrong behavior (no crash, no error — a number or decision is
    just wrong). Treat as highest urgency.
[ ] Loud failure (exception/NotImplementedError/CRITICAL log). Check
    Architecture/Known Gaps.md first — this may be expected behavior, not
    a bug.
[ ] backtest/ sandbox bug (no live-capital impact).

Where observed: <module/function, or "production logs" / "paper trading" /
"backtest output">

Reproduction: <steps, or the minimal input that triggers it, if known>

If this touches core/risk_manager.py or the anti-look-ahead guarantee in
data/feature_engineering.py or core/hmm_engine.py, say so explicitly here —
these route through 08_RISK_MANAGER.md or
04_QUANT_RESEARCHER.md's escalation path, not a routine fix.
```

Ask Claude to write a failing regression test reproducing the issue before
attempting a fix, per [SOPs/Bug Fix Workflow.md](../SOPs/Bug%20Fix%20Workflow.md)
step 2.
