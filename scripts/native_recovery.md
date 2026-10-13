# Native Windows cold backup and passive recovery drill

Classification: **supporting**. Action: **keep**. This is an operator tool for the
single-host PostgreSQL 16 + shared-filesystem product. It does not establish high
availability, automatic failover, an extraction replay policy or a portable
whole-machine backup. The scripts must first be reviewed and tested against a
copy. No live recovery result is implied by the unit tests.

## Supported boundary

- A cleanly stopped **entire** PostgreSQL 16 cluster, including WAL and commit
  state, plus the whole configured product data directory and exact private
  native configuration. PostgreSQL requires a shutdown for this filesystem-copy
  method; stopping new connections alone is insufficient. Individual database
  directories cannot be restored independently this way. [PostgreSQL 16 filesystem backup](https://www.postgresql.org/docs/16/backup-file.html)
- No tablespaces, reparse points, hardlinks, standby/recovery mode, configuration
  includes, external authentication name files, or executable/external PostgreSQL
  configuration. These fail closed instead of producing an incomplete backup.
  `pg_tblspc` can reference files outside PGDATA. [PG16 file layout](https://www.postgresql.org/docs/16/storage-file-layout.html)
  Authentication `include` and `@filename` rules also require explicit handling.
  [PG16 authentication configuration](https://www.postgresql.org/docs/16/auth-pg-hba-conf.html)
- The operator, SYSTEM and Administrators are the only permitted destination ACL
  principals. Backups contain database credentials, password hashes, document
  contents and reviews; keep the entire bundle private. It is **not encrypted**.
- Existing paths are never overwritten or deleted. Failed copies stay unsealed
  for inspection. `manifest.json` and `seal.json` are created exclusively after
  complete pre/post inventories agree. Their hashes detect accidental changes;
  an administrator able to replace both is outside this integrity boundary.
  Save the printed manifest hash in the private operational record separately.
- Backups exclude Python/Node/PostgreSQL binaries, installed packages, local OCR
  models, and the frontend build. A matching clean tracked source revision and
  the same available dependency installations are required for this **same-host**
  drill. A whole-host loss needs separately preserved installers/lockfiles/models.

## Stages (operator-controlled; no automatic shutdown)

Use absolute paths. In the examples, `$python` is the configured interpreter,
`$originalConfig` the private native JSON, `$backup` a new bundle directory,
`$clone` a new recovery runtime directory, and `$cloneRepo` a separate checkout at
the source revision recorded by the backup. Parent directories must already
exist. Choose three unused clone ports different from all three original ports.

### 1. Record a private authenticated baseline while the original is available

Create a private cases JSON containing 1–20 already reviewed cases:

```json
{"cases":[{"job_id":"<32-hex-job-id>","document_id":"<document-id>",
"run_id":"<run-id>","source_relative_path":"frontend/uploads/job_<32-hex-job-id>/<stored-name>"}]}
```

```powershell
& $python scripts/native_recovery_http.py capture --config $originalConfig `
  --cases $cases --out $baseline
```

The output parent must already have private ACLs. This performs anonymous-denial
checks, login, original download and reviewed batch export only. Tokens/passwords
remain in memory. The receipt stores identities, byte counts and SHA-256 hashes,
not response contents. Original source bytes must match the configured upload
path. Finish all reviews before capture and do not modify these cases afterward.

### 2. Stop the owned stack, then create the cold bundle

After explicitly arranging downtime, use the existing ownership-checked stop
script. Its PostgreSQL fast stop completes a clean shutdown rather than an
immediate crash. [PG16 pg_ctl](https://www.postgresql.org/docs/16/app-pg-ctl.html)

```powershell
pwsh -NoProfile -File scripts/stop_native_product.ps1 -ConfigPath $originalConfig
& $python scripts/native_recovery_files.py backup --config $originalConfig `
  --destination $backup --baseline $baseline
& $python scripts/native_recovery_files.py verify-backup --bundle $backup
```

The backup independently refuses a running tracked process, occupied product
port, remaining PID file, configured PostgreSQL/parser process, or a control
file that is not `shut down`. A benchmark using the same parser environment also
blocks backup. Do not remove a PID file to bypass this check. Keep **all** writers
stopped until backup returns; pre/post hash equality supplements that requirement
and is not a replacement for exclusive access. The helper does not stop anything.

### 3. Restore a copy and build its frontend

```powershell
& $python scripts/native_recovery_files.py restore --bundle $backup `
  --destination $clone --repo $cloneRepo --ports 55433 8001 3001
$cloneConfig = Join-Path $clone 'passive-config.json'
pwsh -NoProfile -File scripts/build_native_recovery.ps1 -ConfigPath $cloneConfig
```

Provision the clone checkout's existing locked dependencies before the build.
Do not copy `.env` files. The clone gets a fresh JWT secret, relocated database
URL/ports and no provider configuration. The original private configuration stays
inside the immutable backup. The only allowed product-data rewrite is each
`frontend/jobs/<jobId>.json` `uploadsPath`, after proving it points to that exact
original job upload directory. Its before/after paths and hashes are receipted.
Legacy nonempty job `runPath` values require a separate audit and are refused.
Historical result `path`/`source_path` values remain informational and unchanged;
source readback uses the cloned upload root. Every other copied data byte stays
identical, including result, review, audit and export evidence.

The separate build is necessary because Next's gateway rewrites are compiled for
a port. The verified build cache must point inside the new runtime. Its expected
dependency junction is checked separately from the strictly link-free backup
payload. Do not point the production checkout's build junction at the clone.

### 4. Start the passive copy and verify authenticated readback

```powershell
pwsh -NoProfile -File scripts/start_native_recovery.ps1 -ConfigPath $cloneConfig
& $python scripts/native_recovery_http.py verify --config $cloneConfig `
  --out (Join-Path $clone 'http-drill.json')
pwsh -NoProfile -File scripts/stop_native_product.ps1 -ConfigPath $cloneConfig
```

Only PostgreSQL, the auth-only gateway wrapper and the production frontend start.
No worker starts; copied queue jobs cannot execute. Child environments contain
no provider credentials. PostgreSQL logical-replication/background workers are
disabled for the passive copy. Child environments contain
only OS variables plus explicit clone settings. The frontend passive boundary
allows only login, identity, health, original downloads and reviewed exports.
It refuses extraction, upload, review, user-management and other routes before
processing bodies. Gateway access is similarly restricted; unused research
proxies point to a closed loopback port. Background product reconciliation is
disabled. Responses identify `X-DocAI-Recovery: read-only`; the verifier requires
this marker, the signed process/port ownership receipt and the fresh clone config.

The verifier compares original and reviewed-export hashes with the baseline
sealed inside the backup and requires anonymous requests to remain unauthorized.
It never falls back to original storage or ports. The clone database can change
through normal auth/startup activity; product evidence must stay unchanged.
First-start inventory verification intentionally prevents reusing a previously
started clone. For another drill, restore into another new directory.

If startup fails, retain logs and process receipts and use the existing stop
script for recorded owned processes. Do not adopt, kill or replace an untracked
process. A failure before a PostgreSQL identity receipt requires manual inspection
of that **clone** only. No script automatically removes partial directories.

Record observed backup duration, last preserved transaction boundary, restoration
duration, source count and readback outcomes before making any recovery-time or
recovery-point claim. Successful readback does not test resumed paid extraction,
multi-host failover or a second machine's dependency compatibility.

## Focused verification

```powershell
& $gatewayPython -m pytest scripts/tests/test_native_recovery.py -q
pwsh -NoProfile -File scripts/tests/native_recovery.test.ps1
cd frontend
node --import tsx --test src/server/recovery-access.test.ts src/server/proxy.test.ts
node node_modules/typescript/bin/tsc --noEmit
```

These use synthetic files, process stubs, a fake gateway and in-memory ASGI only.
They never stop or query the production database and make no provider requests.
