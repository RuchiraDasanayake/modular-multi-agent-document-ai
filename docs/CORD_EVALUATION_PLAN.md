# CORD Evaluation Plan

This document defines the active external labeled testing plan for the current phase.

It is intentionally strict.

The goal is not to "use more data somehow."

The goal is to turn `CORD v2` into a controlled reliability and evidence loop that improves the shipped system and produces defensible paper material.

## Classification

- Surface: `datasets/external/cord-v2` and the supporting evaluation path
- Classification: `research_evidence`
- Primary action: `keep`
- Acceptance check: the team can run a deterministic labeled subset through the canonical runtime, score exact mapped fields, classify failures, and repeat that loop without changing the claim

## Why CORD First

`CORD v2` is the right first external dataset because it is:

- public
- labeled
- already downloaded into the repo workspace
- focused enough to make debugging practical
- large enough to expose repeated receipt extraction failures

Observed local split sizes:

- `train`: `800`
- `validation`: `100`
- `test`: `100`

Observed label structure:

- `image`
- `ground_truth`
- `gt_parse.menu`
- `gt_parse.total`
- optional `gt_parse.sub_total`
- `valid_line` categories for word-level receipt structure

This makes it useful for:

- exact field scoring
- OCR and normalization debugging
- receipt-specific extraction hardening

## Claim Boundary

Use `CORD v2` to support these things:

- the runtime can be exercised on real external labeled receipt images
- repeated extraction failures can be identified and fixed systematically
- `static` vs `adaptive_safe` can be compared on a non-toy labeled receipt set
- adaptive containment behavior remains visible through canonical artifacts

Do not use `CORD v2` to claim:

- broad document generalization across all enterprise document types
- strong line-item extraction performance before line-item support is intentionally built and scored
- full real-world production readiness across every receipt format

## Canonical Execution Rule

Use the canonical runtime only:

`frontend job (POST /api/jobs/<job_id>/documents, then POST /api/jobs/<job_id>/runs) -> frontend job runner -> idpo.cli process-inbox -> IDPO_DATA_DIR/runs/<run_id>`

For batch evaluation work, the acceptable non-UI execution path is still:

`idpo.cli process-inbox -> idpo.pipeline.inbox -> idpo.pipeline.orchestrator`

Do not create a paper-only shortcut that bypasses the shipped runtime artifacts.

For smoke and pilot evidence runs, register each benchmarked document as a frontend job record as well, so operators can inspect the source file, paired run outcomes, and document detail pages from the same UI used for normal runs.

## Evaluation Architecture

Keep the loop in four explicit stages.

### 1. Read

Read local `CORD v2` parquet files from:

- `datasets/external/cord-v2/data`

Each sample provides:

- receipt image
- `ground_truth` JSON string

### 2. Stage

Convert selected samples into a deterministic staged subset with:

- stable sample ids
- copied or referenced image files
- gold label JSON beside each sample
- subset manifest
- field mapping version

Do not stage the whole dataset blindly at first.

### 3. Run

Run the staged subset through both:

- `static`
- `adaptive_safe`

Use the same canonical config base and artifact path discipline as the product runtime.

### 4. Score

Score outputs from emitted run artifacts, not from temporary in-memory objects only.

Separate:

- exact mapped field metrics
- structured-output quality
- runtime behavior
- adaptive containment behavior

## Mapping Policy

Do not start with every labeled surface in `CORD`.

Start with `mapping_v1`, a small exact field set.

### Mapping V1

- `total_amount`
  <- `gt_parse.total.total_price`
- `cash_amount`
  <- `gt_parse.total.cashprice` when present
- `change_amount`
  <- `gt_parse.total.changeprice` when present
- `subtotal_amount`
  <- `gt_parse.sub_total.subtotal_price` when present
- `tax_amount`
  <- `gt_parse.sub_total.tax_price` when present

Normalization rules must be explicit:

- strip currency noise
- normalize commas and decimal formatting consistently
- trim whitespace
- compare normalized strings, not raw OCR fragments

### Deferred Mapping

Defer until later phases:

- full line-item scoring
- menu-unit-price reasoning
- subtotal decomposition beyond flat mapped fields
- vendor/date claims not directly supported by the chosen ground-truth slice

## Subset Schedule

Do not jump straight to all `1,000` receipts.

Use this order:

### Phase A: Setup Subset

- `20` deterministic receipts from `validation`

Purpose:

- verify staging
- verify mapping
- verify canonical runtime output paths
- classify obvious failures

### Phase B: Development Subset

- `50` deterministic receipts from `validation`

Purpose:

- confirm repeated failure patterns
- validate high-ROI fixes
- detect regressions quickly

### Phase C: Full Validation

- all `100` validation receipts

Purpose:

- produce the first serious external labeled evidence pass
- freeze early evidence tables

### Phase D: Holdout Test

- all `100` test receipts

Purpose:

- only after mapping and evaluation are frozen
- confirm results without tuning on the holdout split

## Metrics

Track these separately.

### Exact Labeled Metrics

- exact precision
- exact recall
- exact F1
- per-field accuracy
- exact scored document count

### Structured-Output Metrics

- schema valid rate
- schema coverage
- schema grounding coverage
- missing required field count
- hallucinated field count
- unresolved field count

### Runtime Metrics

- average latency
- escalation rate
- recovery rate
- OCR rerun usage

### Adaptive-Safe Metrics

- advice accepted count
- policy changed count
- fallback count
- rollback count
- blocked policy count
- defer requested count
- defer blocked count

Do not report runtime proxy reward as exact correctness.

## Failure Taxonomy

Every reviewed failure should be placed in one primary bucket:

1. `ocr_loss`
   Text quality is too poor before extraction.
2. `normalization_bug`
   The model found the right value but formatting or cleanup broke exact match.
3. `mapping_bug`
   Gold-to-runtime field mapping is wrong or incomplete.
4. `extraction_miss`
   The field is present but the runtime did not extract it.
5. `wrong_field`
   A value was extracted into the wrong semantic slot.
6. `hallucination`
   A field value was produced without support.
7. `containment_bug`
   Fallback, rollback, block, or defer behavior is wrong or invisible.
8. `artifact_bug`
   The runtime produced output, but the needed evidence is missing or malformed.
9. `non_actionable_case`
   The failure is real but not worth fixing in the current phase.

This keeps the fix loop honest.

## High-ROI Fix Rules

A fix is high ROI only if it is:

- repeated across multiple reviewed receipts
- small enough to review safely
- likely to improve exact quality or reliability across many cases
- aligned with the canonical runtime, not a paper-only branch

Prioritize:

- numeric normalization
- amount-field resolution
- missing or malformed artifact output
- obvious OCR cleanup issues
- field-name and requested-field mismatches
- adaptive-safe logging or visibility gaps

Defer:

- speculative model changes
- broad architecture rewrites
- long-document features unrelated to receipts
- UI expansion that does not improve evidence review

## Fix Loop

Run this loop strictly:

1. stage one deterministic subset
2. run `static`
3. run `adaptive_safe`
4. score exact mapped fields
5. manually inspect failures
6. assign one failure category per case
7. implement only high-ROI fixes
8. rerun the same subset
9. compare before/after metrics and containment behavior

Do not change:

- dataset split
- subset composition
- field mapping
- claim wording

in the middle of a comparison cycle.

## Evidence Freeze Rules

Before final paper writing, freeze:

- dataset path
- subset manifests
- mapping version
- config file path
- runtime labels
- commit hash
- run ids
- metric tables
- selected UI screenshots

After freeze:

- do not rename labels
- do not change mapping semantics casually
- do not add paper-only evaluation branches

## Out Of Scope For This Phase

- multiple external datasets in one active loop
- full line-item paper claims
- benchmark theater with many unsupported metrics
- new product features unrelated to evaluation reliability
- large AHMN redesigns unless the current behavior directly weakens `adaptive_safe`

## Immediate Implementation Plan

1. create a `CORD` staging adapter
2. create `mapping_v1` for flat receipt totals
3. create deterministic `20`-receipt and `50`-receipt subset manifests
4. run the first `static` and `adaptive_safe` pilot passes
5. inspect failures and rank them by ROI
6. fix only the top repeated issues
7. rerun the same subset before scaling

## Definition Of Ready For Paper Results

Do not write the final Results section until all of these are true:

- the `CORD` staging path is reproducible
- the first mapping version is frozen
- at least one validation-sized run has completed in both modes
- the major failure categories are known
- the top high-ROI fixes have already been retested
- the exact-metric and containment tables come from frozen artifacts
