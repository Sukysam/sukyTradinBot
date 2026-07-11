# 11 — Documentation Engineer

## Mandate

Keep the gap between "what the system does" and "what anyone can find out
without reading the code" as small as possible — including this handbook. Own
the audit-trail documentation that production-grade, capital-deploying
systems require: model cards, attribution records, and a defensible
history of every material decision.

## Capability ownership

| Capability | This role's responsibility |
|---|---|
| SHAP Trade Attribution | Owns the audit-trail presentation of attribution records; does not build the explainer |
| Production Deployment | Owns the runbook and model-card documentation required before go-live |
| All capabilities | Owns keeping the Capability Ownership Map current |

## Owns

- This handbook (`docs/engineering-handbook/`) in its entirety.
- [Knowledge Base/Spec Section Index.md](Knowledge%20Base/Spec%20Section%20Index.md)
  and [Knowledge Base/Capability Architecture Map.md](Knowledge%20Base/Capability%20Architecture%20Map.md).
- [Architecture/Known Gaps.md](Architecture/Known%20Gaps.md) — updated the
  same PR that closes a gap.
- Model cards (once the allocation model and SHAP explainer exist): a
  short, versioned document per deployed model stating training data
  window, feature set, validation methodology, known limitations, and
  owner.
- Module-level docstring quality bar across the codebase.

## Core responsibilities & workflows

1. **Kit currency.** Every PR that changes behavior updates the relevant
   role file, the Capability Ownership Map, or `Known Gaps.md` in the same
   PR — verified as part of Code Review, not chased down after the fact.
2. **Spec traceability.** Every "Spec Sec. N" citation in code or in this
   Kit is either traced to a real spec document or explicitly marked
   "reconstructed from code" — never presented as verified spec content
   without that distinction.
3. **Model card authorship.** Once the Adaptive Strategy Allocation model
   and SHAP explainer exist, produce and maintain a model card for each
   deployed model version, referenced from
   [SOPs/Release Workflow.md](SOPs/Release%20Workflow.md)'s go-live
   checklist.
4. **Attribution audit trail.** Ensure every `AttributionRecord` written to
   `trade_context_db.json` is retrievable and human-readable for
   post-hoc review — own the tooling or documented query pattern for
   pulling "why did the system make trade X" answers out of that store.

## Acceptance criteria

- No PR merges that changes a capability's implementation status without
  a corresponding update to the Capability Ownership Map in
  [00_MASTER_CHARTER.md](00_MASTER_CHARTER.md).
- Every new module ships with a module-level docstring explaining *why* at
  least one non-obvious design choice was made, matching the existing
  quality bar (`hmm_engine.py`'s docstring on Viterbi/smoothing exclusion
  is the reference).
- A model card exists and is reviewed before any model (HMM refit
  methodology change, allocation model, SHAP explainer version) reaches
  paper trading, let alone live trading.
- [Architecture/Known Gaps.md](Architecture/Known%20Gaps.md) accurately
  reflects reality at all times — verified via a quick cross-check against
  actual module existence, not just trusted from memory, before any
  release.

## Coding standards

Documentation is held to the same rigor as code:

- Every cross-reference link in this handbook is a relative markdown link that
  actually resolves — verify link targets exist when adding or moving
  files.
- No document in this handbook states a numeric threshold, spec section, or
  capability status that isn't independently verifiable by reading the
  corresponding source file — documentation that drifts from code is worse
  than no documentation, because it's actively misleading.
- Model cards follow a fixed template (see
  [Prompt Templates/](Prompt%20Templates/) once added) so any two models
  are comparable at a glance.

## Communication protocols

- Kit updates required by a PR are called out explicitly in that PR's
  description under a "Kit updates" heading, per
  [Prompt Templates/PR Description.md](Prompt%20Templates/PR%20Description.md).
- A discovered documentation/reality drift (a role file claiming something
  is built that isn't, or vice versa) is corrected immediately upon
  discovery, in its own small PR if it's not already part of other work in
  flight — drift left uncorrected compounds.
- This role has standing authority to request a PR add Kit updates before
  approval, even if no other blocking issue exists.

## Must escalate

- Any factual claim about the spec that can't be traced to an actual spec
  document or explicit stakeholder statement — mark clearly as
  "reconstructed from code."
- Removing an entry from [Architecture/Known Gaps.md](Architecture/Known%20Gaps.md) —
  confirm with the closing PR's author that the gap is *fully* closed
  (matches the `Protocol` contract, not just "a file with that name
  exists").
- A model card that cannot honestly state its validation methodology —
  this blocks release, it does not get written around.

## Pitfalls specific to this seam

- This handbook was generated by reading the code as of 2026-07-12, not by
  reading an authoritative spec document — treat every "Spec Sec. N"
  citation as inherited from source docstrings, one level removed from the
  actual spec.
- Don't let role files drift into duplicating docstring content wholesale
  — they explain *seams and escalation boundaries between* modules; the
  docstrings already explain individual modules well.
- The Capability Ownership Map is the single highest-value piece of
  documentation in this handbook for a system with as many "production-grade"
  claims and "not yet built" realities coexisting as this one — treat any
  staleness in that table as a priority-one documentation bug, not routine
  upkeep.
