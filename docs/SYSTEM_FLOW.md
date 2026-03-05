# System Flow Documentation

> Complete reference for how the Modular Multi-Agent Document AI system operates, including component interactions, data flow, learning loops, and background processes.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Service Map](#service-map)
3. [End-to-End Request Flow](#end-to-end-request-flow)
4. [Integration Cycle (IDPO Orchestration)](#integration-cycle)
5. [F1 Score Computation](#f1-score-computation)
6. [AHMN Learning Loop](#ahmn-learning-loop)
7. [Memory Hierarchy (STM → MTM → LTM)](#memory-hierarchy)
8. [Background Jobs](#background-jobs)
9. [Human-in-the-Loop (HITL) Feedback](#hitl-feedback)
10. [Guardrails Validation Pipeline](#guardrails-validation)
11. [XAI Explanation Engine](#xai-explanation-engine)

---

## Architecture Overview

The system consists of **5 microservices**, a **PostgreSQL + pgvector** database, a **Redis** cache, and a **Next.js frontend** — all orchestrated via Docker Compose (8 containers total).

```
┌──────────────┐
│   Frontend   │  Next.js 15 (port 3000)
│   (React 19) │
└──────┬───────┘
       │ HTTP
       ▼
┌──────────────┐
│   Gateway    │  FastAPI reverse proxy (port 8000)
│  (Auth/JWT)  │  JWT authentication, request routing
└──────┬───────┘
       │ Internal HTTP
       ▼
┌──────────────────────────────────────────────────┐
│                     IDPO                          │
│         Intelligent Document Processing           │
│              Orchestrator (port 8004)              │
│                                                    │
│  ┌─────────┐  ┌──────────┐  ┌─────────────────┐  │
│  │  Agents │  │ Pipeline │  │   Integration   │  │
│  │ (14+)   │  │ Executor │  │     Layer       │  │
│  └─────────┘  └──────────┘  └────────┬────────┘  │
└──────────────────────────────────────┼────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
       ┌──────────┐            ┌──────────────┐         ┌──────────┐
       │   AHMN   │            │  Guardrails  │         │ XAI-HITL │
       │ (port    │            │  (port 8002) │         │ (port    │
       │  8001)   │            │              │         │  8003)   │
       │          │            │  Multi-layer │         │          │
       │ Adaptive │            │  validation  │         │ Explain- │
       │ Hierarch │            │  ensemble    │         │ ability  │
       │ Memory   │            │              │         │ + Human  │
       │ Network  │            │              │         │ Review   │
       └────┬─────┘            └──────────────┘         └──────────┘
            │
    ┌───────┴───────┐
    │               │
    ▼               ▼
┌────────┐   ┌──────────┐
│ Redis  │   │ Postgres │
│ (STM)  │   │ pgvector │
│        │   │(MTM/LTM) │
└────────┘   └──────────┘
```

---

## Service Map

| Service        | Port | Role                                                                 |
| -------------- | ---- | -------------------------------------------------------------------- |
| **Frontend**   | 3000 | Next.js UI — document upload, results, dashboard                     |
| **Gateway**    | 8000 | FastAPI — JWT auth, reverse proxy to internal services               |
| **AHMN**       | 8001 | Adaptive Hierarchical Memory Network — bandit learning               |
| **Guardrails** | 8002 | Multi-layer validation ensemble (format, hallucination, consistency) |
| **XAI-HITL**   | 8003 | Explainability engine (DistilBERT + LIME) + Human review             |
| **IDPO**       | 8004 | Document processing orchestrator — 14+ specialist agents             |
| **PostgreSQL** | 5432 | pgvector-enabled — MTM outcomes, LTM embeddings, users               |
| **Redis**      | 6379 | Short-Term Memory cache (30-min TTL)                                 |

---

## End-to-End Request Flow

### Document Upload & Processing

```
User uploads documents via Frontend
        │
        ▼
[1] Frontend → Gateway (POST /api/idpo/process)
        │  JWT token in Authorization header
        ▼
[2] Gateway authenticates → forwards to IDPO
        │
        ▼
[3] IDPO Pre-flight checks
        │  • Validates file types, sizes
        │  • Checks policy store configuration
        │
        ▼
[4] IDPO → AHMN (POST /advice)
        │  Sends: { doc_type, vendor, content_profile }
        │  Receives: { policy_id, policy_data, confidence, rabi_used }
        │  AHMN uses Thompson Sampling to select best policy
        │  (RABI handles cold-start for unseen doc types)
        │
        ▼
[5] IDPO Pipeline Execution
        │  14+ agents run in dependency order:
        │  intake → preprocess → doc_analysis → categorization →
        │  chunking → llm_extraction → structuring → validation →
        │  recovery → retrieval → answering → policy → escalation
        │
        ▼
[6] IDPO → Guardrails (POST /guardrails/validate)  [per document]
        │  Sends: { document_context, query, answer_json, source_contexts }
        │  Receives: { overall_passes, validation_results[], metrics }
        │  Parallelized across documents (up to 4 concurrent)
        │
        ▼
[7] IDPO → XAI-HITL (POST /xai/ask)  [per document]
        │  Sends: { paragraph (doc summary), question (analysis prompt) }
        │  Receives: { answer, confidence, explanation }
        │  Runs DistilBERT + LIME (90s timeout — CPU inference)
        │
        ▼
[8] IDPO → AHMN (POST /advice/log)
        │  Sends: { advice_id, policy_id_used, metrics { f1_score, cost, ... } }
        │  This is the LEARNING SIGNAL — AHMN updates its Beta distributions
        │
        ▼
[9] IDPO returns complete results to Gateway → Frontend
        │  Includes: extracted entities, summaries, validation issues,
        │  XAI explanations, confidence scores, provenance chain
```

---

## Integration Cycle

The integration layer (`idpo/integration.py`) orchestrates all cross-service communication.
IDPO is the **sole orchestrator** — no other service calls another directly.

### Cycle Steps

```python
# Step 1: Pre-processing — get AHMN advice
advice = get_ahmn_advice(doc_type, vendor, content_profile)

# Step 2: Pipeline execution (within IDPO)
doc_records = pipeline.execute(documents, policy=advice.policy_data)

# Step 3: Post-processing — validate with Guardrails
guardrail_results = validate_with_guardrails(doc_records)

# Step 4: Post-processing — get XAI explanations
xai_explanations = get_xai_explanations(doc_records, guardrail_results)

# Step 5: Close the loop — send feedback to AHMN
ahmn_feedback = log_ahmn_feedback(advice, doc_records, guardrail_results, time_ms)
```

### Key Design Decisions

- **Retry with backoff**: All HTTP calls use exponential backoff (max 3 retries, 0.5s–8s waits)
- **ReadTimeout NOT retried**: If a service is slow (vs unreachable), retrying would only queue more work
- **Parallel validation**: Guardrails and XAI calls are parallelized across documents (ThreadPoolExecutor, max 4 workers)
- **Graceful degradation**: If AHMN is unreachable, IDPO uses `default_policy`. If Guardrails/XAI fails, results are returned without those enrichments
- **Actual policy tracking**: Feedback sends the policy IDPO _actually used_, not what AHMN recommended — this is how AHMN learns from reality

---

## F1 Score Computation

The F1 score is a **proxy metric** computed by IDPO and sent to AHMN as the bandit reward signal. It blends extraction quality indicators since ground-truth labels aren't available at inference time.

### Formula

```
F1_proxy = weighted combination of:

1. Entity F1 (harmonic mean):
   precision_proxy = count(entities with confidence ≥ 0.5) / total_entities
   recall_proxy    = min(avg_entities_per_doc / 10.0, 1.0)
   f1_entity       = 2 × precision × recall / (precision + recall)

2. Guardrails success rate:
   success_rate = validated_docs / total_docs

3. Average confidence:
   avg_confidence = mean(all entity confidence scores)

Final blend (when Guardrails ran):
   F1_proxy = 0.5 × f1_entity + 0.3 × success_rate + 0.2 × avg_confidence

Without Guardrails:
   F1_proxy = 0.7 × f1_entity + 0.3 × avg_confidence
```

### Where Confidence Comes From

Entity confidence scores originate from:

- **LLM extraction agent**: Assigns confidence based on extraction certainty
- **Field confidence dict**: Per-field confidence from pattern matching / regex fallback
- **Validation agent**: May adjust confidence based on cross-field consistency

### How F1 Flows to AHMN

```
IDPO computes F1_proxy
    → POST /advice/log { metrics: { f1_score: 0.82, success: true, ... } }
        → AHMN receives f1_score as the bandit reward
            → AHMN updates Beta(α, β) for the policy+context pair:
                α += f1_score      (success evidence)
                β += (1 - f1_score) (failure evidence)
```

---

## AHMN Learning Loop

### Thompson Sampling

AHMN uses **Thompson Sampling** over Beta distributions to select document processing policies:

```
For each policy p in available_policies:
    Sample θ_p ~ Beta(α_p, β_p)
Select policy with highest θ_p
```

### How the Bandit Updates

When IDPO logs feedback:

1. **Receive reward** `r = f1_score` (0.0 to 1.0)
2. **Apply DAAF forgetting** (if drift detected):
   - `α_new = 1 + γ × (α_old - 1)` where `γ ∈ (0, 1)` is the forgetting rate
   - `β_new = 1 + γ × (β_old - 1)`
3. **Update with new observation**:
   - `α_new += r`
   - `β_new += (1 - r)`
4. **Store in MTM** (PostgreSQL `mtm_outcomes` table)

### RABI Cold-Start Handling

When encountering a **new document type** with no history:

```
1. Embed the context vector (doc_type, vendor, content_profile)
2. Query LTM (pgvector) for k-nearest neighbors by cosine similarity
3. Compute softmax weights: w_i = exp(sim_i / τ) / Σ exp(sim_j / τ)
4. Transfer priors:
   α_init = 1 + Σ w_i × (α_i - 1)
   β_init = 1 + Σ w_i × (β_i - 1)
5. Use these warm-started priors for Thompson Sampling
```

This reduces cold-start regret from O(K) to O(L·d_avg) where d_avg is the average distance to neighbors.

### DAAF (Drift-Aware Adaptive Forgetting)

Instead of fixed-rate memory decay, DAAF dynamically adjusts:

```
1. Estimate drift Δ = |μ_recent - μ_older| (mean shift between windows)
2. Estimate noise σ² = Var(rewards) (inherent stochasticity)
3. Compute optimal γ* = √(Δ² / ln(t))
   - High drift → forget faster (γ* larger)
   - Low drift → retain memory (γ* smaller)
4. Classify: NONE / GRADUAL / ABRUPT
5. Apply γ* to Beta parameters before new update
```

---

## Memory Hierarchy

### Three-Tier Architecture

```
┌────────────────────────────────────────────────┐
│  STM (Short-Term Memory) — Redis               │
│  TTL: 30 minutes                                │
│  Purpose: Cache recent AHMN advice              │
│  Key: context_hash → { policy_id, confidence }  │
│  Avoids redundant policy lookups for             │
│  similar documents in the same batch             │
└────────────────────────────────────────────────┘
                    │ Cache miss
                    ▼
┌────────────────────────────────────────────────┐
│  MTM (Medium-Term Memory) — PostgreSQL          │
│  Table: mtm_outcomes                            │
│  Purpose: Store recent observations             │
│  Columns: document_context, policy_id_used,     │
│           outcome_metrics (f1_score),            │
│           human_corrected, created_at            │
│  Used by: Thompson Sampling (α/β updates),      │
│           DAAF drift estimation, promotion job   │
└────────────────────────────────────────────────┘
                    │ Promotion job (every 30 min)
                    ▼
┌────────────────────────────────────────────────┐
│  LTM (Long-Term Memory) — PostgreSQL + pgvector │
│  Table: ltm_strategies                           │
│  Purpose: Proven strategies as vector embeddings │
│  Columns: context_embedding (vector),            │
│           policy_id, alpha, beta,                │
│           usage_count, avg_f1                    │
│  Used by: RABI (nearest-neighbor prior transfer) │
│  Vectors: sentence-transformers embeddings       │
└────────────────────────────────────────────────┘
```

### Data Lifecycle

```
New observation arrives (F1 from IDPO)
  → STM cached for 30 min (Redis)
  → MTM stored immediately (PostgreSQL mtm_outcomes)
  → If avg_f1 > 0.40 and usage_count ≥ 2 over 24h:
      Promotion job embeds context → LTM (ltm_strategies)
  → DAAF forgetting job decays stale MTM entries every 6h
```

---

## Background Jobs

Three scheduled jobs run independently via Docker Compose or cron:

### 1. Promotion Job (`jobs/promote.py`)

- **Schedule**: Every 30 minutes
- **Purpose**: Promote successful MTM strategies to LTM
- **Criteria**: `f1_score > 0.40`, `usage_count ≥ 2`, within last 24 hours, not `default_policy`
- **Process**:
  1. Query MTM for qualifying strategies (grouped by context + policy)
  2. Compute context embedding using sentence-transformers
  3. Upsert into `ltm_strategies` with updated α, β, usage stats
  4. Log promotion metrics

### 2. DAAF Forgetting Job (`jobs/forgetting.py`)

- **Schedule**: Every 6 hours
- **Purpose**: Apply adaptive memory decay to prevent stale strategies
- **Process**:
  1. Fetch recent rewards per context from MTM
  2. Estimate drift using sliding window comparison
  3. Compute optimal forgetting rate γ\* per context
  4. Apply decay: `α = 1 + γ(α-1)`, `β = 1 + γ(β-1)`
  5. Prune entries below threshold (0.4) or inactive > 7 days

### 3. Cleanup Job (`jobs/cleanup_runs.py`)

- **Schedule**: Daily
- **Purpose**: Clean up old pipeline run artifacts from `runs/` directory
- **Process**: Remove run folders older than configurable retention period

---

## HITL Feedback

### Human Review Flow

```
[1] XAI-HITL flags low-confidence documents for review
    │  Threshold: confidence < 0.5 or Guardrails failed
    │
    ▼
[2] Frontend shows document in Expert Review queue
    │  Reviewer sees: extracted entities, XAI explanation,
    │  validation issues, confidence scores
    │
    ▼
[3] Reviewer provides feedback:
    │  • correct — extraction was accurate
    │  • incorrect — extraction had errors
    │  • partially_correct — some fields right, some wrong
    │  • needs_more_context — insufficient data to judge
    │
    ▼
[4] IDPO forwards correction to AHMN
    │  POST /advice/feedback
    │  { advice_id, human_corrected: true/false }
    │
    ▼
[5] AHMN marks MTM outcome with human_corrected flag
    │  This modifies future Thompson Sampling:
    │  • human_corrected=true → penalizes the policy (increases β)
    │  • human_corrected=false → reinforces the policy
```

### Impact on Learning

Human corrections create a **stronger learning signal** than automated F1 because:

- They represent ground truth validation
- AHMN weights human-corrected outcomes more heavily in promotion decisions
- A policy with frequent human corrections gets deprioritized via increased β

---

## Guardrails Validation

### Multi-Layer Ensemble

The Guardrails service runs **multiple validation checks** in sequence:

```
Document enters Guardrails
    │
    ├─ Format Validation
    │    Check: Required fields present, correct data types
    │
    ├─ Consistency Check
    │    Check: Cross-field logical consistency
    │    (e.g., total = subtotal + tax)
    │
    ├─ Hallucination Detection
    │    Check: Extracted values traceable to source text
    │    Method: Source context comparison
    │
    ├─ Confidence Threshold
    │    Check: Entity confidences above minimum
    │
    └─ Domain Rules
         Check: Document-type-specific business rules
         (e.g., invoice must have line items)

Results aggregated:
    overall_passes = ALL checks pass
    validation_results[] = per-check details
    metrics = { precision, recall, f1, hallucination_rate }
```

### Document Type Mapping

IDPO maps its internal doc types to Guardrails-recognized types:

- `table_document` → `Invoice`
- `form_document` / `scanned_document` / `text_document` → `Generic`
- `invoice` → `Invoice`, `receipt` → `Receipt`
- `bank_statement` → `BankStatement`
- `insurance_claim` → `InsuranceClaim`
- `clinical_summary` → `ClinicalSummary`

---

## XAI Explanation Engine

### How Explanations Work

```
[1] IDPO constructs a summary paragraph per document:
    "Document type: invoice. Quality: high. Extracted 12 entities.
     Guardrails: passed (5/5 checks). Summary: ..."

[2] IDPO asks a question:
    "Analyze the extraction quality and explain whether the results
     for this invoice document are reliable."

[3] XAI-HITL processes with DistilBERT:
    • Extractive QA to find relevant answer span
    • LIME generates feature attributions (word importance)

[4] Returns:
    { answer: "...", confidence: 0.87, explanation: { lime_weights, ... } }
```

### Performance Note

XAI runs on CPU (no GPU required) with DistilBERT, which is lightweight but still needs up to **90 seconds** per document. The system uses a longer timeout (`_XAI_TIMEOUT = 90.0`) to accommodate this.

---

## Quick Reference: API Endpoints

| Endpoint                    | Service      | Purpose                    |
| --------------------------- | ------------ | -------------------------- |
| `POST /advice`              | AHMN         | Get policy recommendation  |
| `POST /advice/log`          | AHMN         | Log outcome metrics (F1)   |
| `POST /advice/feedback`     | AHMN         | Forward human correction   |
| `GET /advice/stats`         | AHMN         | Get bandit statistics      |
| `POST /guardrails/validate` | Guardrails   | Validate extraction output |
| `POST /xai/ask`             | XAI-HITL     | Get explanation            |
| `POST /hitl/submit`         | XAI-HITL     | Submit human review        |
| `POST /api/idpo/process`    | Gateway→IDPO | Process documents          |
| `GET /health`               | All          | Health check               |

---

## Service Communication Summary

```
Frontend ──HTTP──► Gateway ──HTTP──► IDPO
                                      │
                                      ├──► AHMN     (advice + feedback)
                                      ├──► Guardrails (validation)
                                      └──► XAI-HITL  (explanation)

AHMN ──► Redis (STM cache)
AHMN ──► PostgreSQL (MTM outcomes + LTM strategies)

Jobs (cron):
  promote.py    ──► PostgreSQL (MTM → LTM)
  forgetting.py ──► PostgreSQL (DAAF decay on MTM)
  cleanup.py    ──► Filesystem (runs/ cleanup)
```
