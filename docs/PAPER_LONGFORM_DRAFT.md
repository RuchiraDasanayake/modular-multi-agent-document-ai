# AHMN / IDPO Long-Form Dissertation-Aligned Draft

## Purpose

This document is the dissertation-aligned long-form companion to `docs/PAPER_DRAFT.md`.

Use it to build:

- the long-form research report or dissertation chapter set
- the later conference-paper compression

The argument must remain the same across both versions:

- AHMN is the policy-learning layer
- IDPO is the adaptive-safe runtime
- the evidence is dual-track
- the claim remains narrow

## Core Thesis Statement

Adaptive document extraction should be treated as a policy-learning and runtime-containment problem rather than as a single static extraction problem. AHMN addresses policy learning through Thompson Sampling, RABI cold-start transfer, and DAAF drift-aware adaptation, while IDPO operationalizes that adaptive behavior safely through explicit runtime containment and artifact-backed auditability.

## Suggested Dissertation Structure

## 1. Introduction

This chapter must include the institution-required parts:

- background literature
- research gap
- research problem
- research objectives

### 1.1 Background

Cover these themes:

- intelligent document processing and the challenge of heterogeneous documents
- practical limits of static routing
- online adaptation in document-processing systems
- cold-start and drift as operational problems
- the need for auditable runtime behavior in adaptive systems

### 1.2 Research Gap

State the gap narrowly:

- many systems focus on extraction quality or model architecture
- fewer works treat adaptive policy selection as a runtime control problem
- fewer still show how adaptive policy choice can be constrained operationally in a real runtime

### 1.3 Research Problem

Use a form close to this:

How can adaptive policy selection be introduced into a real document extraction runtime so that policy changes remain measurable, auditable, and operationally constrained, while still allowing useful adaptation under heterogeneous, cold-start, and drifting document conditions?

### 1.4 Research Objectives

Use objective wording like this:

1. Design AHMN as a practical policy-learning layer for document extraction.
2. Integrate AHMN into an adaptive-safe runtime without breaking the canonical execution path.
3. Evaluate AHMN through controlled evidence for online selection, cold start, and drift.
4. Evaluate the runtime through exact labeled metrics, runtime metrics, and containment behavior.

## 2. Literature and Technical Background

This chapter can be longer than the conference version.

### 2.1 Intelligent Document Processing

Cover:

- OCR-backed extraction systems
- multi-stage document pipelines
- challenges from layout variation and visual noise

### 2.2 Adaptive Policy Selection

Cover:

- why static configuration is limiting
- why policy selection can be cast as sequential decision-making
- why runtime observability matters

### 2.3 Thompson Sampling

Explain:

- exploration vs exploitation
- Beta-Bernoulli interpretation
- why it is appropriate as a practical online selector

### 2.4 Cold Start and RABI

Explain:

- why unseen contexts are hard
- how prior transfer from similar contexts helps
- what assumptions RABI relies on

### 2.5 Drift and DAAF

Explain:

- what drift means in operational document workloads
- why stale memory is dangerous
- how DAAF addresses the issue

### 2.6 Runtime Containment

Explain:

- fallback
- rollback
- defer

This section is important because it distinguishes the work from a purely algorithmic paper.

## 3. System Methodology

This should map cleanly to the institution’s methodology chapter requirement.

### 3.1 Overall System

Describe:

- canonical runtime path
- core services and boundaries
- why the runtime is local-first

### 3.2 AHMN Design

Describe:

- policy state
- advice generation
- job/run scoping
- contextual candidate filtering
- Thompson Sampling decision logic
- RABI role
- DAAF role

### 3.3 Adaptive-Safe Runtime Integration

Describe:

- `static`
- `adaptive_safe`
- how advice is merged with runtime planning
- how containment decisions are applied
- what artifacts are written

### 3.4 Runtime Methodology

Describe:

- document analysis
- planning
- extraction
- validation
- recovery
- escalation
- exports

Keep this section about execution behavior, not code inventory.

### 3.5 Testing and Implementation

This must satisfy SLIIT dissertation expectations.

Include:

- implementation environment
- model/runtime dependencies
- dataset staging path
- benchmarking path
- validation approach

### 3.6 Commercialization Aspect of the Product

Only include this because the dissertation format may require it.

Keep it separate from the core research claim.

Cover briefly:

- operator value
- deployment model
- practical constraints
- potential applied domains

Do not let commercialization language weaken the research tone.

## 4. Evaluation Design

This chapter should formalize the dual-track model.

### 4.1 Evaluation Philosophy

State explicitly:

- exact labeled correctness is separate from runtime proxy reward
- algorithmic evidence is separate from runtime evidence

### 4.2 Track A: AHMN Evidence

Use:

- existing `ahmn_core/experiments`
- robustness studies
- ablations where available

Report:

- Thompson Sampling behavior
- RABI cold-start evidence
- DAAF drift evidence

### 4.3 Track B: Runtime Evidence

Use only:

- canonical runtime path
- `static`
- `adaptive_safe`
- frozen config
- frozen mapping
- frozen benchmark packs

### 4.4 Dataset and Mapping

Describe:

- why `CORD v2` is used first
- exact mapped fields
- normalization rules
- what is intentionally out of scope

### 4.5 Metrics

Separate into:

- exact labeled metrics
- structured-output metrics
- runtime metrics
- containment metrics

## 5. Results and Discussion

This chapter must include:

- results
- research findings
- discussion

### 5.1 AHMN Findings

Discuss:

- what Track A supports strongly
- what it supports only conditionally

### 5.2 Runtime Findings

Discuss:

- policy change behavior
- exact extraction outcomes
- containment outcomes
- latency behavior

### 5.3 Interpretation

Be direct:

- if adaptive quality gains are mixed, state that
- if the runtime claim is stronger than the accuracy claim, state that
- if AHMN is more strongly supported in controlled evidence than runtime evidence, state that

### 5.4 Summary of Contributions by Student

Only include this if required in the dissertation/report submission.

Keep it factual and separate from the research claim.

## 6. Conclusion

The conclusion must include:

- what is actually demonstrated
- what is not yet proven
- the next research step

Recommended structure:

1. restate the narrow claim
2. summarize AHMN role
3. summarize runtime containment role
4. summarize evidence separation
5. identify the next evaluation step

## Writing Rules for the Long Form

### Do

- keep the same core claim as the conference paper
- expand explanation, not claim scope
- use explicit subsections
- separate evidence types clearly
- keep limitations visible

### Do not

- turn the chapter into a project diary
- mix implementation notes with results interpretation
- report runtime proxy reward as exact correctness
- let the dissertation version quietly widen the conference claim

## Shared Evidence Freeze Rules

Both the dissertation-aligned version and the conference version must use the same frozen core:

- one frozen config
- one frozen field mapping
- one frozen benchmark set for final runtime results
- one fixed interpretation of exact metrics

Track A may include controlled experiments outside the runtime benchmark, but that evidence must remain explicitly labeled as algorithmic evidence.

## Conversion Rule: Long Form to Conference Paper

When compressing this long-form version into the conference paper:

- keep the same title family
- keep the same canonical claim
- compress literature review
- compress system description
- keep only high-signal tables
- preserve limitations
- do not remove the dual-track evidence separation
