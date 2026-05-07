# AHMN Service Parity Checklist

This checklist gates any **headline** service-backed benchmark run.

Until every required item here is complete, continue using the current TS-stub
 path for stabilization work and treat service-backed AHMN as experimental.

## Purpose

The repo currently has two AHMN execution paths:

- local direct-import TS stub
- full HTTP AHMN service with RABI and DAAF

That split is acceptable only during stabilization. It is not acceptable for a
paper-facing headline benchmark unless parity risks are explicitly reduced first.

## Hard Rule

Do **not** start a headline service-backed benchmark unless all required items
below are complete and recorded.

Allowed before completion:

- local TS-stub stabilization runs
- targeted service smoke tests
- parity tests
- short experimental service runs clearly labeled as non-headline

Not allowed before completion:

- service-backed paper figures
- service-backed baseline comparisons presented as final evidence
- mixing stub-backed and service-backed runs in one adaptive job or one frozen evidence table

## Required Items

### 1. Advice Transport Parity

Status: `done`

Acceptance check:

- benchmark exact-feedback path uses the same channel selection order as runtime feedback:
  - HTTP service first when configured
  - direct-import fallback only when allowed

Evidence:

- [scripts/run_idpo_benchmark.py](</E:/Research Project/Code/IDPO/scripts/run_idpo_benchmark.py:585>)
- [idpo/tests/test_research_features.py](</E:/Research Project/Code/IDPO/idpo/tests/test_research_features.py:2127>)

### 2. Reward Semantics Parity

Status: `required`

Question:

- does the benchmark send the exact same learning signal to the service path and the stub path?

Current gap:

- stub path consumes a precomputed scalar reward
- service path recomputes blended reward from posted metrics at `/advice/log`

Acceptance check:

- one explicit test proves intended benchmark reward semantics for the service path
- one explicit doc note states whether benchmark mode uses:
  - exact benchmark reward directly
  - or blended service reward intentionally

### 3. Advice/Log Contract Parity Tests

Status: `partial`

Acceptance check:

- advice request test covers service-mode payload shape
- advice response test covers `policy_id`, `advice_id`, `retrieval_source`, `rabi_used`, `n_neighbors`
- log request test covers benchmark/runtime payload shape
- feedback acceptance test proves service log path returns success for expected payload

### 4. RABI Activation Test

Status: `required`

Acceptance check:

- one targeted test or smoke run shows `rabi_used = true` under a real cold-start-like service scenario
- artifact evidence shows neighbor count and retrieval source clearly

### 5. DAAF Update / Forgetting Test

Status: `required`

Acceptance check:

- one targeted test proves `/advice/log` produces non-trivial drift output (`gamma`, drift type, or equivalent)
- one scheduler or manual forgetting smoke test proves the service forgetting path executes successfully

### 6. Mixed-Slice `document_type` Smoke Run

Status: `required`

Acceptance check:

- one small mixed service-backed run shows reduced disagreement across:
  - `dae/output.json`
  - `plan/primary.json`
  - `structuring/extracted.json`
  - `validation/results.json`

Purpose:

- prevents service-backed runs from being confounded by still-broken document-type contract surfaces

### 7. Evidence Bookkeeping Reconciliation

Status: `required`

Acceptance check:

- authoritative processed-doc counts reconcile across:
  - frontend benchmark job
  - job context
  - run artifacts

Purpose:

- prevents paper evidence from failing basic auditability checks

## Optional But Strongly Recommended

### 8. Shared AHMN Engine Plan

Status: `deferred`

Goal:

- define how direct-import and service paths will eventually share one algorithm implementation instead of diverging further

This is recommended, but it is not required before the first service-backed experimental run.

## Completion Rule

This checklist is complete only when:

1. all items marked `required` are complete
2. evidence links or test commands are recorded in `docs/RESEARCH_LOG.md`
3. the next service-backed run is explicitly labeled as:
   - experimental, if any residual risk remains
   - headline-capable, only if no gating item remains open

## Current Decision

Current allowed path:

- continue TS-stub stabilization

Current blocked path:

- headline service-backed benchmark evidence
