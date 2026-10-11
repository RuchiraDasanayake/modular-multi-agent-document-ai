# Productization Plan

Status: target architecture and release gates, updated 2026-10-12. This is not, by itself, a description of implemented behavior.
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

## Current Starting Point And Boundaries

- The opt-in `idpo.cli process-auto` path and owner-scoped review UI now exist as a pilot. They propose scalar fields,
  and a configured model can propose bounded repeated columns with row ordinals; the review UI can inspect cells and
  save typed row corrections. They verify exact OCR text spans and keep unapproved schemas in review. A separate
  owner-scoped registry now stores review-derived schema drafts, explicit `approved_shadow` revisions, and disable
  events; extraction does not match or use them yet. They have no durable queue, runtime recipe reuse, visual table
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
  model and cannot evaluate the new model-backed row path.

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
| Parsing | Native PDF text when reliable; OCR/layout for scans; page, box, reading order and table-cell evidence | Keep current PyPDF/PaddleOCR/Tesseract as the measured baseline; spike Docling and PP-StructureV3 on failure slices. |
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
| Document conversion | [Docling](https://github.com/docling-project/docling/blob/main/docs/usage/supported_formats.md) offers one structured representation across common formats and [page/box provenance](https://docling-project.github.io/docling/reference/docling_document/). Code is MIT licensed. | Compare native text, OCR, tables, language and cost against the current path. Its [typed extractor is beta](https://github.com/docling-project/docling/blob/main/docling/.agents/skills/docling/references/extraction.md), so try it as a baseline, not an assumed dependency. |
| Difficult scans/tables | [PaddleOCR PP-StructureV3](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PP-StructureV3.en.md) provides modular layout, OCR and table parsing; PaddleOCR code is Apache-2.0. A newer VLM parser such as [PaddleOCR-VL-1.6](https://arxiv.org/abs/2606.03264) is an experimental fallback. | Enable only for cohorts where it improves field/row correctness enough to justify compute. Check each weight license. |
| Structured model output | Existing Ollama JSON-schema path remains the local baseline. [vLLM structured outputs](https://docs.vllm.ai/en/v0.31.0/features/structured_outputs/) is a self-hosted GPU option. Cloud APIs are comparison candidates behind the same extractor interface. | Valid JSON and Pydantic types do not prove a value appears in the source. Require field grounding and post-validation. Record provider data terms, regional processing, retention and spend before cloud trials. |
| Gold data and review | [Label Studio](https://github.com/HumanSignal/label-studio) (Apache-2.0) can accelerate annotation. The operator review experience should remain integrated with job/document ownership. | Measure annotation agreement and review time; do not turn an annotation backend into an unexamined production dependency. |
| Jobs | A queue with idempotent workers is sufficient for the first product slice; [Celery documents duplicate-delivery/idempotency tradeoffs](https://docs.celeryq.dev/en/stable/userguide/optimizing.html). [Docling Serve](https://github.com/docling-project/docling/blob/main/docs/usage/api_server/deployment.md) already offers Redis/RQ parsing workers. | Adopt [Temporal](https://docs.temporal.io/production-deployment) only if durable multi-step/human-wait orchestration outweighs another service to operate. |
| Approved examples | Start with explicit, versioned templates and reviewed examples. [pgvector](https://github.com/pgvector/pgvector) permits tenant-filtered exact retrieval in PostgreSQL. | Add vector retrieval only after a no-memory ablation; approximate indexes trade recall for speed. No automatic promotion of unreviewed corrections. |

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
The [bounded six-public-PDF VRDU pilot](evaluations/ICORE_VRDU_SIX_PILOT.json) sent only public cohort documents: one
of six attempted chat calls succeeded, five returned `APIConnectionError`, and no value extraction completed. A
missing OCR executable is strongly indicated for its one zero-text scan; that scan does not measure the provider.
No private document was sent. Published prices, data-use terms and a hard spend limit are still unverified; do not
expand cloud use until transport reliability and a documented spend policy are established. The
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
