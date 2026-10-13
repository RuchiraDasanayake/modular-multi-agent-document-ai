# Job UI Contract

This document defines the target operator-facing UI model for the next frontend cleanup phase.

It does not replace the current runtime contract in `docs/SYSTEM_CONTRACT.md`.

Instead, it defines the structure the frontend should move toward while preserving the existing runtime path.

## Product batch flow, clarified 13 October 2026

For the opt-in product path, the primary action is **extract requested information from a batch**. Keep one compact
workspace with these stages: **Files and request → Preview → Extract → Review and export**. The user can describe the
desired output in ordinary language, enter a schema with field definitions/examples, or ask the system to discover
one. Advanced parser, model and research policy details belong behind a secondary control.

The preview should show the selected sample files, proposed field names/types/groups, a short meaning for each field,
and values beside their source evidence. Ask focused clarification questions only where the requested meaning is
ambiguous. Confirmation pins a schema revision; applying it to the rest of the batch must not silently rename fields
or infer a new business meaning. New layouts or conflicts can return to review with an explicit reason. Reviewed
corrections may propose a new recipe revision for later approval.

Large batches need paginated status and results, bounded uploads and workers, resumable admission, cancellation and
an explicit outcome for each file. Show pending, processing, ready for review, reviewed, unsupported and failed states
in plain language. Do not label a machine result as reliable merely because JSON parsing or a text quote check passed.
Display the configured coverage and route/cost policy before the user starts the remainder of a batch.

This is target behavior. Current product routes lack intent onboarding, schema clarification and a sample preview
gate. The research `adaptive`/`strict`/`both` controls described below remain available for the research runtime;
they do not define the primary product workflow. See [the implementation boundary](SYSTEM_CONTRACT.md).

## Purpose

The operator should think in terms of:

1. `job`
2. `run`
3. `document`

Not in terms of scattered subsystem panels.

The UI must make adaptive extraction results easy to queue, process, track, and inspect at both job level and document level.

## Core Definitions

### Job

A `job` is a user-created processing batch.

A job owns:

- the selected input documents
- the extraction field configuration
- the execution mode
- the optional job-level local model override when the operator does not want the system default
- the job-level status summary
- the job-level AHMN summary

### Run

A `run` is one execution of the documents inside a job.

Valid run modes:

- `adaptive`
- `strict`
- `both`

If the job mode is `both`, the system should treat that as two explicit runs under the same job, not as one mixed result set.

### Document

A `document` is one file inside a job.

Each document should have its own:

- identifier
- filename
- queue status
- result status
- detail page

## Required Status Model

Each document in a job must expose one simple queue status:

- `loaded`
- `processing`
- `processed`
- `failed`

Rules:

1. a newly added document starts as `loaded`
2. once execution begins it becomes `processing`
3. successful completion becomes `processed`
4. terminal failure becomes `failed`
5. failure must preserve a short visible reason

Do not replace this simple operator status model with subsystem jargon.

## Required UI Surfaces

The primary operator-facing UI should move toward:

- `/dashboard/idpo/jobs`
- `/dashboard/idpo/jobs/<job_id>`
- `/dashboard/idpo/jobs/<job_id>/policies`
- `/dashboard/idpo/jobs/<job_id>/docs/<doc_id>`

The current run-centric routes may continue to exist during transition, but the job model should become the primary operator mental model.

Current branch alignment:

- `/dashboard/idpo` redirects into `/dashboard/idpo/jobs`
- `/dashboard/idpo/jobs` exists as the jobs control board
- `/dashboard/idpo/jobs/<job_id>` exists as the main queue-first operator surface
- the job-detail header now exposes live queue state, current run state, and simple job progress while active polling is in effect
- `/dashboard/idpo/jobs/<job_id>/docs/<doc_id>` exists as the atomic document view
- run-centric routes still exist for drilldown and compatibility

## Jobs Page

The jobs page should show a table of jobs.

Minimum columns:

- `job_id`
- `created_at`
- `mode`
- `status`
- `loaded_count`
- `processing_count`
- `processed_count`
- `failed_count`
- `actions`

The jobs page exists to answer:

1. what jobs exist
2. what is currently running
3. which jobs completed cleanly
4. which jobs need attention

## Job Detail Page

The job detail page is the main processing and inspection surface.

It must contain these sections.

### 1. Job Header

Show:

- job id
- job name if present
- creation time
- mode
- overall job status

### 2. Field Configuration

Show the extraction field configuration used for the job.

This must remain visible because the results table only makes sense when the operator can see what was requested.

### 3. Queue Table

Show a table of allocated documents for the job.

Minimum columns:

- `file_name`
- `file_id`
- `status`
- `run_mode` or run selector when relevant
- `selected_policy` or `route`
- `error_summary`
- `review_status`
- `action`

Rules:

1. the queue table is the main execution tracking surface
2. failures must be visible inline
3. the action should open document detail
4. do not overload this table with every subsystem metric

### 4. Structured Results Table

Show a second table below the queue table.

Minimum columns:

- `file_name`
- `file_id`
- one column per requested extraction field

Rules:

1. for `loaded` documents, requested fields show `NA`
2. for `processing` documents, requested fields show `NA`
3. for `processed` documents, requested fields show structured extracted values
4. for `failed` documents, requested fields show `NA` and the failure stays visible in the queue table
5. this table exists to show the actual extraction outcome, not subsystem metadata
6. processed documents should support bulk `Auto review` and per-document human review without leaving the job/document flow
7. exact document `F1` should only exist after a review artifact is written

If the job mode is `both`, keep results mode-specific and unambiguous.

Acceptable patterns:

- separate run selector above the results table
- separate adaptive and strict result groups
- explicit field columns per mode

Unacceptable pattern:

- mixing adaptive and strict values into one ambiguous cell

### 5. AHMN Job Panel

The job detail page should include an AHMN panel near the job view, not as a separate dashboard-first workflow.

The AHMN panel should stay small at first.

It should show:

- job-level job profile or job nature summary if available
- whether memory or prior advice influenced the job
- high-level recommendation or adaptation summary
- whether atomic document outcomes were logged back

Do not let the AHMN panel dominate the page before the core extraction tables are clear.

### 5a. Job Policy Workspace

Each job may expose a separate policy workspace under:

- `/dashboard/idpo/jobs/<job_id>/policies`

This is a secondary surface, not a replacement for the main job queue.

It should show:

- the effective policy bank available to the job
- which policies are defaults versus job-scoped custom policies
- a policy leaderboard using human-reviewed job-local evidence as the canonical score
- a policy table with processed count, human-reviewed count, human-reviewed `F1`, optional auto-review advisory score, and promotion or demotion state
- a small job review-context view showing the current structured context, operator-added job knowledge, and rendered prompt previews
- a way to add job-scoped custom policies

Rules:

1. custom policies added here are job-scoped, not global
2. added custom policies must become available to the next run for that job
3. the queue table policy column should link into this policy workspace or a policy drilldown
4. the policy drilldown must show where that policy was used inside the job
5. this workspace exists to clarify routing behavior, not to become a second orchestration dashboard
6. policy learning views should keep `TS`, `RABI`, decay, and drift signals here, not in the queue or document view
7. operator-added job knowledge should act as a structured overlay on top of reviewed evidence, not replace reviewed evidence

### 6. XAI And HITL Support

`XAI` and `HITL` should also be centered around the same job and document model.

They are not primary top-level workflows on the operator path.

#### XAI

`XAI` belongs to:

- job-level summary where available
- document-level explanation drilldown

The main job page should only show lightweight signals such as:

- explanation availability
- explanation requested or not
- explanation confidence or summary if already produced

Detailed explanation artifacts belong on document detail or an explicit secondary explanation view.

#### HITL

`HITL` belongs to:

- document-level correction and review
- job-level summary of review-needed and feedback-logged counts

The main job page should only show lightweight review state, such as:

- review needed
- feedback logged
- failed and needs human attention

Full review forms and correction flows belong on the document detail surface or a secondary review queue.

## Document Detail Page

The document detail page is the atomic inspection view.

It should show:

- file identity
- current status
- selected route or policy
- inline original document viewing where supported
- document path in order through the pipeline
- document-level log or timeline with timestamps and clear step descriptions
- extracted fields
- validation issues
- escalation or fallback state if present
- failure details if failed

This is the place for deeper inspection.

The main job page should link here instead of trying to expose every detail inline.

When screen size allows, this page should support side-by-side review of the original document and extracted fields so validation does not require excessive scrolling.

To reduce scrolling and duplication, the document-detail page may use a compact inspector pattern for:

- extracted fields
- review issues
- execution notes
- document log

This is acceptable as long as the original document remains prominent and the document log still drives evidence focus on the same page.

The document log should behave like a queue-item execution history:

- one clear row per meaningful step
- simple timestamps
- simple stage names
- concise action summaries
- no raw trace dump on the main path

The next refinement on this surface is:

- selecting a document-log step should focus and highlight the relevant evidence section on the same page
- extraction events should focus extracted fields
- validation and recovery events should focus review issues
- escalation events should focus execution notes

This should be implemented as a narrow evidence-navigation improvement, not as a new dashboard or trace explorer.

Current branch alignment:

- the document detail page has been reduced toward this atomic view
- extracted fields, review issues, fallback/escalation state, and compact adaptive support signals are now treated as the primary content
- document path and document log are exposed on the main document-detail route
- document-log selection now focuses the matching evidence section on the same page
- when the selected event includes field-level or issue-level signal, the page now narrows the visible evidence inside that section instead of only highlighting the container
- the atomic document route now uses a compact inspector to switch between fields, review, notes, and log without forcing long vertical scrolling
- the `Log` inspector tab now summarizes the selected event and exposes direct jump actions to exact extracted fields or exact review issues when the runtime payload includes enough structure
- the selected-event summary now exposes compact event facts such as route, policy, model, issue count, recovery outcome, or escalation outcome when that event payload provides them
- extracted field rows now surface lightweight evidence hints such as confidence, method, page, source, or model when the runtime already provides them
- provenance timelines, raw bundles, and transparency JSON are no longer part of the main document-detail operator path
- the review form pre-fills field states only from benchmark labels; without labels every state starts empty and `Save review` stays disabled until each field has one, so an unread form cannot send feedback to AHMN

## Design Rules

The job-centric UI must follow these rules:

1. table-first, not dashboard-first
2. adaptive extraction outcome first, subsystem detail second
3. status must be simple and readable
4. failures must be graceful and visible
5. requested extraction fields drive the results table structure
6. AHMN is present as support, not as the primary visual focus
7. XAI and HITL are attached to jobs and documents, not promoted to separate operator-first dashboards

## Keep / Simplify / Quarantine / Remove Guidance

### Keep

- jobs list
- job detail queue table
- structured results table
- document detail page
- compact AHMN job panel
- compact XAI availability signal
- compact HITL review signal

### Simplify

- run summaries
- job status summaries
- advanced run settings
- per-document metadata shown at top level

### Quarantine

- provenance timelines
- transparency JSON
- shadow comparison dashboards
- retrieval and answering artifacts
- large raw metrics surfaces
- full explanation internals
- full review forms on the main job page

### Remove

- subsystem-first tabs on the main operator path
- duplicated summaries that do not change action
- decorative analytics that hide extraction outcomes

## Acceptance Criteria

This direction is correctly implemented when:

1. an operator can create a job and see allocated files clearly
2. an operator can see document statuses move through `loaded -> processing -> processed` or `failed`
3. an operator can configure requested extraction fields before execution
4. an operator can read extracted structured results in a table without opening subsystem panels
5. an operator can open one document for atomic inspection
6. AHMN support is visible but does not crowd out the extraction workflow

## Immediate Implementation Guidance

The next frontend passes should not try to build the full final system at once.

Use this order:

1. reshape the main frontend around `job` as the primary object
2. keep the queue table, field configuration, AHMN summary, and structured results table explicit and stable
3. keep current runtime wiring behind the scenes until the UI contract is stable
4. only then decide what backend contract changes are actually required
