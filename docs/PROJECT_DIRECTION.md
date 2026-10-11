# Project Direction

This is the living document for the current project phase.

Unlike `docs/SYSTEM_CONTRACT.md`, this file is expected to change as goals evolve.

## Current Phase

`Accepted paper preserved; product stabilization`

The author reports that a paper was accepted for an oral presentation at ICTAR 2026. The author-provided May PDF
appears to be that submission, but the exact manuscript uploaded to CMT still needs verification. The later October
`paper/ieee/main.tex` and `paper/FINAL_EVIDENCE.md` describe a different paired `static` vs `adaptive_safe` study on
CORD-dev, CORD-holdout, FUNSD-20 and HARD-13. Its results, run folders and regeneration commands are frozen as
**October internal evidence**; they are not verified as the accepted submission. In that study adaptive routing did
not improve accuracy and added latency on receipts. Camera-ready work must reconcile the submitted manuscript,
reviewer comments, venue requirements and later evidence accurately, without overwriting or backdating either study.
Product development is a third track with new evaluations and claims.

## Primary Goal

Deliver better structured extraction from an arbitrary document without manual template setup, at a lower total cost
per accepted document across available local CPU, local GPU and cloud API capacity. Preserve the author-reported
accepted submission and the separate frozen October evidence. Prefer local and open-source components when they meet
the measured quality, cost and data-handling gates.

That means:

- preserve `paper/FINAL_EVIDENCE.md`, its referenced run folders and the October draft's narrow `static` vs
  `adaptive_safe` claim; do not present those results as the accepted submission or reinterpret new product results as
  either earlier study
- make accuracy, grounded field evidence, review burden, latency and compute/API spend visible together
- discover document families and typed fields automatically, then stabilize recurring business fields in approved,
  versioned recipes; ambiguous or unsupported content must abstain for review
- fix release blockers before calling the product deployable: access to another user's jobs/runs/artifacts, live Docker
  worker verification, and durable bounded job execution
- require measured quality or cost gains before keeping AHMN routing, agent loops or separate services in the
  operational hot path; the existing service layout is not a product requirement
- use `docs/PRODUCTIZATION_PLAN.md` for target architecture and acceptance gates; `docs/SYSTEM_CONTRACT.md` continues
  to describe the implemented runtime

## Current In-Scope Work

- identify and archive the exact accepted manuscript from CMT; make reviewer- and venue-compliant camera-ready edits
  with any differences from the May PDF and October draft made explicit
- archive the run folders listed in `paper/FINAL_EVIDENCE.md` as separate October internal evidence
- an end-to-end, owner-scoped job/run/document API and an executable runner in every advertised deployment mode
- a representative, legally usable labeled evaluation set with unseen-document-family, layout, scan-quality and
  line-item slices
- a static extraction baseline, separate schema-discovery and value-extraction scoring, parser/model comparisons and a
  quality-cost frontier on the same test set
- automatic family and typed-schema discovery with source evidence, followed by extraction against a versioned
  proposed or approved schema and a reusable recipe
- provider-neutral comparisons of local CPU, local GPU and opt-in cloud API extraction, with data controls and spend caps
- field-level source evidence, side-by-side human review, adjudicated corrections and auditable outcomes
- defect fixes and focused reduction of the canonical runtime, gateway and frontend job path, with tests
- keeping setup, reproduction and contract docs accurate

## Current Non-Goals

For the current phase, do not prioritize:

- new routing features, more agents, RABI or DAAF in the production path before a head-to-head quality-cost test
- preserving the current microservices because they exist; combine, isolate or remove them when evidence warrants it
- using the frozen October packs as a product tuning set or silently changing their scorer, prompts or results
- claiming the separate Guardrails and XAI-HITL services are integrated into the measured runtime
- broad frontend redesign that does not improve upload, extraction, evidence, review or access control

## Current Success Criteria

This phase is successful when:

- the camera-ready paper is traceable to the verified CMT submission and honestly reconciles later findings; the
  October study and its run folders are separately archived
- a teammate can reproduce the October results from a clean checkout and separately reproduce the product benchmark;
  reproducibility claims for the accepted submission are checked against its actual artifacts
- both unauthorized cross-user access and the Docker runner blocker have passing end-to-end regression checks
- a user can upload an unfamiliar supported document without choosing a template and receive a proposed typed schema,
  grounded values and explicit review or abstention states; schema discovery and value accuracy are scored separately
- each extracted field can be inspected against source evidence, corrected or abstained from, with review time recorded
- a candidate system meets predeclared quality and cost gates on an untouched holdout; no agentic or adaptive path is
  promoted based only on an internal proxy reward
- every substantive extraction implementation milestone processes at least 2,000 unique documents end to end, with
  failures, quality, evidence validity, review work, latency and total cost reported by document-family slice
- the relevant backend, frontend and runner tests pass for each release candidate

## Document Roles

Use the docs this way:

- `docs/PROJECT_DIRECTION.md`
  The current goal, scope, and non-goals
- author-provided May PDF and the CMT-uploaded manuscript (identity to verify)
  The reported accepted submission and the source of truth for camera-ready reconciliation
- `paper/ieee/main.tex` (compiled to `paper/ieee/main.pdf`)
  The later October internal draft; do not label it the accepted submission without verification
- `paper/FINAL_EVIDENCE.md`
  The frozen October results, the run folders they came from and the commands that regenerate them
- `docs/REPRODUCING_RESULTS.md`
  How to rebuild the packs, rerun the benchmarks and the simulation, and compile the paper
- `SETUP.md`
  Local setup of the services, the frontend and the extraction runtime
- `docs/DATASET_PLAN.md`
  The dataset ladder used to build the evidence (completed)
- `docs/CORD_EVALUATION_PLAN.md`
  The labeled testing plan and failure triage loop used to build the evidence (completed)
- `docs/SYSTEM_CONTRACT.md`
  What the implemented system currently is and must emit
- `docs/PRODUCTIZATION_PLAN.md`
  The target architecture, component decisions, quality-cost gates and release blockers; targets here are not claims
  about the current runtime
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

That historical October phase record describes the repository's later draft and its evidence; it does not establish the
identity of the manuscript accepted through CMT.

```text
Date: 2026-10-11
Old phase: Evidence frozen; publication preparation
New phase: Accepted paper preserved; product stabilization
Reason: The author reports ICTAR 2026 acceptance of a manuscript whose uploaded identity remains to be verified and
  wants a useful, lower-cost extraction product. The separate October comparison found no significant accuracy gain
  from adaptive routing and higher receipt latency.
What is now in scope: release blockers, labeled product evaluation, grounded extraction, human review, cost accounting,
  and measured component replacement or reduction.
What is now out of scope: unmeasured agent/routing expansion and rewriting either research study as product evidence.
Which docs must be updated: PROJECT_DIRECTION.md, SYSTEM_CONTRACT.md, PRODUCTIZATION_PLAN.md; setup and deployment docs
  when the executable deployment path changes.
Which code areas are most affected: frontend job API/runner, gateway access checks, IDPO extraction and evaluation;
  October evidence remains frozen; the accepted submission must be identified before camera-ready editing.
```

## Current Next Step

1. use the completed [v6 2,000-source bounded-OCR gate](evaluations/VRDU_2000_NO_MODEL_V6.md) as the reproducible
   no-model comparator: all sources remained reviewable with strict schema F1 4.245% and zero linked cells; no page
   triggered the timeout, so the recovery branch still relies on focused tests and a forced-timeout smoke
2. isolate schema discovery from value extraction with the bounded local oracle-schema diagnostic, then improve field
   semantics and linked rows on small authorized, adjudicated development slices before any model-backed full gate;
   the initial local Qwen and bounded ICORE pilots did not pass real-document quality/reliability
3. complete a live Docker worker smoke on a host with a daemon, then add durable bounded jobs and price plus review-time
   accounting before claiming a scalable lower-cost deployment
4. verify and archive the CMT-submitted manuscript and reconcile camera-ready changes with the reviewers and venue,
   keeping new product results and the frozen October study separately attributed
