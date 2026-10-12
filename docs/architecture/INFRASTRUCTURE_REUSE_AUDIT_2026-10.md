# Infrastructure reuse audit, 12 October 2026

This audit covers product job metadata, migrations, queueing, storage, artifact
validation, review history, and telemetry. The decision criteria are data
integrity and owner isolation first, then operational cost and maintenance. It
does not claim that changing infrastructure improves extraction accuracy. The
[component audit](COMPONENT_REUSE_AUDIT_2026-10.md) covers parser and model
choices.

| Concern | Current code and concrete risk | Reuse decision |
| --- | --- | --- |
| Job records | `frontend/src/server/jobs.ts` rewrote each job JSON directly. A process interruption during a write could truncate the sole live job record. Other product run files already use temporary files and renames. | **Done:** use the MIT-licensed [`atomically` 2.1.1](https://github.com/fabiospampinato/atomically) synchronous writer for the existing job path. It writes a temporary file, syncs it, and renames it. This is a single-host integrity improvement; it does not provide transactions or safe concurrent edits across processes. The alternative [`write-file-atomic` 8](https://github.com/npm/write-file-atomic/blob/main/package.json) requires Node 22.22.2+, while the frontend Dockerfile uses Node 20. |
| Transactional metadata and migrations | Product jobs, reviews, recipes, and leases are files, while PostgreSQL is used for auth/research tables. `scripts/init.sql` is a bootstrap script, not a sequence of reviewed upgrades. | **Schema started, no cutover:** a manual [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html) revision now defines owner-scoped product jobs, document state, immutable review/recipe events, and unique run keys in the existing PostgreSQL database. [Migration and cutover plan](PRODUCT_METADATA_MIGRATION.md). Existing file writers remain authoritative; live PostgreSQL execution, historical import, shadow reads, restricted roles, row security, and failback tests remain before cutover. |
| Queue and retries | The frontend owns a file lease and invokes one HTTP worker. That works on a single host but is not a distributed transactional job queue. | Use [Celery](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/) (BSD-3-Clause [license](https://github.com/celery/celery/blob/main/LICENSE)) with the existing Redis broker only after PostgreSQL holds idempotent run state. Configure bounded worker concurrency, task timeouts and retry classes. [Redis visibility timeouts](https://docs.celeryq.dev/en/latest/getting-started/backends-and-brokers/redis.html) can redeliver long tasks, so a task must tolerate duplicate delivery; Redis persistence and no-eviction policy need a deployment test. [RQ](https://github.com/rq/rq) is simpler, but its default pickle serializer is unsafe with an untrusted broker; JSON serialization would be mandatory. |
| Original and derived bytes | Current content-addressed local files are cheap and adequate while worker and frontend share one host. | Keep local files now. Define an S3-compatible adapter when multi-host execution is real and verify hash, owner, retention, backup and restore through it. Do not add a storage server merely for the 2,000-document local gate. [MinIO Community](https://github.com/minio/minio) was archived in April 2026 and is AGPL-3.0/source-only; it is a poor unexamined default. [SeaweedFS](https://github.com/seaweedfs/seaweedfs) is an active Apache-2.0 candidate, subject to a pinned compatibility, security and operations trial. |
| Artifact validation | Python uses Pydantic in gateway paths; TypeScript checks product result and review shapes with hand-written predicates and adds semantic source/row rules. | On the next contract revision, publish one versioned JSON Schema and evaluate [Ajv](https://github.com/ajv-validator/ajv) (MIT) for structural validation at the TypeScript boundary. Keep semantic checks for exact source quotes, typed values, linked row identity and human provenance. A schema-valid JSON object is not an accurate extraction. Test old artifact compatibility before replacing any predicate. |
| Review and gold labels | The operator UI saves correction events as files. It must remain owner-scoped and preserve the original machine candidate. | Store immutable review events and optimistic revision numbers transactionally with jobs; retain source hashes and audited human overrides. Keep the product review flow tailored to extraction. [Label Studio](https://github.com/HumanSignal/label-studio) (Apache-2.0 [license](https://github.com/HumanSignal/label-studio/blob/develop/LICENSE)) is a candidate for separate benchmark gold annotation, not a drop-in replacement for product review or tenant authorization. |
| Observability | Run receipts now record timings and partial resource use; there is no cross-service trace or complete priced compute ledger. | Add [OpenTelemetry](https://opentelemetry.io/docs/languages/python/instrumentation/) at upload, queue, parser, OCR, schema, values, verification and review boundaries once the service path works in containers. Export only bounded IDs and numeric attributes; never document text, OCR excerpts, credentials or raw provider prompts. Tracing is distinct from the cost ledger, which must record model tokens, local CPU/GPU, provider charges and reviewer time. |
| Frontend dependency reproducibility | The frontend container previously fell back from `npm ci` to `npm install` if the locked install failed, allowing a different package graph into the build. | **Changed:** require `npm ci` to succeed and pin Next.js plus its ESLint preset to 16.4.0. The local production audit reports zero advisories; `npm ci --legacy-peer-deps --dry-run`, 68 server tests, TypeScript, lint, a production build, and unauthenticated route smoke checks passed. Next's production build reports five dynamic filesystem tracing warnings in existing server modules; the local standalone output is 35.1 MiB. A Docker image build is still unverified while the local Docker daemon is unavailable. [Next 16 upgrade guide](https://nextjs.org/docs/app/guides/upgrading/version-16). |

## Order and acceptance

1. Keep the atomic job-write patch as an interim safety fix. The existing job
   tests and TypeScript check must pass; a process crash still requires a
   recovery test when a live container is available.
2. Prove the five-service deployment and PostgreSQL backup/restore. Execute
   the reviewed product migration on a live database; its required unique
   owner/job idempotency key and request fingerprint must be populated by the
   eventual writer. Historical records need a source-verified import.
3. Cut one writer path over to PostgreSQL with a reversible reader fallback.
   Test simultaneous review edits, worker redelivery, interrupted publication,
   backup/restore, and owner isolation. The database commits terminal metadata
   only after the hashed artifact has been published.
4. Introduce the queue after those idempotency tests. Record queue wait,
   redelivery and duplicate suppression. Scale only when throughput and cost
   improve on the same source-locked cohort.

The current product still has file-based cross-process lost-update risk; an
atomic replacement protects bytes on one write but cannot make a read-modify-
write transaction. No live Docker or database migration was performed during
this audit.
