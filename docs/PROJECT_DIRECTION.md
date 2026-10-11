# Project Direction

This is the living document for the current project phase.

Unlike `docs/SYSTEM_CONTRACT.md`, this file is expected to change as goals evolve.

## Current Phase

`Evidence frozen; publication preparation`

The paired `static` vs `adaptive_safe` evaluation on CORD-dev, CORD-holdout, FUNSD-20 and HARD-13 is complete. Its
results, run folders and regeneration commands are frozen in `paper/FINAL_EVIDENCE.md`, and `paper/ieee/main.tex`
reports them as they are: adaptive routing did not improve accuracy, and it added latency on receipts.

## Primary Goal

Publish the paper and a reproducible repository without changing the frozen evidence.

That means:

- every number in the paper traces to a run folder or command listed in `paper/FINAL_EVIDENCE.md`
- `docs/REPRODUCING_RESULTS.md` rebuilds the packs, the runs and the tables from a clean checkout
- runtime changes are limited to defects; a change that would alter benchmark outcomes needs new runs and an update
  of both the paper and the evidence file
- the claim stays narrow: `static` vs `adaptive_safe`, with the negative result stated plainly

## Current In-Scope Work

- venue selection, template formatting and camera-ready edits of the paper
- archiving the run folders listed in `paper/FINAL_EVIDENCE.md` for the artifact release
- an anonymised repository link for review
- defect fixes in the canonical runtime, the gateway and the frontend job path, with tests
- keeping setup, reproduction and contract docs accurate

## Current Non-Goals

For the current phase, do not prioritize:

- new routing features, policies or reward changes (the paper lists these as future work: a text-based document type
  before routing, actions that change OCR output, and rewards tied to correctness)
- wiring Guardrails into the measured pipeline; the paper treats it as a separate service
- enabling RABI or DAAF in the runtime; both are reported as simulation results only
- re-tuning prompts, normalisers or the scorer against the benchmark packs
- broad frontend redesign or cross-service architecture rewrites

## Current Success Criteria

This phase is successful when:

- the paper compiles to six pages and every figure in it matches `paper/FINAL_EVIDENCE.md`
- a teammate can follow `SETUP.md` and `docs/REPRODUCING_RESULTS.md` without prior context
- the `ahmn_core`, `gateway`, `guardrails`, `xai_hitl` and `idpo` test suites and the frontend type check, lint and
  server tests pass
- the run folders behind the paper are archived alongside the release

## Document Roles

Use the docs this way:

- `docs/PROJECT_DIRECTION.md`
  The current goal, scope, and non-goals
- `paper/ieee/main.tex` (compiled to `paper/ieee/main.pdf`)
  The paper
- `paper/FINAL_EVIDENCE.md`
  The frozen results, the run folders they came from and the commands that regenerate them
- `docs/REPRODUCING_RESULTS.md`
  How to rebuild the packs, rerun the benchmarks and the simulation, and compile the paper
- `SETUP.md`
  Local setup of the services, the frontend and the extraction runtime
- `docs/DATASET_PLAN.md`
  The dataset ladder used to build the evidence (completed)
- `docs/CORD_EVALUATION_PLAN.md`
  The labeled testing plan and failure triage loop used to build the evidence (completed)
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

## Goal Change Record

```text
Date: 2026-10-08
Old phase: Dataset-driven stabilization and evidence build
New phase: Evidence frozen; publication preparation
Reason: The paired static vs adaptive_safe runs on all four packs are complete, rescored with the final scorer and
  frozen in paper/FINAL_EVIDENCE.md.
What is now in scope: paper submission, reproducibility, defect fixes with tests, accurate docs.
What is now out of scope: feature work and any change that would alter the frozen benchmark outcomes.
Which docs must be updated: PROJECT_DIRECTION.md, SYSTEM_CONTRACT.md, REPRODUCING_RESULTS.md, SETUP.md, README.md,
  CLAUDE.md.
Which code areas are most affected: paper/ and docs/; code only for defect fixes.
```

## Current Next Step

1. choose the venue and adapt `paper/ieee/main.tex` to its template, page limit and review policy
2. archive the run folders listed in `paper/FINAL_EVIDENCE.md` with the repository release
3. for double-blind review, point the paper's release sentence at an anonymised copy of the repository; add the author
   block for the camera-ready version
4. after any runtime defect fix, rerun the affected test suites; rerun the benchmarks only if the fix can change their
   outcomes, and then update the paper and the evidence file together
