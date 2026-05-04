# Dataset Plan

This document defines the practical dataset path for the current phase.

The phase is no longer centered only on the tiny starter pack.

The active goal is to use one serious external labeled dataset to harden the runtime, expose repeated failures, and build evidence without widening the claim carelessly.

## Active Dataset Ladder

Use datasets in this order.

### 1. Internal Regression Pack

Use:

- `idpo/benchmark/benchmark_pack.json`
- `idpo/benchmark/data/*`

Current size:

- `10` labeled benchmark cases

Purpose:

- smoke-test the canonical benchmark runner
- preserve exact regression checks for existing repo behavior
- catch obvious breakage quickly

This pack stays useful, but it is too small and too synthetic to drive the main reliability loop by itself.

### 2. Primary External Labeled Dataset

Use:

- `datasets/external/cord-v2`

Observed local structure:

- `train`: `800`
- `validation`: `100`
- `test`: `100`

Observed label surfaces:

- image input
- `ground_truth` JSON payload
- `gt_parse.menu`
- `gt_parse.total`
- optional `gt_parse.sub_total`
- word-level `valid_line` categories such as:
  - `menu.nm`
  - `menu.cnt`
  - `menu.price`
  - `total.total_price`
  - `total.cashprice`
  - `total.changeprice`
  - `sub_total.subtotal_price`
  - `sub_total.tax_price`

Purpose:

- first real external labeled testing loop
- repeated receipt extraction debugging
- high-ROI fix discovery
- exact scoring on mapped receipt fields

This is the current primary dataset for system hardening.

### 3. Pilot Real Unlabeled Set

Use:

- `inputs/inbox/*.pdf`

Current size:

- `10` real PDFs already staged in the repo

Purpose:

- OCR-path validation
- UI sanity checks
- manual inspection of non-synthetic outputs

These files help operational testing, but they do not provide exact accuracy evidence yet.

### 4. Future Labeled Real Dataset

Not yet active.

Purpose:

- stronger final research evidence on real documents owned by the team
- broader claim support after annotation rules are stable

Recommended path:

1. `pilot labeled`
   `50-100` docs
2. `research labeled`
   `200+` docs minimum
3. larger unlabeled throughput sets only after the exact evaluation protocol is stable

## Strict Evaluation Rule

Separate these claims:

- `exact extraction quality`
  Needs labeled truth and a frozen field mapping

- `throughput and operational behavior`
  Can use larger unlabeled processing sets after the evaluation protocol is fixed

- `adaptive-safe behavior`
  Must come from canonical run artifacts showing policy choice, fallback, rollback, and defer

Do not mix them.

## Current Dataset Strategy

Use the datasets with different roles:

- internal regression pack
  protects the current benchmark path
- `CORD v2`
  drives the main labeled testing and high-ROI fix loop
- real unlabeled PDFs
  validate OCR and runtime behavior outside the synthetic pack

Do not add more external datasets until `CORD v2` staging, mapping, and scoring are stable.

## Field Scope Rule

Do not try to score everything in `CORD v2` immediately.

Start with a small, strict field set that the runtime can reasonably emit and the labels clearly support.

Recommended first mapped fields:

- `total_amount` from `gt_parse.total.total_price`
- `cash_amount` from `gt_parse.total.cashprice` when present
- `change_amount` from `gt_parse.total.changeprice` when present
- `subtotal_amount` from `gt_parse.sub_total.subtotal_price` when present
- `tax_amount` from `gt_parse.sub_total.tax_price` when present

Defer line-item claims until flat receipt totals are stable and the mapping logic is frozen.

## Immediate Dataset Work

1. keep the internal regression pack running
2. stage `CORD v2` into a deterministic evaluation flow
3. define and freeze the first receipt-field mapping
4. run a small manually reviewed subset first
5. fix only repeated high-ROI failures
6. scale to larger validation runs only after the small loop is stable
7. use the real unlabeled PDFs for OCR-path and UI sanity checks in parallel

## Dataset Freeze Discipline

Before writing the final results section, freeze:

- dataset path and version
- subset manifests
- field mapping version
- config file
- commit hash
- exact metrics tables
- run ids and artifact locations

Do not keep moving the target while collecting evidence.

## Related Plan

For the active execution plan, use:

- [docs/CORD_EVALUATION_PLAN.md](./CORD_EVALUATION_PLAN.md)
