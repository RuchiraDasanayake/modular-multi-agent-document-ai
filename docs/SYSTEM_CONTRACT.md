# System Contract

This file defines the current practical contract for the system. The proposed product architecture and acceptance gates
are in `docs/PRODUCTIZATION_PLAN.md`; they must not be read as implemented features.

It is intentionally shorter and stricter than the long architecture docs.

## Purpose

The system is a document-processing platform with a canonical research runtime and a separate opt-in product extraction
path, plus a few legacy or research-facing support surfaces.

The native Windows product launcher runs local PostgreSQL, the authentication gateway, a separate extraction worker
and the frontend. The worker runs the existing local Python extractor. Docker and Redis are optional for this product mode. Set
`TOKEN_REVOCATION_BACKEND=postgresql` and explicitly apply `gateway/native_auth.sql` to the configured database.
Refresh rotation uses a durable atomic claim before issuing replacement tokens; storage failures deny refresh.
The launcher requires persistent explicit secrets and binds only loopback. It supports a verified production frontend
build or a development server; rate limits remain process-local. Native product extraction uses pg-boss with atomic PostgreSQL admission, per-owner pending
limits and a single active attempt per job. Sources and schema snapshots are verified before execution; interrupted
attempts are terminal and never automatically replay paid calls. Queue state survives web restarts. Artifact storage
is still a configured filesystem shared by web and worker; this does not establish multi-host storage, per-document
resume, or high availability. The historical direct subprocess mode remains for existing deployments/tests. See
[`scripts/native_product.md`](../scripts/native_product.md) for setup, startup and ownership-checked shutdown.

Office intake checks ZIP structure and bounded decoded XML before invoking its readers. Spreadsheet cell coordinates,
merged ranges and hyperlink ranges are checked before allocation, including UTF-16 and relationship targets with
nonstandard names. Complex valid files can exceed these limits and receive an explicit unsupported result. See the
[allocation guard receipt](evaluations/OOXML_ALLOCATION_GUARD_20261013.md) for the reproduced defect and tests.

Product image intake and schema sampling require single-frame sources. Multipage TIFFs and animated PNGs are
explicitly rejected before OCR or model calls; they must be split into separate files. Reading only their first
frame would falsely imply complete coverage. This check does not change the frozen PDF/PNG benchmark checkouts.

New product queue dispatches also seal the selected OCR engine and response format. Optional local RapidOCR
uses a separate pinned CPU environment with page resource bounds and exact line evidence. Optional strict
confirmed-schema output sends an explicit JSON Schema to the provider and independently validates the response
locally. Both remain opt-in, with defaults unchanged. Neither correct JSON nor an exact OCR quotation establishes
semantic correctness. See [RapidOCR](PRODUCT_RAPIDOCR.md) and [strict values](PRODUCT_STRICT_CONFIRMED_VALUES.md).

Strict confirmed values v2 is an additional explicit profile: the provider-facing `values` object requires every
confirmed field ID, with typed values or null. Its text and visual decoders validate the raw reply before converting
it to the existing review representation. V1 profiles and default behavior are preserved; completed v1 studies do
not measure v2 quality. A required key prevents structural omission only when enforced; it does not prove that a
null or proposed value is correct.

Schema and value replies share a 1,000,000-byte UTF-8 JSON limit. The local decoder rejects duplicate properties,
nonfinite numbers, invalid raw Unicode, escaped lone surrogates and nesting that raises its recursion error;
there is no separately configured numerical depth limit. Invalid replies fail the affected document without
aborting later originals. A visual scalar must also coerce to its confirmed type before complete coverage can
be recorded; an invalid scalar fails the whole candidate without fallback or retry. Exact known confirmed field
IDs retain their Unicode identity. String and linked-cell evidence comparisons use lowercase, matching the
frontend in the tested cases; case-fold expansions alone cannot establish a text match. These are structural
and contract guards, not new extraction-quality results. See
[reply integrity](evaluations/PRODUCT_REPLY_INTEGRITY_20261015.md).

An explicit `bounded_text_segments_v1` profile also seals long-document behavior. Confirmed schemas can process
up to four lossless text segments per logical document, each limited to 24,000 characters. Every source page,
including an empty page, must have verified coverage before model execution. Invalid or incomplete replies fail the whole candidate;
conflicting scalar values require review. Complete processing is distinct from correct extraction. Older dispatches
retain their original behavior. See [long documents](PRODUCT_LONG_DOCUMENT_SEGMENTS.md).

The opt-in `bounded_visual_v1` profile routes confirmed-schema images and PDFs requiring OCR to complete
page images with OCR text/geometry aids. All-native PDFs and other supported native/text formats use strict
text extraction. Image requests are prepared before sending any page and require complete coverage within
four requests per logical document (at most 12 images and a complete 4 MiB body per request). Invalid or incomplete visual
replies fail the whole candidate;
all visual values require review, including exact OCR matches. Dispatch versions 3 and 4 seal this choice in an
extraction profile whose version remains 3; older jobs do not acquire visual routing from later server configuration.
This is an implemented candidate, not a validated accuracy claim. See [visual extraction](PRODUCT_VISUAL_BOUNDARY.md).

The explicit `bounded_visual_selective_jpeg95_v1` candidate retains selective-v2 routing and uses full-page
JPEG95 payloads within the same limits. Its lossy payload hash and codec are distinct from the original OCR
raster hash. It is opt-in and quality-unvalidated; existing PNG profiles and frozen study definitions are unchanged.

The frontend accepts only known visual proposal metadata: exact source page IDs, optional `text_match` OCR spans,
and `visual_grounding_verified: false`. It refuses unknown fields, repeated or absent page IDs, and machine-accepted
visual values. The review page marks them **Image-derived — review required** and shows their source pages beside
the original file. A reviewer can explicitly confirm all visible linked cells after inspecting that original;
the revisioned review binds the decision to the source and machine-result hashes. A completed reviewed export then
marks the field `human_verified`. Nested cell status and `visual_grounding_verified` still describe the original
machine proposal, not OCR or pixel verification. Image-derived candidates cannot seed a reusable approved recipe.

On a sealed visual route, a reviewer may add missed scalar values or linked cells using exactly one source
reference: an exact OCR quote, or `human_source_page: {kind: "human_observed_page", page: N}` for an actual page of
the original image. Page observations remain pending until the reviewer completes the revisioned audit. Export
preserves the page reference and `visual_grounding_verified: false` so consumers can distinguish a human observation
from machine-grounded evidence. Text-route additions still require exact OCR quotes; visual additions remain
ineligible to seed reusable recipes.

The selective visual routing v2 profile chooses a path before any model call: short scalar OCR documents use strict
text extraction, while repeated columns, sources over 24,000 text characters, and images or OCR PDFs without usable
text use visual extraction. Native formats and PDFs with usable native text keep their existing paths. It does not
automatically retry a failed paid call through the other path; older v1 dispatches retain their frozen routing.
See [selective visual routing v2](evaluations/SELECTIVE_VISUAL_ROUTING_V2_20261013.md).

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

Document uploads use bounded streams: 20 MiB per file, 32 MiB per raw request including multipart framing, and
32 files or parts per request. The browser sends sequential batches of at most eight files and 30 MiB, reports
accepted versus unconfirmed files after a failed batch, and never silently replays a successful batch. The exact
`POST /api/jobs/<job_id>/documents` route skips Next's proxy body clone so the route can count the original stream;
it authenticates the user and checks job ownership before staging bytes. An aborted or invalid request removes its
temporary files, and a failed job metadata save removes only that request's final files. The current JSON job store
serializes commits only within one server process; cross-process writers and per-owner storage quotas remain open
scaling work.

Browser upload batches carry a fresh idempotency key. The job JSON atomically stores that key, an ordered digest of
the staged names, types and bytes, and the committed file IDs. Retrying the same key and payload returns the current
job without adding duplicates; reusing it for different bytes or after the original changes returns 409. The UI keeps
the failed batch key when a response is lost. This guarantee is for one frontend process; a transactional metadata
store is needed before running multiple frontend writers.

The native frontend admits work to PostgreSQL, and an independently supervised extraction worker invokes
`idpo.cli process-auto`. The historical direct subprocess mode remains available. In Compose, the frontend invokes
a Node bridge to a private Python worker over a Unix socket in the shared data volume. That Docker path has passed static
Compose checks, a frontend build and focused tests but has **not** completed a live container extraction smoke here.
The default Compose profile starts PostgreSQL, Redis, gateway, product worker, and frontend. The four separate
research services start only with `--profile research`; they are not used by this product path. The canonical
research job runner is explicitly unavailable in Docker.
An October two-user audit reproduced cross-owner reading of legacy run artifacts through a traversal document ID;
the frontend now rejects unsafe document IDs and confines document and review artifact paths to the authorized run.
Focused two-user, traversal and directory-link tests pass. This fixes that route, not every possible ownership path;
a broader route audit remains an external-release gate.
The same audit reproduced a separate local filesystem junction escape in the authenticated original-content route.
That route now derives the expected job upload directory from configuration and confines resolved directory and file
paths before reading. A Windows junction regression and the full 78-test frontend server suite pass. A process with
permission to replace local paths can still race a path check against a read; this is not an HTTP-only exploit found
in the bounded audit, and the broader release audit remains open.

The CLI accepts one file or a directory. It supports PDF, common raster images, text, the existing JSON document
format, and source-native DOCX, XLSX, PPTX, HTML, and EML. The five native adapters preserve parser-derived text
offsets and table-cell source locators in an optional `parsed_document` v2 sidecar; the current extraction candidate
and review contract stay v1. A native address is not a pixel box or proof of business meaning. Native source units map
to the existing one-based `pages` evidence interface, and the reviewer sees the unit label and matching native cell
address where available. Native formats bypass OCR normalization. Office ZIP, sheet-grid, HTML-tree, MIME-tree,
derived-text, table-cell, and existing input-byte limits produce unsupported or parse-failed outcomes. The native
view covers Word top-level paragraphs/tables, worksheet cells with formulas unevaluated, slide native text/tables,
HTML DOM text/tables without CSS rendering or network fetches, and one preferred non-attachment EML text body.
Embedded images, presentation notes, email attachments, nested Word/HTML tables and grouped slide shapes are not
extracted; the latter three structural cases explicitly abstain when encountered.

Product JSON intake accepts one document object or a nonempty array within 20 MiB, with at most 5,000 logical
documents per container and a nonempty list of at most 50 pages per document. It validates the entire container
before allocating document or page objects. Document IDs must be nonblank strings; page text must be a string
(empty when omitted), and `raw_text` must be a string or null. Explicit page IDs must be distinct positive integers no greater than
`2^53 - 1`; omitted IDs use one-based positions, and valid explicit IDs are preserved. Duplicate JSON properties,
nonfinite numbers, malformed shapes and invalid Unicode are rejected. Supplied image paths and metadata are
stripped from executable objects, while canonical entry hashes still include the complete original entry.

If any JSON entry is invalid or exceeds a limit, the whole container abstains rather than partially extracting
earlier entries. It produces one original-file failure: `parse_failed` for malformed input,
`json_document_limit_exceeded` for excessive entries, or `too_many_pages` for excessive pages; the latter two
are unsupported outcomes. Other admitted originals continue. Python preflight counts each valid logical document
and one unit per invalid original, rejecting more than 5,000 units before creating run artifacts or calling a model.
It rechecks admitted source hashes before construction. JSON schema samples undergo the same complete validation
before constructing at most the first two logical documents. Shared research intake is unchanged. See the
[JSON input guard](evaluations/PRODUCT_JSON_INPUT_20261015.md).

The research `process-inbox` intake retains its narrower format support. The product path uses local OCR/text extraction
and either a deterministic label/value proposal or an optional
OpenAI-compatible chat model for scalar or bounded repeated-column schema discovery followed by value extraction.
With no model, a conservative native-table adapter also proposes linked columns when a complete parser grid has
credible headers and exact cell anchors. It rechecks the source hash, reads HTML/EML header and visibility structure
or a declared XLSX table and formula/visibility state, and records each proposed cell's native locator beside the
v1 candidate. DOCX/PPTX use a stricter row-shape check because the current parsed contract has no semantic header
flag. Ambiguous, sparse, merged, hidden, or unverified tables abstain; these are literal, review-only proposals,
not a claim that column meanings or row relations are correct. This arm is limited to source-native files and does
not alter PDF or image extraction.
Product-auto Tesseract calls now have a 30-second default timeout and a 120-second per-image-page search budget;
these limits are configurable in the CLI and do not alter the canonical research OCR route. A timeout with no text is
an execution failure, while partial text remains in review. The [pinned v6 gate](evaluations/VRDU_2000_NO_MODEL_V6.md)
completed 2,000 sources with no timeout events. The [PDFium-first v7 gate](evaluations/VRDU_2000_NO_MODEL_V7_PDFIUM.md)
also completed 2,000 distinct sources with no OCR failures; it had 23 more false schema fields and still produced
zero linked rows. The [v8 provenance gate](evaluations/VRDU_2000_NO_MODEL_V8_PROVENANCE.md) checked another
2,000-source execution at the same source hashes: all 831 scanned PDF pages actually used PDFium, and strict
schema F1 remained 4.2423% with zero linked rows. RapidOCR outperformed Tesseract on fixed CORD development
text-box crops and full pages in separate diagnostics, but the unchanged product schema/row layer still mapped
zero exact CORD fields or linked rows from either engine. The product default remains Tesseract.
Local loopback HTTP servers may run without an API key; remote providers require an HTTPS URL and server-side key. The model can replace the
heuristic schema. Proposed values require exact text-span evidence and a matching, JSON-round-trippable typed value
for machine acceptance. Ambiguous boolean quotes and partial identifier matches stay pending review. A newly
discovered schema is unapproved, so every document remains `needs_review` until an operator reviews it.

New model-backed product runs use a server-only output budget of 8,192 tokens and a 180-second per-call timeout by
default. `IDPO_AUTO_MAX_OUTPUT_TOKENS` (1–16,384) and `IDPO_AUTO_TIMEOUT_S` (1–600) can lower or raise those limits;
invalid settings reject admission. PostgreSQL queue dispatch versions 2–4 seal the selected limits with their profile digest,
so later environment changes do not alter a prepared run. Previously prepared version 1 dispatches retain their earlier
CLI defaults of 1,200 tokens and 60 seconds. Direct CLI calls also retain those defaults unless flags are supplied.
The separate draft-suggestion action keeps its own 1,800-token limit; the 24,000-character source cap is unchanged.

New native dispatch envelopes use version 4, without changing extraction-profile version 3. Before queue admission
or direct execution, the server counts immutable staged originals: a standard JSON array reserves its raw length,
with at least one unit for an empty or malformed original; other formats reserve one unit. Selected sets over
5,000 originals reject before copying, after existing idempotent requests have been reconciled. A planned total
over 5,000 logical documents rejects with HTTP 413 before worker or provider execution. JSON reads are bounded
to 20 MiB. Invalid array entries may later collapse to one Python failure, so this reservation is deliberately
conservative rather than a count of valid documents or successful extractions.

Dispatch v4 seals that logical-document budget in prepared bytes and run metadata, uses it for PostgreSQL queue
admission, and verifies agreement with the queued request and recounted source bytes before starting Python.
Previously prepared versions 1–3 retain selected-original counting and reject incompatible added budget fields;
they are not reinterpreted as v4. Interrupted or uncertain paid attempts remain terminal. The text-segment and
visual-request caps above apply per logical document, not per uploaded JSON container. Neither the logical budget
nor those caps establishes an aggregate API-request or USD limit for a run.

A separate owner-scoped registry can save a completed review as a draft schema and explicitly approve it as `approved_shadow`.
The operator may select a current approved revision for one run. The frontend rechecks its source
review and owner, freezes a SHA-256-bound schema snapshot, and the worker skips schema induction
and calls the model only for values. A stale or disabled selection fails closed; an invalid or incomplete
model response fails the document and cannot be reviewed or exported as if the fields were absent.
Receipts identify the exact recipe revision,
event, and snapshot hash. Family selection is explicit; there is no automatic matching or release.
A model can propose repeated columns as `array[object]` values with
shared row ordinals and per-cell text evidence; row links remain pending human review. This is not a visual table
parser, stable row identity across versions, or a guarantee of useful fields on unfamiliar documents.

`product_runs/<run_id>` contains `run.json` as the completion marker, `manifest.jsonl` with source hashes and per-document
receipts, `candidates.jsonl`, and `docs/<doc_id>/result.json` with source-text units, per-page PDF renderer provenance
or native parser identity and locators, the proposal, model-call telemetry and reason. Worker process CPU and boundary RSS snapshots are recorded where
available; they exclude OCR child processes and remote model compute, and RSS is not peak memory. Cost fields exist
but remain null until provider prices, compute rates and review work are recorded. The
frontend checks source hashes and artifact consistency before displaying a completed run. Owner-scoped result and
source routes lead to a field review page. A reviewer can correct or remove proposed scalar fields, add missing
scalar fields, inspect or correct bounded linked cells by row, and add a wholly missed linked column. The server checks
text-backed machine cell evidence and requires a unique exact OCR quote and page for every new linked cell; it also
requires an exact source quote for a newly added scalar. It accepts a human row correction only as a typed array.
The API derives a document-scoped `correctedResult` from the
immutable machine candidate and latest review snapshot. Undecided machine values remain in review; human corrections
are reviewer assertions; newly added scalar and linked-cell corrections carry checked OCR quotes, which prove source
presence but not semantic correctness. Review changes append revisioned events and reject stale saves. A successful
review save returns the verified document, current review revision and audit trail in the same response, so a second
browser read cannot turn a confirmed save into an apparent failure or leave its revision stale. A reviewer may
record 1 to 14,400 seconds of self-reported active work for an individual save; the system does not infer this time
and older events have no such field.

The owner-scoped `GET /api/jobs/<job_id>/auto/<run_id>/docs/<doc_id>/export` route downloads a versioned JSON result only
after that document's review is complete. It rechecks the original source, OCR-page, machine-result, and review hashes
at download time. The export carries typed fields, per-field status and provenance, source and machine hashes, and the
review revision; it omits the raw source and server file paths. A human-corrected value is still a reviewer assertion
unless it has explicit evidence. The owner-scoped `GET /api/jobs/<job_id>/auto/<run_id>/export` route downloads
reviewed JSONL in selected-original order, retaining manifest order for logical documents within each original.
One JSON original can produce multiple records. Every selected original must be represented, every logical
document must have complete, current, source-linked review, and logical IDs and sealed result hashes must agree.
Partial, failed, missing, duplicated, unselected or stale results return a conflict instead of an incomplete
download. The current batch export is bounded to 5,000 logical documents and 64 MiB; the individual JSON export
shape is unchanged. Shared sealed-run and source verification avoids rereading the entire run for every exported
document.

The browser's readiness check counts reviewed logical documents, permits more results than selected originals,
and requires unique logical IDs and a represented-original count matching the selection. Failed and unsupported
documents never count as completed reviews. The remaining-batch preview gate also requires every logical result
to have a completed review of a `needs_review` proposal. These UI checks do not authorize export or batch admission;
the server still verifies exact selected-source membership and the complete sealed manifest and review receipts.

For failed or unsupported documents, the owner-scoped detail API may expose an allowlisted `outcomeReason` code from
the sealed result sidecar. It never returns an arbitrary sidecar error string. The document page maps that code to
fixed cause and next-step copy, keeps the original available, and withholds review and export controls because the
run has no complete reviewable result. Unknown reasons use a generic explanation.
The review-save and individual-export APIs also reject these document statuses with HTTP 409, including previously
saved completed reviews. A failed result cannot become exportable through a direct API call or a legacy review.

The owner-scoped `/api/jobs/<job_id>/auto/brief` API stores a revisioned extraction brief with plain-language intent,
typed field meanings and examples, and 1–5 sample file IDs bound to source SHA-256 hashes. `GET` reports stale sample
IDs; `POST` requires the current revision and appends an immutable draft event. `PATCH` explicitly confirms the current
revision and payload digest only when it has typed fields with descriptions and all sample bytes still match. Any subsequent edit appends
a new draft; it does not inherit confirmation. Intent-only drafts cannot start this schema-guided route.
The browser requires a successful brief read for the current job before enabling schema editing or model actions.
A failed read shows an explicit retry and cannot be treated as an empty saved schema. Setup inputs also lock while
saving, requesting suggestions or admitting/running extraction, so an earlier response cannot replace edits made
while its request is pending. Example fields preserve line breaks while editing; saving trims lines, removes blank
entries and rejects more than three nonblank examples instead of silently dropping them.

The owner-scoped `POST /api/jobs/<job_id>/auto` route accepts an explicit `confirmedBrief` selection. The `preview`
phase must select exactly the confirmed sample files. The `batch` phase excludes those files and requires the exact
confirmed preview run, complete source-linked human review of all its logical documents (including multiple entries
from a JSON sample), unchanged sample sources, and valid run, document, and review receipts. The frontend freezes
a SHA-256-bound schema snapshot; the native worker validates
its bytes and fields before running. It skips schema discovery, sends field descriptions, examples, and intent with
source text to the value model, and checks exact source evidence locally. Values remain pending review. The run,
manifest, and document artifacts carry the same confirmed-schema receipt. This path requires a configured value model
and currently inherits the admin-only model-call gate. The earlier dynamic discovery and approved-recipe v1 paths
remain available. An admin can explicitly request `POST /api/jobs/<job_id>/auto/brief/suggest` for the current saved
draft revision and digest. The server rechecks owner and sample hashes, sends bounded text excerpts from 1–5 sample
sources to the configured OpenAI-compatible model in one call (at most 1,800 output tokens, no retries), and returns
typed fields, clarification questions, source hashes, parser IDs, and usage provenance. The response is an editable proposal;
it does not save, confirm, or run extraction. Users must use the proposed fields in a new draft, resolve questions,
confirm field meanings, then preview and review. This action currently requires admin access and the product Python
environment's optional `cloud` dependency for an OpenAI-compatible model. It can also use a loopback model endpoint
without a cloud key. Sampling uses at most 1,800 characters per source (9,000 total), first two PDF pages, and bounded
OCR for scans; fields outside those excerpts may need manual addition.
PDF/image previews use shared intake, the PDF native-layer paint guard, and the server's
`IDPO_AUTO_OCR_ENGINE` (`rapidocr` or default `tesseract`). PDF text/paint inspection and OCR are limited
to the first two pages; PDFs over 50 pages reject before page extraction or rendering. Each preview OCR
page has a 15-second budget and no quality reruns. Any reported OCR failure stops the suggestion before
the model call. Temporary render/OCR artifacts under `IDPO_DATA_DIR/brief_previews` are removed after
normal completion or handled failure. Parser IDs identify this preview path and configured engine; they do not claim that
every page needed OCR or that the excerpts cover the whole source. Full extraction uses its separate
configured page budgets and full-document coverage rules.
Each request writes a private, content-free attempt receipt under the configured data directory's
`frontend/auto_briefs/<owner-hash>/<job-id>/suggestions` folder. Failure receipts record stage, bounded code,
provider finish reason, usage counts when available, and SHA-256 of the model reply, without the reply or source
text. `IDPO_AUTO_SUGGEST_CAPTURE_RAW=1` is an explicit operator-only diagnostic option that saves the raw reply
as a separate local file with owner-only mode where supported; it is off by default. A failed or uncertain request
is never retried automatically.

The job-scoped recipe API separately records owner-scoped draft, approval, and disable events from completed reviews; it
requires explicit linked-row group confirmation and can configure one explicitly selected run.
This is not geometric table annotation.

The native launcher uses the durable PostgreSQL queue described above. The historical direct mode runs a child
process of the frontend; Docker uses a private worker that admits one run and returns busy for another. The Docker
bridge does not support confirmed-schema preview and batch arguments. Automatic recipe matching, per-document
resume, reusable visual row extraction policies, per-user cloud credit quotas and verified live Docker execution
remain absent. Model-backed UI runs are admin-only until cloud data and spend controls exist. It does not use the AHMN policy router, Guardrails
service, or the separate XAI-HITL service. Its benchmarks and outputs must never be represented as the submitted paper's
results or as the canonical research runtime's outputs.

The native product screen implements intent entry, bounded AI schema suggestions, field-meaning confirmation,
source-pinned sample preview and a reviewed-preview gate before the remaining batch. The queue enforces finite
per-owner admission limits. The authenticated synthetic smoke verifies this flow on two text invoices; it does not
establish real-document quality or arbitrary scale. Reviewed JSON is downloadable per document and JSONL per
completed run under the limits above. UI labels call machine-accepted values **Text matched** because exact OCR quotes do not establish
correct field meaning or correspondence to the original image. Human review remains a separate decision.
Model-backed HTTP run starts require a random 32-hex `Idempotency-Key`; browser requests retain it in session storage until a run is returned or
reconciled. A repeat with the same key and unchanged selection, source bytes, and schema or recipe revision returns
the existing queued, completed, or failed attempt. The server stores a separate random run ID so different jobs can safely reuse the same key. A changed request fails with 409; a claim with no run record also
fails closed. This prevents a lost HTTP response from silently starting another paid attempt. Older API clients that
omit the header can only use the model-free path; direct internal calls retain their legacy behavior. The queue does not promise transactional exactly-once
external model calls. A separate attempt requires an explicit new key.
Schema suggestions request a closed JSON Schema response from the configured provider and are validated again
locally; provider support does not imply semantic correctness. A repeated row is drafted as one `array[object]`
field per column, with a shared `group` string. Scalar suggestions use a null group on the provider wire, which
the helper removes before returning the existing brief field shape. Missing groups and extra properties are
rejected. A structurally valid proposal may still omit a requested column, so
a user must inspect, edit and confirm field meanings before preview or batch extraction.
The [productization plan](PRODUCTIZATION_PLAN.md) records the remaining quality, cost and deployment gates.

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
`frontend/src/proxy.ts` checks their session, and the job API routes resolve the current user before accessing
stored resources:

- Public without a session: `/`, `/features`, `/about`, `/docs`, `/contact`, `/login`, `/signup`, `/forgot-password`,
  `/reset-password`, static assets, and the `/api/*` routes that are proxied to the gateway, which checks them itself.
- Session required: the local job API (`/api/jobs`, `/api/runs`, `/api/benchmarks`) and every other page, including
  `/dashboard/*`.
- A session is the bearer token in the `Authorization` header or the `ahmn_token` cookie. It must be an unexpired JWT
  that the gateway accepts at `GET /api/auth/me`; accepted tokens are cached for 60 seconds.
- Without a valid session the job API answers 401 and pages redirect to `/login`, deleting a rejected cookie. When the
  gateway cannot be reached, both answer 503.
- The proxy reaches the gateway at `INTERNAL_API_URL`, then `NEXT_PUBLIC_API_URL`, then `http://localhost:8000`.

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

The separate product path above may simplify or replace these service boundaries after measured quality, cost,
security and operability checks. Its native worker, bounded visual evidence, explicitly approved recipes and
revisioned review are implemented under the limits above. The remaining quality, cost, security and deployment
acceptance gates in `docs/PRODUCTIZATION_PLAN.md` are not established by those implementations.

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
