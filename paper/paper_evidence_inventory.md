# Paper Evidence Inventory

Last updated: April 26, 2026

Surface classification: `research_evidence`
Primary action: `simplify`

## Purpose

This file is the cleaned paper-support inventory for the current repo state.

It is not a manuscript draft.
It is the working evidence map for:

- what the system actually is
- how the extraction path evolved
- which code paths implement the methods
- which benchmark runs are usable
- what the wins, losses, and current risks are

Use this file before writing or updating:

- [paper/PAPER_LOG.md](./PAPER_LOG.md)
- [paper/evidence_table.md](./evidence_table.md)
- [docs/PAPER_DRAFT.md](../docs/PAPER_DRAFT.md)
- [docs/PAPER_LONGFORM_DRAFT.md](../docs/PAPER_LONGFORM_DRAFT.md)

## Narrow Claim To Defend

The repo direction and paper draft are aligned on a narrow claim, not a broad superiority claim:

`AHMN is a practical policy-learning layer for document extraction and is operationalized inside an adaptive-safe runtime where policy changes remain auditable and constrained through fallback, rollback, and defer.`

Current repo documents do **not** support a safe claim of:

- universal extraction superiority over all available systems
- broad superiority across document families
- runtime proof that RABI and DAAF improve labeled extraction quality end to end

Relevant docs:

- [docs/PROJECT_DIRECTION.md](../docs/PROJECT_DIRECTION.md)
- [docs/SYSTEM_CONTRACT.md](../docs/SYSTEM_CONTRACT.md)
- [docs/PAPER_LOCK_CHECKLIST.md](../docs/PAPER_LOCK_CHECKLIST.md)

## Canonical Runtime And Evidence Path

Canonical runtime path:

`frontend upload -> /api/runs/start -> job runner -> idpo.cli process-inbox -> IDPO_DATA_DIR/runs/<run_id>`

Canonical internal path:

`ingest/inbox -> orchestrator -> executor -> exports`

Core runtime code:

- [idpo/pipeline/inbox.py](../idpo/pipeline/inbox.py)
- [idpo/pipeline/orchestrator.py](../idpo/pipeline/orchestrator.py)
- [idpo/pipeline/executor.py](../idpo/pipeline/executor.py)
- [idpo/pipeline/planning.py](../idpo/pipeline/planning.py)

Benchmark/evidence code:

- [scripts/run_idpo_benchmark.py](../scripts/run_idpo_benchmark.py)

Current benchmark artifacts live outside the repo under:

- `E:\Research Project\Code\idpo-data\runs\benchmarks\benchmark_*`

## Method And Code Map

### 1. Document analysis and routing context

Primary file:

- [idpo/agents/doc_analysis.py](../idpo/agents/doc_analysis.py)

What it emits:

- `doc_type`
- `vendor_cluster`
- `quality_bin`
- `complexity_bin`
- `content_profile`
- `route_bin`
- `layout_cluster_id`
- `quality_features`
- `structural_features`
- `analysis_confidence`
- `semantic_doc_type`

Important correction:

- `semantic_doc_type` is implemented in `DocumentAnalysisAgent` and passed into `DAEOutput` for in-memory routing.
- Historical benchmark bundles were misleading because downstream serialization dropped the field from `PipelineResult`, doc records, and `dae/output.json`.
- Current branch fixes that persistence path. Older notes saying it was never implemented are wrong; notes saying older artifact bundles omitted it are correct.

### 2. Adaptive advice path

Primary files:

- [idpo/pipeline/policy_advisor.py](../idpo/pipeline/policy_advisor.py)
- [ahmn_core/direct_advisor.py](../ahmn_core/direct_advisor.py)

What happens:

- IDPO builds a context payload from `DAEOutput`
- AHMN direct advisor computes candidate policies
- Thompson Sampling chooses the policy
- specialist policies are protected from generic quality policies when a specialist matches
- job/run-scoped posterior state is persisted under `idpo-data/ahmn/direct_advisor`

### 3. AHMN algorithms

Thompson Sampling:

- live selection in [ahmn_core/direct_advisor.py](../ahmn_core/direct_advisor.py)
- tested in [ahmn_core/tests/test_algorithms.py](../ahmn_core/tests/test_algorithms.py)

RABI cold-start transfer:

- [ahmn_core/services/rabi.py](../ahmn_core/services/rabi.py)

Key implemented formula:

- `alpha_init = 1 + Σ w_i (alpha_i - 1)`
- `beta_init = 1 + Σ w_i (beta_i - 1)`
- weights from temperature-controlled softmax over similarity

DAAF drift-aware forgetting:

- [ahmn_core/services/drift_forgetting.py](../ahmn_core/services/drift_forgetting.py)

Key implemented formula:

- `gamma* = sqrt(Delta^2 / ln(t))`

Important paper discipline:

- RABI and DAAF are implemented and unit-tested.
- The runtime benchmark evidence does not by itself prove their benefit on labeled extraction.
- Treat them as Track A controlled algorithm evidence unless and until runtime ablations are frozen.

### 4. Extraction stack

Primary files:

- [idpo/agents/llm_extraction.py](../idpo/agents/llm_extraction.py)
- [idpo/agents/extraction_prompts.py](../idpo/agents/extraction_prompts.py)
- [idpo/agents/extraction_parsing.py](../idpo/agents/extraction_parsing.py)
- [idpo/agents/extraction_heuristics.py](../idpo/agents/extraction_heuristics.py)
- [idpo/agents/extraction_generic_kv.py](../idpo/agents/extraction_generic_kv.py)

Implemented behavior worth citing:

- local-first extraction
- explicit requested fields
- per-field extraction mode
- cloud fallback paths exist but are disabled in the research config by default
- parser drops missing-style values such as `N/A` / `not found`
- explicit-field extraction suppresses unrelated generic outputs

Tests:

- [idpo/tests/test_extraction_enhancements.py](../idpo/tests/test_extraction_enhancements.py)

### 5. OCR and preprocessing

Primary files:

- [idpo/agents/preprocess.py](../idpo/agents/preprocess.py)
- [idpo/tests/test_pipeline_tuning_upgrades.py](../idpo/tests/test_pipeline_tuning_upgrades.py)

Research-relevant points already captured in repo notes:

- PaddleOCR is the primary OCR path
- retry settings, DPI escalation, deskew, and denoise are part of the current runtime
- scanned-document pipelines place cleanup before OCR

### 6. Validation, recovery, reward, and containment

Primary files:

- [idpo/agents/validation.py](../idpo/agents/validation.py)
- [idpo/agents/recovery.py](../idpo/agents/recovery.py)
- [idpo/pipeline/reward.py](../idpo/pipeline/reward.py)
- [idpo/pipeline/policy_safety.py](../idpo/pipeline/policy_safety.py)

Research-relevant points:

- reward now prioritizes policy-declared fields over canonical doc-type fields
- schema coverage and grounding are tracked separately
- runtime proxy reward is not exact correctness
- defer/fallback/rollback are part of the adaptive-safe story

## Evolution History

This is the concise implementation history that matters for the paper.

### Phase 1: Broad system framing

The repo started with a broad multi-service story:

- AHMN
- Guardrails
- XAI/HITL
- IDPO orchestration

This framing is still true architecturally, but the paper direction narrowed later because it was too easy to over-claim from a complex system.

Relevant docs:

- [README.md](../README.md)
- [docs/SYSTEM_FLOW.md](../docs/SYSTEM_FLOW.md)

### Phase 2: Claim narrowing to `static` vs `adaptive_safe`

The project direction was tightened to:

- external labeled evaluation first
- one canonical runtime path
- one narrow paper comparison
- exact labeled metrics separated from runtime proxy reward

Relevant docs:

- [docs/PROJECT_DIRECTION.md](../docs/PROJECT_DIRECTION.md)
- [docs/CORD_EVALUATION_PLAN.md](../docs/CORD_EVALUATION_PLAN.md)
- [docs/PAPER_DRAFT.md](../docs/PAPER_DRAFT.md)

### Phase 3: Specialist policy path added for receipts and correspondence

Research policies now include:

- `receipt_specialist`
- `correspondence_specialist`
- `default`
- generic quality-based policies

Policy store:

- [configs/policy_store_research.json](../configs/policy_store_research.json)

Important behavior:

- policy conditions can match on `vendor_cluster` or `semantic_doc_type`
- direct advisor applies OR logic across identity keys
- specialists suppress competition from generic quality policies when active

### Phase 4: Field-exact scoring and normalization cleanup

Important fixes reflected in code and notes:

- reward bug fixed so policy-declared requested fields take precedence
- numeric normalization improved for currency prefix and leading dot cases
- grounding/schema coverage matching fixed

Primary code:

- [idpo/pipeline/reward.py](../idpo/pipeline/reward.py)
- [scripts/run_idpo_benchmark.py](../scripts/run_idpo_benchmark.py)

### Phase 5: CORD-first evaluation loop

The active evidence loop moved to:

- internal regression pack for smoke tests
- `CORD v2` as the main labeled external dataset
- small exact field mapping first

Relevant docs:

- [docs/DATASET_PLAN.md](../docs/DATASET_PLAN.md)
- [docs/CORD_EVALUATION_PLAN.md](../docs/CORD_EVALUATION_PLAN.md)

## Benchmark History

These runs matter because they are directly referenced in current paper notes.

### Usable historical runs from April 25, 2026

| Benchmark | n | Main reading |
| --- | ---: | --- |
| `benchmark_1777122866` | 10 | CORD-only batch, exact F1 `0.8235` for both modes |
| `benchmark_1777136712` | 50 | Mixed batch, exact F1 `0.4615` for both modes, adaptive changed policy on all 50 docs |
| `benchmark_1777137905` | 20 | Mixed batch after reward-fix era, static `0.5094`, adaptive `0.5047`, adaptive changed policy on all 20 docs |

Source tables:

- `E:\Research Project\Code\idpo-data\runs\benchmarks\benchmark_1777122866\paper_table.md`
- `E:\Research Project\Code\idpo-data\runs\benchmarks\benchmark_1777136712\paper_table.md`
- `E:\Research Project\Code\idpo-data\runs\benchmarks\benchmark_1777137905\paper_table.md`

### Why these runs matter

`benchmark_1777122866`:

- useful as receipt-only evidence
- strong exact extraction on a small set
- does **not** show adaptive lift because both conditions stayed on `default`

`benchmark_1777136712`:

- useful to show adaptive execution is real
- adaptive selected specialists: `receipt_specialist` on 23 docs and `correspondence_specialist` on 11 docs
- exact F1 remained tied at `0.4615`

`benchmark_1777137905`:

- useful because both branches are non-empty and scored
- static stayed on `default`
- adaptive used specialists on 17 of 20 docs
- exact F1 was slightly worse for adaptive: `0.5094` static vs `0.5047` adaptive

This run is important because it blocks any honest claim of stable exact superiority.

### Unusable latest runs from April 26, 2026

Runs:

- `benchmark_1777140191`
- `benchmark_1777140236`
- `benchmark_1777140434`
- `benchmark_1777140702`
- `benchmark_1777140984`

Problem:

- static metrics are all zero
- static policy distribution is empty
- adaptive still has populated metrics

Example from `benchmark_1777140984`:

- static exact F1 `0.0`
- adaptive exact F1 `0.486`

This is not publishable evidence. It looks like a reporting or execution defect in the static branch for those runs.

Rule for the paper:

- do not cite the April 26 runs as performance evidence until the static-zero defect is explained and re-run

## What Is Actually Supported Today

### Strongly supported

1. Adaptive-safe execution is real.
2. Policy changes are real and artifact-backed.
3. The runtime writes useful evidence bundles.
4. Specialist policies exist and are selected under adaptive runs.
5. The extraction system can achieve competitive zero-shot receipt extraction on at least some CORD subsets.
6. The paper must separate exact correctness from runtime proxy reward.

### Mixed or weak

1. Exact superiority of `adaptive_safe` over `static`.
2. Runtime evidence for RABI and DAAF benefit.
3. Broad cross-domain extraction claims beyond the current narrow receipt-first evaluation.
4. Comparison against commercial tools unless the paper frames it as a capability-gap argument rather than a head-to-head metric claim.

### Not currently safe to claim

1. "We are better than available systems" as a general statement.
2. "Adaptive routing clearly improves extraction accuracy" as a stable result.
3. "All latest benchmarks support the claim" because the April 26 bundles are currently broken for static.

## Wins

### Win 1: The story is narrower and better

The project moved from a vague broad system story to:

- one canonical runtime
- one narrow comparison
- one labeled external dataset path
- one paper lock discipline

That is a major improvement for publication quality.

### Win 2: Adaptive behavior is visible

From usable April 25 benchmark bundles:

- adaptive advice is accepted
- policy change counts are non-zero and often large
- specialists appear only in adaptive runs
- feedback logging is active for adaptive runs

### Win 3: Code and tests support the methods section

There is enough implementation evidence to write precise methodology sections for:

- DAE context generation
- Thompson Sampling policy selection
- RABI prior transfer
- DAAF drift-aware forgetting
- local-first extraction
- requested-field scoring
- containment and review logic

### Win 4: Receipt extraction looks genuinely promising

`benchmark_1777122866` gives a small but strong receipt-only result:

- exact precision `0.8235`
- exact recall `0.8235`
- exact F1 `0.8235`

This is useful evidence for the receipt-first claim, as long as it is not inflated into a universal claim.

## Losses And Risks

### Loss 1: No stable adaptive quality lift yet

The most honest usable mixed evidence says:

- `benchmark_1777136712`: tie
- `benchmark_1777137905`: slight adaptive loss

That means the paper cannot honestly center on "adaptive beats static on exact F1" today.

### Loss 2: Old notes were partially stale

Examples:

- some old notes said `semantic_doc_type` was not persisted
- root cause was a serialization gap, not a missing classifier
- paper-support files must stay aligned to the frozen diverse rerun `benchmark_1777174546`
- some later benchmark bundles are invalid but would look impressive if read carelessly

### Loss 3: Benchmark freeze discipline matters

Adaptive-only bundles intentionally have empty static columns. They are admissible only when:

- the paper framing is zero-shot IDPO vs ETL/IDP capability gap, not static-vs-adaptive lift
- the pack is curated
- the exact scorer is frozen against final validated normalized fields

The clean diverse benchmark now satisfying those rules is `benchmark_1777174546`.

### Loss 4: Commercial comparison still needs discipline

The strongest defensible comparison to ABBYY/Kofax/UiPath-style systems is a capability-gap framing:

- template-dependent systems require per-layout setup
- this runtime is zero-shot and policy-adaptive

Do not claim numeric superiority over those systems unless you have a matched benchmark protocol.

## Frozen Protocol

This is the admissibility contract for the paper evidence set.

### Global rules

- Permanent frontend job: `idpo_research_permanent_01`
- Branch: `feature/IDPO`
- Primary paper benchmark mode: `--adaptive-only`
- Reward semantics: score only against pack-declared expected fields; canonical doc-type fields are fallback only
- Exact scoring semantics: use final validated normalized fields, not raw `structured_fields`

### Admissible primary evidence

- CORD headline evidence already frozen in the paper log: `75` unseen receipts, exact F1 `0.763`
- Clean diverse cross-document evidence: `benchmark_1777174546`
  - pack: `datasets/research_batch_diverse_clean_20.json`
  - docs: `20`
  - exact precision: `0.6111`
  - exact recall: `0.5238`
  - exact F1: `0.5641`
  - validation pass rate: `0.90`
  - grounding coverage: `0.975`

### Excluded from primary claims

- `benchmark_1777140984`: raw diverse pack with bad DocVQA mappings
- `benchmark_1777144685`: superseded clean diverse run before the exact-scoring fix
- FUNSD training-heavy runs with empty or garbage targets
- any benchmark used to argue a strong static-vs-adaptive exact-F1 lift

## Current Position

As of April 26, 2026:

- the codebase supports a strong methodology section
- the codebase supports a strong adaptive-safe runtime claim
- the codebase supports a cautious zero-shot receipt extraction claim
- the codebase does **not** yet support a strong exact-superiority claim for adaptive-safe over static

The best current paper shape is:

1. AHMN as the policy-learning layer
2. IDPO as the adaptive-safe runtime
3. Track A for algorithms
4. Track B for runtime evidence
5. explicit statement that adaptive execution is real, but exact gains are mixed so far

## Immediate Paper Tasks

1. Keep [paper/PAPER_LOG.md](./PAPER_LOG.md) and [paper/evidence_table.md](./evidence_table.md) aligned to the frozen diverse rerun `benchmark_1777174546`.
2. Keep the commercial comparison as capability-gap language unless matched evidence exists.
3. Write the methods section from code, not from memory.
4. If semantic routing needs to be discussed empirically, rerun a small post-fix smoke benchmark and inspect persisted `semantic_doc_type` directly.
5. Keep FUNSD training-heavy runs out of the primary quantitative narrative.

## Minimum Citation Set For Writing

Methodology and runtime:

- [docs/PROJECT_DIRECTION.md](../docs/PROJECT_DIRECTION.md)
- [docs/SYSTEM_CONTRACT.md](../docs/SYSTEM_CONTRACT.md)
- [docs/CORD_EVALUATION_PLAN.md](../docs/CORD_EVALUATION_PLAN.md)
- [idpo/agents/doc_analysis.py](../idpo/agents/doc_analysis.py)
- [idpo/pipeline/policy_advisor.py](../idpo/pipeline/policy_advisor.py)
- [idpo/pipeline/reward.py](../idpo/pipeline/reward.py)
- [scripts/run_idpo_benchmark.py](../scripts/run_idpo_benchmark.py)
- [configs/idpo_research_config.json](../configs/idpo_research_config.json)
- [configs/policy_store_research.json](../configs/policy_store_research.json)

Algorithm track:

- [ahmn_core/direct_advisor.py](../ahmn_core/direct_advisor.py)
- [ahmn_core/services/rabi.py](../ahmn_core/services/rabi.py)
- [ahmn_core/services/drift_forgetting.py](../ahmn_core/services/drift_forgetting.py)
- [ahmn_core/tests/test_algorithms.py](../ahmn_core/tests/test_algorithms.py)

## Acceptance Check

This file is correct enough to use if a teammate can answer all of these without re-reading the whole repo:

1. What exactly is the paper claiming?
2. Which code files implement the claim?
3. Which benchmark runs are usable?
4. What did we win?
5. What did we lose?
6. What is the single next evidence task?
