# IDPO/AHMN Continuation Plan

**Branch:** `feature/IDPO`  
**Last updated:** 2026-04-25  
**Status:** Clean-slate reset. All AHMN state cleared. Reference benchmarks preserved.  
**Goal:** Demonstrate measurable adaptive > static on labeled data before paper evidence run.

---

## Current System State

### What works end-to-end
- Pipeline processes documents through OCR → extraction → validation → recovery → escalation
- AHMN selects policy via Thompson Sampling with per-job scope persistence
- `vendor_cluster` derived from document ID prefix routes correctly when filename has known prefix
- `receipt_specialist` and `correspondence_specialist` policies exist with correct conditions
- JSON schema enforcement on Ollama output (full entity-list schema passed via `/api/chat`)
- Static baseline uses `policy_store_baseline.json` (default policy only — genuine dumb baseline)
- Per-field extraction implemented in `LLMExtractionAgent._llm_extract_per_field()`
- Specialist exclusivity: when a specialist matches, quality-based generic policies excluded from TS

### Last measured results (before reset)
```
brf6jk18z run (benchmark_1777097171):
  static:        F1=0.455, tp=30, fp=50, fn=22, latency=14070ms
  adaptive_safe: F1=0.455, tp=30, fp=50, fn=22, latency=13820ms
  latency delta: -249ms (95% CI: -499ms to -52ms, excludes 0)
  validation pass rate: 0.80 (up from 0.65)
  F1 delta: 0.0 — per-field extraction did not run on failing docs (specialist not selected)
```

### Why F1 delta is still 0.0
Per-field extraction is implemented but only fires when `receipt_specialist` or `correspondence_specialist` is selected. Before the AHMN state clear, stale posteriors caused generic quality-based policies to win the TS draw over specialists. Now that:
1. Specialist exclusivity is in place (generic policies excluded when specialist matches)
2. AHMN state is cleared (no contaminated posteriors)

The next run should show specialists winning consistently for `vendor_cluster=cord` and `vendor_cluster=funsd` documents.

---

## Known Issues by Priority

### P0 — Blocks paper claim

#### Issue 1: Policy preprocess silently overridden
**File:** `idpo/pipeline/planning.py`, function `_default_operator_specs()`, lines ~330-336  
**Problem:** Denoise and deskew stages only run if BOTH the policy enables them AND a quality heuristic agrees. If `correspondence_specialist` says `denoise: aggressive` but `quality_bin="A"`, denoise is skipped entirely.  
**Effect:** Specialist policies don't actually behave differently from `default` in preprocessing for clean documents.  
**Fix:** Policy explicit config must override heuristic. Heuristic is fallback only.

```python
# Current (wrong):
if preprocess.get("denoise", {}).get("enabled", True) and (
    dae_output.route_bin == "heavy" or dae_output.quality_bin in {"B", "C"}
):

# Target (correct):
policy_denoise = preprocess.get("denoise", {})
policy_wants = policy_denoise.get("enabled") is True  # explicit True only
quality_suggests = dae_output.route_bin == "heavy" or dae_output.quality_bin in {"B", "C"}
if is_image_pipeline and (policy_wants or quality_suggests):
    specs.append({"operator": "preprocess.denoise", "params": policy_denoise})
```
Same pattern for deskew.

#### Issue 2: Guardrails component never called
**Directory:** `guardrails/`  
**Problem:** A complete 6-layer validation ensemble exists (built by W.L.A.T.) with semantic hallucination detection (`check_relevance`), faithfulness scoring, internal consistency, domain rules, PII leakage. It is **never imported or called** from `idpo/`.  
**Effect:** The best hallucination detection in the repo is dead code.  
**Fix:** Call `check_relevance()` from `idpo/agents/validation.py` after per-field validation. Use the score to adjust field confidence.

Key entry point:
```python
# guardrails/core/ensemble.py
async def run_validation_ensemble(rag_input: RAGInput) -> list[ValidationMetric]

# guardrails/core/validation.py
async def check_relevance(data: dict, source_contexts: list[str], doc_type: str) -> ValidationMetric
# Returns: score 0-1, is_pass bool, details string with low-confidence fields flagged
```

`RAGInput` schema (from `guardrails/models.py`):
```python
class RAGInput(BaseModel):
    answer_json: str           # JSON of extracted entities
    source_contexts: list[str] # OCR text pages
    document_context: GuardrailDocumentContext  # doc_type, doc_id
```

**Note:** `guardrails` requires `sentence_transformers`, `presidio_analyzer`, `torch`. Check if installed before wiring in. May need `pip install sentence-transformers presidio-analyzer`.

#### Issue 3: `doc_type` is too coarse — specialist routing fails for unknown prefixes
**File:** `idpo/agents/doc_analysis.py`  
**Problem:** `doc_type` returns only generic structural types (`"scanned_document"`, `"text_document"`). It never identifies `"receipt"` or `"correspondence"`. AHMN routing is 100% dependent on `vendor_cluster` (filename prefix). Unknown filenames mean no specialist ever matches.  
**Fix:** Add `semantic_doc_type` field: fast text-fingerprint classifier on OCR output.

```python
# Add to DocumentAnalysisAgent.run() after text extraction:
def _classify_semantic_doc_type(self, text: str) -> str:
    """Fast keyword-based doc type identification."""
    lower = text.lower()
    receipt_signals = sum([
        bool(re.search(r"total|subtotal|tax|cash|change|receipt|invoice", lower)),
        bool(re.search(r"[\$\₩\Rp]\s*[\d,.]+|[\d,.]+\s*(?:won|krw|idr)", lower)),
        bool(re.search(r"\b(vat|pb1|ppn|gst)\b", lower)),
    ])
    correspondence_signals = sum([
        bool(re.search(r"\bdear\b|\bsincerely\b|\bregards\b", lower)),
        bool(re.search(r"^from\s*:|^to\s*:|^re\s*:", lower, re.MULTILINE)),
        bool(re.search(r"yours\s+(?:truly|sincerely|faithfully)", lower)),
    ])
    legal_signals = sum([
        bool(re.search(r"\bcourt\b|\bplaintiff\b|\bdefendant\b|\bjudge\b", lower)),
        bool(re.search(r"case\s+(?:no|number|#)|\bfiled\b|\bserved\b", lower)),
    ])
    if receipt_signals >= 2: return "receipt"
    if correspondence_signals >= 2: return "correspondence"
    if legal_signals >= 2: return "legal_form"
    if receipt_signals == 1: return "receipt"
    if correspondence_signals == 1: return "correspondence"
    return "unknown"
```

Store result in `DAEOutput` as `semantic_doc_type`. Then update AHMN payload in `policy_advisor.py` to pass it. Update policy conditions to use it.

### P1 — Important for quality

#### Issue 4: F1 delta not yet confirmed on fresh state
**Action needed:** After P0 fixes, run `probe_3.json` and verify:
- `cord_probe_0020` gets `receipt_specialist` (not noisy_ocr variant)
- Per-field extraction fires (check `diagnostics["per_field_extraction"]` in artifact)
- Subtotal/tax swap is corrected

#### Issue 5: Tesseract not used despite being available
**File:** `idpo/agents/preprocess.py`  
**Problem:** `pytesseract` is installed, Tesseract 5.4.0 is on PATH. The `engine` param in `preprocess.ocr` is parsed in `planning.py:386`. But `preprocess.py` may not have a Tesseract code path.  
**Action:** Check if `_tesseract_ocr()` exists in `preprocess.py`. If not, add it. Enable `engine: tesseract` in `correspondence_specialist` and `noisy_ocr_rescue` policies — Tesseract handles degraded English fax/scan better than PaddleOCR.

#### Issue 6: Job-level field context not auto-accumulated
**Problem:** The job overlay mechanism (`IDPO_JOB_OVERLAY_PATH`) must be manually written. No code auto-populates field success rates across documents within a job.  
**Value:** After 5-10 documents, the system should know "in this job, `change_amount` has 30% success" and pass that to AHMN as a routing signal.  
**Implementation:** Append to `{IDPO_DATA_DIR}/jobs/{job_id}/field_context.jsonl` after each document. Read and summarize at routing time.

#### Issue 7: `avg_schema_grounding_coverage` always 0.0
**Investigation needed:** Every benchmark shows this metric as 0.0. Find where it's computed and why it's never populated. Either fix it or remove it from the paper table if it's a broken metric.

---

## Implementation Sequence

### Phase 1: Fix broken fundamentals (before any new features)

**1a. Fix policy preprocess override** — `idpo/pipeline/planning.py:330-336`  
Time: ~30 mins. Test by checking that `correspondence_specialist` docs actually get denoise when `quality_bin="A"`.

**1b. Wire guardrails relevance check into validation** — `idpo/agents/validation.py`  
Time: ~1 hour. Depends on `sentence_transformers` being installable.  
Test: Run probe, check that extracted entities get relevance scores in validation artifact.

### Phase 2: Better document identification

**2a. Add `semantic_doc_type` to `DocumentAnalysisAgent`** — `idpo/agents/doc_analysis.py`  
Time: ~45 mins. Add `_classify_semantic_doc_type()` method. Store in `DAEOutput`.

**2b. Pass `semantic_doc_type` through AHMN payload** — `idpo/pipeline/policy_advisor.py`  
Time: ~20 mins. Add to `_value_map_from_payload()` in `ahmn_core/direct_advisor.py`.

**2c. Update policy conditions to use `semantic_doc_type`** — `configs/policy_store_research.json`  
Add `"semantic_doc_type": ["receipt"]` to `receipt_specialist`, `"semantic_doc_type": ["correspondence"]` to `correspondence_specialist`. Update `_matches_conditions` in `direct_advisor.py` to support OR matching (condition matches if ANY listed condition key matches, not ALL).  
Time: ~30 mins.

**2d. Add Tesseract path in preprocess.py** (if not already present)  
Time: ~45 mins. Enable in `correspondence_specialist` and `noisy_ocr_rescue`.

### Phase 3: 5-record test

**Build `datasets/probe_5.json`:**
```
cord_validation_0020   — hard receipt (verify subtotal/tax swap fixed)
cord_validation_0006   — receipt that previously scored F1=0.889 (regression check)
funsd_82573104         — correspondence with decent OCR (test thinking mode)
funsd_82491256         — legal form (verify NOT routed to correspondence_specialist)
cord_validation_0025   — unseen CORD receipt (cold-start generalization test)
```

**Observe:**
- Policy selected per doc per condition
- `per_field_extraction` flag in extraction artifact (should be `true` for receipt docs)
- `use_thinking` flag for correspondence docs
- F1 per doc per condition
- Whether semantic_doc_type identifies types correctly

**Success criteria:**
- Receipts → `receipt_specialist` (every time, not just sometimes)
- Correspondence → `correspondence_specialist`
- Legal form → `default` or `unknown_vendor_safe` (NOT correspondence)
- F1 adaptive ≥ F1 static on at least 2 docs
- No regression: docs that previously scored well still score well

### Phase 4: Full benchmark + evidence

Run `mixed_20.json` once all P0 and P1 fixes are in place.  
If F1 adaptive > F1 static on the specialist-routed docs: paper claim stands.  
If still tied: investigate what per-field extraction is actually returning vs bulk.

---

## File Change Summary

Files modified on `feature/IDPO` vs `main`:

| File | Change |
|---|---|
| `idpo/agents/extraction_prompts.py` | N/A rule, per-field prompt builders |
| `idpo/agents/extraction_providers.py` | JSON schema enforcement, Ollama chat wrapper |
| `idpo/agents/llm_extraction.py` | Per-field extraction, thinking mode, policy flags |
| `idpo/agents/validation.py` | Grounding check, fixed amount validation, extended date patterns |
| `ahmn_core/direct_advisor.py` | Specialist exclusivity in candidate selection |
| `configs/policy_store_research.json` | per_field_extraction + use_thinking for specialists |
| `configs/policy_store_baseline.json` | New file — default-only store for static condition |
| `scripts/run_idpo_benchmark.py` | Static uses baseline store; temp file renamed to case_id |
| `datasets/mixed_20.json` | General field descriptions (not dataset-specific) |
| `datasets/probe_3.json` | New file — 3-doc quick test pack |

Files NOT yet modified but targeted:
| File | Planned change |
|---|---|
| `idpo/pipeline/planning.py` | Fix policy preprocess override (P0-1) |
| `idpo/agents/doc_analysis.py` | Add semantic_doc_type classifier (P2a) |
| `idpo/pipeline/policy_advisor.py` | Pass semantic_doc_type to AHMN (P2b) |
| `ahmn_core/direct_advisor.py` | OR logic in condition matching (P2c) |
| `idpo/agents/validation.py` | Wire guardrails relevance check (P1b) |
| `idpo/agents/preprocess.py` | Tesseract OCR path (P1e) |
| `datasets/probe_5.json` | 5-doc test pack (Phase 3) |

---

## Do Not Touch

- `policy_store_baseline.json` — must stay default-only
- `field_descriptions` in `mixed_20.json` — must stay general (not CORD/FUNSD specific)
- `per_field_extraction` on generic policies — specialists only
- `use_thinking` on receipt policies — adds 30-60s latency with no numeric accuracy benefit
- Paper claim scope — routing + specialist extraction story only

---

## PaddleOCR vs Tesseract

| Scenario | Recommendation |
|---|---|
| CORD receipts (Korean/Indonesian text) | PaddleOCR — superior for Asian text |
| FUNSD correspondence (degraded English fax) | Tesseract 5.4 — better on degraded Latin text |
| Policy default | PaddleOCR |
| `correspondence_specialist` | Tesseract (to be added) |
| `noisy_ocr_rescue` | Tesseract (to be added) |

---

## Quick Reference Commands

```bash
# Run 3-doc probe
.venv/Scripts/python scripts/run_idpo_benchmark.py --pack datasets/probe_3.json --config configs/idpo_research_config.json

# Run 5-doc probe (build probe_5.json first per Phase 3 above)
.venv/Scripts/python scripts/run_idpo_benchmark.py --pack datasets/probe_5.json --config configs/idpo_research_config.json

# Inspect results
.venv/Scripts/python scripts/bench_diag.py

# Run full 20-doc benchmark
.venv/Scripts/python scripts/run_idpo_benchmark.py --pack datasets/mixed_20.json --config configs/idpo_research_config.json

# Check AHMN state (should be empty after reset)
ls E:/Research Project/Code/idpo-data/ahmn/direct_advisor/

# Clear AHMN state if needed
rm E:/Research Project/Code/idpo-data/ahmn/direct_advisor/*.json

# Run tests
.venv/Scripts/python -m pytest idpo/tests/ -x -q
```
