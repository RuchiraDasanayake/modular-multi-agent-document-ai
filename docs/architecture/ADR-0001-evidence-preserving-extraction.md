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

**Docling remains a mixed-format adapter candidate**, because its documented representation includes page provenance
where available and table cells with row/column offsets and spans, and its supported inputs include PDF, Office
documents, and images
([formats](https://docling-project.github.io/docling/usage/supported_formats/),
[document model](https://docling-project.github.io/docling/reference/docling_document/)). A measured
[five-file synthetic conversion spike](../evaluations/DOCLING_MIXED_FORMAT_DEV_RESULT_20261012.md) retained table
grids for DOCX, XLSX, HTML and PPTX but lost a multipart EML table and supplied no cell-level boxes. On the
same locked sources, [native parsers](../evaluations/MIXED_FORMAT_NATIVE_DEV_RESULT_20261012.md) recovered all 45
known cells with resolvable source locators, including the EML HTML part. Neither diagnostic measures real files.
This adapter
does not replace the current PDF parser: its frozen table run recovered only
[3/219 exact rows](../evaluations/VRDU_ADBUY12_TABLE_PARSER_COMPARISON_20261012.md). Keep native PDF text plus
PDFium-first rendering and bounded Tesseract as the measured product baseline. The smaller
[MinerU Basic challenge](../evaluations/MINERU_4_BASIC_ADBUY12_RESULT_20261012.md) reached only 6/219 exact rows;
the full PP-StructureV3 profile fails this host's current RAM guard.
The completed [PaddleOCR-VL 1.6 full-pipeline challenge](../evaluations/PADDLEOCR_VL16_ADBUY12_RESULT_20261012.md)
reached 14/219 on that parser-row metric and 0/219 strict exact rows, with no cell-level boxes. No parser has passed
the linked-row promotion gate.

The pinned [NuExtract3 local development run](../evaluations/NUEXTRACT3_LOCAL_DEV_RESULT_20261012.md) fit this
8 GB GPU, but blind schema discovery matched zero of 26 linked field pairs under the frozen mapping. Its separate
reference-schema arm matched 24/43 exact complete rows on six development documents, with no verified source boxes
or spans and substantial source-to-source variance. Therefore a specialist model remains a conditional extractor
candidate behind an independently approved recipe and the evidence verifier; it is not an automatic-schema default.
A separate [12-source self-template follow-on](../evaluations/NUEXTRACT3_GROUP_LEAF_DEV12_RESULT_20261012.md)
matched only 2/52 linked field pairs under a tuned grouped-leaf rule and 0/30 strict complete rows before its
predeclared RAM guard stopped value calls. It did not revise the original six-source score.

| Current evidence in this checkout | Consequence for the target |
| --- | --- |
| [Intake](../../idpo/agents/intake.py) supports JSON, TXT, PDF, and common raster images; PDF text comes from pypdf. [Page](../../idpo/core/types.py) stores text and optional image path/metadata. | Add a parser adapter and explicit format outcomes; do not make downstream code depend on Docling classes. |
| [product_auto](../../idpo/product_auto/workflow.py) proposes at most 24 fields, uses at most 50 pages/24,000 model characters, and writes exact page-text offsets. Its configured model can propose `array[object]` columns with bounded row ordinals; the no-model route cannot. It leaves discovered schemas in review. | Preserve abstention and improve linked-row semantics and visual evidence. Do not call a text match semantic validation. |
| [TableFormAgent](../../idpo/agents/preprocess.py) detects text lines containing pipes or tabs; the auto path does not consume structured cells. | A table parser and row linker need their own measured slice. Flat keys cannot represent line items reliably. |
| [Frontend auto runs](../../frontend/src/server/product-auto.ts) use a local child process or a private Compose worker and store run/review JSON on the shared host volume. Review can correct or remove proposed fields, add source-backed missed scalar fields, and inspect or correct linked cells on one document. A separate [owner-scoped recipe registry](../../frontend/src/server/product-auto-recipes.ts) can approve reviewed schemas in shadow mode, but extraction does not yet match or use them. PostgreSQL and Redis exist in Compose but are not this job path's durable queue or metadata store. | Measure recipe matching and row relation adjudication before claiming reusable extraction; move execution state into durable metadata/queue when the pilot advances. |

The [2,000-document VRDU no-model development baseline](../evaluations/VRDU_2000_NO_MODEL_V1.md) reported 4.33%
strict schema F1 and 0.95% strict value F1 across two families; all 2,500 ad-buy linked-row field records were
missing or unresolved. It made no model calls, so it is not a test of AI-generated schemas or these parser candidates.
Its cost and human-review fields had zero coverage, so it cannot establish cost per accepted document. The later
[v8 provenance gate](../evaluations/VRDU_2000_NO_MODEL_V8_PROVENANCE.md) verified 2,000 distinct PDF sources and
PDFium rendering for all 831 OCR pages, but still had 4.2423% strict schema F1 and zero proposed linked rows. These results
motivate the row/schema gates; they do not predict performance on arbitrary document families. That archived run's
`processed` status also predates the current review-only behavior in `process-auto` and must not be interpreted as
approved, correct output. The [v4 run](../evaluations/VRDU_2000_NO_MODEL_V4.md) found zero proposed linked cells
against 30,133 gold cells; it also lacked the OCR executable, so it is not a valid bounded-OCR comparison.

## Product contracts to introduce

1. **ParsedDocument v2:** immutable source hash and format; parser/model version; ordered source units and elements.
   A unit may be a PDF page, spreadsheet sheet, presentation slide, HTML section, or email MIME part. It has a stable
   format-native locator and text spans; page width, height, rotation, reading order, and coordinates are present only
   when the converter actually supplies them. A table has an ID, containing unit, cells with row/column indices and
   spans, text, and available source locators. Preserve raw parser coordinates and a normalized top-left transform
   for page-based viewers, plus the original file and any page render. A sheet/cell, slide/shape, DOM/text, or MIME-part
   locator can support review without inventing pixel geometry; the viewer must expose that source context. A parser
   element is evidence of content, not proof that the content belongs to a business field. Docling's
   [provenance](https://docling-project.github.io/docling/reference/docling_document/) and
   [span-preserving table model](https://docling-project.github.io/docling/concepts/serialization/) can map into this
   contract; serializing a table only as Markdown loses important structure.
   A small parser-neutral [contract module](../../idpo/product_auto/parsed_document.py) defines source units,
   native/text/box anchors and table grids with validation. The product path now writes this v2 contract for five
   native formats using bounded python-docx, openpyxl, python-pptx, lxml and standard-email adapters. Its synthetic
   fixture check covers 45 exact, independently resolvable cells; real-document extraction quality and the separate
   2,000-source post-change gate remain unmeasured. PDF and image parsing still use the existing v1 result path.
2. **SchemaProposal and approved Recipe:** document-family hypothesis, typed fields, grouping, cardinality, nested or
   repeated-record shape, table-column mapping, label evidence, and version. Auto mode proposes a schema and values in
   one job. Reviewers can add, remove, rename, type, and group fields before approving a reusable recipe. A one-off
   key found on a document remains distinct from a stable customer business field. Never auto-promote an unreviewed
   correction or mutate an approved recipe in place.
3. **ExtractionResult:** values reference schema version and one or more source-unit elements/regions, format-native
   locators, or exact text spans;
   preserve raw and normalized values, missing versus zero, derivation, parser/model version, and accept/review/reject
   state. Repeated records contain a `table_id`, `row_id`, ordered cells, and explicit `continuation_of` for a row
   continued on another page. Link only where headers, geometry, and values support the relation; otherwise leave the
   relation pending review. Stable IDs are scoped to source hash plus parser/recipe revision, not generated field names.
4. **ReviewEvent:** immutable machine proposal, reviewer edits to fields, rows, links and evidence, actor, time,
   revision, reason, and adjudication state. The viewer highlights the exact page region when available, or shows the
   sheet/table cell, slide/shape, DOM context, or MIME part identified by a format-native locator. If a parser
   supplies text only, the UI must disclose that limitation. A value may be accepted automatically only under a
   predeclared policy that has passed holdout tests for that field/family. Exact quoted text alone cannot establish
   semantic correctness, as the existing invoice-to-healthcare-key smoke failure shows in
   [PRODUCTIZATION_PLAN](../PRODUCTIZATION_PLAN.md).

## Component and operations choice

| Boundary | Lean choice | Reason / alternative gate |
| --- | --- | --- |
| Parse/OCR | Current native PDF/PDFium/Tesseract baseline; source-native and Docling mixed-format comparisons; stronger layout/table parser only after a paired win | Native libraries retained 45/45 source-resolvable cells on five tiny synthetic files versus Docling's 36/45, but neither proves real-file extraction. On ad-buy PDFs, Docling colocated the exact gold cells of 3/219 rows, MinerU Basic 6/219 and [PaddleOCR-VL 1.6](../evaluations/PADDLEOCR_VL16_ADBUY12_RESULT_20261012.md) 14/219, allowing extra parser cells. Paddle supplied no cell-level boxes, and none maps business field IDs or justifies automatic row acceptance. Benchmark native PDF, scan, multi-page, and table cases separately; pin code and model weights and inspect licenses. Code licenses do not settle model-weight or dataset rights. |
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
2. **Parser contract spike:** adapt the current parser and any measured candidate into ParsedDocument v2 without
   changing the extractor. Compare source-native libraries and Docling for mixed-file intake before choosing one;
   neither is an automatic linked-row release path. Inspect overlays
   for page/rotation/coordinate correctness and compare text, cells, rows, headers and table spans against adjudicated
   gold. The full PaddleOCR-VL layout/table pipeline completed the frozen hard-table slice but failed the row/evidence
   promotion gate; defer full PP-StructureV3 until a host can safely run it. Reject an adapter that improves text but degrades
   evidence or linked rows beyond predeclared margins.
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
