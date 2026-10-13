# Native Windows product launcher

Requires PowerShell 7.2+ (`pwsh`), Node.js 22.12+, an initialized PostgreSQL 16 data cluster, the repo extraction Python environment, and a gateway Python environment with gateway dependencies. This starts PostgreSQL, the gateway, an independent extraction worker, and the Next.js frontend on `127.0.0.1`. pg-boss provides a durable PostgreSQL queue; the worker executes the local Python extractor. Docker is not required. Run `npm ci` in `frontend` including development dependencies for the TypeScript worker launcher.

Self-service password recovery is unavailable. The unauthenticated recovery and
reset endpoints return 503, including for older reset tokens; they do not send
email. Users who still know their password can use authenticated password change.
See the [recovery shutdown](../docs/evaluations/PASSWORD_RECOVERY_SHUTDOWN_20261013.md).

Store a private JSON config outside the repo, for example `I:\DocAI-Runtime\native-product.json`:

For a **fresh installation**, obtain PostgreSQL 16 Windows binaries through the
[official PostgreSQL Windows page](https://www.postgresql.org/download/windows/) and
[EDB binary archive page](https://www.enterprisedb.com/download-postgresql-binaries?lang=en).
Extract them beneath your runtime directory. Restrict that directory's Windows ACL to the operator, SYSTEM and
Administrators before creating credentials. Install `gateway/requirements.txt` in a separate Python environment.
Then initialize once (adjust the example paths to your installation):

```powershell
& I:\DocAI-Runtime\gateway-venv\Scripts\python.exe scripts/init_native_product.py `
  --runtime-root I:\DocAI-Runtime --pg-bin I:\DocAI-Runtime\postgresql-16.15-5\pgsql\bin
```

This creates random credentials, a SCRAM-authenticated loopback cluster, a non-superuser application role, and the
minimal auth schema; it stops PostgreSQL after initialization. The private config also includes a separate database
maintenance credential. It refuses to overwrite an existing config or data cluster. If initialization is interrupted,
keep those files and inspect the bootstrap log; do not initialize over existing data. To adapt an existing database,
apply `gateway/native_auth.sql` explicitly to the same database named by `databaseUrl`.

Changing an existing deployment from Redis to PostgreSQL token revocation requires migrating unexpired revocation
receipts or rotating the JWT secret to expire existing sessions. A fresh initialization generates a new JWT secret.

The generated config has this shape (the sample below is documentation only):

```json
{
  "repoRoot": "C:\\path\\to\\modular-multi-agent-document-ai",
  "runtimeRoot": "I:\\DocAI-Runtime",
  "pgBin": "I:\\DocAI-Runtime\\pgsql\\bin",
  "pgData": "I:\\DocAI-Runtime\\postgres-data",
  "postgresPort": 55432,
  "databaseUrl": "postgresql://docai:REPLACE_WITH_PASSWORD@127.0.0.1:55432/docai",
  "jwtSecret": "REPLACE_WITH_AT_LEAST_32_RANDOM_CHARACTERS",
  "adminPassword": "REPLACE_WITH_A_STRONG_ADMIN_PASSWORD",
  "dataDir": "I:\\DocAI-Runtime\\data",
  "gatewayPort": 8000,
  "frontendPort": 3000,
  "pythonPath": "C:\\path\\to\\modular-multi-agent-document-ai\\.venv\\Scripts\\python.exe",
  "gatewayPythonPath": "I:\\DocAI-Runtime\\gateway-venv\\Scripts\\python.exe"
}
```

`gatewayPythonPath` defaults to `pythonPath`; `nodePath` defaults to `node.exe` on PATH; `adminUsername` defaults to `admin`. The launcher sets `IDPO_PRODUCT_PYTHON` from `pythonPath`, overriding only the product extractor executable so its environment can live on a separate drive. Give the JSON file a private ACL because it contains credentials. The launcher never writes those secrets to its process receipt or console output.

Use Python 3.13 and install `idpo/product_auto/requirements-worker.txt` in a dedicated product environment.
The historical repository environment may lack PDF, image, OCR or Office dependencies even if text extraction works.
Verify `python -m pip check` and run the mixed-format parser checks before advertising those formats.

For an installation with the separately pinned RapidOCR runtime, the optional
confirmed-schema candidate can be selected explicitly in the private configuration:

```json
{
  "autoOcrEngine": "rapidocr",
  "rapidOcrPythonPath": "I:\\path\\to\\rapidocr-runtime\\Scripts\\python.exe",
  "rapidOcrWorkDir": "I:\\path\\to\\ocr-scratch",
  "rapidOcrTimeoutSeconds": 120,
  "rapidOcrMaxRssMiB": 1536,
  "autoResponseFormat": "strict_confirmed_values_v1",
  "autoLongDocument": "bounded_text_segments_v1",
  "autoVisualDocument": "bounded_visual_selective_v2",
  "autoMaxOutputTokens": 8192,
  "autoTimeoutSeconds": 180
}
```

These keys extend the existing configuration; they do not replace its required
database, authentication and path settings. The selected model must support the
configured strict text and image request contracts. This candidate uses image
input on eligible sources for repeated columns, long text or no usable OCR text;
short scalar tasks keep the text route. See the
[versioned selection rule](../docs/evaluations/SELECTIVE_VISUAL_ROUTING_V2_20261013.md).
The launcher checks the OCR runtime before declaring readiness. New jobs seal
these settings at admission; already queued jobs retain their original settings.
No default deployment is silently changed by installing the newer code.

Startup now runs the offline [product capability preflight](../docs/PRODUCT_RUNTIME_PREFLIGHT.md)
with the configured `pythonPath` before starting services or declaring an existing stack ready.
It allows 60 seconds by default (or the selected optional OCR timeout plus 30 seconds), stops only its identified probe process tree on timeout, and refuses startup on
missing capabilities, invalid output, or a failed probe. The sanitized, timestamped receipt is saved at
`runtimeRoot\state\product-capabilities.json`; raw stdout/stderr capture files are removed. The receipt
contains capability flags and provider setup state, never keys, endpoint URLs, model names or raw errors.
An existing service stack is not stopped by a failed check. `-Status` remains a process-status query and
does not repeat the capability check. Provider state `configured_unverified` does not establish endpoint
health, model availability or credential validity; the preflight makes no API calls.

Optional private config fields `autoModel`, `autoApiBaseUrl`, and `icoreApiKey` configure the same provider for the
web app and worker. Install the `openai` client in the extraction environment for an OpenAI-compatible endpoint.
Use an explicit HTTPS endpoint, or loopback HTTP for a local server. No provider key belongs in tracked files.
Optional `autoMaxOutputTokens` (integer 1–16,384) and `autoTimeoutSeconds` (integer 1–600) map to
`IDPO_AUTO_MAX_OUTPUT_TOKENS` and `IDPO_AUTO_TIMEOUT_S` for both the web helper and worker. Product defaults are
8,192 output tokens and 180 seconds when these server settings are absent. These are per-call bounds;
they do not authorize automatic retries or guarantee provider output completeness.
For portable OCR installations, optional `tesseractPath` and `tessdataDir` set `TESSERACT_CMD` and `TESSDATA_PREFIX`
in both web helper and extraction worker. Verify the executable and language data before processing scans.

Optional `autoOcrEngine` selects `tesseract` (default) or `rapidocr`. RapidOCR requires
`rapidOcrPythonPath` and `rapidOcrWorkDir`, both absolute existing paths, plus optional integer
`rapidOcrTimeoutSeconds` (1–180, default 120) and `rapidOcrMaxRssMiB` (128–2048, default 1536).
Provision the separate CPU environment and model hashes documented in
[the RapidOCR adapter contract](../docs/PRODUCT_RAPIDOCR.md). Startup then runs its additional
synthetic local OCR check. Tesseract remains required for schema sampling.

Optional `autoResponseFormat` selects `plain_json` (default) or
`strict_confirmed_values_v1`. The strict profile applies only to user-confirmed schemas;
discovery and approved recipes retain plain JSON. The provider receives a strict schema and
the product independently validates the returned envelope and source evidence. This does not
establish semantic accuracy or guarantee that every compatible provider enforces the schema.

New queue dispatch version 3 seals the selected OCR environment, bounds and response format
alongside the model budget. Later environment edits cannot change an admitted attempt. Versions
1 and 2 keep their historical arguments. Change these settings only between attempts and restart
the native stack so the web and worker use the same selection. These are experimental extraction
options; the deployment default remains Tesseract with plain JSON until quality trials support
a different choice.

Optional `autoLongDocument` selects `reject` (historical default) or
`bounded_text_segments_v1` for confirmed schemas. The latter plans at most four
24,000-character text segments without overlap or discarded source text. It maps
evidence back to original page offsets, exposes conflicting scalar values for
review, and never silently merges a row across segment boundaries. Requests that
cannot be completely covered within those bounds fail explicitly. Extraction
profile version 2 pins this policy; version 1 retains the historical text limit.

Optional `autoVisualDocument` selects `disabled` (default), `bounded_visual_v1`,
or `bounded_visual_selective_v2`. Version 3 extraction profiles seal this choice.
With a confirmed schema, v1 sends eligible images and PDFs requiring OCR through
the visual path. Selective v2 uses the pre-call selection rule above: short scalar
sources with usable OCR text use strict text extraction, while repeated columns,
long text and missing usable OCR text use the visual path on eligible sources.
All-native PDFs and other native/text formats keep their text path. The visual path
prepares every page before any model call, with at most four requests, 12 images
and 4 MiB per request, and a 2,048-pixel image edge. A source that cannot fit fails
explicitly. Every visual proposal requires review. This option sends source
images to the configured model endpoint; it requires a measured quality/cost
comparison before deployment. See [visual extraction](../docs/PRODUCT_VISUAL_BOUNDARY.md).

The launcher sets `PRODUCT_EXECUTION_MODE=postgres` and `PRODUCT_QUEUE_DATABASE_URL` from `databaseUrl`.
The app role needs schema creation privileges in its own database: pg-boss manages `docai_queue`, and the queue
adapter initializes `product.execution_dispatches` under a database lock. No existing product metadata is imported
by this step. Artifacts still live beneath `dataDir`; every worker must see the same filesystem paths and runner
configuration. Default worker concurrency is one, with at most 64 pending runs/20,000 pending documents per owner,
10,000 documents per run and six hours per active run. These are bounded admission limits, not measured capacity.
Large jobs should be split into bounded runs until per-document resumption is implemented.

Starting a run stores a sealed execution intent and copies its source bytes before atomic queue admission. Lost
database acknowledgements are reconciled by the same run identity. A changed source/schema/runner configuration
fails closed. Worker death or expiry marks the attempt failed; no model call is automatically retried. The user
may explicitly start a new run after inspecting an uncertain outcome. This avoids silently repeating paid requests
but does not provide transactional exactly-once execution of an external API.

From the repo root:

```powershell
pwsh -File scripts/start_native_product.ps1 -ConfigPath I:\DocAI-Runtime\native-product.json
pwsh -File scripts/start_native_product.ps1 -ConfigPath I:\DocAI-Runtime\native-product.json -Status
pwsh -File scripts/stop_native_product.ps1 -ConfigPath I:\DocAI-Runtime\native-product.json
```

The frontend is at `http://127.0.0.1:3000` with the example config. `frontendMode` defaults to `development`
for existing setups. Set it to `production` for a built Next.js server. Stop the tracked stack, then run:

```powershell
pwsh -File scripts/build_native_frontend.ps1 -ConfigPath I:\DocAI-Runtime\native-product.json
pwsh -File scripts/start_native_product.ps1 -ConfigPath I:\DocAI-Runtime\native-product.json
```

The native build uses `.next-product`, a checked junction into `runtimeRoot\frontend-build\output` so build storage
can live on the data drive. A sibling dependency junction points to the checkout's existing `node_modules`;
this preserves Node package resolution from the physical build location. It leaves development and Docker build directories separate. Build logs and
a source-fingerprint receipt are stored under the private runtime directory. Production startup refuses a
missing/stale build or a different baked gateway port; rebuild after frontend source/configuration changes.
The build has a 15-minute bound and will not replace another cache location. It does not need provider credentials.
The signed process receipt binds the frontend mode; switching mode requires stopping the tracked stack.

Startup waits for PostgreSQL, gateway, worker and frontend health. The runtime directory holds process state,
logs, PostgreSQL files and new upload/job data. It does not migrate existing `idpo-data`; the example `dataDir`
opens a fresh workspace. Production compilation removes development-server overhead; it does not establish
public deployment, multi-host readiness or extraction quality.

Startup refuses any occupied, untracked port. A second start against a healthy tracked stack is safe. If startup stops partway through, inspect `-Status` and the logs, then run the stop script before retrying. Stop verifies the recorded process identity and only terminates tracked gateway/frontend/worker process trees; PostgreSQL uses `pg_ctl stop -m fast`. It preserves runtime data and logs. A missing or altered process receipt is never treated as authority to kill a port listener. Stopping a worker during active extraction produces an uncertain failed attempt; queued attempts persist for restart.

Source-free checks:

```powershell
pwsh -File scripts/tests/native_product.test.ps1
pwsh -File scripts/tests/native_product_preflight.test.ps1
```

The second suite substitutes a local Node stub for the capability probe; it makes no model calls and
does not start PostgreSQL or application services.
