# AHMN - Adaptive Hierarchical Memory Network

> A production-ready system for intelligent document processing policy selection using contextual bandits and transfer learning.

---

## Overview

AHMN applies **Thompson Sampling** with two practical enhancements for adaptive document processing:

- **🚀 RABI**: Accelerates cold-start by transferring knowledge from similar contexts
- **🔄 DAAF**: Adapts to changing document formats with automatic forgetting rate tuning

**Key Results:**
- Faster cold-start convergence with statistically significant improvement
- Better adaptation in non-stationary environments
- Production-ready with sub-millisecond latency

---

## The Problem

Traditional multi-armed bandits face two critical challenges in production:

### 1. Cold-Start Problem
When encountering new document types, standard bandits start from scratch, requiring many exploration trials before finding optimal settings.

### 2. Drift Blindness
Document formats change over time. Fixed forgetting rates either adapt too slowly or forget too quickly.

---

## Our Approach

### RABI: Transfer Learning for Cold-Start

**Core Idea:** Similar document contexts likely need similar processing strategies.

**How it works:**
1. Embed new context into semantic vector space (384 dimensions)
2. Find k-nearest historical contexts by cosine similarity
3. Transfer their learned priors using weighted average
4. Initialize Thompson Sampling with informed prior instead of uniform

**What's new:** Application to document processing with empirical validation of cold-start improvement.

---

### DAAF: Adaptive Forgetting

**Core Idea:** Tune forgetting rate based on detected drift magnitude.

**How it works:**
1. Compare recent rewards vs. older rewards to estimate drift
2. Compute adaptive forgetting rate: higher drift → faster forgetting
3. Apply exponential decay to bandit parameters
4. Automatically balance retention vs. adaptation

**What's new:** Automatic forgetting rate tuning from drift estimation, with empirical validation.

---

### Three-Tier Memory

| Tier | Storage | Purpose |
|------|---------|---------|
| **STM** | Redis | Active session cache (fast) |
| **MTM** | PostgreSQL | Raw interaction logs (staging) |
| **LTM** | pgvector | Validated policies with embeddings (permanent) |

---

## Quick Start

```bash
# Minimal demo (no Docker needed)
cd ahmn_core
pip install -r requirements.txt
python demos/demo.py --mode quick

# Full system with database
docker-compose up -d
uvicorn main:app --reload
```

---

## Demo Modes

Run experiments with proper statistical validation:

```bash
# Quick presentation demo (~30 seconds)
python demos/demo.py --mode quick

# Full comparison with confidence intervals (~5 minutes)
python demos/demo.py --mode full

# Research validation with p-values (~15 minutes)
python demos/demo.py --mode experiment

# Test specific algorithms
python demos/demo.py --mode experiment --algorithm rabi
python demos/demo.py --mode experiment --algorithm daaf
```

**Output:** Console results + figures in `output/` folder + `results.json` with detailed statistics.

---

## API Endpoints

```bash
# Get policy recommendation
curl -X POST http://localhost:8000/advice \
  -H "Content-Type: application/json" \
  -d '{"doc_type": "invoice", "vendor": "Acme Corp"}'

# Log processing outcome
curl -X POST http://localhost:8000/log \
  -H "Content-Type: application/json" \
  -d '{"advice_id": "...", "policy_id_used": "...", "metrics": {"f1_score": 0.95}}'

# Submit human correction
curl -X POST http://localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{"advice_id": "...", "human_corrected": true}'
```

---

## Key Features

### Statistically Validated
- Multiple independent runs with different random seeds
- 95% confidence intervals for all metrics
- Welch's t-test for significance testing
- Cohen's d for effect size measurement

### Production-Ready
- Async database operations (psycopg3)
- Redis caching for sub-millisecond responses
- Proper error handling and logging
- Docker Compose setup for easy deployment
- Pydantic validation for all API requests

### Explainable
- RABI shows which historical contexts influenced the decision
- Drift detection provides visibility into environment changes
- Clear retrieval sources (STM/MTM/LTM) in responses

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| API | FastAPI + Uvicorn |
| Database | PostgreSQL 15 + pgvector |
| Cache | Redis 7 |
| Embeddings | SentenceTransformers (all-MiniLM-L6-v2) |
| Statistics | SciPy |
| Visualization | Matplotlib |

---

## Project Structure

```
ahmn_core/
├── main.py                     # FastAPI application
├── requirements.txt
├── docker-compose.yml
├── init.sql                    # Database schema
│
├── app/
│   ├── config.py              # Hyperparameters
│   ├── database.py            # Async connections
│   ├── schemas.py             # Pydantic models
│   └── services/
│       ├── memory.py          # Three-tier memory
│       ├── rabi.py            # Transfer learning
│       ├── drift_forgetting.py # Adaptive forgetting
│       ├── embedding.py       # Vector embeddings
│       └── selection_strategies.py  # Bandit algorithms
│
├── demos/
│   └── demo.py                # Experimental suite
│
└── jobs/
    ├── promote.py             # MTM → LTM promotion
    └── forgetting.py          # Apply DAAF decay
```

---

## Configuration

Key hyperparameters with justifications:

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| RABI k | 5 | Optimal for dense retrieval |
| RABI τ | 0.5 | Sharper similarity weighting |
| RABI δ | 0.4 | Filter dissimilar contexts |
| DAAF window | 50 | Balance responsiveness/stability |
| DAAF γ_min/max | 0.001 / 0.3 | Prevent extreme forgetting |

---

## For Researchers

This project demonstrates practical deployment of multi-armed bandits for document processing. While the underlying techniques (Bayesian transfer learning, drift detection, Thompson Sampling) are established methods, their combination and empirical validation in this domain contributes to understanding production bandit systems.

**Future theoretical work could explore:**
- Formal regret bounds for adaptive forgetting in contextual bandits
- Analysis of hierarchical memory systems
- Optimal transfer learning under distribution shift

---


