# IDPO Architecture

This file documents the runtime that is actually supported today.

## Runtime path

```text
inputs -> intake -> document analysis -> planning -> executor -> exports
```

Supported operational entrypoints:
- `python -m idpo.cli`
- `idpo.ui.app`
- `scripts/run_idpo_benchmark.py`

The canonical processing path inside IDPO is:
- `idpo.pipeline.inbox`
- `idpo.pipeline.orchestrator`
- `idpo.pipeline.executor`

## Main runtime stages

1. Intake normalizes files into `Document` objects.
2. Document analysis produces the current heuristic DAE profile and routing evidence:
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
3. Planning selects a policy and builds an execution plan:
   - `ahmn.policy_mode = "static"` uses deterministic local routing
   - `ahmn.policy_mode = "adaptive"` uses `PolicyAdvisor`, records AHMN top-1 advice telemetry, and logs post-execution feedback to AHMN
   - shadow candidates remain shadow-only and are excluded from canonical routing
4. Execution runs the active operator stack:
   - OCR / deskew / denoise / table extraction when needed
   - field extraction
   - sectioning
   - summarization
   - validation
   - recovery
   - escalation
   - chunking
5. Exports write run-level results, spreadsheets, provenance, and per-document artifacts.

## Evidence artifacts

Per-document evidence files:
- `decision_chain.json`
- `reward.json`
- `recovery_trace.json`

For the canonical paper-facing adaptive path, use `configs/idpo_research_config.json` with `process-inbox` or `scripts/run_idpo_benchmark.py`.
The paper-facing comparison is `static` vs `adaptive_safe`, where IDPO applies safety and fallback logic around fixed AHMN top-1 advice.

Run-level evidence files:
- `metrics.json`
- `decision_chain_summary.json`

Benchmark-level evidence file:
- `IDPO_DATA_DIR/runs/benchmarks/<benchmark_run_id>/paper_evidence.json`

## Storage layout

All writable runtime state lives under `IDPO_DATA_DIR`.

```text
IDPO_DATA_DIR/
  runs/
  inputs/
    inbox/
    processed/
    failed/
```

If `IDPO_DATA_DIR` is unset, IDPO uses `../idpo-data` relative to the repo root.

## Notes on scope

- This document does not describe aspirational or partially wired research behavior as if it were live.
- AHMN, Guardrails, and XAI integrations may exist in the repo, but they are not the source of truth for the current IDPO runtime path.
- Future paper work should extend this path directly instead of adding alternate wrappers or demo-only flows.
