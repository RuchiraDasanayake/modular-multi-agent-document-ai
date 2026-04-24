# Project Direction

This is the living document for the current project phase.

Unlike `docs/SYSTEM_CONTRACT.md`, this file is expected to change as goals evolve.

## Current Phase

`Dataset-driven stabilization and evidence build`

The repository is now in a dataset-driven stabilization phase.

Cleanup still matters, but only when it directly improves:

- external labeled evaluation
- canonical runtime reliability
- adaptive-safe evidence quality
- operator-visible auditability

## Primary Goal

Make `adaptive_safe` and the extraction runtime defensible on real labeled data without widening the claim or breaking the canonical product path.

That means:

- keeping the paper claim narrow: `static` vs `adaptive_safe`
- using external labeled data to find repeated extraction failures early
- fixing only high-ROI issues that improve reliability across many cases
- preserving one clear canonical runtime path
- separating exact labeled metrics from runtime proxy reward
- freezing mapping, config, and evidence before writing final results
- simplifying or removing work that does not help the evidence loop
- keeping docs aligned with the actual execution plan

## Current In-Scope Work

- stage and evaluate `CORD v2` as the primary external labeled dataset
- define a strict receipt-field mapping for the first exact-metric loop
- run repeated `static` vs `adaptive_safe` evaluations through the canonical runtime
- inspect failures manually on small deterministic subsets before scaling
- prioritize only high-ROI fixes in `IDPO`, `frontend`, or `AHMN` that improve evidence quality or runtime reliability
- preserve and clarify run artifacts needed for exact scoring and adaptive containment review
- keep the operator UI and run artifacts aligned with the adaptive-safe claim
- quarantine or defer evaluation paths that do not serve the current claim
- keep docs in sync with the active testing and evidence plan

## Current Non-Goals

For the current phase, do not prioritize:

- major new product features
- broad frontend redesign
- cross-service architecture rewrites
- broad benchmark claim expansion across many document families at once
- adding alternate entrypoints unless explicitly required
- Vercel-first deployment redesign
- broad UI expansion
- adding new knobs, panels, or metrics before the evaluation loop is stable
- multi-dataset expansion before `CORD v2` mapping and scoring are stable
- line-item research expansion before flat receipt totals and containment behavior are reliable

## Current Success Criteria

This phase is successful when:

- the team can run a deterministic labeled subset through the canonical runtime and score it exactly
- `CORD v2` staging, mapping, and scoring are reproducible and documented
- repeated failure categories are known and triaged by ROI instead of guessed ad hoc
- high-ROI fixes improve exact extraction quality, structured-output quality, or containment visibility
- the canonical runtime path remains stable and documented
- exact labeled metrics remain clearly separated from runtime proxy reward
- the main operator-facing UI and run artifacts clearly expose adaptive-safe behavior
- evidence can be frozen without changing runtime labels or adding paper-only branches

## Document Roles

Use the docs this way:

- `docs/PROJECT_DIRECTION.md`
  The current goal, scope, and non-goals
- `docs/DATASET_PLAN.md`
  The active dataset ladder and labeling strategy
- `docs/CORD_EVALUATION_PLAN.md`
  The active external labeled testing plan and failure triage loop
- `docs/SYSTEM_CONTRACT.md`
  What the system currently is and must emit
- `docs/IDPO_CLEANUP_PASS1.md`
  The cleanup plan when a runtime reduction directly helps the evidence loop
- `docs/SYSTEMATIC_REDUCTION_PLAN.md`
  The reduction order and decision method for cleanup work that remains in scope
- `docs/FRONTEND_IDPO_PAGE_REDUCTION_PLAN.md`
  The active plan for the first frontend cleanup target
- `docs/FRONTEND_IDPO_RUN_DETAIL_REDUCTION_PLAN.md`
  The active plan for reducing the run-detail inspection surface
- `docs/JOB_UI_CONTRACT.md`
  The target job-first operator model for the next frontend phase
- `AGENTS.md`
  Rules for AI tools working in the repo

## When Goals Change

If the team changes direction, update docs in this order:

1. `docs/PROJECT_DIRECTION.md`
2. `docs/SYSTEM_CONTRACT.md`
3. the active cleanup or implementation plan doc
4. `AGENTS.md` if the working rules changed

Do not start major implementation first and explain it later in docs.

## Goal Change Template

When changing direction, record it in this format:

```text
Date:
Old phase:
New phase:
Reason:
What is now in scope:
What is now out of scope:
Which docs must be updated:
Which code areas are most affected:
```

## Current Next Step

Run the evaluation program in strict order:

1. set up the external labeled path first
   Use `CORD v2` as the first serious dataset and keep the first mapped field set small and exact
2. build a deterministic pilot subset and manual review loop
   Start with a small receipt subset, inspect failures, and classify them before making fixes
3. apply only high-ROI fixes
   Prioritize repeated normalization, extraction, logging, and containment issues over broad refactors
4. freeze the mapping and scoring path before scaling
   Do not keep changing what counts as correct while collecting evidence
5. run larger validation passes only after the small loop is stable
6. keep cleanup work scoped to what directly improves reliability, auditability, or exact evaluation
