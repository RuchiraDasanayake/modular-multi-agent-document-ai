# Product metadata migration: schema first

The product job API is currently served by the Next.js server and stores job
snapshots, product run records, reviews, and recipe events in local files.
`gateway` authenticates users against the existing Compose PostgreSQL `users`
table, but it does not receive `/api/jobs` requests. `scripts/init.sql` executes
only for a new PostgreSQL volume. Atomic file replacement protects a single
write from truncation; it does not make a cross-process read/modify/write safe.

This first step adds an **unused** versioned `product` schema in that same
PostgreSQL database. It does not change the API, extraction worker, file
readers, or file writers. The owner-scope contracts remain in the frontend
until an explicit data import and database cutover is validated.

## Decision and scope

- `scripts/product_migrations` is a small [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
  environment with one reviewed revision. It uses the existing PostgreSQL 16
  service and psycopg; there is no second database or ORM model to maintain.
- The migration service is a **manual** Compose `maintenance` profile. The
  application will not silently mutate an existing database during startup.
  Alembic stores its version row in `product.alembic_version_product` and
  serializes upgrades with a PostgreSQL transaction advisory lock.
- `product.jobs`, `documents`, `runs`, and `run_documents` hold owner IDs,
  stable job/file/run/document IDs, lifecycle states, timestamps, source hashes
  where available, and JSONB snapshots. PostgreSQL keys include the
  owner; composite foreign keys prevent a row from pointing to another owner's
  job, file, run, document, or source review.
- `product.review_events` and `recipe_events` hold append-only event payloads.
  Unique revision keys and a previous-event foreign key require an unbroken
  chain for each document review or recipe. Triggers reject `UPDATE` and
  `DELETE`. Recipe events reference the exact source review event. The current
  three recipe transitions are constrained; a future recipe lifecycle needs a
  new migration.
- `runs.idempotency_key` is required and unique per owner/job, and each run
  carries a `request_sha256` fingerprint. A future writer must atomically
  compare the request fingerprint when it sees an existing key; a reused key
  with different inputs is a conflict. Historical run imports can derive a
  unique key from each old run ID so that intentional reruns are retained.
  These columns are **not** working queue deduplication yet. The current
  runner does not populate them.

These constraints enforce relationships and shape. They cannot prove a JSONB
event has valid source evidence, that a hash matches an artifact, or that an
authenticated actor is authorized for a job. The future writer must verify
those before committing, avoid storing provider secrets in snapshots, and scope
every query by authenticated owner.
The current Compose PostgreSQL account has broad privileges; row security and
a narrowly privileged product database role are required before treating the
database as a tenant isolation boundary.

## Apply and inspect

Before applying this revision to a persistent volume, take and test a
PostgreSQL backup. Ensure `scripts/init.sql` has already created `public.users`.
Use the same Compose file and environment as the deployment:

```powershell
docker compose --profile maintenance run --rm product-migrations
docker compose -f docker-compose.prod.yml --profile maintenance run --rm product-migrations
```

For review without a database:

```powershell
python -m alembic -c scripts/product_migrations/alembic.ini history
python -m alembic -c scripts/product_migrations/alembic.ini upgrade head --sql
```

For a host-run online upgrade, set `POSTGRES_URI` in the process environment to
an existing PostgreSQL URL. The Compose migration container instead passes
`POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`
separately, so punctuation in the password is encoded by SQLAlchemy rather
than spliced into a URL. No connection values are stored in this repository.

The migration is forward-only to avoid a command that silently deletes audit
history. Application rollback before any cutover is simply to keep using the
existing file-backed release; the new tables remain unused. Restoring a
database backup is the database-level rollback path.

## Required cutover before product use

1. Add a product metadata repository with parameterized SQL, transactions,
   optimistic job revisions, unique run requests, and explicit owner filters.
   Use a restricted database role. Keep raw document bytes in the existing
   source and artifact files; only commit a terminal run row after the published
   artifact and its hash have been verified.
2. In staging, freeze file writes and import a **copy** of historical owner-bearing jobs,
   uploaded file metadata, product runs, run documents, review trails, and
   recipe trails in dependency order. Verify source file hashes, artifact
   hashes, IDs, owners, revision order, prior-event IDs, and review-to-recipe
   provenance. Quarantine corrupt or unowned legacy records; do not guess an
   owner. The old files remain the rollback source.
3. Keep file reads authoritative while a shadow database reader compares
   owner-scoped lists and document/review/recipe details. Include empty jobs,
   failed and interrupted runs, old review versions, and recipes disabled after
   approval. Record mismatches, then fix or quarantine them before cutover.
   In production, repeat the import and comparison inside a bounded write-freeze
   window; a resumed file writer would make the imported DB copy stale.
4. Exercise a read-only cutover and a reverse export from DB rows to files in a
   staging deployment. At production cutover, switch reader and writer together,
   then release the write freeze. Once the database writer is authoritative, avoid
   uncoordinated dual writes. A later failback must first stop writes, export
   every committed DB event into atomic files, compare counts and hashes, and
   only then switch the file reader/writer on. A failed reverse export blocks
   failback rather than dropping new reviews.
5. In live PostgreSQL and Compose integration tests, verify simultaneous
   review saves return one conflict, no duplicate run on worker redelivery,
   transaction rollback on interrupted publication, cross-owner access denial,
   trigger enforcement, migration retry, backup/restore, and failback. Only
   then replace file writers and retire the file reader.

The migration's offline rendering and static tests pass locally. No live
PostgreSQL or Docker daemon was available for an execution test, so this schema
is **not** yet a proven deployable metadata backend.
