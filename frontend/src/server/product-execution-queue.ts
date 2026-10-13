import { PgBoss } from "pg-boss";

const QUEUE = "document-extraction";
const ID = /^[a-f0-9]{32}$/;
const RUN = /^auto_[a-f0-9]{32}$/;
const HASH = /^[a-f0-9]{64}$/;
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;

export interface ProductDispatch {
  ownerId: string;
  jobId: string;
  runId: string;
  dispatchSha256: string;
  documentCount: number;
}

export class QueueAdmissionError extends Error {
  constructor(message: string, readonly statusCode: number) { super(message); }
}

interface DispatchRow {
  owner_id: string;
  job_id: string;
  run_id: string;
  broker_job_id: string;
  dispatch_sha256: string;
  document_count: number;
  status: "queued" | "active" | "succeeded" | "failed";
}

function validate(request: ProductDispatch): void {
  if (!UUID.test(request.ownerId) || !ID.test(request.jobId) || !RUN.test(request.runId) ||
    !HASH.test(request.dispatchSha256) || !Number.isSafeInteger(request.documentCount) ||
    request.documentCount < 1 || request.documentCount > 10000) {
    throw new QueueAdmissionError("Invalid extraction dispatch.", 400);
  }
}

function fromRow(row: DispatchRow): ProductDispatch {
  return { ownerId: row.owner_id, jobId: row.job_id, runId: row.run_id,
    dispatchSha256: row.dispatch_sha256, documentCount: row.document_count };
}

/** PostgreSQL owns admission and attempt state; artifacts remain on shared storage.
 * External model calls are not transactional. Never automatically retry an attempt.
 */
export class ProductExecutionQueue {
  readonly boss: PgBoss;
  private started = false;
  private starting: Promise<void> | null = null;

  constructor(connectionString: string, private readonly options: {
    maxPendingRuns?: number; maxPendingDocuments?: number; concurrency?: number;
    expireInSeconds?: number; heartbeatSeconds?: number;
  } = {}) {
    if (!connectionString) throw new Error("Explicit PostgreSQL connection is required for the product queue.");
    this.boss = new PgBoss({ connectionString, schema: "docai_queue", max: 5,
      application_name: "docai-product-queue", connectionTimeoutMillis: 5000,
      schedule: false, superviseIntervalSeconds: 10 });
    // Do not log connection strings, document contents or provider credentials.
    this.boss.on("error", () => console.error("Product queue database operation failed."));
  }

  async start(): Promise<void> {
    if (this.started) return;
    if (!this.starting) this.starting = this.initialize().finally(() => { this.starting = null; });
    await this.starting;
  }

  private async initialize(): Promise<void> {
    await this.boss.start();
    const db = this.boss.getDb();
    if (!db.beginTransaction) throw new Error("Queue database must support transactions.");
    const transaction = await db.beginTransaction();
    try {
      // IF NOT EXISTS alone still races PostgreSQL catalog inserts across processes.
      await transaction.db.executeSql("SELECT pg_advisory_xact_lock(hashtextextended('docai-execution-schema-v1', 0))");
      await transaction.db.executeSql(`
      CREATE SCHEMA IF NOT EXISTS product;
      CREATE TABLE IF NOT EXISTS product.execution_dispatches (
        run_id text PRIMARY KEY CHECK (run_id ~ '^auto_[a-f0-9]{32}$'),
        broker_job_id uuid UNIQUE NOT NULL,
        owner_id uuid NOT NULL REFERENCES public.users(id),
        job_id text NOT NULL CHECK (job_id ~ '^[a-f0-9]{32}$'),
        dispatch_sha256 text NOT NULL CHECK (dispatch_sha256 ~ '^[a-f0-9]{64}$'),
        document_count integer NOT NULL CHECK (document_count BETWEEN 1 AND 10000),
        status text NOT NULL CHECK (status IN ('queued','active','succeeded','failed')),
        error_code text,
        created_at timestamptz NOT NULL DEFAULT now(),
        started_at timestamptz,
        ended_at timestamptz,
        CHECK ((status IN ('succeeded','failed')) = (ended_at IS NOT NULL))
      );
      CREATE UNIQUE INDEX IF NOT EXISTS execution_one_pending_job
        ON product.execution_dispatches(owner_id, job_id) WHERE status IN ('queued','active');
      CREATE INDEX IF NOT EXISTS execution_owner_status
        ON product.execution_dispatches(owner_id, status, created_at);`);
      await transaction.commit();
    } catch (error) { await transaction.rollback(); throw error; }
    await this.boss.createQueue(QUEUE, { retryLimit: 0, expireInSeconds: this.options.expireInSeconds ?? 21600,
      heartbeatSeconds: this.options.heartbeatSeconds ?? 60, retentionSeconds: 2592000,
      deleteAfterSeconds: 0 });
    this.started = true;
  }

  async enqueue(request: ProductDispatch): Promise<string> {
    validate(request);
    await this.start();
    const db = this.boss.getDb();
    if (!db.beginTransaction) throw new Error("Queue database must support transactions.");
    const transaction = await db.beginTransaction();
    try {
      // Serialize an owner's admission budget and per-job uniqueness checks.
      await transaction.db.executeSql("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", [request.ownerId]);
      const existing = await transaction.db.executeSql(
        "SELECT * FROM product.execution_dispatches WHERE run_id = $1", [request.runId]);
      if (existing.rows.length) {
        const row = existing.rows[0] as DispatchRow;
        if (row.owner_id !== request.ownerId || row.job_id !== request.jobId ||
          row.dispatch_sha256 !== request.dispatchSha256 || row.document_count !== request.documentCount) {
          throw new QueueAdmissionError("The run identity already belongs to a different request.", 409);
        }
        await transaction.commit();
        return row.broker_job_id;
      }
      const pending = await transaction.db.executeSql(
        "SELECT job_id, document_count FROM product.execution_dispatches WHERE owner_id=$1 AND status IN ('queued','active')",
        [request.ownerId]);
      if (pending.rows.some((row: { job_id: string }) => row.job_id === request.jobId)) {
        throw new QueueAdmissionError("This job already has pending extraction.", 409);
      }
      const documentCount = pending.rows.reduce((sum: number, row: { document_count: number }) => sum + row.document_count, 0);
      if (pending.rows.length >= (this.options.maxPendingRuns ?? 64) ||
        documentCount + request.documentCount > (this.options.maxPendingDocuments ?? 20000)) {
        throw new QueueAdmissionError("The pending extraction limit has been reached. Wait for work to finish.", 429);
      }
      const brokerId = request.runId.slice(5).replace(/(.{8})(.{4})(.{4})(.{4})(.{12})/, "$1-$2-$3-$4-$5");
      await transaction.db.executeSql(`INSERT INTO product.execution_dispatches
        (run_id, broker_job_id, owner_id, job_id, dispatch_sha256, document_count, status)
        VALUES ($1,$2,$3,$4,$5,$6,'queued')`,
      [request.runId, brokerId, request.ownerId, request.jobId, request.dispatchSha256, request.documentCount]);
      const sent = await this.boss.send(QUEUE, { runId: request.runId }, {
        id: brokerId, db: transaction.db, retryLimit: 0,
        expireInSeconds: this.options.expireInSeconds ?? 21600,
        heartbeatSeconds: this.options.heartbeatSeconds ?? 60,
        retentionSeconds: 2592000, deleteAfterSeconds: 0,
      });
      if (sent !== brokerId) throw new Error("Queue admission did not publish its broker job.");
      await transaction.commit();
      return brokerId;
    } catch (error) {
      await transaction.rollback();
      if (error && typeof error === "object" && "code" in error && error.code === "23505") {
        throw new QueueAdmissionError("The run identity or job already has an admitted request.", 409);
      }
      throw error;
    }
  }

  async get(ownerId: string, runId: string): Promise<DispatchRow | null> {
    await this.start();
    const result = await this.boss.getDb().executeSql(
      "SELECT * FROM product.execution_dispatches WHERE owner_id=$1 AND run_id=$2", [ownerId, runId]);
    return result.rows[0] ?? null;
  }

  async work(execute: (request: ProductDispatch, signal: AbortSignal) => Promise<void>,
    failed: (request: ProductDispatch) => void | Promise<void>): Promise<void> {
    await this.start();
    const concurrency = this.options.concurrency ?? 1;
    if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 4) throw new Error("Worker concurrency must be 1–4.");
    await this.boss.work<{ runId: string }>(QUEUE, { batchSize: 1, localConcurrency: concurrency,
      pollingIntervalSeconds: 1 }, async ([job]) => {
      const claim = await this.boss.getDb().executeSql(`UPDATE product.execution_dispatches
        SET status='active', started_at=now() WHERE run_id=$1 AND broker_job_id=$2 AND status='queued' RETURNING *`,
      [job.data.runId, job.id]);
      if (claim.rows.length !== 1) throw new Error("Extraction attempt already claimed; automatic replay is forbidden.");
      const request = fromRow(claim.rows[0]);
      try {
        validate(request);
        await execute(request, job.signal);
        if (job.signal.aborted) throw new Error("Extraction attempt interrupted.");
        const completed = await this.boss.getDb().executeSql(`UPDATE product.execution_dispatches
          SET status='succeeded', ended_at=now() WHERE run_id=$1 AND status='active' RETURNING run_id`, [request.runId]);
        if (completed.rows.length !== 1) throw new Error("Extraction attempt lost ownership before completion.");
      } catch {
        await this.boss.getDb().executeSql(`UPDATE product.execution_dispatches SET status='failed',
          ended_at=now(), error_code='execution_failed_or_uncertain' WHERE run_id=$1 AND status='active'`, [request.runId]);
        await failed(request);
        throw new Error("Extraction failed or its outcome is uncertain; automatic retry is disabled.");
      }
    });
  }

  /** Reconcile worker death/expiry without ever repeating a model request. */
  async reconcile(failed: (request: ProductDispatch) => void | Promise<void>): Promise<number> {
    await this.start();
    const pending = await this.boss.getDb().executeSql(
      "SELECT * FROM product.execution_dispatches WHERE status IN ('queued','active') ORDER BY created_at LIMIT 1000");
    let changed = 0;
    for (const row of pending.rows as DispatchRow[]) {
      const [job] = await this.boss.findJobs(QUEUE, { id: row.broker_job_id });
      if (job && !["cancelled", "failed", "completed"].includes(job.state)) continue;
      const result = await this.boss.getDb().executeSql(`UPDATE product.execution_dispatches
        SET status='failed', ended_at=now(), error_code='worker_lost_or_queue_inconsistent'
        WHERE run_id=$1 AND status IN ('queued','active') RETURNING run_id`, [row.run_id]);
      if (result.rows.length) { await failed(fromRow(row)); changed += 1; }
    }
    return changed;
  }

  async stop(): Promise<void> { await this.boss.stop({ graceful: true, timeout: 10000 }); this.started = false; }
}

/** One broker connection pool per web/worker process, including development reloads. */
export function productExecutionQueue(): ProductExecutionQueue {
  const url = process.env.PRODUCT_QUEUE_DATABASE_URL?.trim();
  if (!url) throw new Error("PRODUCT_QUEUE_DATABASE_URL is required.");
  const holder = globalThis as typeof globalThis & { __productQueue?: ProductExecutionQueue };
  holder.__productQueue ??= new ProductExecutionQueue(url);
  return holder.__productQueue;
}
