# IDPO Frontend Runner UI

Frontend-only control plane for browsing and launching IDPO runs.

This project adds:
- Next.js UI for starting and inspecting IDPO runs.
- Local runner API (`/api/*`) that executes a small whitelist of CLI commands.
- Artifact discovery over the external IDPO runtime data root.

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

Runtime data defaults to the shared `IDPO_DATA_DIR` root when that environment variable is set. If it is unset, the checked-in config points to the external sibling folder `../idpo-data` rather than writing under the source tree.

Default command included:

```json
{
  "id": "idpo_process_inbox",
  "program": "python",
  "args": ["-m", "idpo.cli", "process-inbox", "--root", "{workspace_root}", "--config", "{config_path}", "--input-dir", "{input_dir}"],
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

## 4) Run Flow

1. Open `Dashboard > Doc Processing` (`/dashboard/idpo`).
2. Upload documents in **New Run Wizard**.
3. Adjust config and extraction settings if needed.
4. Start run and watch live logs.
5. Open run detail page and show:
   - overview cards
   - document extraction
   - validation
   - recovery/escalation
   - provenance timeline export
6. Open `Presentation Mode` (`/dashboard/idpo/presentation`) to inspect saved runs.

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

## 7) Sample Runs

If `runsDir` is empty/unavailable, UI falls back to:
- `frontend/demo_sample_runs/`

Sample data included in:
- `demo_sample_runs/sample_run_001/`

## 8) Useful Commands

Run build validation:

```bash
npm run build
```

