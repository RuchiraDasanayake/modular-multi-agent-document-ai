# IDPO + AHMN — Claude Code Project Context

> **Read this first.** This file gives you full context to continue work on this repo without needing prior conversation history.

---

## What This Project Is

**IDPO** (Intelligent Document Processing Orchestrator) is a research prototype for adaptive document extraction. A document image goes in; structured key-value pairs come out. The pipeline is modular — OCR, preprocessing, LLM extraction, validation, recovery — and each stage is governed by a **policy** selected at runtime.

**AHMN** (Adaptive Hierarchical Multi-agent Network) is the routing layer. It uses Thompson Sampling (Beta-Bernoulli posteriors) to select which policy to apply to each document, behind an `adaptive_safe` gate that falls back to `default` when a candidate regresses.

This is a **conference paper project**. The research question is narrow:
> Does `adaptive_safe` mode (AHMN-driven routing) improve extraction over `static` mode (fixed default policy) on labeled external datasets (CORD receipts, FUNSD forms) and a hard-document stress pack?

The answer, frozen in `paper/FINAL_EVIDENCE.md`, is **no**: accuracy was tied or slightly lower, and latency was higher on receipts. The paper (`paper/ieee/main.tex`) reports this as a negative result and explains why.

**Branch:** `main`
**Primary author:** Thimuth N
**Guardrails component author:** Wijetunga W.L.A.T.

---

## Environment

| Dependency | Version | Status |
|---|---|---|
| Python | 3.10.10 | `.venv/Scripts/python` |
| PaddleOCR | 2.9.1 on PaddlePaddle 2.6.2 (CPU) | Installed, working |
| pytesseract | - | Installed; Tesseract 5.4.0 on PATH (fallback engine) |
| OpenCV (cv2) | 4.11.0 | Installed |
| PIL / Pillow | - | Installed |
| NumPy | 1.26.4 | Installed |
| Ollama | 0.35.1 | `http://localhost:11434` |
| qwen3.5:9b | 6.6 GB | Primary LLM — **use this** |
| phi3:mini | 2.2 GB | Backup only |
| openai SDK | - | Installed |
| anthropic SDK | - | **Not installed** |

**Always use `.venv/Scripts/python` for all commands, never system Python.** Setup: `SETUP.md`. Reproducing the paper: `docs/REPRODUCING_RESULTS.md`.

```bash
# Run a benchmark (both conditions)
.venv/Scripts/python scripts/run_idpo_benchmark.py --pack datasets/probe_3.json --config configs/idpo_research_config.json

# Diagnose last benchmark
.venv/Scripts/python scripts/bench_diag.py

# Run tests
.venv/Scripts/python -m pytest idpo/tests/ -x -q
```

---

## Repo Structure (what matters)

```
idpo/
 pipeline/
 executor.py — Stage orchestrator. Runs OCR → extract → validate → recover.
 planning.py — Policy selection + operator spec building. Policy-explicit deskew/denoise overrides the quality heuristic.
 orchestrator.py — Top-level run coordinator. Calls DocumentAnalysisAgent then planner.
 policy_advisor.py — Builds AHMN payload from DAEOutput, calls direct_advisor.
 policy_safety.py — Rollback monitor behind the adaptive_safe gate (absolute and baseline-relative limits).
 agents/
 doc_analysis.py — Computes quality_bin, doc_type, vendor_cluster, semantic_doc_type (from OCR text, after routing).
 preprocess.py — OCR (PaddleOCR + Tesseract). PSM and engine are policy-driven.
 llm_extraction.py — LLM extraction. Per-field mode and thinking mode are policy options.
 extraction_prompts.py — Prompt builders. Omit-if-absent rule.
 extraction_providers.py — Ollama/OpenAI wrappers. JSON schema enforcement.
 validation.py — Field validation + grounding check.
 recovery.py — Re-extracts failed fields.

ahmn_core/
 direct_advisor.py — Thompson Sampling core used by the runtime. Specialist exclusivity.
 experiments/ — RABI/DAAF simulator behind the paper's Table V (simulation only; not in the runtime).

guardrails/ — 6-layer validation ensemble (built by W.L.A.T.). A separate service; not called by the measured pipeline.

configs/
 idpo_research_config.json — Research config used for the paper (includes the rollback guard limits)
 policy_store_research.json — Research policies (16: 2 specialists, 13 generic, default)
 policy_store_baseline.json — Static baseline (default policy only)

datasets/
 cord_pack_50.json — CORD-dev (50 validation receipts, seed 17)
 cord_holdout_50.json — CORD-holdout (the other 50 validation receipts)
 funsd_pack_20.json — FUNSD-20 (test-split forms)
 hard_docs_13.json — HARD-13 (6 synthetic hard documents + 4 CORD + 3 FUNSD)
 probe_3.json — 3-doc quick probe

scripts/
 run_idpo_benchmark.py — Main benchmark runner (static vs adaptive_safe)
 aggregate_benchmark_evidence.py — Paper tables and paired bootstrap differences (--rescore)
 analyze_benchmark_errors.py — Per-field errors and label-free reward vs exact F1
 build_cord_benchmark_pack.py, build_cord_holdout_pack.py, build_funsd_pack.py, build_hard_docs_pack.py — Pack builders
 bench_diag.py — Per-doc result inspector

paper/
 ieee/main.tex, ieee/main.pdf — The paper (IEEEtran, six pages)
 FINAL_EVIDENCE.md — Frozen results, run folders and regeneration commands
```

---

## Current State

Phase: **evidence frozen; publication preparation** (`docs/PROJECT_DIRECTION.md`).

### Final results (`paper/FINAL_EVIDENCE.md`)

Paired differences, adaptive minus static, with 95% bootstrap intervals (10,000 resamples, seed 17):

| Pack | Δ doc F1 | Δ latency (s) |
|---|---|---|
| CORD-dev (50) | +0.001 [−0.028, +0.031] | +5.20 [+3.69, +6.63] |
| CORD-holdout (50) | −0.023 [−0.068, +0.003] | +2.61 [+1.16, +4.12] |
| CORD-100 (pooled) | −0.011 [−0.038, +0.011] | +3.91 [+2.84, +4.95] |
| FUNSD-20 | 0 (tied on every document) | +0.54 [−1.38, +2.22] |
| HARD-13 | 0 (tied on every document) | −2.09 [−6.99, +0.81] |

The static pipeline reaches micro F1 0.898 (CORD-dev), 0.871 (CORD-holdout), 0.788 (FUNSD-20) and 0.960 (HARD-13).

Why routing did not help:
- The label-free reward `r = 2TP/(2TP+FP+FN)` measures coverage, not correctness. On CORD its Pearson correlation with exact document F1 was 0.07 (adaptive).
- Only the two specialists change the extraction call, so the effective action space is four behaviours, not sixteen policies.
- Per-field extraction recovered more change amounts but also returned values for fields the receipt does not contain; no net gain.

### Changes made while building the evidence
1. Static baseline store (`policy_store_baseline.json`, `default` only).
2. JSON schema enforcement, omit-if-absent prompt, grounding check in validation, and a fix to the amount check for comma-formatted values.
3. `vendor_cluster` from the case-id prefix of the file name (benchmark temp files are renamed to `case_id + suffix`).
4. Per-field extraction for `receipt_specialist` and `correspondence_specialist`. Thinking mode was tried and reverted: `use_thinking` is `false` for both.
5. Specialist exclusivity in the Thompson sampling draw.
6. Policy-explicit deskew/denoise overrides the quality heuristic (`planning.py`).
7. Baseline-relative rollback guard (`policy_safety.py`, `rollback` block of the research config). The first runs used absolute limits (2.5 s p95 latency, 0.25 validation failure rate), which blocked every non-default policy after five observations, because the default itself takes 9–14 s. The final runs use limits relative to `default` (L = 60 s, F = 0.5, ρ = 0.25, δv = 0.10, δq = 0.08, W = 10, m = 5). The paper reports both rounds.
8. Scorer fixes: date fields also match the same calendar date, and repeated dot-thousands separators (`2.000.000`) are read as numbers. Every saved run was rescored (`aggregate_benchmark_evidence.py --rescore`); no paired comparison changed sign or significance.
9. The frontend job API and dashboard pages need a gateway-verified session (`frontend/src/middleware.ts`); the first admin comes from `ADMIN_PASSWORD`.
10. The AHMN simulator seeds NumPy as well as Python's `random`, so the paper's Table V regenerates exactly.

### Limitations (stated in the paper)
- Specialist eligibility relies on the file-name prefix (`vendor_cluster`), which reveals the dataset. `semantic_doc_type` is computed from OCR text after routing, so it is `unknown` at routing time.
- Prompts, normalisers and specialist context were written while inspecting CORD-dev and FUNSD-20. CORD-holdout is the only clean holdout.
- The runtime sampler is unseeded and four documents run concurrently, so adaptive results vary between runs. Each adaptive configuration ran once.
- RABI and DAAF exist only in the simulator. Guardrails is a separate service.
- FUNSD OCR quality ("Jy" for "July") is the ceiling for forms.

---

## Paper Claim (do not widen this)

> In paired runs with a holdout split, Thompson-sampling routing with a safety gate did not improve the accuracy of a local, template-free OCR–LLM extractor on receipts, forms or hard documents, and it added latency on receipts. A label-free coverage reward cannot teach a router to prefer correct policies over merely complete ones, and safety limits must be calibrated against the baseline, or they silently switch adaptation off.

Every number in the paper must trace to `paper/FINAL_EVIDENCE.md`.

---

## Next Steps

1. Choose the venue and adapt `paper/ieee/main.tex` to its template, page limit and review policy.
2. Archive the run folders listed in `paper/FINAL_EVIDENCE.md` with the repository release.
3. For double-blind review, point the paper's release sentence at an anonymised copy of the repository; add the author block for camera-ready.
4. If a runtime change can alter benchmark outcomes, rerun the benchmarks and update the paper and `paper/FINAL_EVIDENCE.md` together.

The run folders `idpo-data/runs/benchmarks/benchmark_1777096266` and `benchmark_1777097171` are earlier reference runs; do not delete them either.

---

## What NOT to Do

- Do not change `policy_store_baseline.json` — it must stay as dumb default-only
- Do not edit numbers in the paper without regenerating them with the commands in `paper/FINAL_EVIDENCE.md`
- Do not re-tune prompts, normalisers or the scorer against the benchmark packs
- Do not overfit field descriptions to CORD/FUNSD specifically — keep descriptions general and logical
- Do not add `per_field_extraction: true` to default or generic policies — only specialists
- Do not enable `use_thinking: true` for receipt extraction — it adds 30-60s latency with no benefit for numeric extraction
- Do not wire Guardrails, RABI or DAAF into the measured pipeline without new runs and a revised claim
- Do not widen the paper claim
- Do not use `python` directly — always use `.venv/Scripts/python`

---

## Testing

```bash
# Unit tests
.venv/Scripts/python -m pytest idpo/tests/ -x -q
.venv/Scripts/python -m pytest ahmn_core/tests/ gateway/tests/ guardrails/tests/ xai_hitl/tests/ -q
cd frontend; npx tsc --noEmit; npm run lint; npm run test:server

# Quick 3-doc probe
.venv/Scripts/python scripts/run_idpo_benchmark.py --pack datasets/probe_3.json

# Inspect results
.venv/Scripts/python scripts/bench_diag.py
```

Key test files:
- `idpo/tests/test_extraction_enhancements.py`
- `idpo/tests/test_pipeline_tuning_upgrades.py`
- `idpo/tests/test_research_features.py`
- `ahmn_core/tests/test_algorithms.py`
