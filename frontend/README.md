# IDPO Frontend Runner UI

Frontend control plane for browsing and launching IDPO runs through the hosted job path.

This project adds:
- Next.js UI for starting and inspecting IDPO runs.
- Job API (`/api/*`) that queues uploads and executes a small whitelist of CLI commands.
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
- `http://localhost:3000/dashboard/idpo/jobs`

## 4) Run Flow

1. Open `Dashboard > Doc Processing` (`/dashboard/idpo/jobs`).
2. Create a job.
3. Upload documents into the job queue.
4. Configure extraction fields and select `adaptive`, `strict`, or `both`.
5. Process selected documents and watch queue state move through `loaded -> processing -> processed / failed`.
6. Inspect structured results in the job detail page.
7. Open atomic document detail when deeper inspection is needed.

### Opt-in automatic schema extraction

Open a job and select **Automatic schema extraction**. Select uploaded files, run extraction, then open each result to compare the original beside proposed fields, values, document status, and exact text evidence. The preview uses the existing owner-scoped source endpoint. Reviewers can correct values, remove spurious proposed fields, and add missed scalar fields (text, integer, decimal, boolean, or date). The API returns a `correctedResult` derived from the immutable machine candidate and latest audited review. Undecided machine values remain `needs_review`; added fields have human provenance and no machine evidence span. This is document-level adjudication, not approval of a reusable extraction recipe. Every save appends an audit event with reviewer ID, timestamp, original machine values, and decisions. Review saves require the current revision; a concurrent edit returns 409 and must be reloaded before saving again.

The single-host runner invokes `python -m idpo.cli process-auto`; Docker uses a private worker through a Unix socket. Without a model it uses the local deterministic baseline. To enable model proposals, configure `IDPO_AUTO_MODEL` and `IDPO_AUTO_API_BASE_URL` in the **server** environment. `ICORE_API_KEY` is required for HTTPS model endpoints; exact loopback HTTP endpoints (`localhost`, `127.0.0.1`, `[::1]`) may omit it for a local OpenAI-compatible model. The key is never sent to the browser or stored in job artifacts. Model-backed runs require an admin account until quotas and cost controls exist.

Run GETs only read state. The owning frontend renews a five-minute filesystem lease every 15 seconds; a separate Node recovery scan checks every 30 seconds and also runs on a new extraction POST. A fully validated completion marker can appear in GET before the exit callback publishes an exclusive terminal record. An expired incomplete run becomes failed and can be retried. The scan begins when the Node frontend starts; recovery therefore requires a running frontend process. This single-host mechanism does not provide a durable distributed queue, cancellation, or a lock against simultaneous new starts. An expired run may still occupy the private worker briefly; its staged input is retained. See `docs/architecture/ADR-0004-product-run-recovery.md`. Extraction accuracy and cost still require the distinct-document evaluation gate in `docs/PRODUCTIZATION_PLAN.md`.

## 5) API Endpoints (Runner + Artifacts)

- `GET /api/health`
- `GET /api/system/status`
- `GET /api/jobs`, `POST /api/jobs` (create a job)
- `GET /api/jobs/:jobId`, `PATCH /api/jobs/:jobId`
- `POST /api/jobs/:jobId/documents` (multipart upload into the job queue)
- `POST /api/jobs/:jobId/runs` (process selected documents: `{ selectedFileIds, mode, settings }`)
- `GET /api/jobs/:jobId/auto`, `POST /api/jobs/:jobId/auto` (opt-in automatic extraction with server-selected model)
- `GET /api/jobs/:jobId/auto/:runId/docs/:docId`, `POST /api/jobs/:jobId/auto/:runId/docs/:docId` (candidate and append-only human review)
- `GET /api/jobs/:jobId/docs/:docId`, `POST /api/jobs/:jobId/docs/:docId` (document detail and review)
- `GET /api/jobs/:jobId/docs/:docId/content`
- `GET /api/jobs/:jobId/docs/:docId/text` (OCR text of the document's latest run, first 20,000 characters; used by AI Q&A)
- `GET /api/jobs/:jobId/policies`, `POST /api/jobs/:jobId/policies`, `PATCH /api/jobs/:jobId/policies`
- `POST /api/jobs/:jobId/validate`
- `GET /api/runs`, `GET /api/runs/:runId/summary`
- `GET /api/benchmarks`, `GET /api/benchmarks/:benchmarkRunId`

`/api/system/status` now reports both:
- local runner CLI readiness
- live HTTP health for `gateway`, `ahmn`, `guardrails`, `xai-hitl`, and `idpo-ui`

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

## 9) Public Demo Deployment

The currently supported public demo path is not Vercel-only and not a frontend-only container.

Use the single-host deployment model documented in:

- [docs/PUBLIC_DEMO_DEPLOYMENT.md](../docs/PUBLIC_DEMO_DEPLOYMENT.md)

That model keeps the frontend runner on the same host as:

- the repo checkout
- Python and `idpo.cli`
- Ollama
- the writable `IDPO_DATA_DIR`

For host-only secrets such as `OPENAI_API_KEY`, use:

- `.local/public-demo.env.ps1`
- template: `scripts/public-demo.env.ps1.example`

