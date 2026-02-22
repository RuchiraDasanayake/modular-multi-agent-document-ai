# Modular Multi-Agent Document AI

A modular, multi-agent framework for intelligent document understanding and analysis. Integrates specialized agents for parsing, reasoning, summarization, and retrieval with four independently managed component modules:

1. **AHMN Core** — Adaptive Hierarchical Memory Network (Thompson Sampling, RABI, DAAF)
2. **Guardrails** — 5-layer Hallucination Detection Ensemble
3. **XAI & HITL** — Explainable AI Engine + Human-in-the-Loop Feedback
4. _(Component 4 — TBD)_

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                        frontend/  (Next.js 15)                         │
│   Dashboard: Overview │ Submit │ Experiments │ RABI │ DAAF             │
│                XAI │ HITL │ Guardrails │ Results │ Admin              │
└────────────────────────────────┬───────────────────────────────────────┘
                                 │ HTTP
┌────────────────────────────────▼───────────────────────────────────────┐
│                         backend/  (FastAPI)                            │
│   Routers: auth │ advice │ dashboard │ experiments                    │
│            xai │ hitl │ guardrails                                    │
│                                                                        │
│   Imports from 3 independent component modules:                       │
│                                                                        │
│   ┌── ahmn_core/ ──┐  ┌── guardrails/ ──┐  ┌── xai_hitl/ ─────────┐ │
│   │ services/      │  │ models.py       │  │ engine/               │ │
│   │  ├ selection   │  │ config.py       │  │  └ xai_engine.py     │ │
│   │  ├ rabi.py     │  │ core/           │  │ hitl/                 │ │
│   │  ├ drift_forg  │  │  ├ ensemble.py  │  │  └ models.py         │ │
│   │  └ embedding   │  │  └ validation   │  │ tests/                │ │
│   │ experiments/   │  │ tests/          │  │  └ test_xai_hitl.py  │ │
│   │ tests/         │  └────────────────┘  └─────────────────────┘ │
│   └───────────────┘                                                │
│                     │                     │                            │
│              ┌──────▼──────┐      ┌───────▼───────┐                   │
│              │  PostgreSQL  │      │    Redis      │                   │
│              │  (pgvector)  │      │   (STM cache) │                   │
│              └─────────────┘      └───────────────┘                   │
└────────────────────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────┐    ┌─────────────────────┐
│  jobs/               │    │  streamlit_app/      │
│   ├ promote.py       │    │   XAI Q&A demo       │
│   └ forgetting.py    │    │   (standalone)        │
└─────────────────────┘    └─────────────────────┘
```

### Memory Tiers

| Tier                 | Storage                                        | Purpose                                                   |
| -------------------- | ---------------------------------------------- | --------------------------------------------------------- |
| **STM** (Short-Term) | Redis                                          | Transient advice context (30-min TTL)                     |
| **MTM** (Mid-Term)   | PostgreSQL `mtm_outcomes`                      | Raw outcome logs from processing runs                     |
| **LTM** (Long-Term)  | PostgreSQL `ltm_validated_policies` + pgvector | Validated strategies with Beta distributions & embeddings |

### Hallucination Guardrails (5-Layer Ensemble)

| Layer | Check                | Description                                                        |
| ----- | -------------------- | ------------------------------------------------------------------ |
| 1     | Schema Adherence     | Pydantic validation per document type (7 types)                    |
| 2     | Internal Consistency | Business logic: math, negatives, future dates, dosage rules        |
| 3     | Domain Rules         | Tax plausibility (0-30%), vendor fraud, suspicious keywords        |
| 4     | PII Leakage          | Presidio-based, context-aware (allows PERSON/DATE in medical docs) |
| 5     | Faithfulness         | Semantic similarity via `all-MiniLM-L6-v2` (threshold 0.78)        |

---

## Project Structure

```
├── ahmn_core/                  # Component 1: AHMN algorithms (Dasanayake D.R.L.)
│   ├── config.py               # AHMN hyperparameters
│   ├── schemas.py              # Shared Pydantic DTOs
│   ├── services/               # Core algorithms
│   │   ├── selection_strategies.py   # Thompson Sampling, UCB1, ε-Greedy
│   │   ├── rabi.py                   # RABI cold-start transfer
│   │   ├── drift_forgetting.py       # DAAF drift-aware forgetting
│   │   └── embedding.py             # Sentence-transformer service
│   ├── experiments/            # Experimental evaluation framework
│   │   ├── synthetic_data.py        # 4 scenarios
│   │   ├── run_experiments.py       # 7 method runners
│   │   ├── analysis.py             # Post-hoc analysis
│   │   └── robustness_study.py     # Parameter sweeps
│   ├── tests/                  # Core algorithm tests
│   └── demo/                   # Streamlit demo pages
│
├── guardrails/                 # Component 2: Hallucination Detection (Wijetunga W.L.A.T.)
│   ├── models.py               # Document types, RAGInput, GuardrailOutput
│   ├── config.py               # Guardrail settings (thresholds)
│   ├── core/
│   │   ├── ensemble.py         # 5-layer orchestrator
│   │   └── validation.py       # Individual check implementations
│   └── tests/
│       └── test_guardrails.py  # Unit tests for all 5 layers
│
├── xai_hitl/                   # Component 3: XAI + HITL (Pathirana M.M.)
│   ├── engine/
│   │   └── xai_engine.py       # DistilBERT-SQuAD + SHAP + LIME
│   ├── hitl/
│   │   └── models.py           # Feedback types, HITLFeedback dataclass
│   └── tests/
│       └── test_xai_hitl.py    # Data model + round-trip tests
│
├── backend/                    # FastAPI REST API
│   ├── main.py                 # Entry point (7 routers)
│   ├── app/
│   │   ├── config.py           # Pydantic Settings
│   │   ├── database.py         # PostgreSQL + Redis
│   │   ├── deps.py             # FastAPI dependencies (JWT, DB)
│   │   ├── routers/
│   │   │   ├── auth.py         # /api/auth — login, register
│   │   │   ├── advice.py       # /api/advice — core AHMN endpoint
│   │   │   ├── dashboard.py    # /api/dashboard — stats, memory browsers
│   │   │   ├── experiments.py  # /api/experiments — results, demos
│   │   │   ├── xai.py          # /api/xai — explainable Q&A
│   │   │   ├── hitl.py         # /api/hitl — human-in-the-loop
│   │   │   └── guardrails.py   # /api/guardrails — validation ensemble
│   │   ├── schemas/            # Request/response models
│   │   └── services/           # Auth service
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                   # Next.js 15 + React 19 dashboard
│   └── src/
│       ├── app/dashboard/
│       │   ├── guardrails/     # Guardrails validation UI
│       │   ├── xai/            # XAI Q&A interface
│       │   ├── hitl/           # HITL review
│       │   └── ...             # Other pages
│       ├── components/         # Sidebar, stat cards
│       ├── lib/                # API client, auth
│       └── types/              # TypeScript type definitions
│
├── streamlit_app/              # Standalone Streamlit demo (XAI + HITL UI)
├── jobs/                       # Background maintenance
│   ├── promote.py              # MTM → LTM promotion
│   └── forgetting.py           # DAAF decay job
├── scripts/
│   └── init.sql                # PostgreSQL schema + seeds
└── docker-compose.yml          # db, redis, backend, frontend
```

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 18+ (for frontend dev)
- Python 3.11+ (for local dev)

### Run with Docker

```bash
cp .env.example .env
docker compose up --build
```

| Service     | URL                        |
| ----------- | -------------------------- |
| Frontend    | http://localhost:3000      |
| Backend API | http://localhost:8000      |
| API Docs    | http://localhost:8000/docs |

Default admin: `admin` / `admin123`

### Local Development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend
npm install && npm run dev
```

### Run Tests

```bash
# Core algorithm tests
python -m pytest ahmn_core/tests/ -v

# Guardrail tests
python -m pytest guardrails/tests/ -v

# XAI & HITL tests
python -m pytest xai_hitl/tests/ -v
```

---

## API Endpoints

| Prefix             | Router      | Description                             |
| ------------------ | ----------- | --------------------------------------- |
| `/api/auth`        | auth        | Login, register, user management        |
| `/api/advice`      | advice      | Core AHMN policy recommendation         |
| `/api/dashboard`   | dashboard   | Stats, memory browsers, activity        |
| `/api/experiments` | experiments | Pre-computed results, interactive demos |
| `/api/xai`         | xai         | Explainable Q&A with SHAP/LIME          |
| `/api/hitl`        | hitl        | Human-in-the-loop feedback              |
| `/api/guardrails`  | guardrails  | 5-layer hallucination validation        |

---

## Team

| Member             | Component                  |
| ------------------ | -------------------------- |
| Dasanayake D.R.L.  | AHMN Core (TS, RABI, DAAF) |
| Wijetunga W.L.A.T. | Hallucination Guardrails   |
| Pathirana M.M.     | XAI Engine & HITL Feedback |
| Nayanapriya S.A.T. | IDPO          |
