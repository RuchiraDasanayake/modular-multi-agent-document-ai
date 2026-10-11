# Setup Guide

Estimated fresh-machine setup time: **30–60 min** (mostly downloads).

This guide sets up local development on one machine. To rebuild the benchmark packs and reproduce the paper's results
afterwards, follow [docs/REPRODUCING_RESULTS.md](docs/REPRODUCING_RESULTS.md).

---

## 1. Prerequisites (install once, system-wide)

| Tool | Version | Where |
|------|---------|--------|
| Python | **3.10.x** (PaddlePaddle 2.6.2 does not support 3.11 or newer) | python.org |
| Node.js | 18+ | nodejs.org |
| Docker | Docker Desktop or Docker Engine with Compose v2 | docker.com (runs Postgres and Redis for sign-in) |
| Tesseract OCR | 5.x | UB Mannheim installer (Windows): https://github.com/UB-Mannheim/tesseract/wiki |
| Ollama | latest | ollama.com |

---

## 2. Clone and Python environment

```powershell
git clone <repo-url>
cd modular-multi-agent-document-ai

# Must be Python 3.10
py -3.10 --version
py -3.10 -m venv .venv

.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt -r gateway/requirements.txt
.venv\Scripts\python -m pip install -e .
```

Run every Python command from the repository root with the virtual environment's interpreter, as above. On macOS or
Linux use `python3.10 -m venv .venv` and `.venv/bin/python` instead.

---

## 3. Tesseract path (Windows)

After installing Tesseract, add its folder to `PATH` and check that it runs:

```powershell
tesseract --version
```

Default install path: `C:\Program Files\Tesseract-OCR\tesseract.exe`

---

## 4. Ollama + model

```powershell
# Pull the model used in the paper (~6.6 GB download)
ollama pull qwen3.5:9b

# Verify
ollama list   # should show qwen3.5:9b
```

Ollama must be **running** during extraction and benchmarks. Start it with `ollama serve` if it is not running as a
service.

---

## 5. PaddleOCR models (auto-download on first run)

The first time the pipeline reads a scanned image, PaddleOCR downloads about 80 MB of model weights to `~/.paddleocr/`.
No manual step is needed, but the first run needs internet access.

---

## 6. Sign-in: database, Redis and gateway

The job API and the dashboard pages need a session that the gateway accepts (see "Access Control" in
[docs/SYSTEM_CONTRACT.md](docs/SYSTEM_CONTRACT.md)).

```powershell
Copy-Item .env.example .env       # then set JWT_SECRET_KEY and ADMIN_PASSWORD in .env
docker compose up -d db redis     # Postgres with the schema from scripts/init.sql, and Redis

# .env points at the Docker hosts db and redis; outside Docker both are on localhost
$env:POSTGRES_URI = "postgresql://user:password@localhost:5432/ahmn_db"
$env:REDIS_URL = "redis://:docai_redis_secret@localhost:6379/1"
.venv\Scripts\python -m uvicorn gateway.main:app --port 8000
```

On startup, if no admin account exists, the gateway creates one named `ADMIN_USERNAME` (default `admin`) with
`ADMIN_PASSWORD`. Existing accounts are never changed. Give `JWT_SECRET_KEY` a long random value
(`.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(48))"`). With the built-in default the gateway
generates a secret and, outside Docker, usually cannot save it, so every restart signs everyone out.

---

## 7. Frontend

```powershell
cd frontend
npm install
npm run dev     # http://localhost:3000
```

Sign in at http://localhost:3000/login with the admin account. The frontend reaches the gateway at
`NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). Its job runner executes `python -m idpo.cli process-inbox`
with `../.venv/Scripts/python.exe`, as set in `frontend/runner.config.json`; on macOS or Linux change `program` and
`command` there to `../.venv/bin/python`. Runs, uploads and jobs are stored in the `idpo-data` folder next to the
repository; override it with `IDPO_DATA_DIR`.

---

## 8. Run a benchmark

Benchmark packs reference images that are built from the CORD v2 and FUNSD downloads (see sections 2–3 of
[docs/REPRODUCING_RESULTS.md](docs/REPRODUCING_RESULTS.md)). A quick check with five CORD receipts:

```powershell
.venv\Scripts\python scripts\build_cord_benchmark_pack.py --split validation --limit 5 --seed 17
.venv\Scripts\python scripts\run_idpo_benchmark.py --pack datasets\cord_pack_5.json --config configs\idpo_research_config.json
```

Every run processes the pack in both the `static` and `adaptive_safe` conditions. Add `--register-frontend-jobs` to
make the runs visible as jobs in the frontend.

---

## Key config files

| File | Purpose |
|------|---------|
| `configs/idpo_research_config.json` | Research config used for the paper (OCR engine, AHMN, LLM, policies) |
| `configs/policy_store_research.json` | Policy definitions for the `adaptive_safe` condition |
| `configs/policy_store_baseline.json` | `default`-only policy store for the `static` condition |
| `configs/config.json` | Default pipeline config |

---

## What runs where

- **LLM**: Ollama on this machine (`qwen3.5:9b`); must be running
- **OCR**: PaddleOCR 2.9.1 (CPU), with Tesseract as the fallback
- **AHMN routing**: Thompson sampling inside the IDPO pipeline; the `ahmn_core` service is not needed for extraction
- **Job API**: route handlers in the Next.js server (`/api/jobs`, `/api/runs`, `/api/benchmarks`); its runner executes
  `idpo.cli process-inbox` and reads and writes `IDPO_DATA_DIR`
- **Gateway**: FastAPI on port 8000; sign-in, plus a proxy to the Python services
- **Postgres and Redis**: user accounts and the token blacklist for the gateway

---

## Troubleshooting

**PaddleOCR crashes or won't import**: Use Python 3.10. Python 3.11 and newer break PaddlePaddle 2.6.2.

**`tesseract not found`**: Add the Tesseract install folder to `PATH`, or set the `TESSDATA_PREFIX` environment variable.

**`ollama: connection refused`**: Run `ollama serve` in a separate terminal.

**The job API answers 401 "Sign in to use the job API."**: Sign in at `/login`; an expired session also returns 401.

**Pages or the job API answer 503 "The sign-in service is unavailable."**: The frontend cannot reach the gateway. Start
it (section 6) and check `NEXT_PUBLIC_API_URL`.

**The gateway cannot connect to the database or Redis**: Check that `docker compose up -d db redis` is running and that
`POSTGRES_URI` and `REDIS_URL` point at `localhost`, not at `db` or `redis`.

**Benchmark shows Tesseract in results**: The benchmark subprocess resolves to `.venv/Scripts/python.exe`. If
PaddleOCR is still not used, check that `ocr_engine` in `configs/idpo_research_config.json` is `"paddle"`.
