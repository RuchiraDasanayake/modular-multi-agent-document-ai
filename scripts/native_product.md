# Native Windows product launcher

Requires PowerShell 7 (`pwsh`), Node.js, an initialized PostgreSQL 16 data cluster, the repo extraction Python environment, and a gateway Python environment with gateway dependencies. This starts PostgreSQL, the gateway, and the Next.js frontend on `127.0.0.1`. Extraction remains the existing on-demand local Python subprocess. It does not use Docker or start a queue.

Store a private JSON config outside the repo, for example `I:\DocAI-Runtime\native-product.json`:

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

`gatewayPythonPath` defaults to `pythonPath`; `nodePath` defaults to `node.exe` on PATH; `adminUsername` defaults to `admin`. The `pythonPath` must match the `idpo_process_auto` command in `frontend/runner.config.json`. Give the JSON file a private ACL because it contains credentials. The launcher never writes those secrets to its process receipt or console output.

From the repo root:

```powershell
pwsh -File scripts/start_native_product.ps1 -ConfigPath I:\DocAI-Runtime\native-product.json
pwsh -File scripts/start_native_product.ps1 -ConfigPath I:\DocAI-Runtime\native-product.json -Status
pwsh -File scripts/stop_native_product.ps1 -ConfigPath I:\DocAI-Runtime\native-product.json
```

The frontend is at `http://127.0.0.1:3000` with the example config. The launcher currently uses Next.js development mode so a checked-out source tree can start without a build. It waits for PostgreSQL, the gateway's deep health check, and the frontend health route. The separate runtime directory holds process state, logs, PostgreSQL files, and new upload/job data. It does not migrate existing `idpo-data`; with the example `dataDir`, the product opens a fresh workspace.

Startup refuses any occupied, untracked port. A second start against a healthy tracked stack is safe. If startup stops partway through, inspect `-Status` and the logs, then run the stop script before retrying. Stop verifies the recorded process identity and only terminates tracked gateway/frontend process trees; PostgreSQL uses `pg_ctl stop -m fast`. It preserves runtime data and logs. A missing or altered process receipt is never treated as authority to kill a port listener.

Source-free checks: `pwsh -File scripts/tests/native_product.test.ps1`.
