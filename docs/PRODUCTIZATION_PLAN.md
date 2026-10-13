# Productization Plan

Status: target architecture and release gates, updated 2026-10-13. This is not, by itself, a description of implemented behavior.
`docs/SYSTEM_CONTRACT.md` records the current runtime; `paper/FINAL_EVIDENCE.md` records the frozen October internal
study. The author-provided May PDF appears to be the reported accepted paper, pending verification against the exact
CMT-uploaded manuscript. Neither study is the future product benchmark.

## Decision Principle

The product goal is **more correct, source-grounded structured fields for less total cost per accepted document**,
starting from an arbitrary document without manual template setup. Local CPU, local GPU and cloud API capacity are all
available. Use provider-neutral discovery and extraction contracts and compare them on the same holdout. Prefer local
and open-source components when they meet quality, cost and data-handling gates; cloud use requires explicit data
authorization and spend limits. An agent, memory tier or service boundary earns its place only through a measured
gain. The existing four-service research topology is not a product requirement.

The later October internal comparison makes this discipline necessary: on CORD-100, static had mean document F1
**0.886** and mean latency **9.0 s**, versus **0.875** and **12.9 s** for `adaptive_safe`; the paired accuracy difference
was not significant. The adaptive receipt path was significantly slower. The runtime reward also weakly tracked exact
receipt accuracy. These are facts about the [frozen October experiment](../paper/FINAL_EVIDENCE.md), not a verdict on
every possible router or the reported accepted submission.

### October 13 decision update

The [mixed-family 2,000-document
gate](evaluations/MIXED_VRDU_CORD_TRAIN_2000_NO_MODEL_RESULT_20261013.md)
completed on distinct original sources with zero releases, but exact schema F1
was 3.375% and it proposed no linked table rows. The independent
[ExtractBench six-document diagnostic](evaluations/EXTRACTBENCH_TEST6_NO_MODEL_PRODUCT_RESULT_20261013.md)
also proposed no linked cells or rows; one 66-page document exceeded the
current 50-page limit. These are product-path failures on the tested slices.

The [ICORE Luna two-public-PDF diagnostic](evaluations/ICORE_TWO_PUBLIC_QUALITY_RESULT_20261013.md)
matched 0/20 exact gold schema IDs and 0/22 gold linked rows; provider price
and data terms remain unknown. A corrected local Qwen3-VL-2B blind diagnostic
in a separate evaluation worktree produced no valid schema or value calls on
six selected documents. Its result is a small development diagnostic. A
source-locked Granite-Docling trial is prepared for local PDF table parsing,
but its first source run stopped at the host disk guard before parsing. None
of these candidates has earned product integration. Preserve the existing
native-format table path while comparing PDF parsers on exact linked rows and
source geometry.
Separately, a [12-source public schema-diagnostic candidate](evaluations/SCHEMA12_PUBLIC_CANDIDATE_STAGING_20261013.md)
has been staged without gold or model calls. Its version 2 replaced a possible
workforce-template overlap before scoring; source-only parsing found 11/12
within the current 24,000-character model limit. The fraud assessment still
exceeds it. The original version 1 remains an auxiliary coverage receipt:
10/12 fit, and both the fraud assessment and Ofwat workbook exceeded the limit.
Rights, full template disjointness and gold remain open.

The next product change should be one bounded, feature-flagged PDF/image
table adapter **only if** a parser clears its frozen row and evidence gate.
Keep its proposals in the existing HITL queue. Then run the required fresh
2,000-distinct-original-source end-to-end gate through the actual candidate
path, recording false proposals, reviewer time, latency and CPU/GPU cost.
Evaluate automatic schema discovery separately from extraction against a
supplied schema; those are distinct failure modes. The target shape below
remains a modular application with bounded workers. A new service, agent or
memory layer requires a measured quality, cost or reliability gain.

## Current Starting Point And Boundaries

- The opt-in `idpo.cli process-auto` path and owner-scoped review UI now exist as a pilot. They propose scalar fields,
  and a configured model can propose bounded repeated columns with row ordinals; the review UI can inspect cells,
  add missed linked columns with per-cell exact OCR quotes, and save typed row corrections. Optional self-reported
  active reviewer seconds are stored per save; measured total reviewer cost is still unavailable. They verify exact
  OCR text spans and keep unapproved schemas in review. A separate
  owner-scoped registry now stores review-derived schema drafts, explicit `approved_shadow` revisions, and disable
  events; an operator can explicitly select one current approved revision for a model-backed run,
  skipping schema induction while keeping every value in review. Automatic recipe matching and
  release remain unimplemented. They have no durable queue, visual table
  structure, priced cost meter, or demonstrated arbitrary-family accuracy. The first
  2,000-document no-model development baseline failed the quality gate; see
  [the measured v1 report](evaluations/VRDU_2000_NO_MODEL_V1.md). The [v2 safety run](evaluations/VRDU_2000_NO_MODEL_V2.md)
  verified 2,000 distinct sources and eliminated automatic release of unapproved schemas, while strict schema F1
  remained 4.33% and pre-review accepted-value F1 became 0%. These paths are distinct from the research pipeline and
  paper results. The [v3 corrected-OCR diagnostic](evaluations/VRDU_V3_ABORTED_DIAGNOSTIC.md) recovered some previously
  unsupported scans but was stopped at 1,229 distinct sidecars because multipass scan latency was too high. It is not
  a completed quality gate. The [v4 full run](evaluations/VRDU_2000_NO_MODEL_V4.md) verified 2,000 distinct sources,
  but its OCR comparison is invalid because the Tesseract executable was absent from that run's environment. It
  found zero candidate linked cells or rows against 30,133 gold cells and 7,234 gold rows. It did not configure a
  model and cannot evaluate the new model-backed row path. The [v5 pinned-OCR gate](evaluations/VRDU_2000_NO_MODEL_V5.md)
  verified all 2,000 distinct PDFs with a working Tesseract preflight and recovered text on all 35 previously
  unsupported scans. Strict schema F1 was 4.245%, all 2,000 remained in review, and linked cells stayed at zero.
  The [v6 bounded-OCR gate](evaluations/VRDU_2000_NO_MODEL_V6.md) completed 2,000 distinct sources with the timeout
  implementation: no page hit a timeout, all 2,000 remained reviewable, and schema F1 and linked-cell counts were
  unchanged. Focused tests and a forced-timeout smoke cover the limit branch; v6 establishes no quality gain. The
  [v7 PDFium-first gate](evaluations/VRDU_2000_NO_MODEL_V7_PDFIUM.md) completed the same 2,000 source hashes with
  zero releases and zero linked rows; strict schema F1 changed from 4.2448% to 4.2423%. Page-level renderer
  provenance was added after v7. The [v8 provenance gate](evaluations/VRDU_2000_NO_MODEL_V8_PROVENANCE.md)
  verified the same 2,000 distinct source hashes: all 831 OCR PDF pages used PDFium, no fallback or OCR failure
  occurred, and schema F1 and linked-row counts were unchanged. All 2,000 still required review. A separate
  [CORD development crop diagnostic](evaluations/CORD_DEVELOPMENT_TEXT_BOX_OCR_RESULT_20261012.md) found
  88.265% exact recognition with RapidOCR PP-OCRv6 small versus 52.772% with Tesseract on 1,389 fixed annotated
  text boxes. The [paired full-page diagnostic](evaluations/CORD_FULL_PAGE_OCR_DEV_RESULT_20261012.md) on those
  60 development receipts exposed 1,311/1,389 annotated strings in RapidOCR page text versus 791/1,389 with
  Tesseract, yet exact mapped product proposals remained zero for both; the current schema/row layer is the
  bottleneck. These results do not establish a lower total cost or justify changing the OCR default. A separate
  [Docling Graph v1.9.1 plus local Qwen3-4B schema pilot](evaluations/DOCLING_GRAPH_SCHEMA_DEV_RESULT_20261012.md)
  used six source-disjoint scored development documents: reused family schemas matched 4/40 VRDU reference fields
  and 0/26 linked field pairs across ad-buy and receipt documents. That exact route is rejected for product use;
  it did not score extracted values or a generalization holdout. A separate pinned
  [NuExtract3 local development run](evaluations/NUEXTRACT3_LOCAL_DEV_RESULT_20261012.md) matched 22/53 reference
  fields but 0/26 linked field pairs in blind schema discovery under the frozen alias mapping. The model did form
  repeated-object groups; their field IDs did not align with the reference meaning. With the reference field IDs
  and shapes supplied, it matched 13/32 positive scalars and 24/43 complete rows across six documents, with 21
  of those rows from one ad-buy source. No values had verified box/span evidence. This is a conditional extraction
  lead, not an automatic-schema product result or a source-disjoint generalization claim.

- Current job execution is `frontend job API -> frontend runner -> python -m idpo.cli process-inbox -> IDPO_DATA_DIR`.
  IDPO runs `ingest/inbox -> orchestrator -> executor -> exports`. AHMN direct advice is in process. Guardrails and
  XAI-HITL services are not called by the measured document path; RABI and DAAF are simulation results only.
- The single-host demo is the verified end-to-end path. The Compose product-auto route now has a private Python
  worker and shared-volume Unix socket. Static Compose checks, unit tests and a frontend build pass; the local Docker
  daemon was unavailable, so live container extraction remains unverified. The canonical research job route is
  explicitly unavailable in Compose. See [Public Demo Deployment](PUBLIC_DEMO_DEPLOYMENT.md).
- A one-file, no-LLM host smoke on the repository's sample invoice completed, but the generic `forms` policy emitted
  healthcare keys (`claim_number`, `member_id`, `service_date`) for invoice values while validation reported no issues.
  This is a qualitative failure example, not a benchmark. It shows why automatic schema discovery, field semantics and
  reviewer-visible evidence need separate evaluation.
- Owner-scoped access to jobs, runs, uploaded documents and artifacts must be verified across every frontend and gateway
  entrypoint before an external release. Existing or in-progress access code is not a substitute for two-user tests.
  A two-user audit reproduced a cross-owner legacy run-artifact read via a traversal document ID; frontend commits
  `3ded1f0` and `d78d21e` now reject unsafe IDs and confine document/review paths. A separate local-junction
  reproduction in the original-content route was fixed in `5d785ac` by resolving paths inside the configured job
  upload directory. The 78-test frontend server suite, TypeScript and targeted lint passed for these scoped fixes.
  A malicious local process could still race filesystem replacement against a read; no HTTP-only link creation was
  found in the bounded audit. This is not a completed audit of every entrypoint.
- Preserve the submitted manuscript once verified and keep the October draft's configurations, scorer, run IDs,
  negative result and simulation-only claims intact as separate evidence. New product benchmarks get separate
  manifests, run IDs, data rights and reports.

## Target Shape

```text
Browser -> authenticated API -> job metadata + immutable input/artifact storage
                              -> bounded worker queue -> parse/OCR -> schema discovery
                                                      -> typed extraction against versioned schema
                                                      -> evidence checks + business rules
                                                      -> accept / abstain / human review
                                                      -> versioned result + audit trail
```

Begin with a modular application and independently scalable worker processes. Retain the existing API and IDPO entrypoint
where they are useful, while moving long-running execution out of the web process when the single-host pilot is hardened.
Separate CPU parsing and GPU inference capacity only when measurements show different resource or scaling needs. A
service boundary needs a concrete availability, scaling or ownership reason; it is not the default unit of modularity.

| Boundary | Target contract | First implementation decision |
| --- | --- | --- |
| Intake and identity | Authenticated owner, content hash, verified file type, limits, immutable input, job and schema versions; auto mode accepts a document without selecting a template | Preserve the job UI; make all reads and writes owner-scoped and test indirect artifact routes. Unsupported or illegible files get an explicit outcome, never a fabricated schema. |
| Job execution | Durable status, idempotency key, bounded retries, cancellation, stage timings, replayable artifacts | The current private Docker worker admits one active product run and rejects another; add durable queued state before multi-host scale. |
| Parsing | Native PDF text when reliable; OCR/layout for scans; page, box, reading order and table-cell evidence | Keep PDFium-first rendering plus bounded Tesseract as the measured product baseline. The frozen [Docling/pdfplumber comparison](evaluations/VRDU_ADBUY12_TABLE_PARSER_COMPARISON_20261012.md) recovered at most 4/219 permissive parser rows. [MinerU 4.0.9 Basic](evaluations/MINERU_4_BASIC_ADBUY12_RESULT_20261012.md) reached 6/219. The [PaddleOCR-VL 1.6 full pipeline](evaluations/PADDLEOCR_VL16_ADBUY12_RESULT_20261012.md) reached 14/219 but zero strict exact rows and no cell-level boxes, so do not promote it. The prepared full PP-StructureV3 CPU profile fails the current free-RAM guard. |
| Schema discovery | Infer document family, candidate fields, types, groups and table relationships, each with source evidence; propose a versioned reusable recipe | Run on first or unfamiliar documents with no manual template setup. Mark ambiguous candidates and let an authorized reviewer approve or amend a recipe. Never silently rewrite an approved schema. |
| Extraction | Provider-neutral extraction against a versioned proposed or approved schema; bounded prompt/context; typed output; recorded provider/model/version | Compare a simple extractor on local CPU, local GPU and approved cloud APIs against the same holdout. Cloud use is opt-in per data policy, with redaction where required and hard spend caps. |
| Verification | Schema and deterministic format/business rules, source-span or image-region grounding, explicit missing values | Reject unsupported values and route uncertain fields to review; do not use model self-confidence as truth. |
| Review | Original page and highlighted evidence beside fields, correction and abstention, reason, reviewer, timestamps | Build on the job/document flow; use an annotation tool for gold-data creation if it saves time. |
| Results | Raw and normalized values, field evidence, decision and review history, model/config versions, export | Preserve current run artifacts during migration; define a versioned product result rather than mutating paper outputs. |

Each field result should carry at least `field_id`, raw and normalized value, status (`accepted`, `needs_review`,
`missing`, or `rejected`), page/region or text-span reference, evidence excerpt, method and schema/model/pipeline versions.
An absent field is distinct from zero or an empty string. For tables, retain row identity and cell provenance. Reviewers
must be able to adjudicate conflicts, correct a value, and see the original proposal later. These are target requirements,
not claims about today's artifact format or UI.

**Auto mode** proposes a schema and extracts values in one job. It can release low-risk results under an explicit policy;
ambiguous fields, unsupported values and critical business decisions abstain for review. An approved recipe stabilizes
the field names, types and normalization for a recurring document family, so later documents do not drift between
incompatible schemas. Arbitrary keys found in one document are useful for exploration, but they are not automatically
the customer's recurring business fields. Map discovered keys to business concepts explicitly and version the mapping.
Do not promise universal accuracy across all document types; unseen families are a measured generalization problem.

## Component Choices To Test

These are candidates, not a commitment to replace the existing runtime. Pin code **and model weights** after selection.
Schema versioning, deterministic validation and human adjudication are the stable baseline. New VLM parsers, autonomous
schema discovery and agent routing remain experimental until the gates below are met.

| Need | Candidate and reason | Decision gate / caveat |
| --- | --- | --- |
| Document conversion | [Docling](https://github.com/docling-project/docling/blob/main/docs/usage/supported_formats.md) offers one structured representation across common formats; its [five-file synthetic diagnostic](evaluations/DOCLING_MIXED_FORMAT_DEV_RESULT_20261012.md) recovered 36/45 known table cells and missed a multipart EML's HTML alternative. The paired [native-library diagnostic](evaluations/MIXED_FORMAT_NATIVE_DEV_RESULT_20261012.md) recovered 45/45 cells with 45/45 source-resolving sheet, slide, table, DOM or MIME locators. Neither recovered cell pixel boxes or measured real-file extraction. | Benchmark source-native adapters and Docling on the same rights-cleared real documents, including merges, formulas, malformed files and resource-expansion limits. Build format-specific review views. Product intake still needs evidence, cost and the 2,000-source gate; Docling's [typed extractor is beta](https://github.com/docling-project/docling/blob/main/docling/.agents/skills/docling/references/extraction.md). |
| Blind schema discovery | [NuExtract3 Q4](https://huggingface.co/numind/NuExtract3-GGUF) already used template generation locally and matched 22/53 fields under the frozen alias map but 0/26 linked field pairs. [Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B) is a distinct Apache-2.0 multimodal candidate with a [4.55 GB BF16 weight file](https://huggingface.co/Qwen/Qwen3.5-2B/blob/main/model.safetensors-00001-of-00001.safetensors); fit and task accuracy on this host are unmeasured. | Before a product change, compare one blind schema call per model on 12 newly admitted source- and template-disjoint documents from at least four families. Freeze gold, field aliases, repeated-group relations, prompts and model revisions before inference. Score exact IDs and predeclared aliases separately, including linked pairs and human schema-edit time. Do not revise the primary score with post-hoc semantic aliases or call this 12-document diagnostic a 2,000-source gate. |
| Long documents | The current model route refuses a document when extracted text exceeds 24,000 characters. The source-only public version 2 preflight found one such case, an HTML assessment at 144,389 characters. Version 1 also contained an over-limit 39,860-character workbook, preserved as an auxiliary coverage case after a source-only template-overlap substitution. | Trial section-, page- or sheet-bounded extraction with stable source locators and an explicit merge/reconciliation pass; record omitted content, duplicate fields, extra calls and review time. Compare against the same locked gold before enabling it. Never silently truncate or claim whole-document coverage from partial input. |
| Difficult scans/tables | [MinerU 4.0.9 Basic](evaluations/MINERU_4_BASIC_ADBUY12_RESULT_20261012.md) is a measured CPU control, not a release candidate; [PP-StructureV3](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PP-StructureV3.en.md) remains too large for this host's full CPU profile. The [PaddleOCR-VL 1.6 full layout/VLM pilot](evaluations/PADDLEOCR_VL16_ADBUY12_RESULT_20261012.md) ran locally but recovered only 14/219 permissive parser rows and no cell boxes. | Keep the same frozen 12-PDF and 219-row denominator, source/model hashes and child-process resource guards. The parser comparator scores all gold cells colocated with exact text in one parser row, permits extra parser cells, and does not map business field IDs. Enable only for cohorts where mapped field/row correctness, source evidence and total cost improve enough to justify compute and rights. |
| Structured model output | The product adapter currently requests JSON in the prompt without enforcing a response schema. A [pinned llama.cpp schema-constrained diagnostic](architecture/ADR-0005-structured-model-output-candidate.md) is prepared; Ollama is not installed on this host. [vLLM structured outputs](https://docs.vllm.ai/en/v0.31.0/features/structured_outputs/) is a self-hosted GPU option. Cloud APIs are comparison candidates behind the same extractor interface. The [NuExtract3 reference-schema development result](evaluations/NUEXTRACT3_LOCAL_DEV_RESULT_20261012.md) motivates a conditional value-extraction challenger, while its blind schema route failed linked-field matching. | Valid JSON and Pydantic types do not prove a value appears in the source or carries the right field meaning. Require field grounding and post-validation. Record provider data terms, regional processing, retention and spend before cloud trials. |
| Gold data and review | [Label Studio](https://github.com/HumanSignal/label-studio) (Apache-2.0) can accelerate annotation. The operator review experience should remain integrated with job/document ownership. | Measure annotation agreement and review time; do not turn an annotation backend into an unexamined production dependency. |
| Jobs | A queue with idempotent workers is sufficient for the first product slice; [Celery documents duplicate-delivery/idempotency tradeoffs](https://docs.celeryq.dev/en/stable/userguide/optimizing.html). [Docling Serve](https://github.com/docling-project/docling/blob/main/docs/usage/api_server/deployment.md) already offers Redis/RQ parsing workers. | Adopt [Temporal](https://docs.temporal.io/production-deployment) only if durable multi-step/human-wait orchestration outweighs another service to operate. |
| Approved examples | Start with explicit, versioned templates and reviewed examples. [pgvector](https://github.com/pgvector/pgvector) permits tenant-filtered exact retrieval in PostgreSQL. | Add vector retrieval only after a no-memory ablation; approximate indexes trade recall for speed. No automatic promotion of unreviewed corrections. |

The [PP-TableMagic v2 GPU protocol](evaluations/PP_TABLEMAGIC_V2_ADBUY12_GPU_PROTOCOL_20261013.md) is frozen for a conditional local challenge. The CPU arm timed out before producing a page, and the GPU wheel/runtime has not been installed or scored. Its proposed cell boxes still require independent pixel-to-cell review. The newer [Surya 2](https://github.com/datalab-to/surya) offers OCR, layout and table row/column recognition through one local VLM, but its [model license](https://github.com/datalab-to/surya/blob/master/MODEL_LICENSE) includes commercial revenue, funding and competing-service restrictions. It is a research comparison candidate, not a default production dependency without a deployment-rights review. Its published speed and accuracy are vendor measurements, not results on this corpus or host.

Open-source code is not free operation: record CPU/GPU seconds, model memory, storage, network/API charges and human
review minutes. Code licenses do not establish model or dataset rights. For example, [OmniDocBench's repository](https://github.com/opendatalab/OmniDocBench)
restricts its PDFs to research use; do not silently make it a commercial training set. A dependency/license inventory is
part of each release candidate.

### First Cloud Candidate: ICORE

The user supplied an ICORE endpoint and credential for testing. The opt-in `process-auto` route accepts its OpenAI-compatible
base URL and model ID at runtime, using a server-side `ICORE_API_KEY`. A synthetic invoice smoke call to
`innobot-luna-6` succeeded: one schema call, 336 prompt and 179 completion tokens, seven source-grounded accepted fields,
and about 4.3 seconds total. This proves connectivity and response handling for that one example, not field accuracy or
price. Keep the actual key out of files, logs, test fixtures and commits. The
[synthetic pilot](evaluations/ICORE_SYNTHETIC_PILOT.json) authenticated the nine-ID model catalog and exercised schema
and value calls for two synthetic texts with `innobot-luna-6` and `innobot-minimax-m2-5`. The catalog advertises separate
text embedding and image generation routes and some chat models with image inputs; vision extraction was not tested.
The later [six-call synthetic capability diagnostic](evaluations/ICORE_BOUNDED_CAPABILITY_20261012.md) observed
successful strict JSON-schema replies from Luna and MiniMax, while MiniMax rejected a JSON-object auto-schema request
and its strict auto-schema response exhausted the 1,024-token cap. Luna's two-stage JSON-object call proposed 12
fields and produced seven source-grounded accepted values on one synthetic invoice. These small probes do not
establish public-document accuracy, provider uptime or price.
The [bounded six-public-PDF VRDU pilot](evaluations/ICORE_VRDU_SIX_PILOT.json) sent only public cohort documents: one
of six attempted chat calls succeeded, five returned `APIConnectionError`, and no value extraction completed. A
missing OCR executable is strongly indicated for its one zero-text scan; that scan does not measure the provider.
No private document was sent. A later [six-source public development trial](evaluations/ICORE_REAL_DEVELOPMENT_SIX_RESULT_20261012.md)
verified its first PDF/OCR source, then stopped after the first Luna schema request failed with an ambiguous
`APIConnectionError` and no usage receipt. Eight planned document-model cells were not attempted; the run gives
no real-document model-quality comparison or known USD charge. Published prices, API data-use terms and a hard spend
limit are still unverified; do not run a cloud corpus gate until the
[spend and data conditions](evaluations/ICORE_SPEND_AND_DATA_GATES_20261012.md) are met. The
[later two-public-PDF product diagnostic](evaluations/ICORE_TWO_PUBLIC_QUALITY_RESULT_20261013.md)
made three authenticated Luna requests with 10,538 reported tokens but matched
no exact reference schema ID across 20 gold fields and no gold linked row
across 22 rows. It therefore does not justify a default cloud route; cost in
USD is still unknown. The
[local Qwen 12-PDF diagnostic](evaluations/LOCAL_QWEN_VRDU_TWELVE_PILOT.json) used 18 model calls with no cloud fee,
but proposed zero linked cells and matched only one canonical value on nine model-served PDFs. Two scan outcomes are
also confounded by the earlier OCR environment. Local compute cost was not priced, and improved synthetic prompts
did not establish real-document accuracy.

## Quality-Cost Evaluation Contract

1. Define the first document domains and critical business fields with operators, while testing auto mode on unfamiliar
   families with no supplied template. Create a legally usable, de-identified gold set containing born-digital and
   scanned PDFs, images, multi-page forms, tables/line items, weak scans, unfamiliar layouts and explicit missing
   fields. Split by source/layout family so near-duplicates do not cross train/dev/holdout.
   Freeze the holdout and benchmark manifest before candidate tuning. [DocILE](https://github.com/rossumai/docile)
   illustrates KILE, line-item and zero/few-shot layout slices; [olmOCR-Bench](https://github.com/allenai/olmocr/blob/main/olmocr/bench/README.md)
   adds structural parser tests. Public benchmarks supplement, rather than replace, the product holdout.
2. Score **schema induction** separately: document-family grouping, field discovery precision/recall, type/group and
   table relationship accuracy, evidence validity, duplicate or spurious keys, setup minutes and recipe edits. Then
   score **value extraction** against a fixed gold schema: per-field exact and normalized precision/recall, macro and
   micro F1, perfect-document rate, critical-field false acceptance, missing-versus-zero errors, line-item row/cell
   accuracy, evidence validity and abstention/coverage. Also report end-to-end auto-mode results with the proposed
   schema on unseen families. Use one scorer and normalization policy per comparison, report slices and paired
   intervals, and resolve disputed gold labels through human adjudication rather than an LLM self-score.
3. Time parsing, schema discovery, extraction, validation, retry, setup and review separately. Record p50/p95 end-to-end
   latency, throughput, CPU/GPU time, token use, API spend and reviewer minutes. Include amortized owned hardware or
   rented capacity, cloud charges and idle GPU time in the cost model. On a labeled evaluation batch, define **cost
   per accepted document** as all processing, retry, storage, setup and review cost divided by documents released with
   correct critical fields. Also publish automation coverage and review rate so abstention cannot make the denominator
   look artificially good.
4. Before opening the holdout, record minimum critical-field precision, allowable false-acceptance and review rates,
   p95 latency and budget per accepted document for the intended deployment. A candidate advances only if it meets
   those predeclared limits and either improves quality without exceeding the cost cap or reduces cost while staying
   within a predeclared quality non-inferiority margin. Show the full quality-cost frontier, not a single blended score.
5. After each substantive extraction implementation milestone, run **at least 2,000 unique documents end to end**
   through the actual candidate pipeline before promoting it. Freeze document hashes, sources, rights, gold version,
   family/layout/scan slices, provider/config/model versions and run IDs. Report all failures and missing outputs in
   the denominator. Small fixtures and repeated copies of the same document are useful for development or load tests,
   but do not satisfy this quality gate. Run cheap focused checks during development; reserve the full batch for each
   reviewable candidate to control compute and API spend.

### AHMN And Agent Keep/Remove Gate

Compare static routing, a simple deterministic rule router, and AHMN/agentic routing on identical inputs, field schemas,
parsers and model budgets. Repeat stochastic runs and report the extra routing tokens, latency, failures and review work.
Keep a router in the operational path only if untouched-holdout paired results show a repeatable quality gain at
acceptable total cost, or a cost reduction within the predeclared product quality margin, with no unacceptable
critical-field regression. A label-free reward or simulation result cannot clear this gate. Otherwise quarantine AHMN,
RABI/DAAF and multi-agent workflows
as reproducible research assets and use the simplest measured production route. Agent skills can be versioned extraction
recipes and bounded tools; they do not need independent services or permission to act on document instructions. The
[multi-agent failure study](https://arxiv.org/abs/2503.13657) identifies specification, coordination and verification
failures, reinforcing the need for the ablation.

## Staged Acceptance Gates

| Stage | Deliverable | Gate to advance |
| --- | --- | --- |
| 0. Close release blockers | Owner-scoped frontend jobs/runs/documents/artifacts; gate legacy proxy routes until they have ownership; replace or de-advertise Docker runner | Two viewers cannot cross-read or mutate each other's resources through any API/content route; admin cross-user access works only under the documented role and is tested. A Docker-launched job either emits real IDPO artifacts or that deployment is explicitly unsupported. Tests cover both. |
| 1. Establish the baseline | Versioned gold set, separate schema/value scorers, cost telemetry, reproducible simple route and error taxonomy | Clean-checkout rerun matches manifest and metrics on known and unseen document families; local compute, cloud API, storage, setup and reviewer-time costs are observable. Frozen October runs remain untouched. |
| 2. Auto discovery, grounded extraction and HITL | No-template upload, proposed schema with field evidence, reusable approved recipe, review UI with source alongside values, adjudication and audit history | A new document gets proposed typed fields and values without manual setup; ambiguous or high-risk outputs abstain under policy. Every accepted field has inspectable evidence or an explicit reviewer override; corrections and recipe edits are durable and versioned; review time and false acceptance are measured on holdout slices. |
| 3. Candidate frontier | Paired parser/model/route experiments across local CPU, local GPU and approved cloud APIs; clear keep/remove decisions | Every substantive candidate completes the frozen 2,000-unique-document end-to-end gate and satisfies predeclared quality and cost limits; cloud trials have documented data authorization and spend caps; AHMN/agents remain off the hot path unless they clear their separate gate. |
| 4. Reliable scale | Dedicated worker, bounded queue/retries, isolation, backups, observability and restore drill | Representative load and worker-failure tests recover without duplicate or missing results; p95 latency and cost targets hold; authorization, retention and audit checks pass. |
| 5. External release | Versioned contracts, operator docs, supported deployment, license/model inventory | Fresh-install smoke processes a real document through upload, extraction, evidence, review and export; no placeholder runner or unowned artifact read remains. |

## Security And Research Separation

- Treat document bytes and OCR text as untrusted data, including apparent instructions embedded in a page. The extractor
  has no arbitrary shell, network or credential-bearing tools. Validate file types and size/page limits; constrain
  outbound model calls and log their use. [OWASP's LLM prompt-injection guidance](https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf)
  supports this boundary.
- Authorize every job, run, document, review and artifact operation at the resource level. Legacy service endpoints
  without user ownership need an admin-only gate until they are designed and tested for per-user access. Shared storage,
  retrieval and logs must not cross owners; retention and deletion need explicit policy before real customer documents.
- Send document content to a cloud API only under an explicit tenant or dataset policy. Record the provider, region,
  retention/training terms, redaction policy and allowed fields; enforce per-job and aggregate spend caps. Keep API
  credentials server-side and prevent fallback to a provider outside the approved policy.
- Preserve the reported accepted submission once its CMT identity is verified, and separately preserve
  `paper/FINAL_EVIDENCE.md`, the referenced run directories and October scorer/config versions. The May PDF and October
  draft have materially different reported results; neither may be silently overwritten, backdated or presented as the
  other. Camera-ready edits must reconcile the verified submission, reviewer comments, venue requirements and later
  evidence accurately. Keep new datasets, model weights, run manifests and product metrics under separate versioned
  paths. A product improvement never silently revises a research metric or turns simulation into a deployed claim.

## First Implementation Slice After Stage 0

Produce a reproducible auto-mode run on a small, representative **new** gold set including one unseen family. Export
the proposed schema and one row per discovered field with type, group, raw value, normalized value, evidence reference,
validation outcome, human correction and timed review. Score schema discovery and value extraction separately. This
single vertical slice establishes the baseline, tests setup and review economics and tells the team which parser,
model or recipe change is worth building next.
