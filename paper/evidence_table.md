# IDPO Evidence Fact Table

> **Superseded.** This table records earlier, unpaired adaptive-only runs. The paper's numbers come from the paired
> static vs `adaptive_safe` runs in [`FINAL_EVIDENCE.md`](FINAL_EVIDENCE.md); do not cite figures from this file.

> Permanent frontend job: `idpo_research_permanent_01`
> This file tracks only evidence surfaces that are currently defensible for the paper.

---

## 1. Locked facts

| Item | Value |
|---|---|
| Branch | `feature/IDPO` |
| Permanent job | `idpo_research_permanent_01` |
| Benchmark mode for current paper runs | `--adaptive-only` |
| Reward policy | score only against pack-declared expected fields; canonical fields are fallback only |
| Local LLM | `qwen3.5:9b` via Ollama |
| Local LLM params | `temperature=0.0`, `top_p=0.8`, `top_k=20`, `num_ctx=8192` |
| OCR primary | PaddleOCR with pre-processing |
| Pre-processing | upscale to 1600px, grayscale, autocontrast, unsharp mask |

---

## 2. Primary evidence to use

### CORD receipts

| Metric | Value |
|---|---|
| Docs | 75 |
| Exact F1 | **0.763** |
| Perfect docs | **56%** |
| Precision | strong practical claim: near-zero hallucination on receipts |
| Main claim use | **Yes - primary headline** |

Why it matters:
- Zero-shot
- No templates
- Unseen Korean receipt images
- Strongest evidence surface in the repo

### Diverse document benchmark (clean)

Source:
- `datasets/research_batch_diverse_clean_20.json`
- benchmark `benchmark_1777174546`
- 11 invoices + 9 curated DocVQA business documents

| Metric | Value |
|---|---|
| Docs | 20 |
| Benchmark exact F1 | **0.5641** |
| Validation pass rate | **0.90** |
| Avg grounding coverage | **0.975** |
| Avg latency | **20,183.49 ms** |
| Policy distribution | `noisy_ocr_rescue=9`, `default=5`, `scanned_text=4`, `noisy_ocr_precision_local=2` |
| Main claim use | **Yes - cross-document support** |

Clean-pack domain breakdown:

| Domain | Docs | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|
| Invoices | 11 | 22 | 14 | 22 | 0.6111 | 0.5000 | **0.5500** |
| DocVQA business docs | 9 | 11 | 7 | 8 | 0.6111 | 0.5789 | **0.5946** |
| Overall | 20 | 33 | 21 | 30 | 0.6111 | 0.5238 | **0.5641** |

Interpretation:
- The frozen clean diverse rerun already uses final validated normalized fields for exact scoring.
- The benchmark-exported exact F1 and the recomputed field totals now agree: **0.5641**.

---

## 3. Evidence to quarantine

### Raw diverse benchmark

| Item | Value |
|---|---|
| Benchmark | `benchmark_1777140984` |
| Docs | 34 |
| Exact F1 | 0.486 |
| Use in paper | **No** |

Reason:
- Several DocVQA field mappings were wrong in the generated pack.
- Bad examples included:
  - `phone_number -> "Mr. Dominick Griffo"`
  - `address -> "David Orloff, M.D."`
- Keep as internal stress-test only.

### FUNSD training-set heavy runs

| Risk | Reason |
|---|---|
| Empty expected fields | some cases have no usable QA pairs |
| Garbage targets | page numbers or long unrelated strings appear as field values |
| OCR ceiling | degraded fax scans dominate failure mode |

Use FUNSD only as secondary evidence unless the case set is manually curated.

---

## 4. Worked examples worth showing

| Case | Document type | Exact result | Why it matters |
|---|---|---|---|
| `docvqa_14388` | business document | F1 = **1.0000** | clean non-receipt success |
| `invoice_0006` | invoice | F1 = **0.5000** | core fields right, strict exact scoring penalizes missing address tails |
| `invoice_0015` | invoice | F1 = **0.5714** | shows partial extraction on long vendor/customer strings |
| `docvqa_14179` | business document | F1 = **0.0000** | honest failure case caused by OCR/layout confusion |

See [PAPER_LOG.md](/e:/Research%20Project/Code/IDPO/paper/PAPER_LOG.md) for exact expected vs extracted values.

---

## 5. Current research position

Use this framing:

> IDPO is a zero-shot adaptive document extraction system that works without templates or task-specific training. On 75 unseen CORD receipts it reaches exact F1 0.763, and on a curated 20-document diverse benchmark spanning invoices and business documents it reaches exact F1 0.5641, with 0.975 grounding coverage and 0.90 validation pass rate.

Do not use this framing:

> adaptive beats static by X

Reason:
- adaptive/static exact deltas are still not the paper's strongest evidence surface
- the paper is better positioned against template-based ETL/IDP systems, not against its own static fallback

---

## 6. Operational facts

| Item | Value |
|---|---|
| Frontend visibility | all benchmark runs are registered to the permanent job |
| Job file | `E:/Research Project/Code/idpo-data/frontend/jobs/idpo_research_permanent_01.json` |
| Latest clean diverse benchmark | `E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777174546` |
| Latest raw diverse benchmark | `E:/Research Project/Code/idpo-data/runs/benchmarks/benchmark_1777140984` |

---

## 7. Remaining technical debt

| Item | Status |
|---|---|
| historical `semantic_doc_type` omission in benchmark artifacts | fixed on current branch; older bundles remain incomplete |
| benchmark exact scoring vs final normalized fields | fixed in frozen rerun `benchmark_1777174546` |
| guardrails relevance check wiring | still disconnected |
| policy preprocess override precedence | still needs audit |
