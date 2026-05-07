# Schema-Conditioned Online Learning Paper Plan

## Purpose

Build the conference paper around heterogeneous schema-conditioned extraction, not receipt-only extraction.

Core claim:

> Given a fixed requested schema, IDPO can process heterogeneous document types, extract available fields, return `unavailable` when evidence is absent, adapt policy selection over a persistent job, and preserve auditable field-level evidence.

Do not claim "extract any document." The defensible claim is:

> schema-conditioned extraction across a heterogeneous business-document workload.

## Fixed Schema

Every document uses the same requested schema:

- `document_type`
- `document_date`
- `issuer_name`
- `recipient_name`
- `reference_id`
- `primary_organization`
- `total_amount`

Allowed `document_type` values:

- `receipt`
- `invoice`
- `form`
- `other`

Expected unavailable value:

- `unavailable`

## Dataset Pack

Use the generated local pack:

- `datasets/schema_conditioned_100.json`
- `datasets/schema_conditioned_batches/schema_mixed_batch_01.json` through `schema_mixed_batch_20.json`

Generated summary:

- `doc_count`: 100
- document types: `form=36`, `invoice=19`, `other=15`, `receipt=30`
- sources: `FUNSD=36`, `Diverse invoices local=19`, `DocVQA local=15`, `CORD=30`
- average non-type positive fields: `2.54`

Positive field counts:

- `document_type`: 100
- `document_date`: 52
- `issuer_name`: 45
- `recipient_name`: 44
- `primary_organization`: 40
- `total_amount`: 39
- `reference_id`: 34

Important interpretation:

- this is now a narrow business-header schema, not a rich universal schema.
- `total_amount` is meaningful, but invoices in the local synthetic source still under-label it.
- `unavailable` fields test schema obedience and hallucination avoidance, not positive extraction accuracy.

## Research Design

Use one persistent adaptive research job for the online learning phase.

### Phase 1: Online Learning

Process 50 documents as ten sequential 5-document batches:

- `schema_mixed_batch_01.json`
- `schema_mixed_batch_02.json`
- ...
- `schema_mixed_batch_10.json`

After each batch:

1. Record metrics.
2. Inspect policy allocation.
3. Inspect extracted fields.
4. Classify failures.
5. Apply only high-ROI fixes that improve repeated behavior.
6. Do not reprocess previous batches as part of the next batch's metric.

This phase is allowed to improve the system.

### Phase 2: Prospective Evaluation

Freeze code, config, schema, scoring, and prompt wording.

Run the next 20 unseen documents:

- `schema_mixed_batch_11.json` through `schema_mixed_batch_14.json`

Adaptive condition:

- uses the same persistent job and accumulated job memory

Static condition:

- uses the same OCR and local LLM
- does not use adaptive job memory
- does not use AHMN policy adaptation

This prospective 20-document result is the main paper result table.

### Phase 3: Backup Holdout

Keep remaining documents:

- `schema_mixed_batch_15.json` through `schema_mixed_batch_20.json`

Use only if needed for additional holdout checks after the main 20-doc prospective evaluation.

## Required Metrics

Do not report one blended accuracy across all fields. Report separated metrics.

### 1. Document Type Accuracy

Score only `document_type`.

Correct if normalized extracted type equals expected type.

### 2. Positive-Field Precision / Recall / F1

Include fields where:

- expected value is not `unavailable`
- `expected_sources[field]` is not `unavailable_from_unmapped_label`
- field is not `document_type`

Use exact/fuzzy normalization already supported by `scripts/run_idpo_benchmark.py`, but keep numeric/text normalization transparent.

### 3. Unavailable Accuracy

Include fields where expected value is `unavailable`.

Correct if extracted value is absent or a recognized placeholder:

- empty string
- `N/A`
- `NA`
- `none`
- `null`
- `unknown`
- `not found`
- `not available`
- `unavailable`

### 4. Hallucination Rate

For fields expected as `unavailable`, count hallucination when extracted value is concrete and non-placeholder.

Report:

- unavailable field count
- hallucinated unavailable field count
- hallucination rate

### 5. Operational Metrics

For every batch and final prospective run, report:

- policy distribution
- policy changed count
- advice accepted/rejected/no-advice counts
- grounding coverage
- validation pass rate
- recovery rate
- escalation/defer rate
- latency
- feedback logged count

## Current Implementation State

The dataset pack has been generated and validated.

Validation already run:

```powershell
.venv\Scripts\python.exe -m pytest idpo/tests/test_schema_conditioned_pack.py -v
```

Result:

```text
1 passed
```

## Immediate Smaller-Model Task

Implement metric separation only. Do not change extraction behavior yet.

Read:

- `docs/SCHEMA_CONDITIONED_ONLINE_LEARNING_PLAN.md`
- `scripts/run_idpo_benchmark.py`
- `idpo/tests/test_research_features.py`
- `datasets/schema_conditioned_100.json`
- `datasets/schema_conditioned_batches/schema_mixed_batch_01.json`

Goal:

- benchmark evidence separates positive-field F1, unavailable accuracy, hallucination rate, and document type accuracy.

Implementation rules:

1. Use `expected_sources` to decide metric class.
2. Positive labels are expected values not equal to `unavailable` and not sourced from `unavailable_from_unmapped_label`.
3. Exclude `document_type` from positive-field F1.
4. For unavailable fields, accept placeholder outputs as correct unavailable behavior.
5. For unavailable fields, count concrete non-placeholder outputs as hallucinations.
6. Keep runtime proxy reward separate from all exact metrics.

Likely file:

- `scripts/run_idpo_benchmark.py`

Tests to add or update:

- `idpo/tests/test_research_features.py`

Required test cases:

1. Mixed expected fields produce correct positive-field `TP/FP/FN`.
2. Unavailable fields compute unavailable accuracy.
3. Hallucinated unavailable field increments hallucination count.
4. `document_type` accuracy is counted separately.
5. `reference_id` invoice-number normalization is handled separately from generic text matching.

Run:

```powershell
.venv\Scripts\python.exe -m pytest idpo/tests/test_research_features.py -v
```

Stop after this passes. Do not run the full 100-document benchmark yet.

## Batch Commands

First adaptive learning batch, creating or registering the persistent job:

```powershell
.venv\Scripts\python.exe scripts/run_idpo_benchmark.py --pack datasets/schema_conditioned_batches/schema_mixed_batch_01.json --config configs/idpo_research_config.json --register-frontend-jobs --job-name-prefix "Schema Online Learning"
```

Save printed:

```text
frontend_job_id=<JOB_ID>
```

Next batches:

```powershell
.venv\Scripts\python.exe scripts/run_idpo_benchmark.py --pack datasets/schema_conditioned_batches/schema_mixed_batch_02.json --config configs/idpo_research_config.json --register-frontend-jobs --benchmark-job-id <JOB_ID>
```

Time-saving adaptive-only iteration:

```powershell
.venv\Scripts\python.exe scripts/run_idpo_benchmark.py --pack datasets/schema_conditioned_batches/schema_mixed_batch_02.json --config configs/idpo_research_config.json --register-frontend-jobs --benchmark-job-id <JOB_ID> --adaptive-only
```

Before relying on the loop, verify:

- adaptive runs use `<JOB_ID>` as AHMN learning scope
- static runs do not use adaptive job memory

If not true, implement a narrow benchmark-runner fix before collecting evidence.

## Per-Batch Review Template

```text
Batch:
Pack:
Frontend job id:
Benchmark report:

Document type accuracy:
Positive-field precision/recall/F1:
Unavailable accuracy:
Hallucination rate:
Grounding coverage:
Validation pass rate:
Policy distribution:
Policy changed count:
Advice accepted/rejected/no-advice:
Recovery/escalation/defer:
Avg latency:

Failures:
- case_id:
  document_type:
  field:
  expected:
  expected_source:
  extracted:
  failure_class:
  likely_root_cause:
  fix_now: yes/no

Decision:
- Fix before next batch:
- Defer:
- Paper note:
```

Failure classes:

- `document_type_error`
- `positive_extraction_miss`
- `wrong_field`
- `normalization_bug`
- `unavailable_hallucination`
- `ocr_loss`
- `routing_failure`
- `validation_bug`
- `scoring_contract_bug`
## High-ROI Fix Policy

Fix only repeated failures that affect multiple documents or core metrics.

High priority:

- hallucinations on unavailable fields
- document type confusion between `invoice`, `receipt`, `form`, and `other`
- repeated missing positive fields for common fields like `document_date`, `issuer_name`, `recipient_name`, `primary_organization`, `total_amount`, `reference_id`
- grounding coverage not populated
- adaptive job memory not actually being reused
- policy allocation not changing across heterogeneous batches

Low priority:

- one-off reference-id phrasing mismatches
- broad OCR redesign
- adding new datasets before the 100-doc pack is measured

## Paper Claim Boundaries

Allowed:

- fixed-schema extraction across heterogeneous local labeled documents
- explicit unavailable handling as hallucination control
- job-scoped adaptive policy selection over sequential batches
- artifact-backed auditability and field-level evidence
- prospective comparison against static OCR+LLM baseline

Forbidden unless separately proven:

- universal document extraction
- state-of-the-art information extraction
- generalization to all business documents
- HITL effectiveness
- fine-tuning benefit
- superiority over commercial IDP systems

## Stop Conditions

Stop and revise claims if:

- unavailable hallucination rate is high and cannot be reduced quickly
- document type accuracy is unstable
- positive-field F1 does not improve or stabilize after online learning
- policy distribution does not change across mixed batches
- adaptive job memory is not actually used
- most failures are caused by unreadable OCR

Fallback paper framing:

> A systems study of schema-conditioned local extraction, showing measurable auditability, failure modes, and limits of online policy memory under heterogeneous documents.
