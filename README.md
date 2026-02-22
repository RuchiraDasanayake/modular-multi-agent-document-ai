# Modular Multi-Agent Document AI

A production-ready, microservices-based framework for intelligent document understanding and analysis. Each core component runs as an independent Docker service behind a unified API gateway.

1. **AHMN Core** — Adaptive Hierarchical Memory Network (Thompson Sampling, RABI, DAAF)
2. **Guardrails** — 5-layer Hallucination Detection Ensemble
3. **XAI & HITL** — Explainable AI Engine + Human-in-the-Loop Feedback

---

## Architecture Overview

```
                        ┌─────────────────────────────────┐
                        │    frontend/  (Next.js 15)       │
                        │   User: XAI │ HITL │ Guardrails  │
                        │   Admin: Overview │ Experiments   │
                        │          RABI │ DAAF │ Results    │
                        └────────────────┬────────────────┘
                                         │ :3000
                        ┌────────────────▼────────────────┐
                        │   gateway/  (FastAPI)            │
                        │   JWT Auth + Reverse Proxy       │
                        │   /api/auth/* → local            │
                        │   /api/* → route to service      │
                        └──┬──────────┬──────────┬────────┘
                           │ :8001    │ :8002    │ :8003
               ┌───────────▼──┐ ┌────▼──────┐ ┌─▼────────────┐
               │  ahmn_core/  │ │guardrails/│ │  xai_hitl/    │
               │  FastAPI     │ │ FastAPI   │ │  FastAPI      │
               │              │ │           │ │               │
               │  services/   │ │ core/     │ │  engine/      │
               │   selection  │ │  ensemble │ │   xai_engine  │
               │   rabi       │ │  validat. │ │  hitl/        │
               │   drift_forg │ │           │ │   models      │
               │   embedding  │ │ Presidio  │ │  DistilBERT   │
               │  experiments/│ │ MiniLM    │ │  SHAP + LIME  │
               └──────┬───┬──┘ └───────────┘ └───────────────┘
                      │   │
            ┌─────────▼┐ ┌▼──────────┐
            │PostgreSQL│ │  Redis    │
            │(pgvector)│ │(STM cache)│
            └──────────┘ └───────────┘
```

### Service Ports

| Service      | Internal Port | Exposed to Host |
| ------------ | ------------- | --------------- |
| PostgreSQL   | 5432          | 5432            |
| Redis        | 6379          | 6379            |
| AHMN         | 8001          | —               |
| Guardrails   | 8002          | —               |
| XAI-HITL     | 8003          | —               |
| **Gateway**  | 8000          | **8000**        |
| **Frontend** | 3000          | **3000**        |

> Only the gateway and frontend are publicly accessible. Backend services communicate exclusively over Docker's internal network.

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
├── ahmn_core/                  # Microservice 1: AHMN algorithms (Dasanayake D.R.L.)
│   ├── main.py                 # FastAPI entry point (:8001)
│   ├── Dockerfile
│   ├── requirements.txt
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
│   └── tests/                  # Core algorithm tests
│
├── guardrails/                 # Microservice 2: Hallucination Detection (Wijetunga W.L.A.T.)
│   ├── main.py                 # FastAPI entry point (:8002)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── models.py               # Document types, RAGInput, GuardrailOutput
│   ├── config.py               # Guardrail settings (thresholds)
│   ├── core/
│   │   ├── ensemble.py         # 5-layer orchestrator
│   │   └── validation.py       # Individual check implementations
│   └── tests/
│       └── test_guardrails.py  # Unit tests for all 5 layers
│
├── xai_hitl/                   # Microservice 3: XAI + HITL (Pathirana M.M.)
│   ├── main.py                 # FastAPI entry point (:8003)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── engine/
│   │   └── xai_engine.py       # DistilBERT-SQuAD + SHAP + LIME
│   ├── hitl/
│   │   └── models.py           # Feedback types, HITLFeedback dataclass
│   └── tests/
│       └── test_xai_hitl.py    # Data model + round-trip tests
│
├── gateway/                    # API Gateway — auth + reverse proxy
│   ├── main.py                 # FastAPI entry point (:8000)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── config.py               # Pydantic Settings (JWT, service URLs)
│   ├── database.py             # PostgreSQL pool (auth tables only)
│   ├── deps.py                 # FastAPI dependencies (JWT, DB)
│   ├── schemas.py              # Auth request/response models
│   └── auth_service.py         # Password hashing, JWT create/verify
│
├── frontend/                   # Next.js 15 + React 19 web app
│   └── src/
│       ├── app/
│       │   └── dashboard/
│       │       ├── xai/        # XAI Q&A interface (user-facing)
│       │       ├── hitl/       # HITL review (user-facing)
│       │       ├── guardrails/ # Guardrails validation (user-facing)
│       │       ├── admin/      # User management (admin)
│       │       ├── experiments/# Experiment results (admin)
│       │       ├── rabi/       # RABI Cold Start demo (admin)
│       │       ├── daaf/       # DAAF Drift demo (admin)
│       │       └── ...         # Other admin pages
│       ├── components/         # Sidebar (role-based), stat cards
│       ├── hooks/              # useUser hook
│       ├── lib/                # API client, auth helpers
│       └── types/              # TypeScript type definitions
│
├── jobs/                       # Background maintenance
│   ├── promote.py              # MTM → LTM promotion
│   └── forgetting.py           # DAAF decay job
├── scripts/
│   └── init.sql                # PostgreSQL schema + seeds
└── docker-compose.yml          # 7 services: db, redis, ahmn, guardrails, xai-hitl, gateway, frontend
```

---

## Quick Start

### Prerequisites

- Docker & Docker Compose v2

### Run with Docker

```bash
# Clone & configure
cp .env.example .env

# Build and start all services
docker compose up --build
```

| Service     | URL                        |
| ----------- | -------------------------- |
| Frontend    | http://localhost:3000      |
| Gateway API | http://localhost:8000      |
| API Docs    | http://localhost:8000/docs |

Default admin credentials: `admin` / `admin123`

### Local Development

```bash
# Gateway
cd gateway
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn gateway.main:app --reload --port 8000

# AHMN service
pip install -r ahmn_core/requirements.txt
uvicorn ahmn_core.main:app --reload --port 8001

# Guardrails service
pip install -r guardrails/requirements.txt
uvicorn guardrails.main:app --reload --port 8002

# XAI-HITL service
pip install -r xai_hitl/requirements.txt
uvicorn xai_hitl.main:app --reload --port 8003

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

All traffic flows through the gateway at `:8000`.

| Prefix             | Handled By   | Description                             |
| ------------------ | ------------ | --------------------------------------- |
| `/api/auth`        | Gateway      | Login, register, user management        |
| `/api/advice`      | AHMN (:8001) | Core AHMN policy recommendation         |
| `/api/dashboard`   | AHMN (:8001) | Stats, memory browsers, activity        |
| `/api/experiments` | AHMN (:8001) | Pre-computed results, interactive demos |
| `/api/xai`         | XAI (:8003)  | Explainable Q&A with SHAP/LIME          |
| `/api/hitl`        | XAI (:8003)  | Human-in-the-loop feedback              |
| `/api/guardrails`  | GR (:8002)   | 5-layer hallucination validation        |

---

## Frontend Pages

| Path                      | Access | Description               |
| ------------------------- | ------ | ------------------------- |
| `/dashboard/xai`          | All    | XAI Q&A chat interface    |
| `/dashboard/hitl`         | All    | HITL feedback & review    |
| `/dashboard/guardrails`   | All    | Guardrails validation UI  |
| `/dashboard`              | Admin  | AHMN system overview      |
| `/dashboard/submit`       | Admin  | Submit document data      |
| `/dashboard/experiments`  | Admin  | Experiment results        |
| `/dashboard/rabi`         | Admin  | RABI cold-start demo      |
| `/dashboard/daaf`         | Admin  | DAAF drift detection demo |
| `/dashboard/results`      | Admin  | Comparative analysis      |
| `/dashboard/architecture` | Admin  | System architecture view  |
| `/dashboard/admin`        | Admin  | User management           |

---

## Team

| Member             | Component                  |
| ------------------ | -------------------------- |
| Dasanayake D.R.L.  | AHMN Core (TS, RABI, DAAF) |
| Wijetunga W.L.A.T. | Hallucination Guardrails   |
| Pathirana M.M.     | XAI Engine & HITL Feedback |
| Nayanapriya S.A.T. | IDPO                       |
