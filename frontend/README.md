# IDPO Frontend Runner UI

Frontend-only control plane for the multi-agent Document AI stack.

This project adds:
- Next.js web UI for running and inspecting IDPO runs.
- Local Runner API (`/api/*`) inside frontend that executes whitelisted CLI commands.
- Artifact discovery over `runs/<run_id>/...` without backend code changes.
- Presentation mode flow for PP1 demos.

## Stack
- Next.js 15 (App Router) + React + TypeScript
- Tailwind CSS
- Node runtime API routes for runner/artifact endpoints

## 1) Setup

From repo root:

```bash
cd frontend
npm install
```

## 2) Configure Runner

Edit `frontend/runner.config.json`:

- `workspaceRoot`: path to repo root (relative to `frontend/`)
- `runsDir`: real runs folder to read
- `commands`: whitelisted CLI commands only

Default command included:

```json
{
  "id": "idpo_demo",
  "program": "python",
  "args": ["-m", "idpo.demo", "--input", "{input_dir}", "--config", "{config_path}"],
  "cwd": ".."
}
```

Placeholders supported in args:
- `{input_dir}`
- `{config_path}`
- `{workspace_root}`

## 3) Run Dev Server

```bash
npm run dev
```

Open:
- `http://localhost:3000/dashboard/idpo`

## 4) Demo Flow (PP1)

1. Open `Dashboard > Doc Processing` (`/dashboard/idpo`).
2. Upload documents in **New Run Wizard**.
3. Configure shadow mode/policy/budget options.
4. Start run and watch live logs.
5. Open run detail page and show:
   - overview cards
   - document extraction
   - validation/guardrails
   - recovery/escalation
   - provenance timeline export
   - shadow comparison and rerun-with-policy action
6. Open `Presentation Mode` (`/dashboard/idpo/presentation`) for guided step cards.

## 5) API Endpoints (Runner + Artifacts)

- `GET /api/system/status`
- `GET /api/runs`
- `POST /api/runs/start`
- `GET /api/jobs/:jobId`
- `GET /api/runs/:runId/summary`
- `GET /api/runs/:runId/files`
- `GET /api/runs/:runId/file?path=...`
- `GET /api/runs/:runId/docs`
- `GET /api/runs/:runId/docs/:docId`
- `GET /api/runs/:runId/provenance`
- `GET /api/runs/:runId/metrics`
- `GET /api/runs/:runId/shadow`

## 6) Security Controls

- Upload extension allowlist from `runner.config.json`.
- Upload size limit from `runner.config.json`.
- Strict command whitelist (`commands` list only).
- Runtime arg templating only (no raw command execution from user input).
- Path traversal protection for artifact file reads.
- Run file reads restricted to configured run directory.

## 7) Mock Mode (Offline)

If `runsDir` is empty/unavailable, UI falls back to:
- `frontend/demo_sample_runs/`

Sample data included in:
- `demo_sample_runs/sample_run_001/`

## 8) Useful Commands

Run build validation:

```bash
npm run build
```

