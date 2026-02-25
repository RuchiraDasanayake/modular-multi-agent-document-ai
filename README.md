# Modular Multi-Agent Document AI

A production-ready, microservices-based framework for intelligent document understanding and analysis. Each core component runs as an independent Docker service behind a unified API gateway.

1. **AHMN Core** — Adaptive Hierarchical Memory Network (Thompson Sampling, RABI, DAAF)
2. **Guardrails** — 5-layer Hallucination Detection Ensemble
3. **XAI & HITL** — Explainable AI Engine + Human-in-the-Loop Feedback
4. **IDPO** — Intelligent Document Processing Orchestration

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
├── idpo/                       # Microservice 4: IDPO (Nayanapriya S.A.T.)
│   ├── cli.py                  # CLI entry point
│   ├── agents/                 # Multi-agent document processors
│   │   ├── intake.py           # Document intake
│   │   ├── preprocess.py       # Preprocessing
│   │   ├── categorization.py   # Document categorization
│   │   ├── chunking.py         # Text chunking
│   │   ├── doc_analysis.py     # Document analysis
│   │   ├── llm_extraction.py   # LLM-based extraction
│   │   ├── structuring.py      # Data structuring
│   │   ├── validation.py       # Validation agent
│   │   ├── answering.py        # Q&A agent
│   │   ├── retrieval_agent.py  # Retrieval agent
│   │   ├── policy.py           # Policy routing
│   │   ├── escalation.py       # Escalation handling
│   │   └── recovery.py         # Error recovery
│   ├── core/                   # Core utilities
│   │   ├── config.py           # Pipeline configuration
│   │   ├── types.py            # Type definitions
│   │   ├── artifacts.py        # Artifact management
│   │   ├── contracts.py        # Agent contracts
│   │   ├── metrics.py          # Metrics collection
│   │   ├── policy_store.py     # Policy storage
│   │   ├── preflight.py        # Preflight checks
│   │   └── provenance.py       # Audit trail
│   ├── pipeline/               # Pipeline orchestration
│   │   ├── orchestrator.py     # Main orchestrator
│   │   ├── executor.py         # Pipeline executor
│   │   ├── planning.py         # Execution planning
│   │   ├── inbox.py            # Document inbox
│   │   ├── export.py           # Export utilities
│   │   └── serialization.py    # Data serialization
│   ├── retrieval/              # RAG retrieval
│   │   ├── vector_store.py     # Vector storage
│   │   ├── bm25.py             # BM25 search
│   │   ├── hybrid.py           # Hybrid retrieval
│   │   ├── context_selector.py # Context selection
│   │   └── index_bundle.py     # Index bundling
│   ├── evaluation/             # Evaluation framework
│   │   ├── runner.py           # Evaluation runner
│   │   └── hooks.py            # Evaluation hooks
│   └── ui/                     # IDPO UI
│       ├── app.py              # FastAPI UI app
│       ├── static/             # Static assets
│       └── templates/          # HTML templates
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
├── configs/                    # IDPO configuration files
│   ├── sample_config.json      # Sample pipeline config
│   ├── policy_store.json       # Policy definitions
│   └── demo_paths.json         # Demo file paths
│
├── docs/                       # Documentation
│   └── architecture.md         # IDPO architecture docs
│
├── jobs/                       # Background maintenance
│   ├── promote.py              # MTM → LTM promotion
│   └── forgetting.py           # DAAF decay job
├── scripts/
│   ├── init.sql                # PostgreSQL schema + seeds
│   └── run_demo_ui.ps1         # IDPO demo UI script
├── pyproject.toml              # IDPO Python project config
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

## IDPO (Intelligent Document Processing Orchestration)

IDPO is a domain-agnostic Document AI system that is fully auditable, multi-agent, preprocessing-aware, and end-to-end from ingestion to provenance export.

### IDPO Installation

```bash
python -m pip install -e .
```

### IDPO Commands

#### Ingest
```bash
idpo ingest --input data/synthetic/docs --out runs/ingested.json
```

#### Process + Index
```bash
idpo process --input data/synthetic/docs --run-dir runs/demo
```

To inject domain-specific extraction rules and policy routing, provide a config file via `--config` (see `PipelineConfig.structuring.extraction_rules` and `PipelineConfig.knowledge`). A sample config is in `configs/sample_config.json`.

#### Simple Output Layout
```bash
idpo process-simple --input data/demo_inputs --config configs/sample_config.json
```

This writes all outputs to `data/demo_inputs/output/`, including `entities.xlsx` (or CSV fallback), raw categorized files, and `text_extracted/` per file.

#### Query
```bash
idpo query --run-dir runs/demo --question "What is the total charge?" --doc-id doc_001
```

#### Evaluate
```bash
idpo evaluate --input data/synthetic/docs/synthetic_documents.json --run-dir runs/eval
```

#### Export Provenance
```bash
idpo export-provenance --run-dir runs/demo --out runs/demo/provenance_export.json
```

### Scanned Documents (OCR)

To process scanned images or PDF pages, install OCR extras:

```bash
python -m pip install -e ".[ocr]"
```

You also need the Tesseract OCR binary installed and available on PATH. PDF OCR via Pillow may require a PDF renderer (e.g., Ghostscript/Poppler).

### Excel Export (Optional)

```bash
python -m pip install -e ".[excel]"
```

This enables the multi-sheet `entities.xlsx` export. If the Excel extras are not installed, the pipeline writes three CSV files instead.

### IDPO Outputs

- `runs/<run-id>/artifacts/` contains raw and cleaned artifacts.
- `runs/<run-id>/provenance.jsonl` is the append-only audit log.
- `runs/<run-id>/index/` contains vector + lexical indexes.
- `runs/<run-id>/results.json` stores per-document structured outputs.
- `runs/<run-id>/entities.xlsx` stores explicit entities, default entities, and extraction metadata.
- `runs/<run-id>/evaluation.json` stores evaluation metrics (when run).

---

## Team

| Member             | Component                  |
| ------------------ | -------------------------- |
| Dasanayake D.R.L.  | AHMN Core (TS, RABI, DAAF) |
| Wijetunga W.L.A.T. | Hallucination Guardrails   |
| Pathirana M.M.     | XAI Engine & HITL Feedback |
| Nayanapriya S.A.T. | IDPO                       |
