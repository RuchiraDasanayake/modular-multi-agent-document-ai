# Dataset Plan

This document defines the practical dataset path for the current phase.

## Immediate Goal

Use a starter dataset that already exists inside the repo so the team can:

- test the deployed system now
- compare `static` vs `adaptive_safe`
- identify OCR and routing failures early
- build a manual labeling queue for the real research dataset

## Starter Pack

Use:

- [datasets/starter_pack_manifest.json](../datasets/starter_pack_manifest.json)

The starter pack has 3 parts:

1. `benchmark_labeled`
   10 fixed cases from `idpo/benchmark/data`
   Use for exact regression metrics and benchmark script runs

2. `synthetic_demo_unlabeled`
   3 demo JSON cases from `demo_docs`
   Use for UI/demo sanity checks

3. `pilot_real_unlabeled`
   10 real PDFs already in `inputs/inbox`
   Use for OCR-path validation and manual review

## What This Gives You Right Now

- 10 labeled benchmark cases
- 3 synthetic demo cases
- 10 real PDF pilot cases
- total starter pack size: 23 documents

This is enough to:

- verify the system end to end
- test local vs fallback behavior
- exercise OCR and PDF handling
- create the first human-labeled review queue

It is not enough to support the final research claim by itself.

## Research Claim Dataset Requirement

To support a claim like:

`adaptive extraction achieved higher accuracy and faster extraction across many documents`

you need a larger labeled set.

Recommended minimum path:

1. `starter`
   23 docs
   Purpose: system shakeout and pipeline debugging

2. `pilot labeled`
   50 to 100 docs
   Purpose: confirm annotation rules and metric definitions

3. `research labeled`
   200+ docs minimum
   Better target: 500+
   Purpose: defensible final-year research evidence

4. `scale throughput`
   1000s of docs can be processed after the labeled protocol is stable
   Purpose: throughput and operational evidence, not primary accuracy proof by itself

## Strict Evaluation Rule

Separate these two claims:

- `accuracy claim`
  Needs labeled truth

- `throughput / latency claim`
  Can use larger unlabeled processing sets once the evaluation protocol is fixed

Do not mix them.

## Next Dataset Work

Immediate next dataset steps:

1. stage the starter pack into runtime storage
2. run the labeled benchmark pack with `scripts/run_idpo_benchmark.py`
3. process the 10 real PDFs through the public or local UI
4. manually review outputs and create a labeling sheet
5. promote reviewed pilot PDFs into the labeled set

## Annotation Target

For the first manual labeling round, label only a small, stable field set:

- document identifier
- date
- vendor / supplier / sender
- total amount
- one document-specific key field

This keeps early accuracy evaluation realistic.
