# AHMN for Adaptive-Safe Document Extraction

## Working Title

`AHMN for Adaptive-Safe Document Extraction: Practical Policy Learning with Auditable Runtime Containment`

Fallback short title:

`AHMN for Adaptive-Safe Document Extraction`

## Positioning

This is the conference-style manuscript draft.

It is intentionally written as a paper, not as an internal planning memo.

The paper is:

- a practical runtime systems paper
- foregrounding AHMN as the policy-learning layer
- validated through the canonical `static` vs `adaptive_safe` runtime path
- supported by dual-track evidence:
  - controlled AHMN evidence
  - canonical runtime evidence

The paper is not:

- a broad OCR paper
- a general multi-agent paper
- a benchmark-only paper
- a claim that adaptive routing universally outperforms static routing

## Canonical Claim

We present AHMN as a practical policy-learning layer for document extraction and operationalize it inside an adaptive-safe runtime, where adaptive policy advice can alter execution behavior while remaining auditable and constrained through explicit fallback, rollback, and defer mechanisms.

## Abstract

Document extraction systems face a practical tension: deterministic routing is stable but brittle across heterogeneous document conditions, while unconstrained adaptive policy selection can improve handling but introduces operational risk. This paper presents AHMN, a practical policy-learning layer for document extraction, and its deployment inside an adaptive-safe runtime built on IDPO. AHMN combines Thompson Sampling for online policy selection, Retrieval-Augmented Bandit Initialization (RABI) for cold-start prior transfer, and Drift-Aware Adaptive Forgetting (DAAF) for drift-aware memory adaptation. The runtime executes two modes over the same canonical path: `static`, which uses deterministic policy selection, and `adaptive_safe`, in which AHMN advice may alter routing while IDPO constrains risk through explicit fallback, rollback, and defer mechanisms. We evaluate the system using a dual-track evidence model: algorithmic evidence for the AHMN components and runtime evidence on labeled document subsets using exact field metrics, structured-output validity, latency, and containment behavior. The central claim is narrow: adaptive document extraction is credible only when policy changes are measurable, auditable, and operationally contained.

## Keywords

- intelligent document processing
- adaptive policy learning
- Thompson Sampling
- cold-start transfer
- concept drift
- runtime containment

## 1. Introduction

Document extraction systems operate across heterogeneous inputs that vary in structure, visual quality, OCR readability, and vendor-specific layout conventions. In practice, many deployed pipelines continue to rely on fixed routing decisions because deterministic behavior is easier to reason about, easier to reproduce, and easier to support operationally. That stability comes at a cost: static routing is often brittle when document conditions shift.

Adaptive policy selection is a natural response to this problem, but adaptive behavior creates a second problem. A system that silently changes which policy processes each document can become difficult to audit, difficult to debug, and difficult to trust. The practical issue is therefore not whether policy selection can be made adaptive in principle, but whether it can be made adaptive safely inside a real document runtime.

This paper addresses that problem through AHMN, a policy-learning layer for document extraction, and its integration into an adaptive-safe runtime built on IDPO. AHMN combines Thompson Sampling for online policy selection, RABI for cold-start prior transfer from similar contexts, and DAAF for drift-aware memory adaptation. Rather than presenting these mechanisms as an isolated algorithmic stack, we operationalize them in a runtime where adaptive advice can change execution behavior only through a constrained and auditable path.

The runtime exposes two executed modes over the same canonical system path. In `static`, policy selection is deterministic. In `adaptive_safe`, AHMN may recommend a different policy, but IDPO records the static baseline, the recommendation, the final selected policy, and any containment outcome including fallback, rollback, and defer. The result is not a paper-only abstraction, but a system whose adaptive behavior can be inspected through stable run artifacts and operator-facing evidence surfaces.

The paper uses a dual-track evidence model. Track A evaluates AHMN itself through controlled evidence for Thompson Sampling, RABI, and DAAF. Track B evaluates the executed runtime through `static` vs `adaptive_safe` on labeled document subsets using exact field metrics, validation outcomes, latency, and containment behavior. This separation matters because runtime reward is a bandit learning signal, not ground-truth correctness.

The contributions of this paper are fourfold:

1. AHMN as a practical policy-learning layer for document extraction, combining Thompson Sampling, RABI, and DAAF.
2. An adaptive-safe runtime that operationalizes AHMN while constraining adaptive risk through fallback, rollback, and defer.
3. A stable evidence model based on run artifacts, exact reviewed metrics, and operator-visible policy traces.
4. A dual-track evaluation protocol separating algorithmic evidence from runtime extraction evidence.

## 2. Background and Motivation

### 2.1 Static routing versus adaptive selection

Traditional document extraction systems often route documents through fixed policy logic based on hand-authored rules or single-model assumptions. This is attractive operationally because identical inputs receive identical processing behavior. The downside is that such systems adapt poorly when document distributions evolve or when previously unseen structures enter the system.

Adaptive selection offers a more flexible alternative by choosing among multiple extraction policies at runtime. However, the usefulness of adaptation depends on whether the system can learn from outcomes without becoming opaque or unstable.

### 2.2 Thompson Sampling in policy selection

Thompson Sampling provides a practical online decision mechanism for balancing exploration and exploitation. In this setting, each policy can be treated as an arm whose payoff reflects downstream extraction quality. The method is not novel by itself; its value here lies in its interpretability, low overhead, and compatibility with artifact-backed policy decisions.

### 2.3 Cold start and drift in document processing

Two practical difficulties limit naive online adaptation. First, new document contexts may arrive with little or no historical feedback, creating a cold-start problem. Second, reward behavior may shift over time as document styles, OCR quality, or workload composition change, creating drift. These are operational problems, not just abstract bandit settings.

### 2.4 Why containment is necessary

An adaptive policy layer is not operationally credible if it can change execution behavior without visible constraints. Production-facing adaptive systems require an explicit answer to three questions: when should advice be accepted, when should it be rejected or replaced, and when should the system defer rather than act with unjustified confidence. This paper treats containment as a core requirement, not an auxiliary safeguard.

## 3. AHMN Design

### 3.1 Thompson Sampling for online policy choice

AHMN models each candidate policy with a reward posterior and uses Thompson Sampling to select among them during execution. The purpose is not to claim a new bandit algorithm, but to establish a practical online mechanism that can accumulate evidence from repeated policy outcomes.

In the deployed runtime, the bandit state is scoped to the active job or run so that learning can accumulate across documents processed in the same operational context. This makes the adaptive behavior observable and reproducible within the same job boundary.

### 3.2 RABI for cold-start prior transfer

RABI addresses the cold-start problem by transferring prior signal from similar historical contexts instead of forcing every new context to begin from uninformed priors. In paper terms, RABI should be presented as a prior-initialization mechanism that reduces uncertainty when contextual similarity is meaningful.

The important framing is practical: RABI is how the policy-learning layer avoids behaving as if every new context were entirely unknown. It should be evaluated in the algorithmic track and discussed conservatively in the runtime track.

### 3.3 DAAF for drift-aware memory adaptation

DAAF reduces the influence of stale policy evidence when reward behavior shifts over time. Its role is to prevent the memory state from overcommitting to policies that were previously effective but no longer fit the current context distribution.

This should be described as a drift-aware memory adaptation mechanism, not as a blanket claim of superiority in all runtime settings. In the paper, DAAF belongs primarily in the controlled-evidence track.

### 3.4 Decision context and candidate filtering

AHMN does not operate on arbitrary policy choices. The deployed system filters policy candidates using document-analysis context and policy conditions before adaptive selection. This context-constrained selection is important for practical validity: adaptive advice should not be allowed to recommend semantically incompatible policies merely because of bandit uncertainty.

## 4. Adaptive-Safe Runtime Integration

### 4.1 Canonical runtime path

The canonical operational path is:

`frontend upload -> /api/runs/start -> frontend job runner -> idpo.cli process-inbox -> IDPO_DATA_DIR/runs/<run_id>`

Within IDPO, the processing path remains:

`ingest/inbox -> orchestrator -> executor -> exports`

The paper should stress that the evaluation is tied to this actual runtime and not to a paper-only shortcut.

### 4.2 Runtime modes

The system executes two modes:

- `static`
  - deterministic policy selection
  - no adaptive override
- `adaptive_safe`
  - AHMN may recommend a different policy
  - the recommendation is subject to runtime containment

This comparison is the only runtime comparison that should be treated as canonical in the paper.

### 4.3 Policy advice lifecycle

For each document, the runtime records:

- static baseline policy
- AHMN recommended policy
- final selected policy
- whether the policy changed
- advice acceptance or rejection status
- fallback reason
- rollback state
- defer state

This record is the basis of the runtime claim. If a field is not artifact-backed, it should not carry a major paper claim.

### 4.4 Fallback, rollback, and defer

These mechanisms should be defined precisely:

- **fallback**
  - a recommendation is replaced before or during execution with a safer alternative
- **rollback**
  - a selected policy is blocked or reverted because runtime conditions indicate unacceptable behavior
- **defer**
  - the system records that it should not present a result as sufficiently reliable without further review

Containment events are not proof of success. They are proof that adaptive risk is exposed and constrained rather than hidden.

## 5. Evaluation Method

### 5.1 Research questions

The paper should answer these questions:

1. Does `adaptive_safe` actually change policy selection relative to `static`?
2. Do the AHMN mechanisms provide useful controlled evidence for online selection, cold-start handling, and drift adaptation?
3. When policy changes occur in the runtime, do they improve or degrade labeled extraction outcomes?
4. How often does the runtime contain adaptive risk through fallback, rollback, or defer?
5. What latency tradeoffs accompany adaptive behavior?

### 5.2 Dual-track evidence design

The evidence model is split intentionally.

**Track A: AHMN evidence**

- Thompson Sampling as the online selector
- RABI as the cold-start transfer mechanism
- DAAF as the drift-aware forgetting mechanism
- evidence source:
  - `ahmn_core/experiments`
  - robustness study
  - controlled ablations where available

**Track B: Runtime evidence**

- canonical runtime only
- `static` vs `adaptive_safe`
- frozen config
- frozen mapping
- frozen benchmark pack(s)

The paper must not mix these two evidence tracks into one undifferentiated claims section.

### 5.3 Runtime dataset and mapping

The active labeled runtime evidence uses `CORD v2` receipt subsets with a constrained field mapping:

- `total_amount`
- `cash_amount`
- `change_amount`
- `subtotal_amount`
- `tax_amount`

The mapping should be described as intentionally narrow and exact. This is a strength, not a weakness. It avoids vague correctness claims and keeps the evidence tied to explicit labeled fields.

### 5.4 Runtime metrics

Report these separately:

- exact precision
- exact recall
- exact F1
- validation pass rate
- schema-valid rate
- schema coverage
- latency
- recovery rate
- escalation rate
- policy change count
- advice accepted count
- feedback logged count
- fallback count
- rollback count
- defer count

### 5.5 Reporting rule

Runtime proxy reward must be labeled explicitly as a bandit learning signal. It is not exact correctness and must not be used interchangeably with reviewed exact metrics.

## 6. Results

### 6.1 Track A: AHMN evidence

This subsection should summarize:

- why Thompson Sampling is used as the live selector
- what controlled evidence exists for RABI under cold start
- what controlled evidence exists for DAAF under drift
- what ablations or robustness studies are already available

Use concrete tables and keep the claim narrow:

- AHMN components are motivated and supported by controlled evidence
- they are not all claimed to be equally proven by the runtime benchmark alone

### 6.2 Track B: Runtime evidence

This subsection should report the frozen `static` vs `adaptive_safe` runtime results on the canonical labeled benchmark.

Interpretation rules:

- if adaptive quality gains are small, tied, or mixed, say so directly
- if policy change and containment behavior are strong, state that clearly
- do not infer strong extraction superiority unless frozen evidence supports it

### 6.3 Containment analysis

This subsection should focus on:

- how often advice was accepted
- how often fallback or rollback occurred
- whether defer behavior was exercised
- what this implies about operational safety

This is one of the strongest likely sections of the paper because it aligns directly with the deployed runtime.

### 6.4 Latency analysis

Report average latency and stage-level concentration where available. Be explicit about where cost is concentrated. If extraction dominates runtime, say so. If environment limitations such as OCR engine availability affect measured results, say so.

## 7. Limitations and Threats to Validity

The paper must include these limitations explicitly:

1. The runtime benchmark scope is still narrow and tied to the current labeled receipt mapping.
2. Exact extraction gains may depend on policy store composition and document mix.
3. RABI and DAAF are more strongly evidenced in controlled settings than in the current runtime benchmark alone.
4. OCR engine behavior and model environment materially affect runtime outcomes.
5. Runtime proxy reward is not ground truth and must not be interpreted as exact extraction correctness.

## 8. Conclusion

The conclusion should return to the narrow claim only:

- AHMN is a practical policy-learning layer for document extraction.
- The adaptive-safe runtime makes policy changes auditable and constrained.
- The strongest demonstrated result is operational credibility of adaptation, not universal extraction superiority.

End by stating the next research step:

- strengthen frozen runtime evidence on larger labeled sets
- preserve the same canonical runtime path
- avoid widening the claim before the evidence is stable

## Figures and Tables to Prepare

### Figures

1. Canonical runtime path
2. AHMN decision flow:
   - context
   - candidate filtering
   - Thompson Sampling
   - final policy
   - containment branch
3. Artifact map:
   - run-level
   - document-level

### Tables

1. Contributions summary
2. AHMN mechanism summary:
   - TS
   - RABI
   - DAAF
3. Runtime mode comparison:
   - `static`
   - `adaptive_safe`
4. Frozen benchmark results
5. Limitations / threats summary

## Current Evidence Snapshot

This section is for drafting context only and should be replaced or frozen before submission.

### Runtime facts currently safe to say

- `adaptive_safe` is a real executed mode
- policy changes are observable
- advice acceptance is observable
- feedback logging is observable
- containment is a first-class runtime concept

### Runtime facts currently unsafe to overclaim

- consistent exact F1 superiority across frozen labeled sets
- broad generalization beyond the active document family
- strong end-to-end proof of all AHMN components from runtime evidence alone

### Frozen-result insertion rule

Before final paper freeze:

- use one frozen config
- use one frozen field mapping
- use one frozen benchmark set for final runtime tables
- keep Track A and Track B evidence separated in the manuscript
