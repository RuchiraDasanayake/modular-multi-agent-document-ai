# Frontend IDPO Run Detail Reduction Plan

This document is the active cleanup plan for:

- `frontend/src/app/dashboard/idpo/runs/[runId]/page.tsx`

It should be used together with:

1. `docs/PROJECT_DIRECTION.md`
2. `docs/SYSTEM_CONTRACT.md`
3. `docs/SYSTEMATIC_REDUCTION_PLAN.md`
4. `docs/FRONTEND_IDPO_PAGE_REDUCTION_PLAN.md`

## Section Note

```text
Section: IDPO run detail page
Owner service: frontend
Cleanup type: UI reduction and responsibility cleanup
Files in scope: frontend/src/app/dashboard/idpo/runs/[runId]/page.tsx and only the smallest supporting frontend files required by the pass
Classification: core operator UI
Primary action: simplify
Acceptance check: the run page makes adaptive extraction results, route taken, and attention-needed status obvious before any subsystem-specific detail
```

## Why This Page Exists

This page is the main run-level inspection surface after a document batch completes.

It should help an operator answer these questions quickly:

1. what happened in this run
2. what adaptive route was taken
3. what extraction outcome came back
4. which documents need attention
5. where to go next for deeper inspection

If the page behaves like a subsystem dashboard first, it is failing its job.

## Current Problems

The current page is still overloaded.

### 1. It Is Tab-Heavy And Subsystem-First

The file is about `805` lines and exposes `9` top-level tabs:

- `Overview`
- `Documents`
- `Transparency`
- `Extraction`
- `Validation & Guardrails`
- `Recovery & Escalation`
- `Provenance`
- `Shadow Mode`
- `Retrieval/Answering`

That is too many top-level surfaces for the main run view.

### 2. The Opening Screen Prioritizes Metrics Over Results

The `Overview` tab currently leads with many counters such as:

- latency
- cost
- retries
- rollbacks
- blocked policies
- advice accepted
- advice offered
- policy changed
- direct-scored docs
- feedback logged
- fallbacks
- deferred/review

Some are useful, but the set as a whole hides the actual extraction outcome.

### 3. The Run Page Duplicates Secondary And Low-ROI Surfaces

The page currently includes top-level access to:

- transparency artifacts
- provenance timeline
- shadow comparisons
- retrieval and answering artifacts
- rerun-with-policy controls
- metrics JSON

Those may be useful for research support, but they should not dominate the first run-level inspection path.

### 4. The Document Table Is Wider Than The Main Question

The `Documents` table includes many columns at once:

- static policy
- recommendation
- selected policy
- advice
- advice source
- fallback
- safety
- feedback
- validation
- schema
- latency

That is too much to scan if the real question is whether adaptive extraction worked and what needs review.

## Value Decision Map

Use this map for the run-detail cleanup.

### Keep

Keep on the run page:

- run identity and status
- document count and basic run context
- a small run-level summary of adaptive routing outcomes
- a document list focused on:
  - document identity
  - route or selected policy
  - extraction outcome
  - review-needed state
  - direct link to document detail
- one lightweight warnings or issues area

These directly support clear adaptive extraction inspection.

### Simplify

Simplify on the run page:

- the hero/header copy
- overview summary cards
- document table columns
- extraction tab or document preview behavior
- warnings and metrics presentation

These add value, but they are currently too broad.

### Quarantine

Quarantine from the primary run view:

- transparency artifact viewing
- provenance timeline
- shadow mode comparisons
- retrieval and answering artifacts
- rerun-with-policy controls
- raw metrics JSON

These are supporting research and debugging surfaces, not the main inspection path.

They should move behind a secondary route, an advanced section, or a later pass if they still matter.

### Remove

Remove from the main run page if no immediate research inspection value is shown:

- compare-run entry from the run header
- oversized metric walls
- duplicate JSON viewers
- low-signal counters that do not change operator action
- any panel whose first value is subsystem jargon instead of extraction outcome

## Decision Criteria For This Page

Keep something on the run page only if it helps the operator answer one of these quickly:

1. Which documents succeeded cleanly?
2. Which documents need review?
3. What adaptive route or policy was used?
4. What extraction result quality or confidence signal do I have?
5. Which document should I open next?

If a panel does not help answer one of those, it should not sit at top-level.

## Target Shape

The target shape for the run page is:

1. run header
2. small adaptive outcome summary
3. document table or cards with only the highest-value columns
4. one light warnings or issues block
5. links out to document detail and any advanced research surfaces

It should not be the place where every subsystem exposes its own dashboard.

## Planned Passes

### Pass UI-4A: Run Surface Triage

Goal:

- identify which current tabs are core versus supporting
- reduce the run page to the surfaces needed for adaptive extraction inspection

Expected outcome:

- a smaller primary run page
- fewer top-level tabs or no tabs at all
- no subsystem-first opening view

Progress on current branch:

- removed the `9`-tab run dashboard structure entirely from `frontend/src/app/dashboard/idpo/runs/[runId]/page.tsx`
- reduced the run page to a single run summary strip plus one document table
- removed subsystem-first surfaces from the main run path:
  - transparency
  - provenance
  - shadow mode
  - retrieval and answering
  - inline metrics walls
  - rerun-with-policy controls
- kept only the highest-value run inspection data:
  - run status
  - document count
  - processed count
  - needs review count
  - policy changed count
  - failed count
  - direct link to document detail

### Pass UI-4B: Documents Table Reduction

Goal:

- cut the document table down to the fields that directly support review

Expected outcome:

- faster scanning
- clearer emphasis on extraction outcome and attention-needed state

### Pass UI-4C: Advanced Surface Isolation

Goal:

- move or demote provenance, shadow, retrieval, and raw artifact views

Expected outcome:

- advanced research/debugging material still exists
- the main run page stays focused

## First Pass Scope

The first code pass should stay narrow.

In scope:

- reduce top-level navigation and opening summary
- cut low-value run summary cards
- trim the document table

Out of scope for the first pass:

- backend contract changes
- document-detail redesign
- new visualization work
- removal of advanced data from the system entirely

## Current Recommendation

Move to `Pass UI-4B`.

Reason:

- `UI-4A` is now complete on this branch
- the run page no longer behaves like a subsystem dashboard
- the next high-ROI move is to tighten the document table further so each row makes review decisions even faster
