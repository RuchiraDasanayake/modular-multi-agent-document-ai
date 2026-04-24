# Modular Multi-Agent Document AI

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](docker-compose.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](pyproject.toml)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-000000.svg?logo=next.js&logoColor=white)](frontend/package.json)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.114+-009485.svg?logo=fastapi&logoColor=white)](gateway/requirements.txt)

A production-ready, microservices-based framework for intelligent document understanding and analysis. Four independently deployable services communicate through an integration pipeline that forms a continuous learning cycle.

## Key Features

- **13-Agent Document Pipeline** — Intake → OCR → Analysis → Categorization → Structuring → Validation → Recovery → Chunking → Retrieval → Answering → Escalation → Policy → Export
- **Multi-Tier Entity Extraction** — Explicit regex → LLM (Ollama/OpenAI/Anthropic) → Smart heuristic patterns → Generic KV parsing, with aggressive noise filtering
- **RABI Cold-Start Transfer** — Novel Bayesian algorithm that transfers prior knowledge across similar document contexts via softmax-weighted pseudocounts
- **DAAF Drift Detection** — Adaptive forgetting rate $\gamma^* \approx \sqrt{\Delta^2 / \ln(t)}$ for non-stationary environments
- **5-Layer Hallucination Detection** — Schema adherence, internal consistency, domain rules, PII detection (Presidio), and semantic faithfulness (MiniLM)
- **Explainable AI** — DistilBERT extractive Q&A with attention-based importance scoring and LIME local explanations (dynamic 30-80 perturbation samples with prediction caching)
- **Human-in-the-Loop** — Structured feedback loop with 5 feedback types, 4 priority levels, and 3 rating dimensions
- **Full Text Extraction** — OCR'd or digitally extracted text shown in-app with copy functionality
- **Closed-Loop Learning** — Processing outcomes feed back into the bandit system so policies improve with every document

## Performance Optimizations

The system incorporates several performance optimizations for production-viable latency:

| Optimization           | Before                       | After                  | Impact                                                            |
| ---------------------- | ---------------------------- | ---------------------- | ----------------------------------------------------------------- |
| **Pipeline execution** | ~320s                        | <1s                    | 300x+ improvement via smart heuristic extraction                  |
| **LIME perturbations** | 500 fixed                    | 30-80 dynamic          | ~85% latency reduction with prediction caching                    |
| **Sentence relevance** | Per-sentence QA forward pass | TF-IDF pre-filtering   | O(1) vs O(n) model calls                                          |
| **Noise entities**     | 100+ spurious                | ~0                     | Aggressive filtering (special chars, short values, numeric keys)  |
| **HTTP connections**   | New client per call          | Singleton with pooling | Connection reuse across integration cycle                         |
| **Text normalization** | Raw PDF artifacts            | Intake-level cleaning  | Ligature replacement, whitespace normalization, null byte removal |

## Supported Domains & File Formats

### Document Domains

The **IDPO pipeline is domain-agnostic** — it classifies documents by structural layout (table, form, text, scanned), not business domain. Any document type can be processed. The **Guardrails layer** provides domain-specific schema validation for 7 document types:

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

```
                        ┌──────────────────────────────────┐
                        │    frontend/  (Next.js 15)        │
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

### Integration Pipeline Cycle

When a document is processed, it flows through all four services in a continuous learning cycle:

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                                                                 │
  │   ①  IDPO → AHMN     Get policy advice before processing       │
  │   ②  IDPO            Run 13-agent extraction pipeline           │
  │   ③  IDPO → Guard    Validate output through 5-layer ensemble  │
  │   ④  IDPO → XAI      Generate attention/LIME explanations       │
  │   ⑤  IDPO → AHMN     Log metrics (F1, cost, latency) → learn  │
  │                                                                 │
  │        ⑤ feeds back into ① — the system improves with          │
  │           every document processed (closed-loop learning)       │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘
```

This is orchestrated by `idpo/integration.py` using HTTP calls with graceful degradation — if any service is unavailable, the pipeline continues with partial results.

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

- **Docker** & **Docker Compose** v2+ (only requirement for production)
- Python 3.11+ (for local development)
- Node.js 18+ (for frontend development)

### Run with Docker (Recommended)

```bash
# 1. Clone the repository
git clone <repo-url>
cd modular-multi-agent-document-ai

# 2. Configure environment
cp .env.example .env
# Edit .env to set JWT_SECRET_KEY to a random 32-char string

# 3. Build and start all 7 services
docker compose up --build

# 4. Open the app
open http://localhost:3000
```

| Service     | URL                        |
| ----------- | -------------------------- |
| Frontend    | http://localhost:3000      |
| Gateway API | http://localhost:8000      |
| API Docs    | http://localhost:8000/docs |

**Default admin credentials:** `admin` / `admin123`

### Local Development

```bash
# Gateway
cd gateway && pip install -r requirements.txt
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
python -m pytest ahmn_core/tests/ -v   # Core algorithm tests
python -m pytest guardrails/tests/ -v  # Guardrail ensemble tests
python -m pytest xai_hitl/tests/ -v    # XAI & HITL tests
```

---

## API Endpoints

All traffic flows through the gateway at `:8000`. JWT authentication is required for all `/api/*` routes (except `/api/auth/login` and `/api/auth/signup`).

### Authentication

| Method | Path                         | Description           |
| ------ | ---------------------------- | --------------------- |
| POST   | `/api/auth/login`            | Login → JWT token     |
| POST   | `/api/auth/signup`           | Self-registration     |
| GET    | `/api/auth/me`               | Current user profile  |
| POST   | `/api/auth/register`         | Admin: create user    |
| GET    | `/api/auth/users`            | Admin: list all users |
| PATCH  | `/api/auth/users/:id/toggle` | Admin: enable/disable |

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
| `/pricing`  | Plans overview      |
| `/contact`  | Contact information |
| `/login`    | User login          |
| `/signup`   | User registration   |

### Dashboard (Authenticated)

| Path                      | Access | Description                           |
| ------------------------- | ------ | ------------------------------------- |
| `/dashboard`              | All    | Overview with health, stats, pipeline |
| `/dashboard/xai`          | All    | XAI Q&A chat interface                |
| `/dashboard/hitl`         | All    | HITL expert feedback & review         |
| `/dashboard/guardrails`   | All    | Guardrails validation testing         |
| `/dashboard/idpo`         | All    | Document processing with pipeline viz |
| `/dashboard/submit`       | Admin  | Submit document data                  |
| `/dashboard/experiments`  | Admin  | Experiment results & charts           |
| `/dashboard/rabi`         | Admin  | RABI cold-start interactive demo      |
| `/dashboard/daaf`         | Admin  | DAAF drift detection interactive demo |
| `/dashboard/results`      | Admin  | Comparative analysis                  |
| `/dashboard/architecture` | Admin  | System architecture visualization     |
| `/dashboard/admin`        | Admin  | User management                       |

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
│   ├── engine/xai_engine.py    # DistilBERT-SQuAD + Attention Importance + LIME
│   ├── hitl/models.py          # Feedback types, HITLFeedback dataclass
│   └── tests/
│
├── idpo/                       # Service 4: IDPO (Nayanapriya S.A.T.)
│   ├── cli.py                  # CLI entry point
│   ├── integration.py          # ★ Cross-service integration layer
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
├── frontend/                   # Next.js 15 + React 19 web app
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
├── scripts/init.sql            # PostgreSQL schema + seeds
├── docker-compose.yml          # 7 services orchestration
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

## Production Deployment

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
  -d '{"username":"admin","password":"admin123"}'

# View logs
docker compose logs -f --tail=50
```

### 5. Production Hardening Checklist

- [ ] Change the default admin password after first login
- [ ] Set strong, unique values for `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, and `REDIS_PASSWORD`
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
