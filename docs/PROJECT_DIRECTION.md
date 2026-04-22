# Project Direction

This is the living document for the current project phase.

Unlike `docs/SYSTEM_CONTRACT.md`, this file is expected to change as goals evolve.

## Current Phase

`Systematic reduction and stabilization`

The repository is currently in a cleanup phase before major new feature work.

## Primary Goal

Make adaptive extraction results clear, straightforward, and easy to inspect.

That means:

- making the adaptive extraction outcome the main thing the operator sees and understands
- reducing anything that hides, dilutes, or distracts from the extraction result
- reducing unnecessary complexity
- shrinking oversized multi-purpose files
- isolating legacy and demo-only paths
- preserving one clear canonical runtime path
- simplifying UI and UX around the real research workflow
- keeping only the highest-value adaptive and evidence-related behavior
- preserving high-ROI research-backing pieces even when simplifying aggressively
- pausing for team direction when a cleanup choice could weaken the research claim or evidence quality

## Current In-Scope Work

- clean up `idpo/` first
- fix the corrupted and overgrown main `IDPO` UI
- make adaptive extraction results the clearest output in the primary UI path
- move the operator UI toward a job-first model with queue tracking and structured results tables
- finish the core operator path as `job -> document -> result -> log`
- adapt UiPath-style queue-item traceability to document extraction where it fits
- reduce complexity across `IDPO`, `AHMN`, and the frontend a section at a time
- simplify the canonical runtime path
- preserve and clarify run artifacts and output contracts
- reduce AI-generated bloat and overlapping responsibilities
- keep docs in sync with the real system
- prepare a supported single-host public demo deployment path without major restructuring

## Current Non-Goals

For the current phase, do not prioritize:

- major new product features
- broad frontend redesign
- cross-service architecture rewrites
- benchmark claim expansion
- adding alternate entrypoints unless explicitly required
- Vercel-first deployment redesign
- broad UI expansion
- adding new knobs, panels, or metrics before the main workflow is simplified

## Current Success Criteria

This phase is successful when:

- the team can trace one document through the system end-to-end
- the canonical runtime path is stable and documented
- legacy and non-core surfaces are clearly separated
- the biggest runtime files are split by responsibility
- output artifacts remain predictable
- the main operator-facing UI is clear, stable, free of encoding defects, and centered on adaptive extraction results
- adaptive extraction outputs are easy to read without inspecting multiple panels or subsystem jargon
- the operator-facing UI is centered on `job -> document -> result` instead of subsystem-first dashboards
- every major surface has been reviewed with a keep/simplify/quarantine/remove decision

## Document Roles

Use the docs this way:

- `docs/PROJECT_DIRECTION.md`
  The current goal, scope, and non-goals
- `docs/SYSTEM_CONTRACT.md`
  What the system currently is and must emit
- `docs/IDPO_CLEANUP_PASS1.md`
  The active cleanup plan for the current phase
- `docs/SYSTEMATIC_REDUCTION_PLAN.md`
  The cross-repo reduction order and decision method
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

Run the reduction program in strict order:

1. finish the core operator path first
   Keep queue, field configuration, original-document validation, structured results, document path, and document log simple and explicit
2. tighten the document-detail page around evidence-driven review
   Add clickable log-to-evidence focus before adding more surface area
3. reduce any remaining low-value frontend surfaces that compete with the job-first flow
4. restore only high-ROI buried functionality that fits the job and document model cleanly
5. integrate `AHMN`, then `XAI`, then `HITL` into the same job/document architecture in small passes
6. continue reducing hot-path complexity in `idpo/agents/llm_extraction.py`
7. continue reducing non-essential orchestration complexity in `idpo/pipeline/orchestrator.py`
