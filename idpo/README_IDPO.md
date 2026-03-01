# IDPO Research-Grade Orchestration

This document describes the IDPO enhancements added for research-grade orchestration while preserving existing CLI and run compatibility.

## 1) Architecture (Updated)

```text
                +-------------------------------+
Input Docs ---> | DAE (Complexity-Aware)       |
                | - quality features           |
                | - structural features        |
                | - route_bin/light|std|heavy |
                +---------------+---------------+
                                |
                                v
                +-------------------------------+
                | PolicyAdvisor (AHMN adapter) |
                | - ranked policy advice       |
                | - HTTP / import / fallback   |
                +---------------+---------------+
                                |
                                v
                +-------------------------------+
                | PlanRouter + Operator Stack  |
                | - specialization              |
                | - budgets & constraints       |
                +---------------+---------------+
                                |
                                v
      +------------------ PlanExecutor ------------------+
      | preprocess -> extract(fields) -> validate        |
      |      -> field-level recovery -> field escalation |
      |      -> chunking                                 |
      +------------------+-------------------------------+
                         |
                         +----> Shadow mode (sampled alt policies)
                         |
                         +----> PolicySafetyMonitor (rollback)
                         |
                         +----> Provenance + Metrics + Reports
```

## 2) Core Additions

- `idpo/core/budget.py`: budget/rate/latency/retry/escalation controls.
- `idpo/core/calibration.py`: Platt/isotonic calibration + ECE/reliability outputs.
- `idpo/pipeline/policy_advisor.py`: AHMN policy advice adapter with ranked fallback.
- `idpo/pipeline/policy_safety.py`: rolling policy safety checks and rollback trigger.
- `idpo/pipeline/run_layout.py`: standardized run-output folder management.
- `idpo/demo.py`: reproducible demo runner.

## 3) DAE Output (What Changed)

DAE now emits:
- `doc_type`
- `vendor_cluster`
- `layout_cluster_id`
- `quality_features`: blur/contrast/skew/noise estimates
- `structural_features`: table density, blocks, sections, form patterns
- `route_bin`: `light|standard|heavy`
- `analysis_confidence` + `confidence_type` (`heuristic|calibrated`)

## 4) Policy Advice + Routing

- IDPO first requests ranked recommendations from AHMN (HTTP or import adapter).
- If unavailable, deterministic fallback ranking is used from policy store rules.
- Router selects policy and builds specialized operator stack:
  - base route: `light|standard|heavy`
  - specialization: `table-heavy|form-centric|image-dominant|text-dominant`
  - stack choices: OCR passes, denoise strength, table parser mode, chunking mode

## 5) Field-Level Extraction / Recovery / Escalation

Extraction includes per-field:
- `value`
- `evidence_span` / optional bbox
- `confidence_score`
- `confidence_type`
- `extraction_method` (`local_model|llm_tool|rule_based`)

Recovery:
- retries only failing fields
- supports alternate strategy stack and RAG hints
- enforced by retry budgets (`max_retries_per_field`, `max_total_retries_per_doc`)

Escalation:
- field-level only
- budget/rate limited
- target model from config
- when unavailable, marks `escalation_unavailable` (safe simulation path)

## 6) Shadow Mode + Safe Rollback

Shadow mode:
- sampled docs run alternative policies after canonical output
- canonical output is unchanged
- artifacts go under `runs/<run_id>/.../shadow/<policy_id>/`
- comparison file in `metrics/comparisons.json` (configurable)

Rollback:
- rolling monitoring per policy (latency p95, validation pass, quality proxy)
- if regression exceeds thresholds, policy is blocked
- router automatically reverts to baseline/known-good
- provenance event: `RollbackTriggered`

## 7) Queue Partitioning Fairness

Partition key is config-driven (default: `doc_type + vendor_cluster`).
Scheduler uses fair round-robin dispatch across partitions so hot partitions do not starve cold ones.

## 8) Standardized Run Outputs

Each run ensures:

```text
runs/<run_id>/primary/
  input/ dae/ route/ preprocess/ extract/ validate/ recover/ escalate/
  index/ retrieve/ answer/ provenance/ metrics/ shadow/ reports/
```

Backward-compatible legacy artifacts and JSON outputs are still generated.

## 9) Configuration Knobs

Research config example: `configs/idpo_research_config.json`

Key sections:
- `routing`: route/specialization thresholds
- `budget`: doc/minute cost, latency, retries, escalation quotas
- `shadow`: sample rate, candidate policies, comparison file
- `rollback`: regression thresholds
- `queue`: partition keys and concurrency
- `ahmn`: endpoint/mode/advice/log settings
- `calibration`: method/mode/model path
- `escalation`: flagship model and estimated cost/latency

## 10) Calibrated vs Heuristic Confidence

- `heuristic`: raw confidence from extraction/validation heuristics.
- `calibrated`: confidence transformed by a trained calibrator (Platt/isotonic).
- If no calibrator model is configured, outputs remain explicitly `heuristic`.

## 11) Run Demo

```bash
python -m idpo.demo --input demo_docs/ --shadow --report
```

This run includes:
- mixed docs (image-heavy, table-heavy, clean text)
- field-level recovery trigger
- field-level escalation trigger
- shadow comparisons and final report in `reports/summary.md`

## 12) Run Tests

```bash
python -m pytest idpo/tests -v
```

## 13) Calibrator Training + Evaluation

Fit:
```bash
python -m idpo.cli calibrate-fit --dataset idpo/tests/fixtures/calibration_samples.jsonl --out runs/calibration/model.json --method platt --bins 10
```

Evaluate:
```bash
python -m idpo.cli calibrate-eval --dataset idpo/tests/fixtures/calibration_samples.jsonl --model runs/calibration/model.json --out runs/calibration/eval.json --bins 10
```
