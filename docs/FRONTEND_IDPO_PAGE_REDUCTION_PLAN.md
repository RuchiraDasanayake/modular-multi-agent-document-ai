# Frontend IDPO Page Reduction Plan

This document is the active cleanup plan for:

- `frontend/src/app/dashboard/idpo/page.tsx`

It should be used together with:

1. `docs/PROJECT_DIRECTION.md`
2. `docs/SYSTEM_CONTRACT.md`
3. `docs/SYSTEMATIC_REDUCTION_PLAN.md`

## Section Note

```text
Section: IDPO main operator page
Owner service: frontend
Cleanup type: defect cleanup, then UI reduction
Files in scope: frontend/src/app/dashboard/idpo/page.tsx and only the smallest supporting frontend files required by the pass
Classification: core operator UI
Primary action: simplify
Acceptance check: the page is readable, stable, free of mojibake, and focused on upload -> process -> inspect results
```

## Why This Page Exists

This page is the main operator-facing entrypoint for the system.

It must support the canonical flow:

1. upload files
2. declare requested fields
3. run processing
4. monitor status
5. inspect results
6. download outputs

If the page does not make that path obvious, it is failing its job.

It must also make the adaptive extraction outcome easy to understand at a glance.

## Current Problems

The current page has 3 major problems.

### 1. Visible Defect

The file contains mojibake and corrupted text markers such as:

- `Ã`
- `â`
- corrupted arrows
- corrupted emoji/icon strings

This is a real defect, not a design preference issue.

### 2. Scope Bloat

The page currently mixes:

- main operator flow
- compare-oriented behavior
- benchmark-oriented entry points
- deep integration detail panels
- duplicated summaries
- multiple document card styles
- simulated progress and decorative status behavior

That is too much for the main screen.

### 3. State Explosion

The page is currently over `2500` lines and holds too much state at once:

- upload state
- run settings
- progress simulation
- paired-run state
- entity filtering/pagination state
- integration sub-tab state
- result persistence state
- large inline rendering helpers

That makes the page harder to trust and harder to repair.

## Value Decision Map

Use this map for the page cleanup.

### Keep

Keep on the main page:

- file upload
- extraction field entry
- one primary run action
- simple processing status
- run-level success/error message
- document result list
- clear adaptive extraction outcome and field preview
- basic downloads
- a clear link to run details

These support the real operator workflow directly.

### Simplify

Simplify on the main page:

- header and hero area
- processing status presentation
- document cards
- tabs and result summaries
- advanced settings
- session persistence

These add value, but they currently do too much.

### Move Out Of The Main Screen

Move out of the main screen or demote behind links:

- paired static vs adaptive run flow
- compare-run entry behavior
- benchmark-result entry behavior
- deep integration sub-panels for AHMN, guardrails, XAI, and feedback
- large aggregate entity table if it duplicates detail pages

These are supporting surfaces, not the primary operator path.

### Remove

Remove from this page if not needed by a later pass:

- corrupted icon strings and corrupted comment separators
- duplicate document-card implementations when one is enough
- decorative runtime jargon that does not help the user act
- simulated progress behavior that does not reflect real runtime state
- duplicated summaries that repeat the same numbers in different layouts

## Decision Criteria For This Page

Keep something on the main page only if it helps the operator answer one of these quickly:

1. What am I uploading?
2. What am I extracting?
3. Is the run working?
4. What came out?
5. What should I inspect next?
6. What did the adaptive extraction actually return?

If a control or panel does not help answer one of those, it should not dominate the page.

## Target Shape

The target shape for the page is:

1. upload and requested fields
2. one small settings area
3. one clear run action
4. one live status area
5. one results area
6. one link out to deeper run details

It should not be a full system dashboard for every subsystem.

## Planned Passes

### Pass UI-1: Defect Cleanup And Shell Reduction

Goal:

- remove mojibake
- remove corrupted icon text
- restore readable labels and comments
- trim obvious clutter from the header and top-level controls

Expected outcome:

- no visible alien characters
- main page is readable again
- no behavior redesign yet beyond light cleanup

Progress on current branch:

- replaced the corrupted `IDPO` page with a smaller ASCII-safe operator page
- removed mojibake and corrupted icon text from the main screen
- removed compare, benchmark, paired-run, and deep integration surfaces from the primary operator page
- kept the core operator flow: upload -> fields -> settings -> run -> inspect results -> open run detail

### Pass UI-2: Main Workflow Reduction

Goal:

- keep only the primary operator workflow on the page
- reduce tabs and summaries that do not directly help the current run
- remove or demote compare/benchmark-oriented controls

Expected outcome:

- page is focused on upload, run, and result inspection

Progress on current branch:

- reduced the run summary area to operator-facing status instead of dashboard-style analytics
- removed extracted-text preview and detailed validation panels from the main page
- reduced document expansion to summary plus field preview
- pushed deep inspection responsibility to the run detail and document detail routes

### Pass UI-3: Component Extraction

Goal:

- split the page into a small number of clear components
- keep data ownership understandable
- avoid pushing complexity into too many tiny fragments

Expected outcome:

- the main page file becomes readable
- rendering sections are easier to test and reason about

Progress on current branch:

- consolidated the page onto the existing shared component module at `frontend/src/components/idpo/operator-page.tsx`
- reduced `frontend/src/app/dashboard/idpo/page.tsx` to a stateful container for data flow and event handlers
- reused existing frontend primitives such as `IdpoCard` and `StatusBadge` instead of adding another UI pattern
- kept the simplified operator workflow unchanged while moving section rendering out of the page file

### Pass UI-4: Secondary Surface Review

Goal:

- decide what remains on the main page versus what belongs on run detail pages or separate routes

Expected outcome:

- no duplicated responsibility between the main page and the run detail surfaces

### Pass UI-5: Job-First Alignment

Goal:

- reshape the main page around job creation, queue tracking, and structured results
- keep the current backend wiring intact while moving the operator mental model away from raw run dashboards

Expected outcome:

- the main page reads as a job workspace
- queued documents have simple statuses
- structured extraction results are shown in a table

Progress on current branch:

- the main page now presents itself as an `IDPO` job workspace instead of a generic run launcher
- selected files now live in a queue table with simple statuses: `loaded`, `processing`, `processed`, `failed`
- the main output surface is now a structured results table keyed by requested extraction fields
- `AHMN`, `XAI`, and `HITL` are represented as compact support signals instead of expanding into separate primary UI flows on the main page

## First Pass Scope

The first code pass should stay narrow.

In scope:

- text cleanup
- icon cleanup
- top-level header cleanup
- remove or hide obvious low-value controls from the main path

Out of scope for the first pass:

- full component extraction
- data-contract redesign
- backend changes
- major styling redesign

## Acceptance Checks

Pass UI-1 is done when:

1. the page shows no mojibake or corrupted visible text
2. the top-level flow is readable without explaining subsystem jargon
3. the page still starts a run and shows results
4. no backend contract changes were required

## Current Recommendation

Move to the next job-first pass on the main page, then continue with `Pass UI-4` on the run-detail page.

Reason:

- the main page is now aligned with the job-first direction at a basic level
- the next high-ROI move on the main page is to reduce any remaining friction or ambiguity in the queue and results tables
- after that, the run-detail page still needs to be cut down so it stops behaving like a subsystem dashboard
