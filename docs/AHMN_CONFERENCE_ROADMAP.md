# AHMN Conference Roadmap

This document is the execution plan for getting the repository from its current state to a conference-paper-level system with AHMN as the real contribution and IDPO as the controlled extraction surface.

Current status:

- The codebase is not paper-ready.
- AHMN is the only component with any plausible algorithmic core.
- IDPO is mostly a heuristic extraction system with policy-flavored configuration.
- The repository still contains dead paths, stale assumptions, and paper-risky inconsistencies.

The plan below is not a wishlist. It is the minimum path to something defensible.

## Paper target

Target paper type:

- AHMN-focused systems paper with controlled IDPO integration

Target claim:

- AHMN improves top-1 policy selection for document extraction under vendor/layout shift compared with static routing and simpler adaptive baselines, while IDPO provides a stable execution environment for measuring extraction quality, latency, and cost.

Non-claims:

- IDPO itself is not the novel algorithm.
- Policy JSONs are not research contributions.
- Large heuristic code volume is not evidence of novelty.
- XAI / Guardrails / HITL are not part of the core claim unless they are made part of the actual canonical runtime and evaluated separately.

## Canonical runtime to keep

Keep exactly one runtime path as the research path:

- `frontend -> /api/runs/start -> frontend job runner -> idpo.cli process-inbox -> idpo.pipeline.inbox -> idpo.pipeline.orchestrator`

Files:

- `frontend/src/server/runner.ts`
- `idpo/cli.py`
- `idpo/pipeline/inbox.py`
- `idpo/pipeline/orchestrator.py`

Everything else is either removed, deprecated harder, or moved out of the paper path.

## Phase 0: Stop the damage

Goal:

- Eliminate features and claims that actively poison correctness, reproducibility, or paper framing.

Tasks:

- Remove benchmark-time policy rewriting from `idpo/pipeline/inbox.py`.
- Remove or hard-disable no-op controls currently exposed by the frontend:
  - `ahmn.policy_override_id`
  - `routing.force_route_bin`
  - `IDPO_SKIP_GUARDRAILS`
  - `IDPO_SKIP_XAI`
- Validate every condition key in `configs/policy_store_research.json` against actual DAE outputs.
- Fix the broken `long_document_chunked` policy conditions.
- Decide on one rollback implementation and delete the duplicate one.
- Mark `idpo/ui/app.py:/idpo/run` and `idpo/integration.py` as non-canonical for paper work, or remove them from the active path entirely.
- Remove stale or duplicate research scripts such as `temp_check.py`.

Files:

- `idpo/pipeline/inbox.py`
- `frontend/src/server/runner.ts`
- `idpo/core/config.py`
- `configs/policy_store_research.json`
- `idpo/pipeline/policy_safety.py`
- `idpo/ui/app.py`
- `idpo/integration.py`
- `temp_check.py`

Acceptance criteria:

- There is one research runtime.
- No UI control exists without backend effect.
- Every research policy can actually match live runtime outputs.
- The benchmark does not mutate policy semantics at execution time.

## Phase 1: Make AHMN real

Goal:

- Turn AHMN from a deterministic retrieval wrapper into a clean, measurable adaptive policy selector.

Tasks:

- Redesign policy selection in `ahmn_core/main.py` so the decision is over policy arms, not raw retrieved rows.
- Make exploration explicit and real. Do not hide it behind an unused `?explore=true` path.
- Separate three modes:
  - offline evaluation mode
  - online deterministic serving mode
  - online exploratory serving mode
- Log the full candidate set per advice:
  - candidate policy ids
  - per-policy prior
  - per-policy score
  - retrieval neighbors
  - whether seeds were involved
- Split seeded priors from learned memory in storage and reporting.
- Redesign reward logging so AHMN learns from exact extraction quality, not field-presence proxies.
- Replace ad hoc reward shaping with a versioned reward contract:
  - exact field-value F1
  - schema validity
  - hallucination count
  - grounding coverage
  - latency
  - cost
  - defer / escalation outcome
- Make scheduler promotion/forgetting context-safe:
  - no policy-id-only context reconstruction
  - no `default_policy` vs `default` mismatch
  - promotion and forgetting must use the same context schema as advice serving

Files:

- `ahmn_core/main.py`
- `ahmn_core/services/rabi.py`
- `ahmn_core/services/drift_forgetting.py`
- `ahmn_core/services/scheduler.py`
- `ahmn_core/services/embedding.py`
- `ahmn_core/seeds.py`
- `scripts/init.sql`

Acceptance criteria:

- AHMN selection logic matches the method claimed in the paper draft.
- Advice serving, feedback logging, promotion, and forgetting share one context schema.
- Seeded and learned performance can be reported separately.
- Candidate-level traces can explain every adaptive decision.

## Phase 2: Clean up the AHMN research contribution

Goal:

- Reduce the contribution to something small, precise, and defensible.

Tasks:

- Decide whether the actual contribution is:
  - RABI only
  - RABI + drift-aware forgetting
  - or full memory hierarchy
- Delete contribution theater:
  - classes not used in the live runtime
  - service descriptions that overstate behavior
  - stale seed comments that reference the wrong policy set
- Version the context encoder and store the version with each memory entry.
- Add ablations for:
  - no retrieval
  - retrieval without transfer
  - transfer without forgetting
  - forgetting without transfer
  - full AHMN
- Add negative controls:
  - static first-match
  - random policy
  - nearest-neighbor vote without Beta updating
  - plain Thompson Sampling with flat priors

Files:

- `ahmn_core/main.py`
- `ahmn_core/services/rabi.py`
- `ahmn_core/services/drift_forgetting.py`
- `ahmn_core/experiments/run_experiments.py`
- `ahmn_core/experiments/synthetic_data.py`
- `ahmn_core/seeds.py`

Acceptance criteria:

- The claimed algorithm and the deployed algorithm are the same thing.
- Every named AHMN mechanism has an ablation.
- The paper contribution can be stated in three bullets without lying.

## Phase 3: Make IDPO a valid evaluation surface

Goal:

- IDPO needs to be stable, measurable, and less noisy. It does not need to pretend to be the novelty.

Tasks:

- Refactor `DocumentAnalysisAgent` so DAE outputs are well-defined and validated:
  - stop inferring `vendor_cluster` from filename prefixes when possible
  - separate observed metadata from inferred metadata
  - emit uncertainty and source tags for each inferred field
- Split extraction into explicit modules:
  - heuristic extractor
  - LLM extractor
  - rescue heuristics
  - validation
  - recovery
- Benchmark those modules independently.
- Reduce heuristic sprawl in `idpo/agents/llm_extraction.py` by moving domain-specific rescue logic into explicit rulesets or deleting it.
- Make policies simpler and more meaningful:
  - each policy should correspond to a genuinely different operator profile
  - if two policies only tweak minor constants, merge them
- Replace field-presence reward in IDPO with exact-value evaluation when gold labels exist.
- Add structured failure reasons to extraction output:
  - not found
  - conflicting candidates
  - low confidence
  - validation rejected
  - recovery failed
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

- Every major extraction stage can be evaluated independently.
- DAE outputs are schema-validated.
- Policy differences are material, not cosmetic.
- Gold-label runs use exact-value scoring inside the runtime.

## Phase 4: Remove unnecessary code and abstractions

Goal:

- Shrink the paper-facing surface area so the system becomes understandable.

Remove or isolate:

- legacy direct-run flow in `idpo/ui/app.py`
- cross-service integration code not used by the canonical runtime in `idpo/integration.py`
- duplicate rollback implementation in `idpo/pipeline/policy_safety.py` or the inline orchestrator monitor
- dead config fields not honored by runtime
- unused experiment duplicates and stale demo artifacts

Simplify:

- `PolicyAdvisor` to one responsibility: call AHMN and normalize advice
- `PlanRouter` to one responsibility: choose policy and build plan
- reward logic so there is one scoring contract for runtime and research
- benchmark reporting so exact metrics and proxy metrics cannot be confused

Files:

- `idpo/ui/app.py`
- `idpo/integration.py`
- `idpo/pipeline/policy_safety.py`
- `idpo/pipeline/policy_advisor.py`
- `idpo/pipeline/planning.py`
- `idpo/pipeline/orchestrator.py`
- `scripts/run_idpo_benchmark.py`

Acceptance criteria:

- The paper-facing runtime can be explained in one page.
- There is no duplicate safety or routing logic.
- Runtime metrics and paper metrics use the same definitions.

## Phase 5: Build a real evaluation setup

Goal:

- Stop relying on toy internal regression cases and disconnected synthetic simulations.

Tasks:

- Create a real benchmark corpus with:
  - held-out vendors
  - held-out layouts
  - OCR noise variation
  - long-document cases
  - mixed-content cases
  - time-sliced drift scenarios
- Separate:
  - development set
  - validation set
  - final test set
- Store exact gold labels per field and document.
- Add experiment configs for:
  - static
  - adaptive without seeds
  - adaptive with seeds
  - adaptive with retrieval only
  - adaptive with RABI only
  - adaptive with DAAF only
  - full adaptive
- Add paired significance testing.
- Add cost and latency reporting.
- Add robustness tests:
  - OCR corruption
  - field synonym shifts
  - unseen vendors
  - missing metadata
  - layout perturbations

Files:

- `idpo/benchmark/benchmark_pack.json`
- `idpo/benchmark/data/*`
- `scripts/run_idpo_benchmark.py`
- new evaluation scripts under `scripts/` or `idpo/evaluation/`

Acceptance criteria:

- The benchmark is large enough to support subgroup analysis.
- Exact-value metrics are first-class.
- Simpler baselines are included.
- Statistical confidence is computed on meaningful sample sizes.

## Phase 6: Replace fake experiments with credible ones

Goal:

- Synthetic experiments can remain as sanity checks, but they cannot carry the paper.

Tasks:

- Keep synthetic AHMN experiments only as controlled mechanism tests.
- Make their policy/action space match the real runtime policy space if they stay.
- Add live-runtime replay experiments driven by recorded IDPO runs.
- Add offline counterfactual evaluation where possible using logged candidate scores and gold labels.
- Report synthetic and real-runtime results separately.

Files:

- `ahmn_core/experiments/run_experiments.py`
- `ahmn_core/experiments/synthetic_data.py`
- new replay / offline evaluation tooling

Acceptance criteria:

- No paper table mixes synthetic and live-runtime evidence without explicit labeling.
- The main claims are supported by real document extraction experiments.

## Phase 7: Reproducibility lock

Goal:

- Make it possible for another group to rerun the paper without reverse engineering the repo.

Tasks:

- Create one top-level reproducible environment spec for the paper run.
- Pin model versions:
  - embedding model
  - OCR engine
  - local LLM
  - cloud LLM API version and model
- Snapshot policy files and config files used for each result table.
- Store dataset hashes, run ids, and code commit hashes with every result bundle.
- Add one-command scripts for:
  - seed/reset
  - benchmark run
  - live replay
  - table generation
- Remove silent environment-dependent behavior where possible.

Files:

- `pyproject.toml`
- `idpo/requirements.txt`
- `ahmn_core/requirements.txt`
- `docker-compose.yml`
- `scripts/*`

Acceptance criteria:

- A paper result bundle can be reproduced from a tagged commit.
- Every table and figure maps to a concrete config and artifact bundle.

## Phase 8: Paper package

Goal:

- Only start writing after the system and evidence are stable.

Required paper figures:

- canonical runtime diagram
- AHMN memory / update diagram
- policy-selection ablation chart
- exact-value extraction results table
- latency/cost tradeoff plot
- robustness table by subgroup
- error taxonomy

Required paper tables:

- baseline comparison
- AHMN ablations
- IDPO extraction ablations
- seed vs no-seed
- seen-vendor vs unseen-vendor
- drift adaptation results

Required appendices:

- configuration schema
- policy definitions
- reward contract
- dataset statistics
- failure analysis examples

Start writing only when:

- the contribution is stable
- the runtime path is frozen
- evaluation scripts are frozen
- benchmark data is frozen
- result tables no longer depend on manual interpretation

## Priority order

Do this in order:

1. Phase 0
2. Phase 1
3. Phase 3
4. Phase 5
5. Phase 2
6. Phase 6
7. Phase 7
8. Phase 8

Reason:

- There is no point polishing the contribution story before the runtime is correct.
- There is no point expanding the benchmark before the adaptive mechanism and extraction metrics are valid.
- There is no point writing a paper before the evidence chain is frozen.

## What to keep

- AHMN memory retrieval concept
- RABI-style prior transfer as the likely contribution kernel
- IDPO artifact and provenance generation
- static vs adaptive comparison framework
- benchmark/reporting infrastructure after metric cleanup

## What to remove

- dead runtime branches
- fake UI controls
- duplicate safety logic
- stale seed comments and mismatched policy references
- benchmark-time policy mutation
- paper claims that exceed live runtime behavior

## Minimum bar before submission

The minimum conference-ready bar is:

- one canonical runtime
- one exact contribution definition
- one clean reward contract
- one real benchmark with exact labels
- strong simpler-method baselines
- full AHMN ablations
- explicit seeded vs learned comparisons
- exact-value extraction improvements, not proxy-only improvements
- latency and cost reporting
- reproducible scripts and pinned configs

Anything short of that is still a prototype.
