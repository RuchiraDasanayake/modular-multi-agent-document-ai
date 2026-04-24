# Paper Draft

## Scope

This draft is constrained by the current product and repo documents.

The paper is about one narrow claim only:

`adaptive_safe` is a real runtime mode in which AHMN can change policy selection and IDPO keeps those adaptive decisions safe through fallback, rollback, and defer.

This draft does not assume stronger claims than the current code, UI, and benchmark can defend.

## Classification

- Surface: `docs/PAPER_DRAFT.md`
- Classification: `research_evidence`
- Primary action: `keep`
- Acceptance check: the team can use this file to write the paper without drifting away from the canonical runtime or widening the claim

## Assumptions

1. The canonical comparison remains `static` vs `adaptive_safe`.
2. The canonical runtime remains:
   `frontend upload -> /api/runs/start -> frontend job runner -> idpo.cli process-inbox -> IDPO_DATA_DIR/runs/<run_id>`.
3. The paper should be product-first, not algorithm-theater.
4. Exact metrics, screenshots, and benchmark deltas will be inserted only after evidence is regenerated and checked.

## Working Title Options

1. Adaptive-Safe Document Extraction: Containing Policy Advice in a Local-First Intelligent Document Pipeline
2. Safe Adaptive Policy Selection for Document Extraction with Runtime Fallback, Rollback, and Defer
3. From Static to Adaptive-Safe: Auditable Policy Selection in a Document Processing Runtime

Recommended title:

`Adaptive-Safe Document Extraction: Auditable Policy Selection with Runtime Containment`

## One-Sentence Claim

We present a local-first document extraction runtime where adaptive policy advice can change execution behavior, while the production path remains auditable and contained through explicit fallback, rollback, and defer mechanisms.

## Abstract Draft

Document extraction systems often face a practical tension: fixed routing is stable but inflexible, while adaptive policy selection can improve handling across heterogeneous document conditions but introduces operational risk. We present an adaptive-safe document extraction runtime built on a local-first intelligent document processing pipeline. The system compares two executed modes over the same canonical path: `static`, which uses deterministic policy selection, and `adaptive_safe`, which allows AHMN policy advice to alter routing while IDPO applies containment through fallback, rollback, and defer. The contribution is not a paper-only wrapper, but an auditable runtime whose adaptive decisions are exposed through stable run artifacts, operator-facing UI surfaces, and benchmark evidence. We define a narrow evaluation focused on exact field metrics where labels exist, structured-output validity, latency, escalation behavior, policy change rate, and containment events. The paper argues for a practical position: adaptive policy selection is only credible in document AI when the system makes policy changes measurable and safety behavior explicit. Final quantitative results should be inserted only from the regenerated benchmark and verified UI/runtime artifacts.

## Problem Statement

Static extraction pipelines are easy to reason about but brittle across varying document layouts, quality levels, and routing conditions. Purely adaptive systems are harder to trust because they can change behavior without clear containment or auditability. The practical problem is therefore not "how to make policy selection adaptive at any cost," but how to let adaptive advice influence execution while preserving visible safeguards and stable evidence.

## Paper Positioning

What this paper is:

- a narrow systems paper about executed adaptive policy selection in document extraction
- an evidence-backed comparison of `static` vs `adaptive_safe`
- a product-grounded account of runtime containment and auditability

What this paper is not:

- a broad claim about general multi-agent intelligence
- a paper centered on XAI, Guardrails, or HITL as the primary novelty
- a claim that AHMN alone solves document extraction
- a benchmark story detached from the shipped runtime

## Claimed Contributions

Keep these modest.

1. A canonical runtime that exposes adaptive policy decisions through stable artifacts and operator-facing UI rather than hidden internal traces.
2. An `adaptive_safe` execution mode that permits policy changes while containing risk through fallback, rollback, and defer.
3. A product-grounded evaluation protocol comparing `static` and `adaptive_safe` on identical inputs using exact field metrics, structured-output quality signals, latency, and containment behavior.

## System Overview

The paper should describe the system in this order:

1. Canonical runtime path
2. Document analysis and planning
3. `static` versus `adaptive_safe`
4. Containment logic: fallback, rollback, defer
5. Stable run artifacts and UI evidence surfaces
6. Benchmark path and reporting

Short system summary:

The frontend starts a run through `/api/runs/start`, the frontend job runner invokes `python -m idpo.cli process-inbox`, and IDPO processes documents through `ingest/inbox -> orchestrator -> executor -> exports`. In `static`, deterministic local routing is used. In `adaptive_safe`, AHMN advice can alter the selected policy, but IDPO records the static baseline, recommended policy, final selected policy, advice status, and any containment outcome.

## Method Section Skeleton

### 1. Runtime Modes

- `static`: deterministic local policy selection
- `adaptive_safe`: AHMN advice plus IDPO containment

### 2. Adaptive Decision Record

For each document, describe these fields explicitly:

- static baseline policy
- recommended policy
- final selected policy
- whether the policy changed
- advice acceptance or rejection status
- fallback reason
- rollback state and reason
- defer state and reason

### 3. Containment Semantics

Define these carefully:

- fallback: adaptive recommendation is replaced before execution or routed back to a safer path
- rollback: selected policy is blocked or reverted due to monitored runtime behavior
- defer: the system intentionally avoids unsafe confidence in a result and records that state

### 4. Evidence Artifacts

Primary artifacts to cite:

- `run.json`
- `run_metadata.json`
- `metrics.json`
- `decision_chain_summary.json`
- per-document `decision_chain.json`
- per-document `reward.json`
- per-document `recovery_trace.json`
- benchmark `paper_evidence.json`

## Evaluation Section Skeleton

### Research Questions

1. Does `adaptive_safe` actually change policy selection relative to `static`?
2. When policy changes occur, does `adaptive_safe` improve extraction quality or structured-output quality on the benchmark?
3. How often does IDPO contain adaptive risk through fallback, rollback, or defer?
4. What latency, escalation, or recovery tradeoffs accompany adaptive behavior?

### Canonical Comparison

Use only:

- `static`
- `adaptive_safe`

Use only:

- `configs/idpo_research_config.json`
- `python scripts/run_idpo_benchmark.py --config configs/idpo_research_config.json`

### Metrics To Report

- exact precision
- exact recall
- exact F1
- validation pass rate
- schema valid rate
- schema coverage
- schema grounding coverage
- latency
- escalation rate
- recovery rate
- policy change count
- advice accepted count
- fallback count
- rollback count
- blocked policy count
- defer requested count
- defer blocked count

### Reporting Rule

Do not mix exact reviewed scores with runtime proxy reward. If runtime proxy reward is discussed, label it explicitly as a bandit reward signal, not as final extraction correctness.

## Figures And Tables

### Figures

1. Canonical runtime diagram:
   `frontend -> /api/runs/start -> runner -> idpo.cli -> inbox -> orchestrator -> executor -> exports`
2. Adaptive decision path:
   static baseline, AHMN recommendation, final selected policy, containment branch
3. Run artifact map:
   run-level and document-level evidence files

### Tables

1. System modes:
   `static` vs `adaptive_safe`
2. Main benchmark comparison:
   exact F1, schema valid rate, latency, escalation, policy change, fallback, rollback, defer
3. Subgroup results:
   document type, route bin, policy transition type, seen vs less-seen regimes if supported

## Results Writing Template

Use this wording pattern and replace placeholders only after evidence is verified:

`Compared with static, adaptive_safe changed policy selection for [X]% of benchmark documents. It improved exact field F1 by [X], schema-valid rate by [X], and [reduced/increased] average latency by [X] ms. IDPO contained adaptive risk through [X] fallback events, [X] rollbacks, and [X] defer states, making policy intervention visible rather than implicit.`

If the numbers do not support improvement, say so directly. Do not bury regressions.

## Threats To Validity

1. The benchmark is tied to the current product path and may not generalize beyond the supported runtime.
2. Runtime proxy reward is not ground truth and must not be reported as exact correctness.
3. Adaptive gains may depend on the current policy store and document mix.
4. The system is local-first and operational results may differ under different model/runtime environments.
5. Safety events such as fallback and rollback indicate containment, not automatic success.

## Strict Writing Rules

1. Do not describe legacy paths as canonical.
2. Do not widen the claim beyond `static` vs `adaptive_safe`.
3. Do not present speculative algorithmic novelty as proven contribution.
4. Do not claim full end-to-end cloud deployment support for the current runtime.
5. Do not report numbers without a traceable artifact source.

## Immediate Evidence To Collect Before Finalizing Results

1. Run one live `static` job from the canonical UI path.
2. Run one live `adaptive_safe` job from the same UI path.
3. Capture screenshots from the canonical run and document pages showing policy selection and containment fields.
4. Regenerate benchmark evidence with:
   `python scripts/run_idpo_benchmark.py --config configs/idpo_research_config.json`
5. Record the exact commit hash used for the benchmark.
6. Freeze screenshots, benchmark bundle, and metric tables before polishing prose.

## Suggested Section Order For The Actual Paper

1. Introduction
2. Problem and design criteria
3. System and runtime design
4. Adaptive-safe execution model
5. Evaluation setup
6. Results
7. Threats to validity
8. Conclusion

## Introduction Draft

Document extraction systems must operate across heterogeneous files, varying OCR quality, and shifting structural patterns, yet many practical deployments still depend on fixed routing decisions because adaptive behavior is difficult to trust in production. The central issue is not whether adaptive policy selection can be invented, but whether it can be executed in a way that is measurable, auditable, and operationally contained. This paper presents a narrow answer: a local-first document processing runtime that compares deterministic `static` execution against `adaptive_safe`, where policy advice can change the selected route but the runtime records and constrains that change through fallback, rollback, and defer. Rather than claiming a broad autonomous document intelligence system, we focus on the concrete properties that matter in deployment: stable artifacts, visible policy transitions, structured-output quality, and explicit containment behavior.

## Next Writing Pass

The next pass should convert this draft into venue format and fill only these sections first:

1. Introduction
2. System overview
3. Evaluation setup

Do not write the final Results section until the benchmark and UI evidence are frozen.
