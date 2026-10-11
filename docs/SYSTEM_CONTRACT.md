# System Contract

This file defines the current practical contract for the system. The proposed product architecture and acceptance gates
are in `docs/PRODUCTIZATION_PLAN.md`; they must not be read as implemented features.

It is intentionally shorter and stricter than the long architecture docs.

## Purpose

The system is a document-processing platform with a canonical research runtime and a separate opt-in product extraction
path, plus a few legacy or research-facing support surfaces.

The current runtime must remain understandable, stable and auditable while product stabilization proceeds. Its research
policy outputs are retained for the frozen October internal study, which is separate from the author-reported accepted
May submission; whether adaptive routing belongs in the future product is an open measurement decision.

## Document Precedence

Use the project docs with this precedence:

1. `docs/PROJECT_DIRECTION.md`
   Defines the current phase, goal, and non-goals
2. `docs/SYSTEM_CONTRACT.md`
   Defines the current system contract and canonical outputs
3. `docs/PRODUCTIZATION_PLAN.md`
   Defines proposed product changes and their gates, without changing this current contract
4. `docs/IDPO_CLEANUP_PASS1.md`
   Defines the active cleanup plan
5. `AGENTS.md`
   Defines AI workflow rules for working in the repo

If they conflict, update the stale document instead of letting the mismatch persist.

## Canonical Research Runtime

The canonical operational path is:

`frontend job (POST /api/jobs/<job_id>/documents, then POST /api/jobs/<job_id>/runs) -> job runner -> idpo.cli process-inbox -> IDPO_DATA_DIR/runs/<run_id>`

Inside IDPO, the canonical runtime path is:

`ingest/inbox -> orchestrator -> executor -> exports`

That is the path cleanup work should protect.

## Opt-in Product Extraction Path

The separate, experimental product path is:

`owner-scoped job upload -> POST /api/jobs/<job_id>/auto -> frontend server runner -> product extraction worker -> IDPO_DATA_DIR/product_runs/<run_id>`

On a single host, the runner executes `idpo.cli process-auto` directly. In Compose, the frontend invokes a Node
bridge to a private Python worker over a Unix socket in the shared data volume. That Docker path has passed static
Compose checks, a frontend build and focused tests but has **not** completed a live container extraction smoke here.
The canonical research job runner is explicitly unavailable in Docker.

The CLI accepts one file or a directory. It supports PDF, common raster images, text, and the existing JSON document
format. It uses local OCR/text extraction and either a deterministic label/value proposal or an optional
OpenAI-compatible chat model for scalar or bounded repeated-column schema discovery followed by value extraction.
Local loopback HTTP servers may run without an API key; remote providers require an HTTPS URL and server-side key. The model can replace the
heuristic schema. Proposed values require exact text-span evidence and a matching, JSON-round-trippable typed value
for machine acceptance. Ambiguous boolean quotes and partial identifier matches stay pending review. A newly
discovered schema is unapproved, so every document remains `needs_review` until an operator reviews it. There is no
approved recipe or automatic release policy yet. A model can propose repeated columns as `array[object]` values with
shared row ordinals and per-cell text evidence; row links remain pending human review. This is not a visual table
parser, stable row identity across versions, or a guarantee of useful fields on unfamiliar documents.

`product_runs/<run_id>` contains `run.json` as the completion marker, `manifest.jsonl` with source hashes and per-document
receipts, `candidates.jsonl`, and `docs/<doc_id>/result.json` with OCR pages, the proposal, model-call telemetry and
reason. Cost fields exist but remain null until provider prices, compute rates and review work are recorded. The
frontend checks source hashes and artifact consistency before displaying a completed run. Owner-scoped result and
source routes lead to a field review page. A reviewer can correct or remove proposed scalar fields, add missing
scalar fields, and inspect or correct bounded linked cells by row. The server checks each machine cell's text evidence
and accepts a human row correction only as a typed array. The API derives a document-scoped `correctedResult` from the
immutable machine candidate and latest review snapshot. Undecided machine values remain in review; human corrections
are assertions and have no machine evidence. Review changes append revisioned events and reject stale saves. This is
one-document adjudication, not an approved reusable recipe or geometric table annotation.

The single-host path runs as a child process of the frontend server; Docker sends it to one private worker that admits
one active run and returns a busy error for another. It has no durable queue, cancellation, approved schema registry,
reusable row recipe, per-user cloud quota, or verified live Docker execution. Model-backed
UI runs are admin-only until cloud data and spend controls exist. It does not use the AHMN policy router, Guardrails
service, or the separate XAI-HITL service. Its benchmarks and outputs must never be represented as the submitted paper's
results or as the canonical research runtime's outputs.

## Canonical Research Policy Routing

Policy routing runs in-process through `ahmn_core/direct_advisor.py` (Thompson Sampling over the policies whose conditions match, with job-scoped posteriors). The runtime does not call the Guardrails or XAI-HITL services, and RABI and DAAF are not active in it; those are separate services and simulation experiments.

## Policy Actions Honoured By The Runtime

A policy's `actions` block is recorded in `plan/primary.json`, but only some of it changes what the pipeline does:

| Action | Effect in the current runtime |
| --- | --- |
| `preprocess.ocr.engine`, `lang` | Selects PaddleOCR or Tesseract and the OCR language |
| `preprocess.ocr.psm`, `alt_psm`, `passes`, `oem` | Used only when Tesseract runs (as the engine or as the fallback) |
| `preprocess.deskew.enabled`, `preprocess.denoise.enabled` | For image documents, `true` forces the stage on and `false` turns it off; when unset, quality heuristics decide |
| `extraction.per_field_extraction`, `extraction_context`, `use_thinking`, `model_tier` | Applied to the LLM extraction call |
| `extraction.explicit_entities`, `field_descriptions` | Used only when the job does not define its own fields |
| `execution_mode`, `escalation.tier` | Select which stages run and the escalation tier |
| `preprocess.denoise.strength` | Recorded only; every denoise uses the same median filter |
| `recovery.strategy` | Recorded only; recovery always re-extracts failing fields with the LLM |
| `preprocess.table_extract`, `chunking` | Write table and chunk artifacts that extraction does not read |
| `retrieval`, `token_budget` | Recorded only; question answering uses the global retrieval config |

With PaddleOCR and job-defined fields, the generic research policies therefore behave like `default`; the specialist policies differ through per-field extraction and their extraction context.

## Core Runtime Responsibilities

The runtime should:

1. ingest supported document files
2. analyze document structure and route characteristics
3. choose a policy through the supported planning path
4. run preprocessing, extraction, validation, recovery, escalation, and chunking
5. write stable run artifacts under `IDPO_DATA_DIR`

The canonical runtime is local-first:

- the active policy bank loaded by default is local-only
- automatic cloud fallback is disabled by default
- optional paid cloud policies may exist in separate extension config, but they are not part of the default runtime contract

## Canonical Outputs

Every successful run should produce a stable run directory under:

`IDPO_DATA_DIR/runs/<run_id>`

Important run-level outputs:

- `run.json`
- `run_metadata.json`
- `metrics.json`
- `docs.xlsx` or `docs.csv`
- `run.xlsx` or `run.csv`

Optional run-level outputs when the run produces them:

- `fields.json`
- `entities.xlsx` or `entities.csv`

Important per-document outputs under `docs/<doc_id>/`:

- `input/manifest.json`
- `input/hashes.json`
- `dae/output.json`
- `plan/primary.json`
- `preprocessing/ocr/text.json`
- `structuring/extracted.json`
- `validation/results.json`
- `recovery/attempts.jsonl`
- `decision_chain.json`
- `reward.json`
- `review/results.json` when operator or AI review exists
- `recovery_trace.json`
- `chunking/chunks.jsonl`
- `provenance/events.jsonl`
- `provenance/graph.json`
- `provenance/transparency.json`

Cleanup work should preserve this contract unless the task explicitly changes it.

## Stable Vs Changeable

Treat these as relatively stable unless there is an explicit decision to change them:

- the canonical runtime path
- the main run artifact layout
- the primary frontend read path for results
- the distinction between core runtime and legacy surfaces

Treat these as changeable as goals evolve:

- which phase the project is in
- which cleanup pass is active
- what is currently in scope or out of scope
- what the next priority should be

Those moving parts belong in `docs/PROJECT_DIRECTION.md`, not here.

## Canonical UI Surfaces

The primary operator-facing UI is in the frontend:

- `/dashboard/idpo/jobs`
- `/dashboard/idpo/jobs/<job_id>`
- `/dashboard/idpo/jobs/<job_id>/docs/<doc_id>`
- `/dashboard/idpo/runs/<run_id>`
- `/dashboard/idpo/runs/<run_id>/docs/<doc_id>`

`/dashboard/idpo` now redirects to `/dashboard/idpo/jobs`.

The job-first routes should be treated as the main operator path for runtime output.

The run-centric routes still exist as supporting drilldowns and compatibility views.

Supporting pages, outside the operator path:

- research evidence: `/dashboard/idpo/benchmark` (paired differences from the saved run reports), `/dashboard/idpo/compare`
  (two runs side by side) and `/dashboard/idpo/presentation` (demo walkthrough)
- separate services: `/dashboard/xai` and `/dashboard/xai/explanation` (XAI-HITL Q&A over a processed document's OCR text,
  read through `GET /api/jobs/<job_id>/docs/<doc_id>/text`), `/dashboard/hitl` (rating the last answer),
  `/dashboard/guardrails` and `/dashboard/submit` (a policy request to the AHMN service, explained on
  `/dashboard/architecture`)
- simulator only: `/dashboard/experiments`, `/dashboard/rabi` and `/dashboard/daaf`

`/dashboard/results` redirects to `/dashboard/experiments` and `/dashboard/history` to `/dashboard/idpo/jobs`.

The primary UI requirement is:

- an operator should be able to see what adaptive path was taken
- what was extracted
- whether the result needs attention

without digging through subsystem-specific panels first.

The near-term job-first UI model is defined in `docs/JOB_UI_CONTRACT.md`. Product review and field-evidence gates are
defined separately in `docs/PRODUCTIZATION_PLAN.md`; AHMN-specific UI requirements remain subject to its keep/remove
decision.

That model is job-first:

- `job`
- `run`
- `document`

The current runtime remains run-centric underneath, but the frontend now treats `job -> run -> document` as the primary operator model instead of adding more run-dashboard complexity.

## Access Control

The job API and the dashboard pages are served by the frontend server, so the gateway never sees those requests.
`frontend/src/middleware.ts` checks their session, and the job API routes resolve the current user before accessing
stored resources:

- Public without a session: `/`, `/features`, `/about`, `/docs`, `/contact`, `/login`, `/signup`, `/forgot-password`,
  `/reset-password`, static assets, and the `/api/*` routes that are proxied to the gateway, which checks them itself.
- Session required: the local job API (`/api/jobs`, `/api/runs`, `/api/benchmarks`) and every other page, including
  `/dashboard/*`.
- A session is the bearer token in the `Authorization` header or the `ahmn_token` cookie. It must be an unexpired JWT
  that the gateway accepts at `GET /api/auth/me`; accepted tokens are cached for 60 seconds.
- Without a valid session the job API answers 401 and pages redirect to `/login`, deleting a rejected cookie. When the
  gateway cannot be reached, both answer 503.
- The middleware reaches the gateway at `INTERNAL_API_URL`, then `NEXT_PUBLIC_API_URL`, then `http://localhost:8000`.

The gateway creates the first admin account at startup from `ADMIN_PASSWORD` (with `ADMIN_USERNAME` and `ADMIN_EMAIL`)
when no admin exists, and never changes existing users.

On the current branch, a new job records its creator as `ownerUserId`. Viewers can access their own jobs, related runs
and document artifacts; admins can access all jobs. Jobs from before ownership was recorded are admin-only. The local
benchmark API is admin-only. The gateway's catch-all `/api/{path:path}` proxy is also admin-only, including legacy
`/api/{advice,dashboard,scheduler,guardrails,xai,hitl,idpo,experiments}/...` routes, because those services do not yet
enforce per-user ownership. This is a temporary isolation gate, **not** per-user HITL or Guardrails support. The
multi-user route matrix and end-to-end artifact reads remain a release verification gate in
`docs/PRODUCTIZATION_PLAN.md`.

The frontend run API currently rejects viewer-supplied model, cloud, custom config, escalation and resource overrides,
and rejects a viewer run when a cloud policy is enabled. Creating or changing job policies is admin-only; a viewer may
read policies for a job they own. These are temporary spend and data-egress controls until per-user authorization,
quotas and provider policies are implemented and tested. They do not define the final product's cloud access policy.

Public sign-up (`POST /api/auth/signup`) always creates a viewer and follows the gateway's `PUBLIC_SIGNUP_ENABLED`
setting: off by default until per-user processing and storage quotas exist. It can be explicitly set to `true` for a
controlled deployment. While it is off, sign-up answers 403, admins create accounts on `/dashboard/admin`, and the frontend reads
`GET /api/auth/signup-status` to replace its sign-up links with sign-in.

## Supported Demo Deployment

The currently supported public demo deployment is:

- one host machine runs the repo, Python environment, frontend runner, and local model runtime
- the frontend runner executes `python -m idpo.cli process-inbox` on that same host
- other laptops access the system through the frontend in a browser

This deployment path is documented in `docs/PUBLIC_DEMO_DEPLOYMENT.md`.

The following are not the supported end-to-end path for the current runtime:

- Vercel-only deployment
- frontend-only Docker deployment
- any deployment where the frontend runner cannot access local Python and the repo workspace

## Legacy Or Non-Core Surfaces

These exist, but they are not the core system path:

- `idpo/ui/app.py`
- `idpo/integration.py`
- `scripts/run_idpo_benchmark.py`
- `idpo/benchmark/*`
- `idpo/evaluation/*`

Rules:

1. do not add new main-runtime logic there
2. only change them for compatibility, isolation, or explicit benchmark work
3. do not let legacy surfaces define the architecture of the core runtime

## What The System Should Be

For cleanup of the canonical research runtime, that path should be:

- one understandable research runtime path
- one stable run artifact contract
- one primary UI path for reading results
- adaptive extraction results presented more clearly than supporting metrics or subsystem detail
- clearly separated core runtime and legacy/research surfaces
- small enough that a teammate can trace one document end-to-end without guesswork

It should not be:

- a collection of undocumented overlapping research entrypoints with different behavior
- a mix of demo logic and production-path logic in the same core files
- dependent on giant multi-purpose files for basic reasoning

The separate product pilot above may simplify or replace these service boundaries after measured quality, cost,
security and operability checks. The target worker, structured visual evidence, approved recipes and scalable review
requirements in `docs/PRODUCTIZATION_PLAN.md` remain future work.

## Change Protocol

If goals or architecture direction change:

1. update `docs/PROJECT_DIRECTION.md`
2. update this file if the current runtime contract changes
3. update the active cleanup or implementation plan
4. only then implement or continue the code changes

This keeps the team from coding against stale assumptions.

## Required Task Output

When an AI tool or teammate finishes a task, the task result should clearly state:

1. what changed
2. what was validated
3. what remains risky or intentionally deferred
4. the single best next step

That reporting format is part of the team workflow and should stay consistent.
