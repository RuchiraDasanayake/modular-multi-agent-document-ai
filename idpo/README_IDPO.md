# IDPO Runtime Overview

IDPO is the document-processing runtime in this repo. The supported path is intentionally small:

`ingest/inbox -> orchestrator -> executor -> exports`

The supported entrypoints are:
- `python -m idpo.cli`
- `idpo.ui.app`
- `scripts/run_idpo_benchmark.py`

In the integrated UI, the supported hosted launch path is:

`frontend job (POST /api/jobs/<job_id>/documents, then POST /api/jobs/<job_id>/runs) -> frontend job runner -> idpo.cli process-inbox -> IDPO_DATA_DIR/runs/<run_id>`

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
   - `ahmn.policy_mode = "adaptive"` uses `PolicyAdvisor` to consume fixed AHMN top-1 advice and falls back deterministically when needed
4. Executes preprocessing, extraction, validation, recovery, escalation, chunking, and indexing. OCR is Paddle-first for OCR-backed docs with Tesseract fallback retained.
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

For the paper-facing adaptive path, use:

```bash
idpo process-inbox --root . --config configs/idpo_research_config.json
```

## AHMN Seed Control

For cleaner adaptive evaluations, treat seeded and unseeded AHMN runs separately:

```bash
# Seeded AHMN memory
python scripts/reset_and_seed_db.py

# Unseeded AHMN memory
python scripts/reset_and_seed_db.py --no-seed
set AHMN_SEED_MODE=unseeded
```

The AHMN service now exposes its active startup seed mode through `/health`.

## Benchmark

Use the fixed benchmark runner for paper-safe `static` vs `adaptive_safe` evidence:

```bash
python scripts/run_idpo_benchmark.py --config configs/idpo_research_config.json
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
- config-gated `static` vs `adaptive_safe` policy routing
- AHMN top-1 advice telemetry and post-execution feedback logging in run artifacts
- explicit separation between AHMN advisor output and deterministic IDPO fallback candidates
- explicit reward, recovery, escalation, and rollback traces in run artifacts
- one canonical benchmark artifact: `paper_evidence.json`

Claims beyond those artifacts should still be treated as future work or secondary evidence.
