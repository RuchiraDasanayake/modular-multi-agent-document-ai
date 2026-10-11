# ADR 0001: Evidence-preserving document extraction

Status: **accepted as the staged target architecture**, 2026-10-12. Owner: product extraction. Parser, model, and queue
adapters remain subject to the stated measurement gates. This is not an implemented contract or a quality claim.
[SYSTEM_CONTRACT](../SYSTEM_CONTRACT.md) describes the current runtime;
[PRODUCTIZATION_PLAN](../PRODUCTIZATION_PLAN.md) owns the broader release gates. The accepted May manuscript, frozen
October study, and new product benchmark remain separate.

## Decision and criteria

Build one modular extraction path around a **versioned parsed-document contract**, then compare parser and model
adapters on the same holdout. Keep a simple, fixed processing route until another route demonstrates a better
quality-cost frontier. Rank decisions by (1) critical-field and linked-row correctness, (2) inspectable source
evidence and reviewer time, (3) total cost per correctly released document, and (4) reliability and data isolation.
Open-source and local components are preferred when they meet these gates; local CPU, local GPU, and approved cloud APIs
are all candidates. "Any document" means no template choice at intake, with explicit unsupported/illegible outcomes;
it does not imply that every file format or unseen family is accurately understood.

```text
owned upload -> immutable source -> bounded parse/OCR -> ParsedDocument v2
             -> proposed typed schema -> value/row extraction -> evidence + rules
             -> accept under policy / abstain / human adjudication -> versioned export
```

The first parser candidate is **Docling**, because its documented representation includes page provenance and table
cells with row/column offsets and spans, and its supported inputs include PDF, Office documents, and images
([formats](https://docling-project.github.io/docling/usage/supported_formats/),
[document model](https://docling-project.github.io/docling/reference/docling_document/)). This is a **spike**, not a
decision to replace the current parser. Keep [pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
plus Tesseract/PaddleOCR as the measured baseline. Try [PaddleOCR PP-StructureV3](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PP-StructureV3.en.md)
only on scan/table slices where it adds value: its documented output includes reading-order blocks, OCR polygons,
table HTML, and cell boxes. Conversion quality and deployment cost are unmeasured in this repository.

| Current evidence in this checkout | Consequence for the target |
| --- | --- |
| [Intake](../../idpo/agents/intake.py) supports JSON, TXT, PDF, and common raster images; PDF text comes from pypdf. [Page](../../idpo/core/types.py) stores text and optional image path/metadata. | Add a parser adapter and explicit format outcomes; do not make downstream code depend on Docling classes. |
| [product_auto](../../idpo/product_auto/workflow.py) proposes at most 24 scalar fields, uses at most 50 pages/24,000 model characters, and writes exact page-text offsets. It leaves discovered schemas in review. | Preserve its safe abstention behavior; extend the result contract for nested/repeated fields and visual evidence. Do not call a text match semantic validation. |
| [TableFormAgent](../../idpo/agents/preprocess.py) detects text lines containing pipes or tabs; the auto path does not consume structured cells. | A table parser and row linker need their own measured slice. Flat keys cannot represent line items reliably. |
| [Frontend auto runs](../../frontend/src/server/product-auto.ts) spawn a child process and store run/review JSON on the host. Review can correct or remove proposed scalar fields and add missed scalar fields on one document, but cannot approve reusable schemas or edit linked rows. PostgreSQL and Redis exist in Compose but are not this job path's durable queue or metadata store. | Add approved schema revisions and row adjudication before claiming reusable recipes; move execution state into durable metadata/queue when the single-host pilot advances. |

The [2,000-document VRDU no-model development baseline](../evaluations/VRDU_2000_NO_MODEL_V1.md) reported 4.33%
strict schema F1 and 0.95% strict value F1 across two families; all 2,500 ad-buy linked-row field records were
missing or unresolved. It made no model calls, so it is not a test of AI-generated schemas or these parser candidates.
Its cost and human-review fields had zero coverage, so it cannot establish cost per accepted document. These results
motivate the row/schema gates; they do not predict performance on arbitrary document families. That archived run's
`processed` status also predates the current review-only behavior in `process-auto` and must not be interpreted as
approved, correct output.

## Product contracts to introduce

1. **ParsedDocument v2:** immutable source hash and format; parser/model version; pages with width, height, rotation,
   source coordinate system, text/word spans, reading order, and elements. A table has an ID, page region, cells with
   row/column indices and spans, text, and evidence. Store both raw parser coordinates and one normalized top-left
   coordinate transform for the viewer. Preserve the original file and page render. A parser element is evidence of
   content, not proof that the content belongs to a business field. Docling's
   [provenance](https://docling-project.github.io/docling/reference/docling_document/) and
   [span-preserving table model](https://docling-project.github.io/docling/concepts/serialization/) can map into this
   contract; serializing a table only as Markdown loses important structure.
2. **SchemaProposal and approved Recipe:** document-family hypothesis, typed fields, grouping, cardinality, nested or
   repeated-record shape, table-column mapping, label evidence, and version. Auto mode proposes a schema and values in
   one job. Reviewers can add, remove, rename, type, and group fields before approving a reusable recipe. A one-off
   key found on a document remains distinct from a stable customer business field. Never auto-promote an unreviewed
   correction or mutate an approved recipe in place.
3. **ExtractionResult:** values reference schema version and one or more page elements/regions or exact text spans;
   preserve raw and normalized values, missing versus zero, derivation, parser/model version, and accept/review/reject
   state. Repeated records contain a `table_id`, `row_id`, ordered cells, and explicit `continuation_of` for a row
   continued on another page. Link only where headers, geometry, and values support the relation; otherwise leave the
   relation pending review. Stable IDs are scoped to source hash plus parser/recipe revision, not generated field names.
4. **ReviewEvent:** immutable machine proposal, reviewer edits to fields, rows, links and evidence, actor, time,
   revision, reason, and adjudication state. Side-by-side page rendering highlights the exact region; if a parser
   supplies text only, the UI must disclose that limitation. A value may be accepted automatically only under a
   predeclared policy that has passed holdout tests for that field/family. Exact quoted text alone cannot establish
   semantic correctness, as the existing invoice-to-healthcare-key smoke failure shows in
   [PRODUCTIZATION_PLAN](../PRODUCTIZATION_PLAN.md).

## Component and operations choice

| Boundary | Lean choice | Reason / alternative gate |
| --- | --- | --- |
| Parse/OCR | Current pypdf/Tesseract/Paddle baseline; Docling adapter first; PP-StructureV3 for measured hard slices | Docling documents configurable table recognition and PDF cell mapping ([options](https://docling-project.github.io/docling/usage/advanced_options/)); Paddle exposes cell boxes and OCR output. Benchmark native PDF, scan, multi-page, and table cases separately. Pin code and model weights and inspect licenses. Docling code is MIT; PaddleOCR and Tesseract code are Apache-2.0 ([Docling](https://github.com/docling-project/docling), [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), [Tesseract](https://tesseract-ocr.github.io/tessdoc/)). Code licenses do not settle model-weight or dataset rights. |
| Schema/value model | Provider-neutral interface over local CPU, local GPU, and approved cloud API; fixed two-step schema then values | Compare each under identical parsing, prompt budgets, and held-out documents. Strict JSON/schema validation and source evidence are required but cannot prove field meaning. Keep bounded fallback only if it lowers total reviewed cost. |
| Queue and metadata | For release beyond one host, PostgreSQL for jobs, owners, recipe/review revisions, and an outbox; Redis-backed Celery workers for bounded parse and inference tasks | Compose already includes PostgreSQL/Redis. Celery documents that late-ack tasks may execute more than once, so worker outputs need idempotent keys and atomic publish ([tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html)). Do not add Temporal until human waits/replay cannot be managed with this smaller design. |
| Bytes and tenants | Keep content-addressed originals/derived artifacts behind a storage interface; single-host files first, object storage when workers span hosts. Every metadata row, object reference, cache key, retrieval query and review action carries tenant/owner scope. | Authorize in the API and test indirect artifact URLs. PostgreSQL row-level security can provide defense in depth, but owners/superusers can bypass it, so role design and tests still matter ([PostgreSQL](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)). Cloud egress requires explicit tenant policy, provider terms, regional processing, redaction if needed, and hard spend caps. |

No retrieval memory, vector index, agent loop, or extra service is required for the first useful extractor. Approved
recipes and examples can be retrieved by exact tenant/family filters. Add semantic retrieval or adaptive routing only
after a no-memory/static-route ablation improves the same holdout without critical-field regressions.

## Migration and acceptance gates

1. **Freeze comparator:** snapshot current `process-auto` outputs and tests on a legally usable product set. Include
   born-digital/scanned PDFs, DOCX and images, rotated pages, unfamiliar families, repeated tables, cross-page rows,
   blank cells, missing values, and zero. Split by source/layout family and keep the holdout untouched. Record source
   hash, parser/model versions, reviewer minutes, CPU/GPU time, API spend, retries, latency and failure reasons.
2. **Parser contract spike:** adapt current parser and Docling into ParsedDocument v2 without changing the extractor.
   Inspect overlays for page/rotation/coordinate correctness and compare text, cells, rows, headers and table spans
   against adjudicated gold. Test PP-StructureV3 only on preselected failed scan/table slices. Reject an adapter that
   improves text but degrades evidence or linked rows beyond predeclared margins.
3. **Schema and row slice:** add nested/repeated schema proposals and one line-item family through the fixed route.
   Score schema induction separately from extraction against a gold schema, then score end-to-end auto mode on unseen
   families. Report field/type/group precision and recall, row grouping and cross-page link accuracy, cell-level
   value/evidence accuracy, critical-field false acceptance, abstention coverage, and perfect-document rate. The
   [DocILE KILE/LIR format](https://github.com/rossumai/docile) is a useful public reference for localized fields and
   linked line-item IDs; product acceptance still needs its own permitted, representative holdout.
4. **HITL and recipes:** let a reviewer correct both values and schema/row structure against page highlights; store
   append-only events and approved recipe revisions. Gate on adjudicator agreement, false acceptance, median/p95
   review time, and correct documents released per reviewer hour. Re-run old documents against a new recipe version
   without overwriting their original proposal or decision.
5. **Durable operation:** replace child-process-only status with queued, idempotent workers and transactional metadata.
   Verify crash/retry, duplicate delivery, cancellation, owner isolation through all API/artifact paths, backup/restore,
   and per-tenant queue/spend limits. Separate CPU and GPU workers only when measured contention warrants it.
6. **Selection:** predeclare critical-field precision, row-link error, acceptable abstention/review rate, p95 latency,
   and total cost per *correctly accepted* document before opening holdout results. Keep the simplest candidate on the
   acceptable quality-cost frontier. Report all failed slices and do not infer universal accuracy from public
   benchmarks or one successful demo.

This ADR does not authorize migration of the frozen October research runs, revision of the reported accepted paper,
or a claim that Docling/Paddle/agents outperform the current implementation. Those claims require their own evidence.
