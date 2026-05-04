# Systematic Reduction Plan

This document is the active cross-repo cleanup method for the current phase.

It exists because `docs/IDPO_CLEANUP_PASS1.md` covers `idpo/` only, while the current problem is broader:

- `IDPO` has runtime complexity
- `AHMN` is not clearly bounded from the document pipeline
- the frontend main UI has grown beyond the research need
- the current `IDPO` page also has visible text-encoding corruption

This plan is subordinate to:

1. `docs/PROJECT_DIRECTION.md`
2. `docs/SYSTEM_CONTRACT.md`

## Current Goal

Reduce the system to the smallest version that still supports the real research objective:

`adaptive document extraction on large unstructured document sets, with measurable quality and throughput outcomes`

That means the system should stay capable of:

- ingesting many files
- preprocessing and OCR when needed
- extracting requested structured fields
- using local-first extraction with controlled fallback
- showing usable results clearly
- logging the feedback and policy signals that matter for the adaptive story

Everything else must justify its existence.

## Reduction Rules

For every area, classify each surface as one of:

- `core`
- `supporting`
- `research_evidence`
- `demo_only`
- `legacy`
- `dead`

Then choose one primary action:

- `keep`
- `simplify`
- `quarantine`
- `remove`

Do not skip classification and jump straight into editing.

## Decision Criteria

Keep something only if at least one is true:

1. it is required for the canonical runtime path
2. it is required for the adaptive-research claim
3. it is required for the supported public demo path
4. removing it would break the main operator workflow

Simplify something if:

1. it adds value but has too many branches or responsibilities
2. the same concept is represented in multiple places
3. the UI forces the user to think about system internals they should not manage
4. the runtime spends time collecting signals that are not used to make real decisions

Quarantine something if:

1. it is useful for paper evidence, migration, or compatibility
2. it is not part of the canonical operator path
3. deleting it immediately would create risk or churn

Remove something if:

1. it is unused
2. it duplicates a better surface
3. it exists only to support old prompting or demo drift
4. it adds latency, confusion, or maintenance cost without supporting the research goal

## What High ROI Means Here

High ROI work is work that does at least one of these:

1. reduces runtime latency or failure risk in the main document path
2. removes a major source of team confusion
3. improves the reliability of the research evidence path
4. makes the public demo easier to operate and explain
5. fixes a user-facing defect that undermines trust

Low ROI work includes:

- decorative UI expansion
- duplicate views of the same result
- metrics that are shown but not used
- optional branches that rarely help but add many failure modes
- preserving AI-generated complexity for its own sake

## Required Cleanup Method Per Pass

Every cleanup pass should follow the same shape:

1. identify the owning service
2. list the files in scope
3. classify each file or surface
4. decide `keep`, `simplify`, `quarantine`, or `remove`
5. make only one kind of change in that pass
6. run the narrowest validation that proves the pass is safe
7. update docs if the contract, workflow, or priorities changed

Do not mix all cleanup types at once.

## Cleanup Types

Use only one primary cleanup type per pass:

1. `boundary cleanup`
   Make responsibilities smaller and clearer
2. `runtime reduction`
   Remove optional branches and low-value hot-path work
3. `UI reduction`
   Remove controls, panels, or states that do not help the research workflow
4. `defect cleanup`
   Fix correctness or quality issues such as encoding corruption
5. `legacy isolation`
   Move or freeze non-core paths

## Repo-Wide Cleanup Order

Use this order unless a blocking defect overrides it.

### Phase 0: Contracts And Triage

- update docs and AI rules first
- define the cleanup order
- identify obvious user-facing defects

### Phase 1: UI Defect And Main-Path Clarity

Scope:

- `frontend/src/app/dashboard/idpo/page.tsx`
- related frontend read-path files only if needed

Goals:

- remove mojibake and encoding corruption
- cut the main page down to the actual operator workflow
- restore a clear main screen for upload, status, and results

This is first because the current UI is actively misleading and visibly broken.

### Phase 2: IDPO Runtime Reduction

Scope:

- `idpo/agents/llm_extraction.py`
- `idpo/pipeline/orchestrator.py`
- directly related helper modules only

Goals:

- remove or disable low-value extraction branches
- reduce hot-path latency
- keep only the adaptation and evidence signals that actually matter

### Phase 3: AHMN Boundary Review

Scope:

- `ahmn_core/`
- `idpo/pipeline/planning.py`
- `idpo/pipeline/policy_advisor.py`
- `idpo/pipeline/orchestrator.py` feedback boundary

Goals:

- keep the advice and feedback loop
- reduce anything that is not clearly contributing to the adaptive story
- make the AHMN contract understandable without reading the whole repo

### Phase 4: UI And UX Simplification

Scope:

- `frontend/src/app/dashboard/idpo/*`
- `frontend/src/server/artifacts.ts`
- small supporting components

Goals:

- keep one main operator path
- move compare, benchmark, and presentation surfaces out of the primary operator flow if they distract
- reduce state explosion and duplicated summaries

### Phase 5: Legacy And Evidence Isolation

Scope:

- benchmark surfaces
- demo-only assets
- legacy entrypoints

Goals:

- keep them usable
- stop them from defining the core runtime

## Current Known Defects To Track

1. `frontend/src/app/dashboard/idpo/page.tsx`
   Status: visible encoding corruption and state/UI bloat
   Action target: `simplify` plus `defect cleanup`

2. `idpo/agents/llm_extraction.py`
   Status: oversized hot-path file with too many fallback and diagnostics branches
   Action target: `simplify`

3. `idpo/pipeline/orchestrator.py`
   Status: too many runtime and policy concerns in one file
   Action target: `simplify`

## Pass Template

Use this template before touching a section:

```text
Section:
Owner service:
Cleanup type:
Files in scope:
Classification:
Why this exists:
Why it matters to the research goal:
Primary action:
Acceptance check:
```

## Success Criteria For This Phase

This reduction phase is successful when:

- the main UI is readable, stable, and not visibly corrupted
- the canonical runtime path is fast enough to reason about and demo
- AHMN participation is understandable and bounded
- the team can explain what each major surface is for
- low-value demo and research extras no longer dominate the operator path

## Immediate Next Section

Start with:

- `frontend/src/app/dashboard/idpo/page.tsx`

Reason:

- it is visibly broken
- it is user-facing
- `main` was simpler here
- reducing it will immediately lower confusion for both the team and the viva/demo audience
