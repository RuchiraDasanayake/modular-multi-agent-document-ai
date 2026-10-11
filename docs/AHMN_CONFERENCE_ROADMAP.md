# Adaptive Extraction Roadmap

This is the working roadmap for turning the current repository into a narrow, defensible, evidence-backed adaptive extraction product.

This is not a paper-first plan.
This is a product-first plan that should also yield a conference paper if executed cleanly.

## Product-first rule

The final target is a client-facing system that is useful, stable, and measurable.

The paper is a progress artifact, not the product goal.

That means:

- do not rebuild the system around a paper narrative
- do not add research theater that does not improve the shipped system
- do not expand AHMN unless a change is a clear and direct win
- prefer fixing, simplifying, removing, and instrumenting current code
- make core claims visible through the actual UI and run artifacts

## Narrow system target

The system we are building and defending is:

- `static`: fixed policy selection path
- `adaptive_safe`: AHMN advice plus IDPO containment through fallback, rollback, and defer

The paper should prove only this:

- `adaptive_safe` is a real executed runtime path
- AHMN advice changes policy selection in measurable cases
- IDPO keeps adaptive execution safe through fallback, rollback, and defer
- adaptive improves extraction quality, structured output quality, or runtime behavior relative to static
- claims stay limited to what the code, UI, and benchmark actually support

Non-goals:

- turning AHMN into a larger research platform
- turning IDPO into a paper-only architecture
- expanding XAI / Guardrails / HITL into the core claim
- inventing new algorithmic machinery just to sound novel

## Ownership rule

IDPO can be changed aggressively.

AHMN should be changed minimally, and only when one of these is true:

- the current implementation is internally inconsistent
- the current implementation weakens the `adaptive_safe` claim
- the change directly improves runtime behavior or evidence quality

If an AHMN change is not an obvious win, do not do it.

## Canonical runtime to keep

Keep exactly one path as canonical:

- `frontend job (POST /api/jobs/<job_id>/documents, then POST /api/jobs/<job_id>/runs) -> frontend job runner -> idpo.cli process-inbox -> idpo.pipeline.inbox -> idpo.pipeline.orchestrator`

Files:

- `frontend/src/server/runner.ts`
- `frontend/src/app/api/jobs/[jobId]/runs/route.ts`
- `frontend/src/app/dashboard/idpo/page.tsx`
- `frontend/src/lib/api.ts`
- `idpo/cli.py`
- `idpo/pipeline/inbox.py`
- `idpo/pipeline/orchestrator.py`

Everything important for the product claim must be visible through this path.

## UI-first evidence rule

Most claims should be demonstrable from the current UI and its generated artifacts.

The UI must make the following visible:

- selected policy
- static policy baseline
- AHMN recommendation
- whether adaptive changed the final policy
- whether advice was accepted or rejected
- fallback reason
- rollback / blocked-policy status
- defer status and reason
- extraction quality and structured output quality
- latency / cost / escalation where relevant

If a claim is not visible in the runtime artifacts or UI, it is weak.

## Current direction

Phase 0 is already the cleanup baseline:

- one canonical runtime
- benchmark-time policy mutation removed
- broken research policy condition fixed
- dead frontend controls removed from the canonical path
- duplicate rollback entry point collapsed
- legacy flows marked non-canonical

The remaining work should now move toward product usefulness and paper defensibility at the same time.

## Phase 1: Make `adaptive_safe` real and visible

Goal:

- ensure `adaptive_safe` is a real runtime mode with auditable behavior, not branding

Primary focus:

- IDPO runtime semantics
- minimal AHMN fixes only where current behavior is misleading or weak
- UI visibility of adaptive decisions

Tasks:

- Ensure `static` and `adaptive_safe` are the only canonical user-facing runtime modes.
- In `idpo/pipeline/policy_advisor.py`, normalize AHMN responses so the runtime can always distinguish:
  - no advice
  - advice accepted
  - advice rejected
  - fallback to static
- In `idpo/pipeline/orchestrator.py`, log per-document:
  - static baseline policy
  - recommended adaptive policy
  - final selected policy
  - whether a policy change happened
  - whether fallback, rollback, or defer happened
- In the run and document pages, surface those fields directly.
- In AHMN, make only the minimum changes needed so the returned advice is coherent and explainable:
  - aggregate by policy id if current selection is still row-based
  - remove misleading branches that suggest behavior not actually used
  - separate seeded from learned contribution in the trace if possible without schema churn
- Keep AHMN deterministic by default if that is the current deployed behavior.
- Do not introduce a new research mode unless the product already needs it.

Files:

- `idpo/pipeline/policy_advisor.py`
- `idpo/pipeline/orchestrator.py`
- `idpo/pipeline/serialization.py`
- `frontend/src/app/dashboard/idpo/runs/[runId]/page.tsx`
- `frontend/src/app/dashboard/idpo/runs/[runId]/docs/[docId]/page.tsx`
- `frontend/src/app/dashboard/idpo/compare/`
- `ahmn_core/main.py`
- `ahmn_core/seeds.py`
- `ahmn_core/services/scheduler.py`

Acceptance criteria:

- `adaptive_safe` appears as a real mode throughout the canonical runtime
- the UI can show when AHMN changed policy selection
- the UI can show when IDPO contained adaptive risk through fallback, rollback, or defer
- no runtime label implies behavior that does not actually happen

## Phase 2: Improve IDPO extraction quality and policy meaning

Goal:

- make IDPO better as a product and make adaptive decisions matter on real extraction outcomes

Primary focus:

- extraction quality
- structured output quality
- policy differences that actually mean something
- removal of heuristic bloat that does not pull its weight

Tasks:

- Clean up `DocumentAnalysisAgent` outputs so routing signals are stable and understandable.
- Stop overloading policies with cosmetic parameter changes.
- Merge policies that do not produce materially different operator behavior.
- Reduce heuristic sprawl in `idpo/agents/llm_extraction.py`:
  - move field- or domain-specific rescue logic into explicit rulesets where justified
  - delete rescue logic that has no measurable effect
- Improve runtime exact-value scoring whenever gold labels exist.
- Add clearer structured-output metrics to runtime artifacts:
  - schema valid
  - grounding coverage
  - missing required count
  - hallucinated field count
  - unresolved field count
- Make extraction failures explainable in product terms:
  - not found
  - conflicting candidates
  - validation rejected
  - recovery failed
  - deferred
  - escalated

Files:

- `idpo/agents/doc_analysis.py`
- `idpo/agents/llm_extraction.py`
- `idpo/agents/validation.py`
- `idpo/agents/recovery.py`
- `idpo/agents/escalation.py`
- `idpo/pipeline/planning.py`
- `idpo/pipeline/executor.py`
- `idpo/pipeline/orchestrator.py`
- `configs/policy_store_research.json`

Acceptance criteria:

- extraction quality improves in a way visible to the client-facing system
- policy differences correspond to actual operator differences
- run artifacts make extraction success and failure legible
- adaptive policy changes are capable of affecting extraction outcomes in measurable ways

## Phase 3: Tighten AHMN only where it clearly helps

Goal:

- keep AHMN small, coherent, and useful to the product

Primary focus:

- remove weak or misleading behavior
- keep the minimum mechanism that strengthens `adaptive_safe`

Tasks:

- Clean `ahmn_core/main.py` so serving behavior matches what IDPO actually uses.
- Keep deterministic advice as the default if exploratory behavior is not essential to the product.
- Fix obvious inconsistencies:
  - row-level vs policy-level advice semantics
  - stale seed comments and mismatched ids
  - scheduler default-id mismatches
  - reward logging that silently mixes weak proxy signals with stronger exact signals
- Keep or remove forgetting logic based on whether it is actually wired into live behavior.
- Remove or demote unused experiment-only or demo-only abstractions from the claimed path.

Files:

- `ahmn_core/main.py`
- `ahmn_core/seeds.py`
- `ahmn_core/services/rabi.py`
- `ahmn_core/services/drift_forgetting.py`
- `ahmn_core/services/scheduler.py`
- `idpo/pipeline/policy_advisor.py`
- `idpo/pipeline/orchestrator.py`

Acceptance criteria:

- AHMN advice semantics are coherent
- the current implementation is easier to explain honestly
- AHMN changes remain minimal and directly useful
- no major product claim depends on hidden or dead AHMN behavior

## Phase 4: Benchmark the shipped system, not a paper toy

Goal:

- evaluate the exact product path the UI exposes

Primary focus:

- static vs adaptive_safe
- outcome metrics that matter to both client and paper

Tasks:

- Keep benchmark evaluation tied to the canonical runtime and config.
- Compare only:
  - `static`
  - `adaptive_safe`
- Report:
  - exact precision / recall / F1 where labels exist
  - schema valid rate
  - grounding coverage
  - hallucinated field count
  - unresolved / deferred field count
  - latency
  - cost
  - escalation rate
  - fallback rate
  - rollback / blocked-policy rate
  - policy change rate
- Add subgroup reporting for:
  - document type
  - route bin
  - policy transition type
  - seen vs less-seen regimes if the data supports it
- Ensure the benchmark page renders all major claim surfaces directly.

Files:

- `scripts/run_idpo_benchmark.py`
- `idpo/benchmark/benchmark_pack.json`
- `frontend/src/app/dashboard/idpo/benchmark/`
- `frontend/src/app/dashboard/idpo/compare/`
- `frontend/src/server/benchmarks.ts`

Acceptance criteria:

- benchmark results correspond to the shipped UI/runtime path
- adaptive_safe can be defended relative to static using visible metrics
- evidence is product-useful, not just paper-useful

## Phase 5: Product finalization with paper freeze discipline

Goal:

- finalize the client-facing system without breaking the paper story

Primary focus:

- polish, reliability, presentation, and freeze discipline

Tasks:

- Finalize run pages and comparison views for client review.
- Clean wording so labels reflect real behavior.
- Freeze runtime labels:
  - `static`
  - `adaptive_safe`
- Freeze benchmark semantics before writing the paper.
- Avoid late architectural changes that would invalidate collected evidence.
- Treat the paper as a constrained description of the finalized system state, not as a reason to rebuild anything.

Files:

- `frontend/src/app/dashboard/idpo/`
- `frontend/src/server/artifacts.ts`
- `frontend/src/types/idpo.ts`
- `frontend/src/types/index.ts`
- `docs/PAPER_LOCK_CHECKLIST.md`

Acceptance criteria:

- the client-facing system is coherent and demoable
- the evidence trail remains valid
- the paper can be written from the finalized product path without system rebuild

## What to remove aggressively

Remove, merge, or sideline anything that adds explanation cost without product or evidence value:

- dead runtime controls
- policies with cosmetic differences only
- duplicate rollback logic
- stale benchmark assumptions
- research-only branches not reflected in the shipped runtime
- AHMN abstractions that are not part of the actual adaptive_safe path

## Final paper position

If this roadmap is executed, the paper should be positioned as:

- a narrow adaptive extraction systems paper
- centered on `adaptive_safe`
- with modest claims about AHMN-driven policy adaptation
- and stronger claims about the usefulness of combining adaptive advice with runtime containment

The final claim should remain limited to:

`AHMN can change policy selection in measurable cases, and IDPO makes that adaptation safe enough to be useful in a real extraction product.`
