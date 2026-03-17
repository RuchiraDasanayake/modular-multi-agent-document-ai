# IDPO Runtime Overview

IDPO is the document-processing runtime in this repo. The supported path is intentionally small:

`ingest/inbox -> orchestrator -> executor -> exports`

The supported entrypoints are:
- `python -m idpo.cli`
- `idpo.ui.app`
- `scripts/run_idpo_benchmark.py`

Everything else in IDPO should be treated as internal support code for those entrypoints.

## What the runtime does today

1. Ingests `.txt`, `.json`, `.pdf`, and common image files.
2. Runs document analysis to derive routing evidence:
   - `doc_type`
   - `vendor_cluster`
   - `quality_bin`
   - `complexity_bin`
   - `content_profile`
   - `route_bin`
   - `layout_cluster_id`
   - `quality_features`
   - `structural_features`
3. Selects a policy through one config-gated planner path:
   - `ahmn.policy_mode = "static"` keeps local deterministic routing
   - `ahmn.policy_mode = "adaptive"` uses `PolicyAdvisor` and falls back deterministically when needed
4. Executes preprocessing, extraction, validation, recovery, escalation, chunking, and indexing.
5. Writes run artifacts under `IDPO_DATA_DIR` instead of under the source tree.

Default runtime storage:
- `IDPO_DATA_DIR/runs`
- `IDPO_DATA_DIR/inputs/inbox`
- `IDPO_DATA_DIR/inputs/processed`
- `IDPO_DATA_DIR/inputs/failed`

If `IDPO_DATA_DIR` is unset, IDPO defaults to the sibling folder `../idpo-data`.

## CLI

Supported commands:

```bash
idpo ingest --input data/docs --out out/ingested.json
idpo process --input data/docs --run-dir ../idpo-data/runs/demo
idpo process-inbox --root . --config configs/config.json
idpo process-inbox --root . --config configs/config.json --input-dir data/docs
idpo query --run-dir ../idpo-data/runs/demo --question "What is the total amount?"
idpo evaluate --input data/ground_truth.json --run-dir ../idpo-data/runs/eval
idpo export-provenance --run-dir ../idpo-data/runs/demo --out provenance.json
idpo migrate-storage --root .
```

`process-inbox` is the preferred operational path because it creates the full run layout, metrics, and per-document artifacts.

## Benchmark

Use the fixed benchmark runner for paper-safe static vs adaptive evidence:

```bash
python scripts/run_idpo_benchmark.py --config configs/config.json
```

Benchmark reports are written to:

```text
IDPO_DATA_DIR/runs/benchmarks/
```

The canonical benchmark artifact is:

```text
IDPO_DATA_DIR/runs/benchmarks/<benchmark_run_id>/paper_evidence.json
```

Per-document runtime artifacts now include:
- `decision_chain.json`
- `reward.json`
- `recovery_trace.json`

## Paper claim boundary

The supported paper-facing evidence in the runtime is:
- DAE-driven routing signals from the live analysis step
- config-gated `static` vs `adaptive` policy routing
- explicit reward, recovery, and escalation traces in run artifacts
- one canonical benchmark artifact: `paper_evidence.json`

Claims beyond those artifacts should still be treated as future work or secondary evidence.
