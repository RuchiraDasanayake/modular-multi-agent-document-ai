# Contributing to Modular Multi-Agent Document AI

Thank you for your interest in contributing! This document provides guidelines for the development workflow.

## Project Structure

This monorepo contains the document extraction product and separate research services.
The supported Windows product runs natively with PostgreSQL, the gateway, a persistent
Python worker and the Next.js frontend. The research services and optional Docker
deployment have separate prerequisites and validation boundaries.

| Directory     | Owner              | Description                         |
| ------------- | ------------------ | ----------------------------------- |
| `ahmn_core/`  | Dasanayake D.R.L.  | AHMN bandit engine (TS, RABI, DAAF) |
| `guardrails/` | Wijetunga W.L.A.T. | 5-layer hallucination detection     |
| `xai_hitl/`   | Pathirana M.M.     | XAI explanations + HITL feedback    |
| `idpo/`       | Nayanapriya S.A.T. | Document processing orchestration   |
| `gateway/`    | Shared             | JWT auth + reverse proxy            |
| `frontend/`   | Shared             | Next.js 16 web application          |

## Getting Started

For Windows without Docker, follow the [native product setup](scripts/native_product.md).
It describes the runtime configuration, production build, launcher, health checks and
storage directories. Then use the [product quickstart](docs/PRODUCT_QUICKSTART.md)
to create a job, confirm a schema, preview, review and export.

For the optional Docker deployment:

```bash
# 1. Clone the repo
git clone <repo-url>
cd modular-multi-agent-document-ai

# 2. Copy environment file
cp .env.example .env

# 3. Build and run
docker compose up --build
```

Docker's Automatic extraction path uses a
private product worker and shared data volume. The canonical research job runner
still requires the single-host setup. See [Public Demo Deployment](docs/PUBLIC_DEMO_DEPLOYMENT.md)
for each supported path and its validation limits.

## Development Workflow

### Branch Naming

```
feature/<component>/<description>   # e.g., feature/ahmn/rabi-temperature-tuning
fix/<component>/<description>       # e.g., fix/guardrails/pii-false-positive
docs/<description>                  # e.g., docs/update-architecture-diagram
```

### Running Tests

```bash
# All tests
python -m pytest ahmn_core/tests/ guardrails/tests/ xai_hitl/tests/ -v

# Individual service
python -m pytest ahmn_core/tests/ -v
python -m pytest guardrails/tests/ -v
python -m pytest xai_hitl/tests/ -v
```

### Code Style

- **Python**: Follow PEP 8. Use type hints. Docstrings for all public functions.
- **TypeScript**: Strict mode enabled. Use functional components with hooks.
- **CSS**: Use Tailwind utility classes. Follow the glassmorphism design system (`glass-panel`, `glass-card`, `glass-input`, `glass-button`).

### Adding a New Endpoint

1. Add the route handler in the appropriate service's `main.py`
2. Add the Pydantic request/response models
3. The gateway auto-proxies based on path prefix — no gateway changes needed
4. Add the TypeScript type in `frontend/src/types/index.ts`
5. Add the API method in `frontend/src/lib/api.ts`
6. Add the UI component/page

### Docker Builds

```bash
# Build all services
docker compose build

# Rebuild one service
docker compose build <service-name>

# View logs
docker compose logs -f <service-name>
```

## Architecture Decisions

- **No shared database** between services (except gateway auth tables in the same PostgreSQL instance as AHMN)
- **HTTP-based integration** via `idpo/integration.py` — IDPO orchestrates the cycle
- **Graceful degradation** — if a service is down, the integration layer returns partial results
- **In-memory stores** for guardrails audit log and HITL feedback (stateless services)

## Pull Request Checklist

- [ ] Tests pass (`pytest`)
- [ ] TypeScript compiles (`npx tsc --noEmit`)
- [ ] Docker builds succeed (`docker compose build`)
- [ ] No hardcoded secrets or credentials
- [ ] README updated if adding new features/endpoints
