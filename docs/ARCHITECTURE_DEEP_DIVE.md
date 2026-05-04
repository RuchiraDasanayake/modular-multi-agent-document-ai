# Architecture Deep Dive — AHMN, IDPO, Guardrails & XAI-HITL

> A plain-language guide to every component, how they work internally, and how they talk to each other.

---

## Table of Contents

1. [The Big Picture](#1-the-big-picture)
2. [AHMN — Adaptive Hierarchical Memory Network](#2-ahmn--adaptive-hierarchical-memory-network)
3. [IDPO — Intelligent Document Processing Orchestrator](#3-idpo--intelligent-document-processing-orchestrator)
4. [Guardrails — Hallucination & Quality Detection](#4-guardrails--hallucination--quality-detection)
5. [XAI-HITL — Explainability & Human-in-the-Loop](#5-xai-hitl--explainability--human-in-the-loop)
6. [Integration Map — How All 4 Connect](#6-integration-map--how-all-4-connect)
7. [End-to-End Document Flow](#7-end-to-end-document-flow)
8. [Policy Alignment Across Services](#8-policy-alignment-across-services)
9. [Learning Loop — How the System Gets Smarter](#9-learning-loop--how-the-system-gets-smarter)

---

## 1. The Big Picture

```
                        ┌──────────────┐
                        │   Gateway    │  ← JWT auth, routing
                        │  (port 8000) │
                        └──────┬───────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
     ┌──────▼──────┐   ┌──────▼──────┐   ┌───────▼──────┐
     │    AHMN     │   │  Guardrails │   │   XAI-HITL   │
     │ (port 8001) │   │ (port 8002) │   │  (port 8003) │
     │  Memory &   │   │ Hallucin.  │   │ Explanations │
     │  Learning   │   │ Detection  │   │ & Feedback   │
     └──────▲──────┘   └──────▲──────┘   └───────▲──────┘
            │                  │                  │
            └──────────────────┼──────────────────┘
                               │
                        ┌──────▼──────┐
                        │    IDPO     │
                        │ (port 8004) │
                        │ Orchestrator│
                        └─────────────┘
```

**One-sentence summaries:**

| Service | Role |
|---------|------|
| **AHMN** | "The brain" — remembers which processing strategy works best for each document type and improves over time |
| **IDPO** | "The conductor" — runs a 14-agent pipeline that actually processes each document, and calls the other 3 services |
| **Guardrails** | "The quality gate" — checks extraction output against 5 layers of validation to catch hallucinations and errors |
| **XAI-HITL** | "The explainer + reviewer" — generates human-readable explanations of answers and captures expert corrections |

---

## 2. AHMN — Adaptive Hierarchical Memory Network

### What it does in simple terms

Think of AHMN as a **librarian with a great memory**. Every time a document arrives, AHMN says:
> "I've seen documents like this before. Last time, the `table_heavy` processing strategy got an F1 score of 0.85. Use that one."

If it's a document type AHMN has never seen, it uses **RABI** (a cold-start mechanism) to say:
> "I haven't seen this exact type, but it looks similar to invoices and receipts. Those worked well with `table_heavy`, so start with that."

After the document is processed, IDPO tells AHMN how well it went (F1 score). AHMN updates its memory so the next recommendation is even better.

### Three-tier memory hierarchy

```
┌─────────────────────────────────────────────────────────┐
│  STM (Short-Term Memory)                                │
│  Storage: Redis   TTL: 30 minutes                       │
│  What: Active advice contexts (advice_id → input data)  │
│  Why: Link a recommendation to its outcome when IDPO    │
│       reports back minutes later                        │
├─────────────────────────────────────────────────────────┤
│  MTM (Mid-Term Memory)                                  │
│  Storage: PostgreSQL table `mtm_outcomes`               │
│  What: Every processing run with its F1 score           │
│  Why: Raw training data — collected fast, evaluated     │
│       later during promotion cycles                     │
├─────────────────────────────────────────────────────────┤
│  LTM (Long-Term Memory)                                 │
│  Storage: PostgreSQL table `ltm_validated_policies`     │
│         + pgvector embeddings (384-dim)                 │
│  What: Proven context→policy mappings with Beta(α,β)    │
│  Why: The actual "knowledge" — only policies that have  │
│       demonstrated F1 > 0.50+ get promoted here         │
└─────────────────────────────────────────────────────────┘
```

### Core algorithms

#### Thompson Sampling (policy selection)

Each policy has a Beta(α, β) distribution. The **mean** α/(α+β) represents how good that policy is.

- **Default mode (deterministic):** Picks the policy with the highest expected value (mean). Same input → same result every time.
- **Explore mode** (`?explore=true`): Draws a random sample from each Beta distribution and picks the highest. This lets the system try less-proven policies occasionally. Even in explore mode, the random seed is derived from the input, so identical requests return identical results.

```
Example:
  table_heavy  → Beta(α=12, β=3)  → mean = 0.80 ← selected
  forms        → Beta(α=6,  β=4)  → mean = 0.60
  default      → Beta(α=2,  β=3)  → mean = 0.40
```

#### RABI (cold-start handling)

When AHMN sees a new document type, it has no history (α=1, β=1, flat prior). RABI fixes this:

1. **Query LTM** for the 5 most similar contexts (by embedding cosine similarity)
2. **Weight** neighbors using softmax: closer neighbors count more
3. **Transfer** their (α-1, β-1) pseudocounts: `α_init = 1 + Σ wᵢ·(αᵢ - 1)`

**Result:** Instead of starting from scratch, a new document type starts with an informed prior. Reduces cold-start regret from O(K) to O(L·d_avg).

#### DAAF (drift-aware forgetting)

Document distributions change over time (new vendors, new formats). DAAF handles this:

1. **Detects drift** by comparing two sliding windows (recent vs older observations)
2. **Separates noise from drift:** Variance within a window = noise (ignore). Mean shift between windows = drift (act on)
3. **Computes optimal forgetting rate:** γ* = √(Δ² / ln(t))
4. **Applies forgetting:** `α_new = 1 + (1-γ)(α_old - 1)` — decays old evidence proportional to drift

Three drift types:
- **NONE** (Δ < 0.05): No action
- **GRADUAL** (0.05 ≤ Δ < 0.15): Gentle forgetting
- **ABRUPT** (Δ ≥ 0.15): Aggressive forgetting (double the rate)

### Background jobs

| Job | Interval | What it does |
|-----|----------|-------------|
| **Promotion** | Every 30 min | Promotes MTM outcomes to LTM if F1 > 0.50 and ≥ 2 observations. Updates α/β and confidence. |
| **Forgetting** | Every 6 hours | Decays inactive LTM entries (> 7 days). Archives + deletes entries below confidence 0.35. |

### API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/advice` | Get policy recommendation (deterministic by default) |
| POST | `/advice?explore=true` | Get recommendation with Thompson Sampling exploration |
| POST | `/advice/log` | Log outcome (F1 score) — triggers learning |
| POST | `/advice/feedback` | Record human correction flag |
| GET | `/dashboard/stats` | Platform-wide statistics |
| GET | `/dashboard/memory/stm` | Active STM entries |
| GET | `/dashboard/memory/mtm` | Recent processing outcomes |
| GET | `/dashboard/memory/ltm` | All learned policies |

---

## 3. IDPO — Intelligent Document Processing Orchestrator

### What it does in simple terms

IDPO is the **assembly line**. It takes a raw document (PDF, image, JSON) and runs it through 14 specialized agents, each handling one step of processing. Think of it as a factory where each station does one thing really well.

### The 14-agent pipeline

```
Document In
     │
     ▼
 ┌─────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────────┐
 │ 1.Intake │──▶│ 2.Preprocess │──▶│ 3.Doc        │──▶│ 4.Categorize  │
 │ (ingest) │   │ (OCR/clean)  │   │   Analysis   │   │  (classify)   │
 └─────────┘   └──────────────┘   └──────────────┘   └───────────────┘
                                                              │
     ┌────────────────────────────────────────────────────────┘
     ▼
 ┌──────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────────┐
 │ 5.Policy │──▶│ 6.Chunking   │──▶│ 7.Retrieval  │──▶│ 8.LLM Extract │
 │ (select) │   │ (split text) │   │  (RAG fetch) │   │  (entities)   │
 └──────────┘   └──────────────┘   └──────────────┘   └───────────────┘
                                                              │
     ┌────────────────────────────────────────────────────────┘
     ▼
 ┌──────────────┐   ┌──────────┐   ┌──────────────┐   ┌───────────────┐
 │ 9.Structure  │──▶│10.Answer │──▶│ 11.Validate  │──▶│ 12.Recovery   │
 │ (sections)   │   │  (Q&A)   │   │  (checks)    │   │  (fix errors) │
 └──────────────┘   └──────────┘   └──────────────┘   └───────────────┘
                                                              │
     ┌────────────────────────────────────────────────────────┘
     ▼
 ┌──────────────┐   ┌──────────┐
 │ 13.Escalate  │──▶│ 14.Export │──▶ Results Out (JSON / Excel)
 │ (flag hard)  │   │ (output) │
 └──────────────┘   └──────────┘
```

### Key agents explained

| # | Agent | What it does |
|---|-------|-------------|
| 1 | **Intake** | Reads file (PDF, image, JSON), extracts raw text. Handles encoding, file types. |
| 2 | **Preprocess** | Runs OCR (Tesseract), deskews images, denoises. Config varies by policy (e.g., `table_heavy` uses PSM 6 for table layouts). |
| 3 | **Doc Analysis** | Characterizes document: quality_bin (good/fair/poor), complexity_score, content_profile (text-heavy, table-heavy, mixed). |
| 4 | **Categorize** | Classifies document type: invoice, clinical_summary, insurance_claim, etc. |
| 5 | **Policy** | Selects processing policy from `policy_store.json` based on doc type, quality, complexity. Potentially overridden by AHMN advice. |
| 6 | **Chunking** | Splits text into chunks for retrieval. Chunk size varies by policy (e.g., 600 tokens for forms, 1000 for tables). |
| 7 | **Retrieval** | Hybrid search: dense (vector similarity) + sparse (BM25), fused with MMR reranking. Finds the most relevant chunks for extraction. |
| 8 | **LLM Extract** | Entity extraction via LLM. The heart of processing — extracts structured fields from unstructured text. |
| 9 | **Structure** | Identifies sections and generates summaries. |
| 10 | **Answer** | Generates Q&A pairs from extracted data. |
| 11 | **Validate** | Field-level consistency checks (before guardrails). |
| 12 | **Recovery** | Attempts to fix extraction errors (re-extract failed fields with alternate strategies). |
| 13 | **Escalate** | Marks fields that couldn't be extracted or validated for human review. |
| 14 | **Export** | Outputs final results as JSON or Excel. |

### Hybrid retrieval system

IDPO uses a **two-signal retrieval approach** for maximum accuracy:

```
┌───────────────────────────────────────┐
│            Query: "total amount"      │
│                    │                  │
│         ┌─────────┴─────────┐        │
│         ▼                   ▼        │
│   Dense Search         BM25 Search   │
│  (vector cosine)     (keyword TF-IDF)│
│         │                   │        │
│         └─────────┬─────────┘        │
│                   ▼                  │
│         Reciprocal Rank Fusion       │
│                   │                  │
│                   ▼                  │
│          MMR Reranking               │
│    (Maximal Marginal Relevance)      │
│    removes near-duplicate chunks     │
│                   │                  │
│                   ▼                  │
│          Top-K chunks returned       │
└───────────────────────────────────────┘
```

### API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/idpo/run` | Upload documents and process (multipart form) |
| GET | `/api/idpo/runs/{id}/results.xlsx` | Download processed results |

---

## 4. Guardrails — Hallucination & Quality Detection

### What it does in simple terms

Guardrails is the **quality inspector**. After the pipeline extracts data from a document, Guardrails checks: "Is this extraction trustworthy, or did the LLM hallucinate?"

It runs **5 independent checks** in sequence. All 5 must pass for the extraction to be considered valid.

### The 5 validation layers

```
Layer 1: Schema Adherence
   "Are all required fields present and correctly typed?"
   ├── Pydantic model validation per document type
   ├── 7 document schemas: Invoice, Receipt, ClinicalSummary, etc.
   └── Score: 1.0 (all valid) or fraction of valid fields

Layer 2: Internal Consistency
   "Do the numbers add up?"
   ├── Math: subtotal + tax ≈ total (± tolerance)
   ├── No negative amounts where positives expected
   ├── No future dates for historical documents
   ├── Medical: dosage within safe ranges
   └── Score: fraction of consistency rules passed

Layer 3: Domain Rules
   "Does this make business sense?"
   ├── Tax rate plausibility (0-30%)
   ├── Vendor fraud indicators
   ├── Suspicious keyword detection
   └── Score: fraction of domain rules passed

Layer 4: PII Leakage
   "Is sensitive data properly handled?"
   ├── Presidio-based entity recognition
   ├── Context-aware: SSN ok in insurance, not in invoice
   ├── Checks: SSN, credit cards, emails, phone numbers
   └── Score: 1.0 (no leakage) or 0.0 (leakage detected)

Layer 5: Faithfulness (Hallucination Detection)
   "Is the extraction supported by the source text?"
   ├── Encodes extracted fields with sentence-transformers
   ├── Computes cosine similarity against source chunks
   ├── Threshold: 0.78 (below = likely hallucinated)
   └── Score: average cosine similarity across fields
```

### How faithfulness detection works

```
Extracted field: "Total: $15,234.00"
Source chunks:   ["The grand total is $15,234.00 including tax",
                  "Payment due within 30 days"]

Step 1: Embed "Total: $15,234.00" → vector_field (384-dim)
Step 2: Embed each source chunk  → vectors_source[]
Step 3: Cosine similarity = dot(field, source) / (|field| × |source|)
Step 4: Average similarity = 0.92 → PASS (> 0.78 threshold)

If extracted "Total: $99,999.00" but source says "$15,234.00":
   Cosine similarity = 0.41 → FAIL (hallucination detected)
```

### API endpoint

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/guardrails/validate` | Validate extraction output against 5 layers |

**Input:**
```json
{
  "document_context": "invoice",
  "query": "Extract all fields",
  "answer_json": { "total": 15234.00, "vendor": "Acme" },
  "source_contexts": ["The grand total is $15,234.00..."]
}
```

**Output:**
```json
{
  "overall_passes": true,
  "validation_results": [
    { "name": "schema_adherence", "score": 1.0, "is_pass": true },
    { "name": "internal_consistency", "score": 0.95, "is_pass": true },
    { "name": "domain_rules", "score": 1.0, "is_pass": true },
    { "name": "pii_leakage", "score": 1.0, "is_pass": true },
    { "name": "faithfulness", "score": 0.89, "is_pass": true }
  ],
  "audit_log_id": "abc-123",
  "processing_time_ms": 145
}
```

---

## 5. XAI-HITL — Explainability & Human-in-the-Loop

### What it does in simple terms

XAI-HITL has two halves:

**XAI (Explainability):** When the system extracts an answer from a document, XAI explains *why* — which words mattered, how the model reasoned. Think of it as showing the model's "thought process."

**HITL (Human-in-the-Loop):** Domain experts review answers and explanations. Their corrections feed back into AHMN to improve future recommendations.

### XAI Engine

The engine uses three complementary explanation techniques:

```
┌────────────────────────────────────────────────────────┐
│  Input: paragraph + question                           │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 1. DistilBERT Q&A                                │  │
│  │    Fine-tuned on SQuAD (extractive Q&A)          │  │
│  │    Finds the answer span in the paragraph        │  │
│  └──────────────────┬───────────────────────────────┘  │
│                     │                                  │
│  ┌──────────────────▼───────────────────────────────┐  │
│  │ 2. Attention Weights                             │  │
│  │    Shows which input tokens the model focused on │  │
│  │    "The model paid 73% attention to '$15,234'"   │  │
│  └──────────────────┬───────────────────────────────┘  │
│                     │                                  │
│  ┌──────────────────▼───────────────────────────────┐  │
│  │ 3. LIME (Local Interpretable Explanations)       │  │
│  │    Perturbs input → sees what changes answer     │  │
│  │    30-80 dynamic samples, cached for speed       │  │
│  │    "Removing 'total' drops confidence by 45%"    │  │
│  └──────────────────┬───────────────────────────────┘  │
│                     │                                  │
│  Output: answer + confidence + highlighted_spans +     │
│          derivation_steps + token_importance[]          │
└────────────────────────────────────────────────────────┘
```

### HITL Feedback

Experts can submit structured feedback on any answer:

| Field | Options |
|-------|---------|
| **Type** | CORRECT, INCORRECT, PARTIALLY_CORRECT, NEEDS_MORE_CONTEXT, XAI_UNCLEAR |
| **Priority** | LOW, MEDIUM, HIGH, CRITICAL |
| **Ratings** (1-5) | explanation_quality, highlight_accuracy, xai_helpfulness |
| **Free text** | comment, corrected_answer |

### How HITL feedback flows back to AHMN

```
Expert submits feedback
    │
    ▼
XAI-HITL stores feedback entry
    │
    ▼
IDPO reads feedback (via integration layer)
    │
    ▼
POST /advice/feedback → AHMN
    human_corrected = true/false
    │
    ▼
AHMN sets flag in MTM outcome
    │
    ▼
During promotion cycle:
    Human-corrected outcomes weighted higher
    Corrects systematic biases in Beta(α,β)
```

### API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/xai/ask` | Answer + explain (paragraph + question) |
| GET | `/api/xai/explanation/{id}` | Retrieve cached explanation |
| POST | `/api/hitl/feedback` | Submit expert feedback |
| GET | `/api/hitl/feedback/{id}` | Get single feedback entry |
| GET | `/api/hitl/stats` | Feedback statistics |

---

## 6. Integration Map — How All 4 Connect

### Direct service-to-service calls

```
                    ┌──────────────────────────────────┐
                    │            IDPO                   │
                    │        (Orchestrator)              │
                    └─┬──────────┬──────────┬──────────┘
                      │          │          │
              Step 1  │  Step 3  │  Step 4  │  Step 5
            (before)  │ (after)  │ (after)  │ (after)
                      │          │          │
                      ▼          ▼          ▼
                   ┌──────┐  ┌──────┐  ┌──────┐
                   │ AHMN │  │Guard-│  │ XAI- │
                   │      │  │rails │  │ HITL │
                   └──────┘  └──────┘  └──────┘
```

| Step | When | From → To | What | Endpoint |
|------|------|-----------|------|----------|
| 1 | **Before** pipeline | IDPO → AHMN | "What policy should I use for this invoice?" | `POST /advice` |
| 2 | **During** pipeline | IDPO internal | 14 agents process document | — |
| 3 | **After** extraction | IDPO → Guardrails | "Is this extraction valid?" | `POST /guardrails/validate` |
| 4 | **After** extraction | IDPO → XAI-HITL | "Explain this answer" | `POST /xai/ask` |
| 5 | **After** everything | IDPO → AHMN | "Here's how it went (F1=0.82)" | `POST /advice/log` |

### What each service knows about the others

| Service | Knows about | Doesn't know about |
|---------|-------------|-------------------|
| **AHMN** | Nothing — it's passive. Receives requests and responds. | IDPO pipeline details, guardrails layers, XAI internals |
| **IDPO** | All 3 services. Calls each at the right time. | AHMN's internal Thompson Sampling, Guardrail internals, XAI model weights |
| **Guardrails** | Nothing — it's passive. Validates what it's given. | AHMN policies, IDPO pipeline stages, XAI explanations |
| **XAI-HITL** | Nothing — it's passive. Answers questions and stores feedback. | AHMN policies, IDPO pipeline, Guardrail results |

### Shared data structures

All services align on these common identifiers:

| Concept | Used by | Example values |
|---------|---------|---------------|
| `advice_id` (UUID) | AHMN, IDPO | Links recommendation → outcome |
| `policy_id` (string) | AHMN, IDPO, Policy Store | `"forms"`, `"table_heavy"`, `"scanned_text"`, `"mixed_content"`, `"default"` |
| `doc_type` (string) | All 4 services | `"invoice"`, `"clinical_summary"`, `"receipt"` |
| `f1_score` (float) | IDPO, AHMN | 0.0–1.0 extraction quality |

### Graceful degradation

If any service is unreachable, IDPO continues with defaults:

| Service down | Fallback behavior |
|-------------|-------------------|
| AHMN unreachable | Uses `default` policy from `policy_store.json` |
| Guardrails unreachable | Marks validation as "skipped", continues processing |
| XAI-HITL unreachable | Skips explanation generation, continues export |

---

## 7. End-to-End Document Flow

Here's what happens when you upload an invoice:

```
User uploads invoice.pdf via Gateway
         │
         ▼
    ┌─────────┐
    │ Gateway  │ Authenticates JWT, routes to IDPO
    └────┬────┘
         │
         ▼
    ┌─────────┐
    │  IDPO   │
    │         │
    │ Step 1: │ POST /advice → AHMN
    │         │   Input:  { doc_type: "invoice", vendor: "Acme" }
    │         │   Output: { policy_id: "table_heavy", confidence: 0.82 }
    │         │
    │ Step 2: │ Run 14-agent pipeline with table_heavy policy
    │         │   • OCR with PSM 6 (table layout mode)
    │         │   • Chunk size 1000, overlap 150
    │         │   • Extract: vendor, date, total, line_items, tax
    │         │   • Result: { vendor: "Acme Corp", total: 15234.00, ... }
    │         │
    │ Step 3: │ POST /guardrails/validate
    │         │   • Schema: ✅ All invoice fields present
    │         │   • Consistency: ✅ subtotal + tax = total
    │         │   • Domain: ✅ Tax rate 8% (plausible)
    │         │   • PII: ✅ No leakage
    │         │   • Faithfulness: ✅ 0.91 similarity vs source
    │         │   → overall_passes: true
    │         │
    │ Step 4: │ POST /xai/ask
    │         │   Input:  { paragraph: "...", question: "What is the total?" }
    │         │   Output: { answer: "$15,234.00", confidence: 0.94,
    │         │             highlights: ["$15,234.00"], lime_importance: [...] }
    │         │
    │ Step 5: │ POST /advice/log → AHMN
    │         │   Input:  { advice_id: UUID, policy_id_used: "table_heavy",
    │         │             metrics: { f1_score: 0.88 } }
    │         │   AHMN updates: table_heavy Beta(α+0.88, β+0.12)
    │         │   Drift check: Δ=0.02 → NONE
    │         │
    └─────────┘
         │
         ▼
    Results returned to user (JSON + optional Excel)
```

---

## 8. Policy Alignment Across Services

All 4 services reference the same 5 policies defined in `configs/policy_store.json`:

| Policy ID | Best for | OCR config | Chunks | Retrieval | Extraction targets |
|-----------|----------|-----------|--------|-----------|--------------------|
| `forms` | Forms, clinical summaries | 2 passes, PSM 4 | 600 / 100 overlap | k=8, dense | patient_name, diagnosis, medications |
| `scanned_text` | Reports, letters, narratives | Enhanced, PSM 3 | 800 / 150 overlap | k=6, sparse-boost | title, summary, key_points |
| `table_heavy` | Invoices, receipts, ledgers | PSM 6 (tables), dpi 300 | 1000 / 150 overlap | k=10, MMR λ=0.8 | vendor, date, total, line_items, tax |
| `mixed_content` | Contracts, agreements | Multi-pass | 800 / 200 overlap | k=8, balanced | parties, effective_date, terms, clauses |
| `default` | Unknown / fallback | Standard 1 pass | 500 / 100 overlap | k=5, basic | generic fields |

**AHMN seeds** its LTM with these 5 policies on first boot, each with initial Beta distributions biased toward success (e.g., `table_heavy` starts with α=8, β=2 for invoices).

---

## 9. Learning Loop — How the System Gets Smarter

```
    ┌─────────────────────────────────────────────────────┐
    │                  LEARNING LOOP                       │
    │                                                     │
    │  ┌─────────┐    recommend     ┌─────────┐          │
    │  │  AHMN   │ ───────────────▶ │  IDPO   │          │
    │  │ (Brain) │                  │(Pipeline)│          │
    │  │         │ ◀─────────────── │         │          │
    │  │         │    f1_score      │         │          │
    │  └────┬────┘                  └────┬────┘          │
    │       │                            │               │
    │       │  α += reward               │ validate      │
    │       │  β += (1-reward)           │               │
    │       │                            ▼               │
    │       │                     ┌───────────┐          │
    │       │                     │ Guardrails│          │
    │       │  ◀────────────────  │           │          │
    │       │  guardrails pass    └───────────┘          │
    │       │  contributes to                            │
    │       │  f1_proxy score                            │
    │       │                                            │
    │       │  human correction   ┌───────────┐          │
    │       │  ◀────────────────  │ XAI-HITL  │          │
    │       │                     │ (Experts) │          │
    │       │                     └───────────┘          │
    └───────┴────────────────────────────────────────────┘
```

### The two learning signals

**Signal 1: Automated F1 proxy (every document)**
```
F1_proxy = 0.5 × entity_f1 + 0.3 × guardrails_pass_rate + 0.2 × avg_confidence
```
- Fast — computed immediately after processing
- Updates Beta distribution: α += reward, β += (1-reward)
- Drives rapid adaptation

**Signal 2: Human feedback (selective, high-value)**
- Expert marks an outcome as correct/incorrect via HITL
- Sets `human_corrected` flag in MTM
- During promotion cycles, human-corrected outcomes are weighted higher
- Corrects systematic biases that automated metrics miss

### What "getting smarter" looks like over time

```
Day 1:   AHMN has only seed data. Recommends table_heavy for invoices
         with 60% confidence. F1 = 0.72.

Day 7:   After 50 invoices, table_heavy Beta(α=42, β=10). Mean = 0.81.
         Confidence = 0.89. F1 has improved because IDPO uses better OCR
         settings from the policy.

Day 30:  New vendor "GlobalTech" sends invoices with unusual layouts.
         RABI detects similarity to existing invoice context, transfers
         a warm prior. First-attempt F1 = 0.78 instead of groping at 0.5.

Day 60:  Vendor "OldCorp" changes their invoice format. DAAF detects
         drift (Δ = 0.12, GRADUAL). Increases forgetting rate.
         Old evidence decays, system adapts within ~10 documents.

Day 90:  Expert reviews 5 tricky extractions via HITL. Marks 2 as
         incorrect. AHMN downgrades those context→policy mappings.
         System stops making the same mistakes.
```

---

## Quick Reference Card

### Service URLs (Docker Compose)

| Service | Internal URL | External (via Gateway) |
|---------|-------------|----------------------|
| Gateway | `http://gateway:8000` | `http://localhost:8000` |
| AHMN | `http://ahmn:8001` | `http://localhost:8000/api/advice/*` |
| Guardrails | `http://guardrails:8002` | `http://localhost:8000/api/guardrails/*` |
| XAI-HITL | `http://xai-hitl:8003` | `http://localhost:8000/api/xai/*`, `/api/hitl/*` |
| IDPO | `http://idpo:8004` | `http://localhost:8000/api/idpo/*` |

### Key files per component

| Component | Entry point | Core logic | Config |
|-----------|------------|------------|--------|
| AHMN | `ahmn_core/main.py` | `ahmn_core/services/rabi.py`, `drift_forgetting.py`, `scheduler.py` | `ahmn_core/seeds.py` |
| IDPO | `idpo/cli.py` | `idpo/pipeline/orchestrator.py`, `idpo/integration.py` | `configs/policy_store.json`, `configs/config.json` |
| Guardrails | `guardrails/main.py` | `guardrails/core/ensemble.py`, `guardrails/core/validation.py` | `guardrails/models.py` (schemas) |
| XAI-HITL | `xai_hitl/main.py` | `xai_hitl/engine/xai_engine.py` | `xai_hitl/hitl/models.py` |
