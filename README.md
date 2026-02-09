# AHMN — Adaptive Hierarchical Memory Network

> **Self-learning document processing advisor** that automatically selects optimal OCR pipelines using Thompson Sampling, RABI (cold-start transfer), and DAAF (drift adaptation).

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/downloads/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Next.js Frontend                      │
│   Login │ Dashboard │ Experiments │ RABI │ DAAF │ Admin  │
└────────────────────────┬────────────────────────────────┘
                         │ REST / JWT
┌────────────────────────▼────────────────────────────────┐
│                   FastAPI Backend                         │
│   /api/auth   /api/advice   /api/dashboard   /api/exp    │
└───────┬───────────────┬─────────────────────────────────┘
        │               │
   ┌────▼────┐   ┌──────▼──────┐   ┌─────────────┐
   │  Redis  │   │ PostgreSQL  │   │  ahmn_core   │
   │  (STM)  │   │ + pgvector  │   │ (algorithms) │
   └─────────┘   │  MTM + LTM  │   └──────────────┘
                 └─────────────┘
```

## Project Structure

```
modular-multi-agent-document-ai/
├── ahmn_core/          # Pure algorithm library (no web/DB deps)
│   ├── services/       # TS, RABI, DAAF, embeddings
│   ├── experiments/    # 840-run experiment framework
│   ├── tests/          # Pytest suite
│   └── output/         # Pre-computed results
├── backend/            # FastAPI server
│   ├── app/routers/    # auth, advice, dashboard, experiments
│   ├── app/services/   # JWT, password hashing
│   └── app/schemas/    # Pydantic models
├── frontend/           # Next.js dashboard
│   └── src/app/        # Pages: login, dashboard, RABI, DAAF, admin
├── scripts/            # init.sql, migrations
├── jobs/               # Cron: forgetting, promotion
├── docker-compose.yml  # Full stack orchestration
└── .env.example        # Environment template
```

## Quick Start

### Prerequisites

- Docker & Docker Compose (recommended)
- **OR** Node.js 20+, Python 3.13+, PostgreSQL 16, Redis

### Option 1: Docker (Recommended)

One command to run everything:

```bash
docker compose up --build
```

Then open **http://localhost:3000** and login:

- **Username**: `admin`
- **Password**: `admin123`

Services:

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### Option 2: Local Development

**1. Start Infrastructure**

```bash
cp .env.example .env
docker compose up -d db redis
```

**2. Backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**3. Frontend** (in a new terminal)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**

### Stop Services

```bash
docker compose down        # Stop all containers
docker compose down -v     # Stop and remove volumes (⚠️ deletes data)
```

## Core Algorithms

| Algorithm             | Purpose             | Key Formula                                    |
| --------------------- | ------------------- | ---------------------------------------------- |
| **Thompson Sampling** | Policy selection    | Sample θ ~ Beta(α, β), pick argmax             |
| **RABI**              | Cold-start transfer | α_init = 1 + Σ wᵢ·(αᵢ-1), wᵢ = softmax(simᵢ/τ) |
| **DAAF**              | Drift adaptation    | γ\* = √(Δ²/ln(t)), α_new = 1 + (1-γ)(α-1)      |

## API Endpoints

| Endpoint                          | Auth | Description                 |
| --------------------------------- | ---- | --------------------------- |
| `POST /api/auth/login`            | —    | Get JWT token               |
| `GET /api/auth/me`                | ✅   | Current user                |
| `POST /api/advice`                | ✅   | Get policy recommendation   |
| `POST /api/advice/log`            | ✅   | Log outcome (triggers DAAF) |
| `GET /api/dashboard/stats`        | ✅   | System statistics           |
| `GET /api/dashboard/memory/ltm`   | ✅   | LTM policies with α/β       |
| `POST /api/experiments/demo/daaf` | ✅   | Interactive DAAF demo       |
| `POST /api/experiments/demo/rabi` | ✅   | Interactive RABI demo       |

## Default Credentials

| Username | Password   | Role  |
| -------- | ---------- | ----- |
| `admin`  | `admin123` | Admin |

## Experiment Results

- **840 runs**: 7 methods × 4 scenarios × 30 seeds
- **AHMN-Full** (TS + RABI + DAAF) achieves lowest regret across all scenarios
- Robustness validated via 4 parameter sweeps

## Development

### Project Requirements

**Backend** ([backend/requirements.txt](backend/requirements.txt)):

- FastAPI 0.115+ — Web framework
- psycopg 3.2+ — Async PostgreSQL driver
- python-jose + bcrypt — JWT authentication
- sentence-transformers 3.3+ — Embeddings (384d)

**Frontend** ([frontend/package.json](frontend/package.json)):

- Next.js 15 + React 19 — Framework
- Recharts 2.15+ — Visualization
- Tailwind CSS 3.4 — Styling

### Docker Files

- **backend/Dockerfile** — Python 3.13-slim, single-stage
- **frontend/Dockerfile** — Node 20-alpine, multi-stage (deps → builder → runner)
- **docker-compose.yml** — Orchestrates 4 services (db, redis, backend, frontend)

### Code Quality

All code follows:

- Python: PEP 8, type hints, async/await patterns
- TypeScript: Strict mode, proper typing
- React: Server components, hooks best practices
- Docker: Multi-stage builds, .dockerignore for efficiency

## Troubleshooting

**Backend won't connect to DB:**

```bash
docker logs ahmn_backend  # Check for connection errors
docker compose up -d db   # Ensure DB is running
```

**Frontend build fails:**

```bash
cd frontend
rm -rf node_modules .next
npm install
npm run build
```

**Port already in use:**

```bash
# Edit .env and change ports:
BACKEND_PORT=8001
POSTGRES_PORT=5433
REDIS_PORT=6380
```

## License

MIT
