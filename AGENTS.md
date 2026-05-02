# AGENTS.md

Project-level instructions for Codex and other AI coding agents working in this repository.

## Purpose

This is a monorepo for a final-year research system with:

- `ahmn_core/`: adaptive policy learning and memory
- `guardrails/`: hallucination and validation checks
- `xai_hitl/`: explainability and human review
- `idpo/`: orchestration and document pipeline
- `gateway/`: FastAPI reverse proxy and auth
- `frontend/`: Next.js application

Read these files before making non-trivial changes:

1. `README.md`
2. `CONTRIBUTING.md`
3. `docs/SYSTEM_FLOW.md`
4. `docs/ARCHITECTURE_DEEP_DIVE.md`
5. `docs/PROJECT_DIRECTION.md`
6. `docs/SYSTEM_CONTRACT.md`
7. `docs/IDPO_CLEANUP_PASS1.md`
8. `docs/SYSTEMATIC_REDUCTION_PLAN.md`
9. `docs/FRONTEND_IDPO_PAGE_REDUCTION_PLAN.md`
10. `docs/FRONTEND_IDPO_RUN_DETAIL_REDUCTION_PLAN.md`
11. `docs/JOB_UI_CONTRACT.md`
12. `docs/PUBLIC_DEMO_DEPLOYMENT.md`

## Working Rules

1. Do not make cross-service architecture changes unless the task explicitly requires it.
2. Prefer fixing one component at a time. Keep changes small and easy to review.
3. Before editing, identify the owning service and inspect its tests first.
4. Preserve existing interfaces unless the task requires a breaking change.
5. If a change affects API shape, update the backend model, gateway behavior if needed, frontend types, and docs in the same task.
6. Add or update tests for behavior changes.
7. Do not add secrets, hardcoded credentials, or environment-specific paths.

## Current Cleanup Mode

The repository is in a cleanup and stabilization phase before new feature work.

During cleanup:

1. Prefer simplification over expansion.
2. Do not add new features unless the task explicitly asks for them.
3. Reduce mixed responsibilities before changing behavior.
4. Preserve the canonical runtime path:
   - `ingest/inbox -> orchestrator -> executor -> exports`
5. Use the repo-wide reduction method in `docs/SYSTEMATIC_REDUCTION_PLAN.md`.
6. For each touched file or surface, classify it before editing:
   - `core`
   - `supporting`
   - `research_evidence`
   - `demo_only`
   - `legacy`
   - `dead`
7. For each touched file or surface, choose exactly one primary action:
   - `keep`
   - `simplify`
   - `quarantine`
   - `remove`
8. Prefer removing optional runtime branches, duplicated UI states, and low-signal metrics before adding new logic.
9. Treat these as legacy or non-core surfaces unless the task explicitly targets them:
   - `idpo/ui/app.py`
   - `idpo/integration.py`
   - `scripts/run_idpo_benchmark.py`
   - `idpo/benchmark/*`
10. Do not move fast by mixing refactor, feature work, and architecture redesign in one task.
11. UI and UX work is in scope only when it improves clarity, removes confusion, fixes defects, or makes the research workflow easier to operate.
12. Do not preserve a complicated screen or control just because it already exists.
13. When simplifying operator-facing UI, prioritize making adaptive extraction results clear and straightforward over exposing more subsystem detail.
14. Simplify aggressively, but do not remove high-ROI research-backing pieces just because they are complex.
15. If a cleanup choice could weaken the research claim, evidence quality, or core operator understanding, pause and get user direction before proceeding.

## System Boundary

Use `docs/SYSTEM_CONTRACT.md` as the source of truth for:

- what the current system is
- the canonical runtime path
- what artifacts the runtime must emit
- which UI surfaces are canonical
- which surfaces are legacy

If code and docs disagree, update the docs as part of the task or call out the mismatch explicitly.

Use `docs/PROJECT_DIRECTION.md` as the source of truth for:

- the current phase of the project
- the current primary goal
- current non-goals
- what should happen next if priorities change

If the project goal changes materially, update docs before or alongside implementation.

Use `docs/PUBLIC_DEMO_DEPLOYMENT.md` as the source of truth for:

- the supported public demo deployment model
- host prerequisites for the current frontend runner path
- what is and is not supported without a worker redesign

Use `docs/SYSTEMATIC_REDUCTION_PLAN.md` as the source of truth for:

- the current cross-repo cleanup order
- the keep/simplify/quarantine/remove decision method
- what counts as high-ROI research support
- which areas should be cleaned first and which are deferred

Use `docs/JOB_UI_CONTRACT.md` as the source of truth for:

- the target operator-facing job model
- the distinction between job, run, and document in the UI
- the required queue table, results table, and document-detail responsibilities

## Service Ownership

- `ahmn_core/`: AHMN, Thompson Sampling, RABI, DAAF
- `guardrails/`: validation layers, PII checks, consistency rules
- `xai_hitl/`: explanations, review workflows, HITL feedback
- `idpo/`: orchestration, pipeline steps, integrations, extraction flow
- `gateway/`: auth, proxying, service routing
- `frontend/`: UI, dashboard pages, API client types

When possible, keep a task inside the service owned by the responsible teammate. Shared changes should be explicit.

## Preferred Workflow

1. Read the relevant module and its tests.
2. Confirm the entrypoint:
   - Python services: usually `main.py` or package modules
   - Frontend: `frontend/src/app/`, `frontend/src/components/`, `frontend/src/server/`
3. Make the smallest change that solves the problem.
4. Run targeted tests first, then broader validation if the change touches shared behavior.

For cleanup tasks, prefer this order:

1. remove unused or duplicate code
2. split oversized files by responsibility
3. isolate legacy or demo-only paths
4. only then adjust behavior

For cleanup planning tasks, prefer this order:

1. classify the surface
2. state why it exists
3. state whether it supports the research goal directly
4. choose `keep`, `simplify`, `quarantine`, or `remove`
5. define one acceptance check

Do not start editing a surface before this is clear.

If the team changes direction, update documents in this order:

1. `docs/PROJECT_DIRECTION.md`
2. `docs/SYSTEM_CONTRACT.md`
3. the active cleanup or implementation plan doc
4. `AGENTS.md` only if AI workflow or repo rules changed

Do not implement a major direction change while leaving the contract docs stale.

## Verification

Use the narrowest command that proves the change:

```powershell
python -m pytest ahmn_core/tests/ -v
python -m pytest guardrails/tests/ -v
python -m pytest xai_hitl/tests/ -v
python -m pytest idpo/tests/ -v
python -m pytest gateway/tests/ -v
cd frontend; npx tsc --noEmit
cd frontend; npm run lint
```

## Definition Of Done

A task is not complete unless all relevant items below are true:

- the code change is scoped to the correct component
- tests or validation were run, or a clear reason is given if they were not
- docs are updated when behavior or setup changed
- direction and contract docs stay aligned if the task changes goals, outputs, or boundaries
- the change is understandable by a teammate without re-prompting an AI tool

## Required Task Close-Out

After each non-trivial task, the final response should make these items clear:

1. `Scope`: what was changed
2. `Validation`: what tests or checks were run
3. `Risk`: anything still unclear, frozen, or intentionally deferred
4. `Next step`: the single best next task

Keep the close-out concise. Do not return a vague progress update with no concrete next action.
