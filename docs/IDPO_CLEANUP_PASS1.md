# IDPO Cleanup Pass 1

This document defines the first strict cleanup pass for `idpo/`.

The goal is not to add features. The goal is to reduce ambiguity, split mixed responsibilities, and establish a smaller stable runtime that the team can reason about before making new changes.

This plan is subordinate to:

1. `docs/PROJECT_DIRECTION.md`
2. `docs/SYSTEM_CONTRACT.md`

If the project phase or system contract changes, update those documents first and then refresh this plan.

## Cleanup Objective

Keep the canonical runtime path small and explicit:

`ingest/inbox -> orchestrator -> executor -> exports`

For Pass 1, prefer:

- no behavior changes unless fixing a clear defect
- smaller files with single responsibility
- clearer boundaries between core runtime, compatibility surfaces, and paper/demo tooling

## Canonical Runtime

These files are the current core and should be preserved:

- `idpo/cli.py`
- `idpo/core/config.py`
- `idpo/core/types.py`
- `idpo/core/storage.py`
- `idpo/core/artifacts.py`
- `idpo/core/provenance.py`
- `idpo/core/policy_store.py`
- `idpo/agents/intake.py`
- `idpo/agents/doc_analysis.py`
- `idpo/agents/preprocess.py`
- `idpo/agents/llm_extraction.py`
- `idpo/agents/validation.py`
- `idpo/agents/recovery.py`
- `idpo/agents/chunking.py`
- `idpo/pipeline/planning.py`
- `idpo/pipeline/executor.py`
- `idpo/pipeline/orchestrator.py`
- `idpo/pipeline/inbox.py`
- `idpo/pipeline/serialization.py`
- `idpo/pipeline/export.py`

These tests currently define much of the stable behavior and should be kept passing during cleanup:

- `idpo/tests/test_storage_paths.py`
- `idpo/tests/test_pipeline_tuning_upgrades.py`
- `idpo/tests/test_extraction_enhancements.py`
- `idpo/tests/test_idpo.py`
- selected runtime-focused cases from `idpo/tests/test_research_features.py`

## Keep / Split / Quarantine / Delete

### Keep As Core

- `idpo/core/*`
  Reason: config, storage, artifacts, provenance, and type contracts are foundational runtime pieces.
- `idpo/pipeline/planning.py`
  Reason: routing and plan construction are part of the canonical path and already reasonably bounded.
- `idpo/pipeline/executor.py`
  Reason: stage execution is close to a clean unit and should remain the execution boundary.
- `idpo/agents/doc_analysis.py`
  Reason: DAE output is a key contract for routing and evidence.

### Split First

- `idpo/pipeline/inbox.py`
  Current problem: one file handles ingestion, filesystem layout, per-doc artifact writing, run summaries, Excel/CSV export, schema metrics, and database telemetry.
  Target split:
  - `idpo/pipeline/inbox.py`: orchestration only
  - `idpo/pipeline/doc_layout.py`: doc directory creation and normalization
  - `idpo/pipeline/doc_artifacts.py`: write per-doc JSON artifacts
  - `idpo/pipeline/run_reports.py`: `docs.xlsx`, `entities.xlsx`, `run.xlsx`, CSV fallbacks
  - `idpo/pipeline/telemetry.py`: optional DB telemetry writes
  Notes:
  - `_write_provenance()` appears unused and should be removed after verifying no callers.
  - `process_inbox()` should stop containing low-level file-writing details.

- `idpo/pipeline/orchestrator.py`
  Current problem: one file owns runtime initialization, queueing, shadow execution, rollback, reward computation, AHMN feedback logging, exports, and the giant `PipelineResult` contract.
  Target split:
  - `idpo/pipeline/orchestrator.py`: high-level `Pipeline` flow only
  - `idpo/pipeline/results.py`: `PipelineResult`
  - `idpo/pipeline/policy_safety.py`: real rollback and gate logic, not only a wrapper
  - `idpo/pipeline/reward.py`: reward and schema-quality computation
  - `idpo/pipeline/shadow.py`: shadow planning and comparison logic
  - `idpo/pipeline/feedback.py`: AHMN feedback posting
  Notes:
  - queueing can stay in orchestrator for Pass 1 if needed, but shadow and reward should move out first.

- `idpo/agents/llm_extraction.py`
  Current problem: a 1900+ line file mixing heuristic extraction, key normalization, prompt building, provider calls, response parsing, fallback logic, and diagnostics.
  Target split:
  - `idpo/agents/llm_extraction.py`: agent orchestration only
  - `idpo/agents/extraction_rules.py`: heuristic and regex extraction
  - `idpo/agents/extraction_prompts.py`: prompt construction and targeted context
  - `idpo/agents/extraction_providers.py`: OpenAI/Ollama/Anthropic transport
  - `idpo/agents/extraction_parsing.py`: JSON/entity parsing and canonicalization
  Notes:
  - preserve current extraction behavior before attempting algorithm changes
  - do not mix provider integration work with heuristic cleanup in the same pass

### Quarantine As Non-Core

- `idpo/ui/app.py`
  Status: explicitly marked as legacy compatibility surface.
  Rule: no new features here. Only compatibility fixes.
  Follow-up: eventually move to `idpo/legacy/ui_app.py` or equivalent after callers are updated.

- `idpo/integration.py`
  Status: explicitly marked as legacy cross-service path, not the canonical paper-facing runtime.
  Rule: freeze it. No new runtime logic should depend on it.
  Follow-up: move to `idpo/legacy/integration.py` after gateway/tests/docs are updated.

- `scripts/run_idpo_benchmark.py`
- `idpo/benchmark/*`
  Status: paper-evidence tooling, not core runtime.
  Rule: keep working, but treat as a separate surface from canonical runtime.

- `idpo/evaluation/runner.py`
  Status: useful support tooling, not part of the main operational path.
  Rule: keep outside core cleanup until runtime boundaries are stable.

- `idpo/pipeline/export.py`
  Status: operational/reporting support, not the heart of the runtime.
  Rule: preserve, but avoid letting reporting concerns dictate runtime structure.

### Delete Or Demote After Callers Are Gone

- `idpo/pipeline/inbox.py::_write_provenance`
  Current status: removed in Pass 1A after repo-wide caller check.
  Follow-up: none unless an external dependency is discovered.

- `idpo/pipeline/policy_safety.py`
  Current status: compatibility wrapper around `PolicyRollbackMonitor`, used by tests only.
  Action: either make this the real home of rollback logic or remove the wrapper after tests are updated.

- duplicate export/report plumbing inside `idpo/pipeline/inbox.py`
  Action: remove after `run_reports.py` or equivalent exists.

## First Cleanup Sequence

### Pass 1A: Stabilize Boundaries

1. Add a thin runtime contract note at the top of the key files if needed.
2. Remove clearly unused code such as `inbox._write_provenance`.
3. Move legacy surfaces into a documented quarantine list without changing behavior.
4. Reduce test ambiguity by marking which tests are canonical runtime vs paper/demo coverage.

Acceptance:

- existing runtime tests still pass
- no behavioral changes in `process_inbox()` or `Pipeline.process_document()`

Progress on current branch:

- removed unused `inbox._write_provenance()`
- added runtime-boundary notes to `inbox.py`, `orchestrator.py`, and `llm_extraction.py`
- extracted run-level reporting helpers from `inbox.py` into `idpo/pipeline/run_reports.py`
- extracted per-document artifact writing from `inbox.py` into `idpo/pipeline/doc_artifacts.py`
- extracted optional DB telemetry persistence from `inbox.py` into `idpo/pipeline/telemetry.py`
- extracted document-record shaping from `inbox.py` into `idpo/pipeline/doc_records.py`

### Pass 1B: Split `inbox.py`

1. Extract per-doc artifact writers.
2. Extract run-level report writers.
3. Extract telemetry persistence.
4. Leave `process_inbox()` as a short coordinator.

Acceptance:

- `process_inbox()` becomes readable end-to-end
- file layout and run outputs do not change
- storage path tests continue to pass

### Pass 1C: Split `orchestrator.py`

1. Move reward computation out.
2. Move rollback/shadow logic out.
3. Move feedback logging out.
4. Move `PipelineResult` out of the file.

Acceptance:

- `Pipeline.process_document()` is mostly orchestration
- reward, safety, and feedback logic can be tested separately

Progress on current branch:

- extracted reward computation and policy-gate evaluation from `orchestrator.py` into `idpo/pipeline/reward.py`
- extracted AHMN feedback posting from `orchestrator.py` into `idpo/pipeline/feedback.py`
- extracted shadow execution, comparison shaping, and comparison persistence from `orchestrator.py` into `idpo/pipeline/shadow.py`
- extracted `PipelineResult` from `orchestrator.py` into `idpo/pipeline/results.py`
- moved canonical rollback monitoring out of `orchestrator.py` into `idpo/pipeline/policy_safety.py`
- extracted `PipelineResult` assembly out of `orchestrator.py` into `idpo/pipeline/results.py`

### Pass 1D: Split `llm_extraction.py`

1. Extract provider transport code.
2. Extract prompt building.
3. Extract parsing/canonicalization.
4. Keep the agent entrypoint thin.

Acceptance:

- extraction tests still pass
- provider logic is isolated from heuristics

Progress on current branch:

- extracted the local-first and cloud-first mode orchestration out of `LLMExtractionAgent.run()` into focused helper methods
- extracted provider transport into `idpo/agents/extraction_providers.py` for Ollama, OpenAI, and Anthropic calls
- extracted prompt construction and extraction-input/context shaping into `idpo/agents/extraction_prompts.py`
- extracted JSON parsing and entity canonicalization into `idpo/agents/extraction_parsing.py`
- extracted explicit rule matching and generic/schema fallback helpers into `idpo/agents/extraction_rules.py`
- extracted smart-field and label-anchor heuristics into `idpo/agents/extraction_heuristics.py`
- extracted generic key-value extraction and inline line-parsing/noise-filtering into `idpo/agents/extraction_generic_kv.py`
- preserved existing local fallback, cloud fallback, flagship fallback, and description-refinement behavior
- kept some small compatibility wrappers in `llm_extraction.py` so this step stayed behavior-safe

## High-ROI Cleanups

- shrink the largest files before changing algorithms
- remove unused helpers and wrappers
- isolate legacy UI/integration paths from the core runtime
- keep paper/benchmark code out of the canonical execution path
- reduce duplicated schema/reward/transparency shaping logic across `orchestrator.py` and `inbox.py`

## Things To Avoid In Pass 1

- do not redesign policy semantics
- do not change benchmark definitions and cleanup structure in the same PR
- do not rewrite the frontend while runtime boundaries are still unstable
- do not delete `ui/app.py` or `integration.py` yet because gateway/docs/tests still reference them

## Recommended Next PRs

1. `cleanup/idpo-inbox-split`
2. `cleanup/idpo-orchestrator-split`
3. `cleanup/idpo-extraction-split`
4. `cleanup/idpo-legacy-quarantine`

## Practical Definition Of Done

Pass 1 is complete when:

- the canonical runtime files are understandable without tracing through legacy surfaces
- no single IDPO runtime file is trying to do ingestion, execution, reporting, and telemetry together
- legacy surfaces are clearly marked and isolated
- the team can explain the runtime path without reading 1000+ line files

## When To Replace This Document

Replace or archive this document when:

- the project leaves the cleanup and stabilization phase
- the canonical runtime path changes materially
- the highest-priority work is no longer the `idpo/` cleanup sequence described here
