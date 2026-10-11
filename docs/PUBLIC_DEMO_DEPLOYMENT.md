# Public Demo Deployment

This document defines the fastest supported path for making the current system publicly accessible without a major architecture rewrite.

## Supported Deployment Model

Use a `single-host public demo` setup:

- one host machine runs the full stack
- the host machine contains the repo checkout
- the frontend runner spawns `python -m idpo.cli process-inbox` locally
- other laptops use a browser only

This is the current supported deployment model for demos, viva, and short-term public access.

## Why This Path

It matches the current runtime path:

`frontend job (POST /api/jobs/<job_id>/documents, then POST /api/jobs/<job_id>/runs) -> frontend job runner -> idpo.cli process-inbox -> IDPO_DATA_DIR/runs/<run_id>`

The job API (`/api/jobs`, `/api/runs`, `/api/benchmarks`) and the dashboard pages run on the frontend server, so the
frontend middleware checks every request against the gateway's `/api/auth/me` before serving it. A request without a
session the gateway accepts gets `401` (API) or a redirect to `/login` (pages); if the gateway is unreachable it gets
`503`. The frontend server must therefore reach the gateway at `INTERNAL_API_URL` (default `http://localhost:8000`).

That means the machine running the frontend must also have:

- Python environment for `idpo`
- Node.js for the frontend
- Ollama for local extraction
- access to `OPENAI_API_KEY` for cloud fallback
- local repo workspace access
- writable `IDPO_DATA_DIR`

## Unsupported For The Full Runtime

These are not the supported end-to-end deployment path right now:

- Vercel-only deployment
- frontend-only Docker deployment (the image ships `runner.config.docker.json`, whose
  command is a placeholder; jobs started there fail with "wrote no run output")
- any deployment where the frontend server cannot run local Python commands

Vercel can still host the UI later, but not the current full job-runner path without a separate worker redesign.

## Required Host Components

Required on the demo host:

- Python 3.10
- Node.js 18+
- repo checkout
- working virtual environment for Python services
- PostgreSQL
- Redis
- Ollama
- pulled Ollama model `qwen3.5:9b` (the `llm.local_model` in `configs/idpo_research_config.json`)
- `paddleocr` installed in the Python environment
- `pymupdf` installed in the Python environment, for scanned / image-only PDFs
  (Poppler is no longer required; `pdf2image` + Poppler is only a fallback)
- Tesseract OCR, as the fallback OCR engine. It is found on `PATH`, via
  `TESSERACT_CMD`, or in the default Windows install folders under
  `Program Files` / `%LOCALAPPDATA%\Programs`

Required for cloud fallback:

- `OPENAI_API_KEY`

Optional but recommended:

- `cloudflared` for public HTTPS access

## Python Version Note

For the current Windows public demo path, use `Python 3.10`.

The validated host setup in this repo now runs on `3.10` because the combined
`torch` / `sentence-transformers` / `paddleocr` stack was not stable in the
previous `3.13` environment on this machine.

## Ports

Expected local ports:

- `3000` frontend
- `8000` gateway
- `8001` AHMN
- `8002` guardrails
- `8003` xai_hitl
- `8004` IDPO
- `5432` PostgreSQL
- `6379` Redis

Publicly expose only:

- frontend on `3000`
- gateway on `8000`

Keep the other services host-local.

## Startup Scripts

Use these scripts from the repo root:

- `scripts/check_public_demo_host.ps1`
  Verifies the host is ready for the public demo path
- `scripts/start_public_demo_stack.ps1`
  Starts the stack with frontend and gateway bound for remote access
- `scripts/start_public_demo_tunnels.ps1`
  Starts Cloudflare quick tunnels for frontend and gateway, then restarts the stack with those public origins
- `scripts/start_frontend_public_url.ps1`
  Starts or reuses a frontend-only public URL for fast UI checks while developing against the local Next dev server
- `scripts/run_public_demo_smoke.ps1`
  Submits one small document through the real frontend runner path and verifies emitted artifacts
- `scripts/stop_local_stack.ps1`
  Stops tracked local service processes and any quick tunnels started by the repo scripts

## Local Secrets And Host Overrides

Do not hardcode secrets into tracked repo files.

For host-only settings, create:

`.\.local\public-demo.env.ps1`

You can copy the template from:

`scripts/public-demo.env.ps1.example`

Typical contents:

```powershell
$env:OPENAI_API_KEY = "replace-with-openai-key"
$env:AHMN_SEED_MODE = "seeded"
$env:PUBLIC_FRONTEND_ORIGIN = "https://frontend-demo.example.com"
$env:PUBLIC_API_ORIGIN = "https://api-demo.example.com"
```

`scripts/check_public_demo_host.ps1` and `scripts/start_public_demo_stack.ps1` load that file automatically when it exists.

## Basic Host Startup

From PowerShell:

```powershell
.\scripts\check_public_demo_host.ps1
.\scripts\start_public_demo_stack.ps1 `
  -FrontendOrigin "https://frontend-demo.example.com" `
  -ApiOrigin "https://api-demo.example.com"
```

For LAN-only use:

```powershell
.\scripts\start_public_demo_stack.ps1 `
  -FrontendOrigin "http://HOST_IP:3000" `
  -ApiOrigin "http://HOST_IP:8000"
```

The script turns public sign-up off (`PUBLIC_SIGNUP_ENABLED=false`), so visitors cannot create accounts. Create the
accounts you hand out (for example a viewer account for examiners) on `/dashboard/admin`. Pass `-AllowSignup`, or set
`PUBLIC_SIGNUP_ENABLED=true`, to keep `/signup` open.

After startup, run the smoke test. It signs in first, so give it an account password through `-Password`,
`SMOKE_PASSWORD`, or `ADMIN_PASSWORD` (the user defaults to `admin`; override with `-Username` or `SMOKE_USERNAME`):

```powershell
$env:SMOKE_PASSWORD = "<admin password>"
.\scripts\run_public_demo_smoke.ps1
```

This validates the real path:

`sign in -> POST /api/jobs -> POST /api/jobs/<job_id>/documents -> POST /api/jobs/<job_id>/runs -> frontend job runner -> idpo.cli process-inbox -> run artifacts on disk`

You can also inspect live stack health through:

`http://HOST:3000/api/system/status`

## Cloudflare Tunnel

Recommended public path:

1. run the stack on the host
2. start quick tunnels for frontend `3000` and gateway `8000`
3. restart the stack with those public origins
4. open the frontend public URL from another laptop

Typical tunnel mapping:

- `frontend-demo.example.com` -> `http://localhost:3000`
- `api-demo.example.com` -> `http://localhost:8000`

The frontend public origin and API public origin must match the values used when starting the stack.

For quick temporary public URLs on this host, use:

```powershell
.\scripts\start_public_demo_tunnels.ps1
```

That script:

- starts a quick tunnel to `http://127.0.0.1:8000`
- starts a quick tunnel to `http://127.0.0.1:3000`
- restarts the stack with the generated public origins
- writes tunnel state under `.local/tunnels.json`

For frontend-only UI iteration, use:

```powershell
.\scripts\start_frontend_public_url.ps1
```

That script:

- checks that the local frontend is reachable on `3000`
- reuses an existing live frontend tunnel when possible
- otherwise starts a fresh quick tunnel to `http://127.0.0.1:3000`
- writes state under `.local/frontend-tunnel.json`

## What To Show In Viva

Recommended flow:

1. show the repo and code on the host machine
2. show the deployment script and host readiness check
3. open the public frontend URL on another laptop
4. upload scanned PDFs or images
5. show results, artifacts, and run pages
6. explain that all compute happens on the host and client laptops are browser-only

## Operational Notes

- if the host machine is off, the public demo is off
- if `OPENAI_API_KEY` is missing, cloud fallback will not run
- if `qwen3.5:9b` is not installed in Ollama, local extraction will not run as configured
- choosing a different local model on a job (for example `phi3:mini`) makes the runner pull it
  through the Ollama HTTP API at `llm.base_url` before the run starts; the `ollama` CLI does not
  need to be on `PATH`, and the first run with a new model waits for the download
- if `paddleocr` is missing, scanned-document quality will degrade or fail depending on path
- if the frontend server restarts while a job is running, that job is marked failed
  ("Interrupted") on next load and must be run again
- set `NEXT_PUBLIC_CONTACT_EMAIL` before building the frontend to enable the Contact page form

## Next Evolution

If the team later needs a stronger always-on deployment, the next step is:

- keep the same frontend
- move `process-inbox` execution into a dedicated worker or service

That is explicitly future work, not required for the current public demo path.
