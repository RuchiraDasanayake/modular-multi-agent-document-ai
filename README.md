# Modular Multi-Agent Document AI

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](docker-compose.yml)
[![Python 3.10](https://img.shields.io/badge/Python-3.10-3776AB.svg?logo=python&logoColor=white)](SETUP.md)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000.svg?logo=next.js&logoColor=white)](frontend/package.json)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.114+-009485.svg?logo=fastapi&logoColor=white)](gateway/requirements.txt)

A microservices-based research system for adaptive document extraction. A document goes in; structured key-value fields come out. The IDPO pipeline (OCR, preprocessing, local-LLM extraction, validation, recovery) is governed by a policy that the AHMN layer selects per document with Thompson Sampling. Guardrails and XAI-HITL are separate services with their own dashboard pages.

> **Research results and how to reproduce them:** see [`docs/REPRODUCING_RESULTS.md`](docs/REPRODUCING_RESULTS.md).

> **Project status:** This is a research prototype under product stabilization. An opt-in
> automatic extraction path now proposes scalar and bounded repeated-column schemas with source-anchored values,
> with owner-scoped human review. It is a pilot, not a validated
> general-purpose extractor. The first 2,000-document no-model development run
> scored 4.33% strict schema F1 and 0.95% strict value F1, with unsafe automatic acceptance;
> the second kept every discovered schema in review and scored 0% pre-review accepted-value F1.
> The [v4 run](docs/evaluations/VRDU_2000_NO_MODEL_V4.md) verified 2,000 distinct sources but lacked its OCR
> executable, so it is not a valid OCR comparison; it also proposed zero linked cells against 30,133 gold cells.
> The [v5 pinned-OCR run](docs/evaluations/VRDU_2000_NO_MODEL_V5.md) recovered text on all 35 previously unsupported
> scans across 2,000 distinct PDFs, but strict schema F1 was only 4.245%, every result required review, and no linked
> cells were proposed. It did not configure a model or measure cost per correct document.
> The [v6 bounded-OCR run](docs/evaluations/VRDU_2000_NO_MODEL_V6.md) again completed 2,000 distinct PDFs with
> zero failures or unsupported results. No page hit its timeout; schema F1 and linked-row quality were unchanged.
> See [v1](docs/evaluations/VRDU_2000_NO_MODEL_V1.md) and [v2](docs/evaluations/VRDU_2000_NO_MODEL_V2.md).
> The later October paired evaluation in [`paper/FINAL_EVIDENCE.md`](paper/FINAL_EVIDENCE.md)
> did not show an accuracy gain from adaptive routing, and the canonical research
> document job path is unavailable in Docker. See the [productization plan](docs/PRODUCTIZATION_PLAN.md)
> for the proposed quality, cost, review, and deployment gates.

## Opt-in Product Pilot

On a configured single-host installation, upload a document to a job and open its **Automatic extraction** page.
The job owner can inspect proposed fields, linked cells, source quotes and the original file, then record field and
row corrections. Model-backed runs currently require an admin. The command-line equivalent is:

```powershell
python -m idpo.cli process-auto --input path/to/document.pdf
```

The opt-in product path accepts PDF, common raster images, TXT, JSON, DOCX, XLSX, PPTX, HTML, and EML. The last five
use source-native text and table-cell locators; they have no invented pixel boxes. The separate research `process-inbox`
runtime has a narrower input list. New formats remain review-only and have no measured accuracy claim.

Add `--model MODEL_ID --api-base-url HTTPS_OR_LOCAL_URL` to use a configured OpenAI-compatible model; the server reads
the key from `ICORE_API_KEY` by default for remote providers. A loopback HTTP model server can run without an API key.
The local, no-model route is a weak label/value baseline, not an accuracy
substitute for a model or reviewer. Run artifacts are written to `IDPO_DATA_DIR/product_runs/<run_id>` and stay separate
from the research `process-inbox` path. `run.json` is the completion marker. See the
[current system contract](docs/SYSTEM_CONTRACT.md) and [product direction](docs/PROJECT_DIRECTION.md) for the boundaries.

## Research Components

- **Policy-driven document pipeline** — Intake → Document analysis → Policy selection → Preprocessing and OCR → Extraction → Validation → Recovery → Export, with each stage parameterised by the selected policy
- **Local-first entity extraction** — Ollama (`qwen3.5:9b`) with JSON-schema-constrained output, a grounding check against the source text, and optional OpenAI cloud fallback
- **Adaptive routing (AHMN)** — Beta-Bernoulli Thompson Sampling over the policies whose conditions match the document, with job-scoped posteriors updated from a label-free per-document reward
- **RABI cold-start transfer and DAAF drift-aware forgetting** — AHMN service algorithms evaluated in simulation (`ahmn_core/experiments/`); they are not active in the document runtime
- **5-Layer Hallucination Detection** — Schema adherence, internal consistency, domain rules, PII detection (Presidio), and semantic faithfulness (MiniLM); a separate service, not part of the measured extraction pipeline
- **Explainable AI** — DistilBERT extractive Q&A with attention-based importance scoring and LIME local explanations (dynamic 30-80 perturbation samples with prediction caching)
- **Human-in-the-Loop** — Structured feedback loop with 5 feedback types, 4 priority levels, and 3 rating dimensions
- **Full Text Extraction** — OCR'd or digitally extracted text shown in-app with copy functionality

## Supported Domains & File Formats

### Document Domains

The research IDPO pipeline classifies documents by structural layout (table, form, text, scanned) rather than business
domain. It can attempt many document types, but its extraction accuracy on a new family is not guaranteed. The separate
Guardrails service provides domain-specific schema validation for 7 document types; it is not part of the measured
document-processing path:

| Domain          | Document Types                           | Validated Fields                                          |
| --------------- | ---------------------------------------- | --------------------------------------------------------- |
| **Healthcare**  | Clinical Summary, Medication Dosage      | Patient name, condition, dosage, frequency                |
| **Finance**     | Invoice, Insurance Claim, Bank Statement | Amounts, tax rates, policy numbers, balances              |
| **Procurement** | Purchase Order, Receipt                  | PO numbers, suppliers, line items, totals                 |
| **Generic**     | Any other                                | Entities extracted via regex + LLM (no schema validation) |

### Supported File Formats

| Format              | Extensions                                       | Text Extraction                                   |
| ------------------- | ------------------------------------------------ | ------------------------------------------------- |
| **PDF**             | `.pdf`                                           | PyPDF text extraction; falls back to scanned mode |
| **Images**          | `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp` | OCR via PaddleOCR first, with Tesseract fallback  |
| **Plain Text**      | `.txt`                                           | Direct text ingestion                             |
| **Structured JSON** | `.json`                                          | Multi-page document objects with metadata         |

| #   | Service        | Description                                                                                                            | Owner              |
| --- | -------------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------ |
| 1   | **AHMN Core**  | Adaptive Hierarchical Memory Network — Thompson Sampling with RABI cold-start transfer and DAAF drift-aware forgetting | Dasanayake D.R.L.  |
| 2   | **Guardrails** | 5-layer Hallucination Detection Ensemble — schema, consistency, domain, PII, faithfulness                              | Wijetunga W.L.A.T. |
| 3   | **XAI & HITL** | Explainable AI Engine (Attention Importance + LIME + DistilBERT) with Human-in-the-Loop feedback loop                  | Pathirana M.M.     |
| 4   | **IDPO**       | Intelligent Document Processing Orchestration — 13-agent pipeline from intake to export                                | Nayanapriya S.A.T. |

---

## Architecture Overview

The diagram below shows the research services available through the `research` Compose profile. The default
product pilot uses the gateway, frontend, product worker, PostgreSQL, and Redis; Automatic extraction does not
call AHMN, Guardrails, XAI-HITL, or the legacy IDPO HTTP service.

```
                        ┌──────────────────────────────────┐
                        │    frontend/  (Next.js 16)        │
                        │   User: XAI │ HITL │ Guardrails   │
                        │          │ Doc Processing          │
                        │   Admin: Overview │ Experiments    │
                        │          RABI │ DAAF │ Results     │
                        └───────────────┬──────────────────┘
                                        │ :3000
                        ┌───────────────▼──────────────────┐
                        │   gateway/  (FastAPI)              │
                        │   JWT Auth + Reverse Proxy         │
                        │   /api/auth/* → local              │
                        │   /api/* → route to service        │
                        └──┬──────────┬──────────┬─────┬───┘
                           │ :8001    │ :8002    │:8003│:8004
               ┌───────────▼──┐ ┌────▼──────┐ ┌▼─────┴──────┐
               │  ahmn_core/  │ │guardrails/│ │  xai_hitl/   │
               │   Thompson   │ │  5-layer  │ │  DistilBERT  │
               │   Sampling   │ │  ensemble │ │  Attn + LIME │
               │   RABI+DAAF  │ │  Presidio │ │  HITL review │
               └──▲────┬──┬──┘ └───▲───────┘ └──▲───────────┘
                  │    │  │        │             │
                  │    │  │   ┌────┴─────────────┴──┐
                  │    │  │   │     idpo/  (:8004)   │
                  │    │  │   │   Integration Layer   │
                  │    │  │   │  13-agent pipeline    │
                  │    │  │   └──────────────────────┘
                  │    │  │
            ┌─────┴───┐│ ┌▼──────────┐
            │PostgreSQL││ │  Redis    │
            │(pgvector)││ │(STM cache)│
            └──────────┘│ └───────────┘
                        │
         ───────────────┘
```

### Document Processing Path

Documents are processed by one canonical runtime path (see [`docs/SYSTEM_CONTRACT.md`](docs/SYSTEM_CONTRACT.md)):

```
  frontend /api/jobs ──► job runner ──► python -m idpo.cli process-inbox
                                              │
      ingest/inbox ──► orchestrator ──► executor ──► exports (IDPO_DATA_DIR/runs/<run_id>)
                          │
                          ├─ document analysis (quality bin, document type, vendor cluster)
                          ├─ AHMN direct advisor: Thompson Sampling over matching policies
                          └─ per-document outcome ──► job-scoped posterior update
```

AHMN routing runs in-process (`ahmn_core/direct_advisor.py`), so no AHMN server is needed to process documents. Guardrails and XAI-HITL are not called during document processing; they are used from their own dashboard pages. `idpo/integration.py`, which chained all four services over HTTP, is a legacy path.

> **Deep Dive**: See [`docs/SYSTEM_FLOW.md`](docs/SYSTEM_FLOW.md) for the complete system flow documentation including F1 score computation, AHMN learning loop, memory hierarchy, and background jobs.

### Service Ports

| Service      | Internal Port | Exposed to Host |
| ------------ | ------------- | --------------- |
| PostgreSQL   | 5432          | 5432            |
| Redis        | 6379          | 6379            |
| AHMN         | 8001          | —               |
| Guardrails   | 8002          | —               |
| XAI-HITL     | 8003          | —               |
| IDPO         | 8004          | —               |
| Product worker | Unix socket | —             |
| **Gateway**  | 8000          | **8000**        |
| **Frontend** | 3000          | **3000**        |

> Only the gateway and frontend are publicly accessible. Backend services communicate exclusively over Docker's internal network.

### Memory Tiers (AHMN)

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

## Quick Start

### Prerequisites

- **Docker** & **Docker Compose** v2+ for the supporting services
- Python 3.10 (for local development; the document pipeline is tested on 3.10.10 with PaddlePaddle 2.6.2)
- Node.js 20.9+ (for frontend development)
- [Ollama](https://ollama.com) with `qwen3.5:9b` and Tesseract 5 (for document extraction; see [docs/REPRODUCING_RESULTS.md](docs/REPRODUCING_RESULTS.md))

### Start the supporting services with Docker

The Docker frontend is wired to a private product extraction worker over a Unix socket and shared data volume.
The **Automatic extraction** path targets that worker; the canonical research job path returns an explicit
unavailable response in Docker. Compose configuration and focused tests pass, but a live image/container extraction
smoke has not run on this host. The verified end-to-end research demo remains the single-host setup in
[Public Demo Deployment](docs/PUBLIC_DEMO_DEPLOYMENT.md), checked with `scripts/run_public_demo_smoke.ps1`.
By default, Compose starts the five services needed for the product pilot: PostgreSQL, Redis, gateway,
product worker, and frontend. The AHMN, Guardrails, XAI-HITL, and legacy IDPO services are available with
`docker compose --profile research up --build`; they are not called by Automatic extraction.

```bash
# 1. Clone the repository
git clone <repo-url>
cd modular-multi-agent-document-ai

# 2. Configure environment
cp .env.example .env
# Edit .env: set JWT_SECRET_KEY to a random 32-char string and ADMIN_PASSWORD for the first admin account

# 3. Build and start the product pilot
docker compose up --build

# 4. Open the app
open http://localhost:3000
```

| Service     | URL                        |
| ----------- | -------------------------- |
| Frontend    | http://localhost:3000      |
| Gateway API | http://localhost:8000      |
| API Docs    | http://localhost:8000/docs |

**First login:** there is no default password. On startup, if no admin account exists, the gateway creates one from `ADMIN_USERNAME` (default `admin`) and `ADMIN_PASSWORD` in `.env`. Existing accounts are never changed.

### Local Development

Run every Python command from the repository root inside the Python 3.10 virtual environment (see [SETUP.md](SETUP.md)).

```bash
# Postgres (schema from scripts/init.sql) and Redis for sign-in, in Docker
docker compose up -d db redis

# Gateway. Outside Docker the database and Redis are on localhost; these values override a .env copied from
# .env.example, which points at the Docker hosts db and redis. Set ADMIN_PASSWORD once to create the first admin.
pip install -r gateway/requirements.txt
export POSTGRES_URI=postgresql://user:password@localhost:5432/ahmn_db
export REDIS_URL=redis://:docai_redis_secret@localhost:6379/1
uvicorn gateway.main:app --reload --port 8000

# AHMN Core
pip install -r ahmn_core/requirements.txt
uvicorn ahmn_core.main:app --reload --port 8001

# Guardrails
pip install -r guardrails/requirements.txt
uvicorn guardrails.main:app --reload --port 8002

# XAI-HITL
pip install -r xai_hitl/requirements.txt
uvicorn xai_hitl.main:app --reload --port 8003

# Frontend
cd frontend && npm install && npm run dev
```

### Run Tests

```bash
python -m pytest idpo/tests/ -v       # Document pipeline, routing and safety tests
python -m pytest ahmn_core/tests/ -v   # Core algorithm tests
python -m pytest guardrails/tests/ -v  # Guardrail ensemble tests
python -m pytest xai_hitl/tests/ -v    # XAI & HITL tests
python -m pytest gateway/tests/ -v     # Auth and proxy tests
cd frontend && npx tsc --noEmit && npm run lint && npm run test:server
```

---

## API Endpoints

All traffic flows through the gateway at `:8000`. JWT authentication is required for all `/api/*` routes (except `/api/auth/login`, `/api/auth/signup` and `/api/auth/signup-status`).

### Authentication

| Method | Path                         | Description           |
| ------ | ---------------------------- | --------------------- |
| POST   | `/api/auth/login`            | Login → JWT token     |
| POST   | `/api/auth/signup`           | Self-registration (viewer accounts; 403 while `PUBLIC_SIGNUP_ENABLED` is false) |
| GET    | `/api/auth/signup-status`    | Whether self-registration is open |
| GET    | `/api/auth/me`               | Current user profile  |
| POST   | `/api/auth/register`         | Admin: create user    |
| GET    | `/api/auth/users`            | Admin: list all users |
| PATCH  | `/api/auth/users/:id/toggle` | Admin: enable/disable |

Public sign-up is disabled by default until per-user processing and storage quotas are enforced.
An admin can create viewer accounts through `/api/auth/register`.

### AHMN Core (→ :8001)

| Method | Path                               | Description                            |
| ------ | ---------------------------------- | -------------------------------------- |
| POST   | `/api/advice`                      | Get policy recommendation              |
| POST   | `/api/advice/log`                  | Log processing outcome → bandit learns |
| POST   | `/api/advice/feedback`             | Record human-corrected flag            |
| GET    | `/api/dashboard/stats`             | Aggregate platform statistics          |
| GET    | `/api/dashboard/memory/stm`        | Active Redis STM entries               |
| GET    | `/api/dashboard/memory/mtm`        | Recent MTM outcomes                    |
| GET    | `/api/dashboard/memory/ltm`        | LTM validated policies                 |
| GET    | `/api/dashboard/memory/ltm/chart`  | LTM chart data                         |
| GET    | `/api/dashboard/activity`          | Recent system activity feed            |
| GET    | `/api/experiments/results`         | Pre-computed experiment results        |
| GET    | `/api/experiments/robustness`      | Robustness sweep results               |
| POST   | `/api/experiments/demo/daaf`       | Interactive DAAF demo                  |
| POST   | `/api/experiments/demo/rabi`       | Interactive RABI demo                  |
| POST   | `/api/experiments/demo/comparison` | TS vs DAAF comparison                  |

### Guardrails (→ :8002)

| Method | Path                       | Description                     |
| ------ | -------------------------- | ------------------------------- |
| POST   | `/api/guardrails/validate` | Run 5-layer validation ensemble |
| GET    | `/api/guardrails/stats`    | Aggregate validation statistics |
| GET    | `/api/guardrails/history`  | Recent audit log entries        |

### XAI-HITL (→ :8003)

| Method | Path                       | Description                          |
| ------ | -------------------------- | ------------------------------------ |
| POST   | `/api/xai/ask`             | Q&A with attention/LIME explanations |
| POST   | `/api/xai/explain`         | Word weights and highlighted spans for an existing answer |
| GET    | `/api/xai/explanation/:id` | Retrieve cached explanation          |
| POST   | `/api/hitl/feedback`       | Submit human feedback                |
| GET    | `/api/hitl/history`        | Recent feedback entries              |
| GET    | `/api/hitl/feedback/:id`   | Single feedback by ID                |
| GET    | `/api/hitl/stats`          | Aggregate HITL statistics            |

### IDPO (→ :8004)

| Method | Path                               | Description                            |
| ------ | ---------------------------------- | -------------------------------------- |
| POST   | `/api/idpo/run`                    | Upload & process documents (multipart) |
| GET    | `/api/idpo/runs/:id/docs.xlsx`     | Download extracted docs                |
| GET    | `/api/idpo/runs/:id/entities.xlsx` | Download extracted entities            |
| GET    | `/api/idpo/runs/:id/run.xlsx`      | Download run metadata                  |

---

## Frontend Pages

### Public Pages

| Path        | Description         |
| ----------- | ------------------- |
| `/`         | Landing page        |
| `/features` | Feature showcase    |
| `/about`    | About the project   |
| `/docs`     | Documentation       |
| `/contact`  | Contact form (needs `NEXT_PUBLIC_CONTACT_EMAIL`) |
| `/login`    | User login          |
| `/signup`   | User registration   |

### Dashboard (Authenticated)

| Path                      | Access | Description                           |
| ------------------------- | ------ | ------------------------------------- |
| `/dashboard`              | All    | Overview with health, stats, pipeline |
| `/dashboard/idpo`         | All    | Document jobs (redirects to `/dashboard/idpo/jobs`) |
| `/dashboard/idpo/benchmark` | All  | Static versus adaptive benchmark runs |
| `/dashboard/idpo/compare` | All    | Two runs side by side, document by document |
| `/dashboard/idpo/presentation` | All | Step-by-step walkthrough of one run |
| `/dashboard/xai`          | All    | AI Q&A over the OCR text of a processed document, or pasted text |
| `/dashboard/xai/explanation` | All | How the last answer was found: highlights, SHAP, LIME, reasoning steps |
| `/dashboard/hitl`         | All    | Expert review of the last AI Q&A answer |
| `/dashboard/guardrails`   | All    | Quality checks against the Guardrails service |
| `/dashboard/submit`       | Admin  | Policy check: ask the AHMN service which policy it would pick |
| `/dashboard/experiments`  | Admin  | AHMN simulator results (Table V)      |
| `/dashboard/rabi`         | Admin  | RABI cold-start simulation            |
| `/dashboard/daaf`         | Admin  | DAAF drift detection simulation       |
| `/dashboard/architecture` | Admin  | How the AHMN service answers and learns |
| `/dashboard/admin`        | Admin  | User management                       |
| `/dashboard/database`     | Admin  | Stored memory, users, quality-check log and ratings |

`/dashboard/results` and `/dashboard/history` redirect to `/dashboard/experiments` and `/dashboard/idpo/jobs`.

---

## Project Structure

```
├── ahmn_core/                  # Service 1: AHMN algorithms (Dasanayake D.R.L.)
│   ├── main.py                 # FastAPI entry point (:8001)
│   ├── services/
│   │   ├── selection_strategies.py   # Thompson Sampling, UCB1, ε-Greedy
│   │   ├── rabi.py                   # RABI cold-start transfer
│   │   ├── drift_forgetting.py       # DAAF drift-aware forgetting
│   │   └── embedding.py             # Sentence-transformer service
│   ├── experiments/            # Evaluation framework (synthetic + robustness)
│   └── tests/
│
├── guardrails/                 # Service 2: Hallucination Detection (Wijetunga W.L.A.T.)
│   ├── main.py                 # FastAPI entry point (:8002)
│   ├── core/
│   │   ├── ensemble.py         # 5-layer orchestrator
│   │   └── validation.py       # Individual check implementations
│   └── tests/
│
├── xai_hitl/                   # Service 3: XAI + HITL (Pathirana M.M.)
│   ├── main.py                 # FastAPI entry point (:8003)
│   ├── engine/xai_engine.py    # BART (vblagoje/bart_lfqa) answers + attention importance + LIME
│   ├── hitl/models.py          # Feedback types, HITLFeedback dataclass
│   └── tests/
│
├── idpo/                       # Service 4: IDPO (Nayanapriya S.A.T.)
│   ├── cli.py                  # CLI entry point
│   ├── integration.py          # Legacy HTTP chain across services (not the runtime path)
│   ├── agents/                 # 13 document processing agents
│   ├── core/                   # Config, types, artifacts, provenance
│   ├── pipeline/               # Orchestrator, executor, planning, export
│   ├── retrieval/              # RAG: vector store + BM25 + hybrid
│   ├── evaluation/             # Evaluation runner + hooks
│   └── ui/app.py               # FastAPI app (:8004) with dashboard
│
├── gateway/                    # API Gateway — JWT auth + reverse proxy
│   ├── main.py                 # FastAPI entry point (:8000)
│   ├── auth_service.py         # Password hashing, JWT create/verify
│   ├── database.py             # PostgreSQL pool (auth tables)
│   └── deps.py                 # FastAPI dependencies (JWT, DB)
│
├── frontend/                   # Next.js 16 + React 19 web app
│   └── src/
│       ├── app/dashboard/      # All dashboard pages (XAI, HITL, Guardrails, IDPO, admin)
│       ├── components/         # Sidebar (role-based), toast, stat cards
│       ├── hooks/              # useUser hook
│       └── lib/api.ts          # Typed API client for all endpoints
│
├── jobs/                       # Background maintenance
│   ├── promote.py              # MTM → LTM promotion
│   └── forgetting.py           # DAAF decay job
├── configs/                    # IDPO configuration files
├── scripts/init.sql            # PostgreSQL schema
├── docker-compose.yml          # Research services, frontend, and product worker
├── CONTRIBUTING.md             # Developer guidelines
└── LICENSE                     # MIT
```

---

## IDPO CLI Reference

IDPO can also be used standalone via CLI for batch document processing:

```bash
# Install
python -m pip install -e .

# Ingest documents
idpo ingest --input data/synthetic/docs --out ../idpo-data/runs/ingested.json

# Process + index (full pipeline)
idpo process --input data/synthetic/docs --run-dir ../idpo-data/runs/demo

# Preferred operational flow with managed runtime storage
idpo process-inbox --root . --config configs/config.json --input-dir data/demo_inputs

# Query processed documents
idpo query --run-dir ../idpo-data/runs/demo --question "What is the total charge?" --doc-id doc_001

# Evaluate extraction quality
idpo evaluate --input data/synthetic/docs/synthetic_documents.json --run-dir ../idpo-data/runs/eval

# Export provenance audit trail
idpo export-provenance --run-dir ../idpo-data/runs/demo --out ../idpo-data/runs/demo/provenance_export.json
```

### Optional Extras

```bash
# Scanned document OCR (PaddleOCR first; Tesseract fallback still supported)
python -m pip install -e ".[ocr]"

# Excel export (multi-sheet entities.xlsx; falls back to CSV otherwise)
python -m pip install -e ".[excel]"
```

### IDPO Outputs

| Path                         | Contents                                         |
| ---------------------------- | ------------------------------------------------ |
| `runs/<id>/artifacts/`       | Raw and cleaned document artifacts               |
| `runs/<id>/provenance.jsonl` | Append-only audit log                            |
| `runs/<id>/index/`           | Vector + lexical indexes                         |
| `runs/<id>/results.json`     | Per-document structured outputs                  |
| `runs/<id>/entities.xlsx`    | Explicit entities, defaults, extraction metadata |
| `runs/<id>/evaluation.json`  | Evaluation metrics (when run)                    |

---

## Environment Variables

Create a `.env` file from the example:

```bash
cp .env.example .env
```

| Variable            | Default                  | Description                     |
| ------------------- | ------------------------ | ------------------------------- |
| `JWT_SECRET_KEY`    | _(required)_             | 32+ char secret for JWT signing |
| `POSTGRES_USER`     | `user`                   | PostgreSQL username             |
| `POSTGRES_PASSWORD` | `password`               | PostgreSQL password             |
| `POSTGRES_DB`       | `ahmn_db`                | PostgreSQL database name        |
| `REDIS_PASSWORD`    | `docai_redis_secret`     | Redis authentication password   |
| `AHMN_URL`          | `http://ahmn:8001`       | AHMN service URL                |
| `GUARDRAILS_URL`    | `http://guardrails:8002` | Guardrails service URL          |
| `XAI_URL`           | `http://xai-hitl:8003`   | XAI-HITL service URL            |
| `IDPO_URL`          | `http://idpo:8004`       | IDPO service URL                |

---

## Legacy Docker Service Deployment

For the current five-service product stack, start with
[Current single-host deployment path](docs/DEPLOYMENT_CURRENT.md). The
instructions below describe an older topology and are retained for research
context.

The steps below describe the legacy service/UI stack plus the product extraction worker.
The worker boundary has passed Compose parsing and focused tests but has not passed a live container smoke on this host.
Its current single-run limit and lack of a durable queue make it a pilot rather than a production deployment.
The canonical research job path remains available through the single-host setup in
[Public Demo Deployment](docs/PUBLIC_DEMO_DEPLOYMENT.md).

### Prerequisites

- A Linux server (Ubuntu 22.04+ recommended) with Docker & Docker Compose v2+
- A registered domain name with DNS pointing to your server
- Minimum 4 GB RAM, 2 vCPUs (8 GB / 4 vCPUs recommended for ML models)

### 1. Server Setup

```bash
# SSH into your server
ssh user@your-server-ip

# Clone the repository
git clone <repo-url>
cd modular-multi-agent-document-ai

# Create production environment file
cp .env.example .env
```

Edit `.env` with production values:

```env
JWT_SECRET_KEY=<random-64-char-hex-string>
POSTGRES_USER=docai_prod
POSTGRES_PASSWORD=<strong-random-password>
POSTGRES_DB=docai_prod
REDIS_PASSWORD=<strong-random-password>
```

### 2. Reverse Proxy with Nginx

Install Nginx and configure it as a reverse proxy with SSL:

```bash
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
```

Create `/etc/nginx/sites-available/docai`:

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 50M;
        proxy_read_timeout 600s;
    }
}
```

Enable the site and obtain an SSL certificate:

```bash
sudo ln -s /etc/nginx/sites-available/docai /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d yourdomain.com
```

### 3. Update Frontend API URL

Rebuild the frontend with your production domain:

```bash
# In docker-compose.yml, update the frontend build arg:
#   NEXT_PUBLIC_API_URL=https://yourdomain.com
# Also update the environment variable:
#   NEXT_PUBLIC_API_URL=https://yourdomain.com
#   INTERNAL_API_URL=http://gateway:8000

docker compose up --build -d
```

### 4. Verify Deployment

```bash
# Check all services are healthy
docker compose ps

# Test the API
curl https://yourdomain.com/api/auth/login \
  -X POST -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<your ADMIN_PASSWORD>"}'

# View logs
docker compose logs -f --tail=50
```

### 5. Production Hardening Checklist

- [ ] Set a strong `ADMIN_PASSWORD` before the first start; once the admin account exists the value is no longer read and can be removed from `.env`
- [ ] Set strong, unique values for `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, and `REDIS_PASSWORD`
- [ ] Leave public sign-up off (`docker-compose.prod.yml` sets `PUBLIC_SIGNUP_ENABLED=false` unless `.env` says `true`) and create accounts on the Admin page
- [ ] Ensure PostgreSQL and Redis ports are bound to `127.0.0.1` (default in docker-compose)
- [ ] Enable UFW firewall: `sudo ufw allow 80,443/tcp && sudo ufw enable`
- [ ] Set up automated SSL renewal: `sudo certbot renew --dry-run`
- [ ] Configure log rotation for Docker: add `"log-driver": "json-file"` with `"max-size": "10m"` in `/etc/docker/daemon.json`
- [ ] Set up periodic database backups: `docker exec docai_postgres pg_dump -U docai_prod docai_prod > backup.sql`
- [ ] Monitor disk usage for `runs/` and `inputs/` directories

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines, branch naming conventions, and PR checklist.

---

## Team

| Member                 | Component  | Key Contributions                                                                       |
| ---------------------- | ---------- | --------------------------------------------------------------------------------------- |
| **Dasanayake D.R.L.**  | AHMN Core  | Thompson Sampling, RABI cold-start transfer, DAAF drift-aware forgetting, 3-tier memory |
| **Wijetunga W.L.A.T.** | Guardrails | 5-layer hallucination ensemble, Presidio PII, MiniLM faithfulness                       |
| **Pathirana M.M.**     | XAI & HITL | DistilBERT QA, Attention-based importance, LIME explanations, human feedback loop       |
| **Nayanapriya S.A.T.** | IDPO       | 13-agent pipeline, integration layer, CLI, RAG retrieval                                |

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
