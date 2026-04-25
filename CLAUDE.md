# IDPO + AHMN — Claude Code Project Context

> **Read this first.** This file gives you full context to continue work on this repo without needing prior conversation history.

---

## What This Project Is

**IDPO** (Intelligent Document Processing Orchestrator) is a research prototype for adaptive document extraction. A document image goes in; structured key-value pairs come out. The pipeline is modular — OCR, preprocessing, LLM extraction, validation, recovery — and each stage is governed by a **policy** selected at runtime.

**AHMN** (Adaptive Hierarchical Multi-agent Network) is the routing layer. It uses Thompson Sampling (Beta-Bernoulli posteriors) to select which policy to apply to each document. The core claim: adaptive routing (AHMN) produces better operational results than static single-policy processing.

This is a **conference paper project**. The research claim is narrow:
> `adaptive_safe` mode (AHMN-driven routing) vs `static` mode (fixed default policy) on labeled external datasets (CORD receipts + FUNSD correspondence).

**Branch:** `feature/IDPO`  
**Primary author:** Thimuth N  
**Guardrails component author:** Wijetunga W.L.A.T.

---

## Environment

| Dependency | Version | Status |
|---|---|---|
| Python | 3.10.10 | `.venv/Scripts/python` |
| PaddleOCR | paddle 2.6.2 | Installed, working |
| pytesseract | - | Installed; Tesseract 5.4.0 on PATH |
| OpenCV (cv2) | 4.11.0 | Installed |
| PIL / Pillow | - | Installed |
| NumPy | 1.26.4 | Installed |
| Ollama | local | `http://localhost:11434` |
| qwen3.5:9b | 6.6 GB | Primary LLM — **use this** |
| phi3:mini | 2.2 GB | Backup only |
| openai SDK | - | Installed |
| anthropic SDK | - | **Not installed** |

**Always use `.venv/Scripts/python` for all commands, never system Python.**

```bash
# Run a benchmark
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
    executor.py       — Stage orchestrator. Runs OCR → extract → validate → recover.
    planning.py       — Policy selection + operator spec building. BUG HERE (see below).
    orchestrator.py   — Top-level run coordinator. Calls DocumentAnalysisAgent then planner.
    policy_advisor.py — Builds AHMN payload from DAEOutput, calls direct_advisor.
  agents/
    doc_analysis.py   — Computes quality_bin, doc_type, vendor_cluster. Runs BEFORE routing.
    preprocess.py     — OCR (PaddleOCR + Tesseract). PSM and engine are policy-driven.
    llm_extraction.py — LLM extraction. Per-field mode + thinking mode now implemented.
    extraction_prompts.py — Prompt builders. N/A rule added.
    extraction_providers.py — Ollama/OpenAI wrappers. JSON schema enforcement added.
    validation.py     — Field validation + grounding check.
    recovery.py       — Re-extracts failed fields.

ahmn_core/
  direct_advisor.py   — Thompson Sampling core. Specialist exclusivity fix added.

guardrails/           — 6-layer validation ensemble (built by W.L.A.T.). NOT YET WIRED IN.
  core/ensemble.py    — Orchestrates 6 checks: schema, relevance, consistency, domain, PII, faithfulness
  core/validation.py  — Relevance (hallucination) + faithfulness checks
  models.py           — Document type schemas (Receipt, Invoice, etc.)

configs/
  idpo_research_config.json    — Active research config
  policy_store_research.json   — Research policies (specialist + generic)
  policy_store_baseline.json   — Static baseline (default policy only)

datasets/
  mixed_20.json       — 20-doc benchmark (10 CORD + 10 FUNSD)
  probe_3.json        — 3-doc quick probe
  FUNSD/              — 50 FUNSD test images + annotations
  derived/            — CORD derived packs (100-seed)
  external/cord-v2/   — Raw CORD parquet

scripts/
  run_idpo_benchmark.py  — Main benchmark runner (static vs adaptive_safe)
  bench_diag.py          — Per-doc result inspector
```

---

## What's Been Implemented on This Branch

All changes are on `feature/IDPO`. See git log for specifics.

### Done ✓
1. **Static baseline policy store** (`policy_store_baseline.json`) — static condition now uses only `default` policy (no specialist routing). True dumb baseline.
2. **JSON schema enforcement** — Ollama `/api/chat` receives full entity-list JSON schema. Prevents hallucinated field names and malformed JSON.
3. **Anti-hallucination prompt** — Per-field `[omit if not present]` + "do NOT guess or infer". Rule 6 now returns `"N/A"` with confidence 0.0 for absent fields (parsing already filters these).
4. **Grounding check in validation** — Post-extraction: value tokens (>3 chars) must appear in source document text. Ungrounded values flagged as `ungrounded_value` (severity: high).
5. **Fixed `_looks_like_amount`** — Was rejecting all comma-formatted amounts (`70,000`, `379,500`). Now strips separators then checks `isdigit()`.
6. **Vendor_cluster bug fix** — FUNSD filenames (e.g. `82092117.png`) yielded wrong `vendor_cluster`. Benchmark now renames temp files to `case_id + suffix`, so `funsd_82092117.png` → vendor_cluster="funsd".
7. **Per-field extraction mode** — `per_field_extraction: true` in policy extraction config runs one LLM call per field instead of bulk. Fixes field assignment confusion. Enabled for `receipt_specialist` and `correspondence_specialist`.
8. **Thinking mode per policy** — `use_thinking: true` in policy extraction config enables Qwen3's reasoning chain for complex docs. Enabled for `correspondence_specialist`.
9. **Specialist exclusivity in AHMN** — When a vendor-cluster specialist is a candidate, quality-based generic policies (`noisy_ocr_rescue`, `noisy_ocr_precision_local`, `scanned_text`) are excluded from the TS draw. Specialist always wins when it matches.
10. **AHMN state cleared** — All old TS posteriors deleted. Clean slate for new runs.

### Last Benchmark Results (reference, do not delete these folders)
- `idpo-data/runs/benchmarks/benchmark_1777096266` — static baseline fix, no prompt improvements
- `idpo-data/runs/benchmarks/benchmark_1777097171` — all improvements; F1=0.455 both conditions, validation pass 0.80

---

## Known Issues / What Is NOT Working

### P0 — Critical gaps

**1. Policy preprocess is overridden by quality heuristics (`planning.py:330-336`)**
```python
# Current — policy denoise only runs if quality heuristic agrees:
if preprocess.get("denoise", {}).get("enabled", True) and (
    dae_output.route_bin == "heavy" or dae_output.quality_bin in {"B", "C"}
):
```
If a specialist says `denoise: aggressive` but quality_bin is "A", denoise is skipped. The policy's intent is silently ignored. **Fix: policy explicit config must override heuristic defaults.**

**2. Guardrails component is completely disconnected**
`guardrails/` is a full 6-layer validation ensemble (schema adherence, relevance/hallucination detection, consistency, domain rules, PII, faithfulness). It is **never imported or called** from the IDPO pipeline. The hallucination detection (semantic relevance of extracted values vs source text) in `guardrails/core/validation.py:check_relevance()` is exactly what we need. Zero effort to wire in.

**3. `doc_type` is too coarse for routing**
`DocumentAnalysisAgent` returns `"scanned_document"`, `"text_document"`, `"form_document"` — generic structural categories. It never identifies "receipt" or "correspondence". Only `vendor_cluster` (filename prefix) provides document identity. If a document arrives without a known prefix, AHMN routes blind.

**4. F1 delta between static and adaptive is 0.0**
Per-field extraction and thinking mode are implemented but **only fire when the specialist is selected**. With specialist exclusivity now in place and AHMN state cleared, the next benchmark should show a real delta for docs that route to specialists. This needs to be verified.

**5. No job-level field tracking**
Field extraction success/failure rates are computed per-document and discarded. There is no accumulation of "in this job, `change_amount` fails 70% of the time" to inform future routing or recovery. The job overlay mechanism (`IDPO_JOB_OVERLAY_PATH`) exists but must be manually populated — it is not auto-written.

### P1 — Important but not blocking

**6. `avg_schema_grounding_coverage` is always 0.0**
Every benchmark shows this metric as 0.0. Either the metric is never populated or the signal is always empty. Needs investigation.

**7. FUNSD OCR quality is the hard ceiling**
"Jy" for "July", "Amst" for "August" — PaddleOCR struggles with degraded fax/scan artifacts in FUNSD documents. Tesseract 5.4.0 is installed and pytesseract is available. Tesseract handles degraded English text better. OCR engine should be a policy-selectable option (infrastructure partially exists — `preprocess.ocr.engine` param is supported in planning.py).

**8. `cord_probe_0020` field swap not yet confirmed fixed**
Per-field extraction was implemented and specialist exclusivity added, but we haven't run the probe after both fixes are active and AHMN state is clean. This is the primary verification needed.

---

## Immediate Next Steps (in order)

### Step 1: Fix policy preprocess override (`planning.py`)
In `_default_operator_specs()` (~line 330), change the deskew/denoise conditions so that if the policy **explicitly** sets `enabled: true`, the stage runs regardless of quality_bin. Quality heuristic is a fallback only when the policy has no opinion.

```python
# Target behaviour:
policy_wants_denoise = preprocess.get("denoise", {}).get("enabled") is True  # explicit True
quality_suggests_denoise = dae_output.route_bin == "heavy" or dae_output.quality_bin in {"B", "C"}
if is_image_pipeline and (policy_wants_denoise or quality_suggests_denoise):
    specs.append({"operator": "preprocess.denoise"})
```

### Step 2: Add fine-grained doc_type fingerprinting (`doc_analysis.py`)
After initial text extraction, run a fast heuristic classifier on OCR text to detect:
- `"receipt"` — currency symbols, "total", "tax", "cash", amount patterns
- `"correspondence"` — "Dear", "Sincerely", "From:", "To:", salutation patterns
- `"legal_form"` — "COURT", "CASE", "PLAINTIFF", "FILED", "JUDGMENT"
- `"structured_form"` — high label:value line density without financial amounts
- `"unknown"` — fallback

Store as a separate field `semantic_doc_type` (not replacing `doc_type`) on DAEOutput.

### Step 3: Update AHMN policy conditions to use `semantic_doc_type`
Add `semantic_doc_type` conditions to specialist policies so they match even when vendor_cluster is unknown:
```json
"conditions": {
  "vendor_cluster": ["cord"],
  "semantic_doc_type": ["receipt"]  // either condition matches
}
```
Update `_matches_conditions` to support OR logic across multiple condition keys (current logic is AND).

### Step 4: Add Tesseract as policy-selectable OCR engine
`pytesseract` is installed, Tesseract 5.4.0 is on PATH. `preprocess.py` already accepts an `engine` parameter from policy. Add a `_tesseract_ocr()` method alongside `_paddleocr()`. Enable in `correspondence_specialist` and `noisy_ocr_rescue` policies for English degraded documents.

### Step 5: Wire guardrails relevance check into validation pipeline
In `idpo/agents/validation.py`, after per-field validation, call `guardrails.core.validation.check_relevance()` with the extracted entities and source document text. Add the resulting score to the field confidence adjustment. This catches hallucinated values that pass pattern/grounding checks but are semantically unrelated to the source.

### Step 6: Auto-accumulate job-level field context
After each document completes, append to a job-scoped context file:
```json
{"policy_id": "receipt_specialist", "doc_type": "receipt", "vendor_cluster": "cord",
 "field_results": {"total_amount": {"extracted": true, "confidence": 0.92},
                   "change_amount": {"extracted": false, "confidence": 0.0}}}
```
Load this at the start of each document's routing as an additional signal for AHMN. After N documents, the system knows which fields are reliably extracted in this job and can bias policy selection accordingly.

### Step 7: Run 5-record test and observe
After Steps 1-3 are complete, run:
```bash
.venv/Scripts/python scripts/run_idpo_benchmark.py \
  --pack datasets/probe_5.json \
  --config configs/idpo_research_config.json
```
Build `probe_5.json` with:
1. `cord_validation_0020` — hard receipt (subtotal/tax swap — verify per-field fixes it)
2. `cord_validation_0006` — receipt that worked before (regression check)
3. `funsd_82573104` — correspondence with decent OCR (test thinking mode)
4. `funsd_82491256` — legal form (test semantic_doc_type routes it away from correspondence_specialist)
5. `cord_validation_0025` — unseen CORD receipt (cold-start routing test)

**Success criteria for Step 7:**
- Docs 1-2 route to `receipt_specialist` (per-field fires)
- Doc 3 routes to `correspondence_specialist` (thinking fires)
- Doc 4 routes to `default` or `unknown_vendor_safe`, NOT correspondence_specialist
- Doc 5 routes to `receipt_specialist` based on semantic_doc_type="receipt" alone
- F1 for adaptive condition is higher than static on at least 1 receipt doc

---

## Paper Claim (do not widen this)

> `adaptive_safe` correctly identifies document type, routes to specialist policies that use context-appropriate extraction strategies (per-field LLM calls for receipts, reasoning-enabled calls for correspondence), and produces measurably better extraction accuracy and lower latency than a fixed static baseline. The AHMN routing layer learns from per-document outcomes via Thompson Sampling, accumulates job-level context, and improves routing decisions over time within a job.

**Evidence needed:**
1. Policy distribution differs (static=all default, adaptive=diverse specialists) ✓ already shown
2. F1 delta > 0 on documents that route to specialists — **needs Step 7 to verify**
3. Latency delta statistically significant (95% CI excludes 0) ✓ shown in brf6jk18z
4. Validation pass rate improves with guardrails wired in — **needs Step 5**

---

## What NOT to Do

- Do not change `policy_store_baseline.json` — it must stay as dumb default-only
- Do not overfit field descriptions to CORD/FUNSD specifically — keep descriptions general and logical
- Do not add `per_field_extraction: true` to default or generic policies — only specialists
- Do not enable `use_thinking: true` for receipt extraction — it adds 30-60s latency with no benefit for numeric extraction
- Do not widen the paper claim beyond the narrow routing + specialist extraction story
- Do not use `python` directly — always use `.venv/Scripts/python`

---

## Testing

```bash
# Unit tests
.venv/Scripts/python -m pytest idpo/tests/ -x -q

# Quick 3-doc probe
.venv/Scripts/python scripts/run_idpo_benchmark.py --pack datasets/probe_3.json

# Full 20-doc benchmark
.venv/Scripts/python scripts/run_idpo_benchmark.py --pack datasets/mixed_20.json

# Inspect results
.venv/Scripts/python scripts/bench_diag.py
```

Key test files:
- `idpo/tests/test_extraction_enhancements.py`
- `idpo/tests/test_pipeline_tuning_upgrades.py`
- `idpo/tests/test_research_features.py`
