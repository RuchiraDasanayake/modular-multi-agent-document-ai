# Paper Lock Checklist

Use this checklist before freezing paper claims.

The paper must fit the system. The system must not be bent into a paper-only branch.

## 1. Canonical Paper Position

Lock these before writing final results:

- paper type:
  - runtime systems paper
- novelty foreground:
  - AHMN first
  - adaptive-safe runtime second
- runtime comparison:
  - `static`
  - `adaptive_safe`
- evidence model:
  - Track A: algorithmic AHMN evidence
  - Track B: canonical runtime evidence

## 2. Canonical Runtime Constraint

Use only this runtime path for Track B:

`frontend upload -> /api/runs/start -> frontend job runner -> idpo.cli process-inbox -> IDPO_DATA_DIR/runs/<run_id>`

Do not use:

- legacy wrappers
- paper-only shortcuts
- alternate runtime branches with different semantics

## 3. Canonical Claim Constraint

Use one narrow core claim:

`AHMN is a practical policy-learning layer for document extraction and is operationalized inside an adaptive-safe runtime where policy changes remain auditable and constrained through fallback, rollback, and defer.`

Do not freeze stronger claims unless the evidence genuinely supports them.

Especially do not freeze:

- universal extraction superiority
- broad generalization across document families
- strong end-to-end proof of RABI and DAAF from runtime evidence alone

## 4. Dual-Track Evidence Lock

### Track A: AHMN evidence

Lock what will be cited for:

- Thompson Sampling
- RABI
- DAAF

Allowed sources:

- `ahmn_core/experiments`
- robustness study outputs
- reproducible ablations

Track A must be explicitly labeled as:

- controlled evidence
- algorithmic evidence

It must not be presented as identical to runtime benchmark evidence.

### Track B: Runtime evidence

Lock all of these:

- one frozen config
- one frozen mapping
- one frozen benchmark set
- one frozen reporting table for final runtime numbers

Track B must use:

- exact labeled metrics
- runtime metrics
- containment metrics

Track B must not treat runtime proxy reward as exact correctness.

## 5. Required Runtime Artifacts

Before final freeze, verify that the runtime artifacts exist and are stable enough to support the paper.

Required run-level artifacts:

- `run.json`
- `run_metadata.json`
- `metrics.json`

Required document-level artifacts:

- `dae/output.json`
- `plan/primary.json`
- `structuring/extracted.json`
- `validation/results.json`
- `decision_chain.json`
- `reward.json`
- `recovery_trace.json`
- `review/results.json` when review exists

## 6. Required Runtime-Visible Evidence

The runtime evidence must support visibility of:

- static baseline policy
- recommended policy
- final selected policy
- whether policy changed
- advice acceptance or rejection
- fallback state and reason
- rollback state
- defer state
- exact extraction outcome where labels exist
- latency and containment behavior

If these cannot be shown from artifacts or canonical UI surfaces, do not make them paper claims.

## 7. Required Verification Before Final Results

Complete all of these before final lock:

1. Run the active labeled evaluation loop defined in `docs/CORD_EVALUATION_PLAN.md`.
2. Verify one live `static` job on the canonical runtime path.
3. Verify one live `adaptive_safe` job on the same path.
4. Verify the runtime artifacts clearly expose policy-change and containment behavior.
5. Regenerate the frozen benchmark evidence bundle for the final runtime result table.
6. Confirm the final paper tables use only frozen evidence.

## 8. Interpretation Rules

When writing results:

- if adaptive quality gains are weak or tied, say so directly
- if containment behavior is strong, say so directly
- if policy change is real but quality superiority is mixed, do not hide that distinction

Allowed interpretation:

- adaptive execution is real
- policy change is observable
- containment is explicit
- exact superiority is conditional or mixed if the evidence says so

Disallowed interpretation:

- proxy reward equals ground-truth correctness
- runtime tie somehow proves strong superiority
- runtime evidence alone fully proves all AHMN subcomponents

## 9. Conference and Dissertation Alignment

Before finalizing writing:

- ensure the conference manuscript and the dissertation-aligned draft share the same core claim
- ensure the dissertation version expands explanation, not claim scope
- ensure both versions cite the same frozen evidence core for runtime results

## 10. Final Lock Condition

The paper is ready to finalize only if all statements below are true:

- the claim does not depend on unproven strong F1 superiority
- Track A and Track B are clearly separated
- one frozen config, mapping, and benchmark set are chosen
- the conference paper fits IEEE-style structure cleanly
- the dissertation-aligned version expands from the same evidence base without changing the claim
