import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";
import { PgBoss } from "pg-boss";
import { ProductExecutionQueue, QueueAdmissionError, type ProductDispatch } from "./product-execution-queue";

// This suite never loads application credentials or defaults to the application DB.
// Provision a NEW empty PostgreSQL database named docai_queue_test_<unique suffix>,
// then run TEST_DATABASE_URL=<url> node --import tsx --test this-file.
const connectionString = process.env.TEST_DATABASE_URL;
const QUEUE = "document-extraction";
type QueueOptions = NonNullable<ConstructorParameters<typeof ProductExecutionQueue>[1]>;

function request(ownerId: string, overrides: Partial<ProductDispatch> = {}): ProductDispatch {
  return {
    ownerId,
    jobId: randomUUID().replaceAll("-", ""),
    runId: `auto_${randomUUID().replaceAll("-", "")}`,
    dispatchSha256: randomUUID().replaceAll("-", "").repeat(2),
    documentCount: 2,
    ...overrides,
  };
}

function admissionStatus(statusCode: number): (error: unknown) => boolean {
  return (error) => error instanceof QueueAdmissionError && error.statusCode === statusCode;
}

async function eventually(check: () => Promise<boolean>, message: string): Promise<void> {
  const deadline = Date.now() + 12_000;
  do {
    if (await check()) return;
    await delay(40);
  } while (Date.now() < deadline);
  assert.fail(message);
}

test("product queue PostgreSQL integration", {
  skip: connectionString ? false : "Set TEST_DATABASE_URL to a new disposable PostgreSQL database.",
  timeout: 120_000,
}, async (t) => {
  let url: URL;
  try { url = new URL(connectionString!); }
  catch { throw new Error("TEST_DATABASE_URL must be a PostgreSQL connection URL."); }
  const databaseName = decodeURIComponent(url.pathname.slice(1));
  assert.ok(["postgres:", "postgresql:"].includes(url.protocol), "Test URL must use PostgreSQL.");
  assert.ok(["127.0.0.1", "localhost", "[::1]"].includes(url.hostname), "Tests require a loopback database.");
  assert.match(databaseName, /^docai_queue_test_[a-z0-9_]{1,45}$/, "Refusing a non-test database.");
  const harness = new PgBoss({ connectionString: connectionString!, schema: "queue_test_harness", schedule: false,
    supervise: false, application_name: "docai-queue-integration-test" });
  harness.on("error", () => undefined);
  await harness.start();
  const db = harness.getDb();
  t.after(async () => { await harness.stop(); });
  const identity = await db.executeSql("SELECT current_database() AS name");
  assert.equal(identity.rows[0].name, databaseName);
  const existing = await db.executeSql(`SELECT to_regclass('public.users') AS users,
    to_regnamespace('product') AS product, to_regnamespace('docai_queue') AS broker`);
  assert.deepEqual(existing.rows[0], { users: null, product: null, broker: null },
    "Use a new empty test database; existing users or product state must never be overwritten.");
  await db.executeSql("CREATE TABLE public.users (id uuid PRIMARY KEY)");
  const ownerA = randomUUID();
  const ownerB = randomUUID();
  await db.executeSql("INSERT INTO public.users (id) VALUES ($1),($2)", [ownerA, ownerB]);

  async function withQueues(
    count: number,
    options: QueueOptions,
    run: (queues: ProductExecutionQueue[]) => Promise<void>,
  ): Promise<void> {
    const queues = Array.from({ length: count }, () => new ProductExecutionQueue(connectionString!, options));
    try {
      await run(queues);
    } finally {
      const stops = await Promise.allSettled(queues.map((queue) => queue.stop()));
      const failedStop = stops.find((result) => result.status === "rejected");
      assert.equal(failedStop, undefined, "A queue instance failed to stop cleanly.");
      // The name and empty-state guards above establish that these are test-owned tables.
      const tables = await db.executeSql(`SELECT to_regclass('product.execution_dispatches') AS dispatches,
        to_regclass('docai_queue.job') AS jobs`);
      if (tables.rows[0].dispatches) await db.executeSql("DELETE FROM product.execution_dispatches");
      if (tables.rows[0].jobs) await db.executeSql("DELETE FROM docai_queue.job");
    }
  }

  await t.test("cold concurrent admission initializes once and preserves one durable identity", async () => {
    await withQueues(3, {}, async (queues) => {
      const dispatch = request(ownerA);
      const ids = await Promise.all(Array.from({ length: 12 }, (_, index) => queues[index % queues.length].enqueue(dispatch)));
      assert.equal(new Set(ids).size, 1);
      const rows = await db.executeSql("SELECT * FROM product.execution_dispatches WHERE run_id=$1", [dispatch.runId]);
      assert.equal(rows.rows.length, 1);
      assert.equal(rows.rows[0].status, "queued");
      const jobs = await queues[0].boss.findJobs(QUEUE, { id: ids[0] });
      assert.equal(jobs.length, 1);
      assert.equal(jobs[0].retryLimit, 0);
      assert.equal(jobs[0].retryCount, 0);
    });
  });

  await t.test("run identity and reads are owner scoped and immutable", async () => {
    await withQueues(1, {}, async ([queue]) => {
      const dispatch = request(ownerA);
      const id = await queue.enqueue(dispatch);
      assert.equal(await queue.enqueue({ ...dispatch }), id);
      assert.equal(await queue.get(ownerB, dispatch.runId), null);
      assert.equal((await queue.get(ownerA, dispatch.runId))?.dispatch_sha256, dispatch.dispatchSha256);
      for (const altered of [
        { ownerId: ownerB }, { jobId: randomUUID().replaceAll("-", "") },
        { dispatchSha256: "f".repeat(64) }, { documentCount: 3 },
      ]) await assert.rejects(queue.enqueue({ ...dispatch, ...altered }), admissionStatus(409));
      const jobs = await queue.boss.findJobs(QUEUE, { id });
      assert.equal(jobs.length, 1);
    });
  });

  await t.test("a simultaneous cross-owner run collision returns a conflict without leaking the other run", async () => {
    await withQueues(2, {}, async (queues) => {
      await Promise.all(queues.map((queue) => queue.start()));
      // Both real transactions must read the absent identity before either inserts.
      // This controls the race without mocking a database result or its constraints.
      let arrived = 0;
      let release!: () => void;
      const barrier = new Promise<void>((resolve) => { release = resolve; });
      for (const queue of queues) {
        const database = queue.boss.getDb();
        const begin = database.beginTransaction!.bind(database);
        database.beginTransaction = async () => {
          const transaction = await begin();
          const execute = transaction.db.executeSql.bind(transaction.db);
          transaction.db.executeSql = async (sql, parameters) => {
            const result = await execute(sql, parameters);
            if (sql.startsWith("SELECT * FROM product.execution_dispatches WHERE run_id =")) {
              arrived += 1;
              if (arrived === queues.length) release();
              await Promise.race([barrier, delay(5_000, undefined, { ref: false })
                .then(() => { throw new Error("Admission race barrier timed out."); })]);
            }
            return result;
          };
          return transaction;
        };
      }
      const dispatch = request(ownerA);
      const outcomes = await Promise.allSettled([
        queues[0].enqueue(dispatch), queues[1].enqueue({ ...dispatch, ownerId: ownerB }),
      ]);
      assert.equal(outcomes.filter((outcome) => outcome.status === "fulfilled").length, 1);
      const rejected = outcomes.find((outcome) => outcome.status === "rejected");
      assert.ok(rejected && admissionStatus(409)(rejected.reason), "A run collision must be an admission conflict.");
      const rows = await db.executeSql("SELECT owner_id FROM product.execution_dispatches WHERE run_id=$1", [dispatch.runId]);
      assert.equal(rows.rows.length, 1);
      const nonOwner = rows.rows[0].owner_id === ownerA ? ownerB : ownerA;
      assert.equal(await queues[0].get(nonOwner, dispatch.runId), null);
    });
  });

  await t.test("parallel requests for the same owner and job admit only one run", async () => {
    await withQueues(2, {}, async (queues) => {
      await Promise.all(queues.map((queue) => queue.start()));
      const jobId = randomUUID().replaceAll("-", "");
      const outcomes = await Promise.allSettled(Array.from({ length: 10 }, (_, index) =>
        queues[index % 2].enqueue(request(ownerA, { jobId }))));
      assert.equal(outcomes.filter((outcome) => outcome.status === "fulfilled").length, 1);
      const conflicts = outcomes.filter((outcome) => outcome.status === "rejected");
      assert.equal(conflicts.length, 9);
      for (const conflict of conflicts) assert.ok(admissionStatus(409)(conflict.reason));
      await queues[0].enqueue(request(ownerB, { jobId }));
      const pending = await db.executeSql("SELECT * FROM product.execution_dispatches WHERE status='queued'");
      assert.equal(pending.rows.length, 2, "Another owner has an independent job namespace.");
    });
  });

  await t.test("concurrent admissions obey owner run and document quotas", async () => {
    await withQueues(2, { maxPendingRuns: 2, maxPendingDocuments: 5 }, async (queues) => {
      await Promise.all(queues.map((queue) => queue.start()));
      const outcomes = await Promise.allSettled(Array.from({ length: 8 }, (_, index) =>
        queues[index % 2].enqueue(request(ownerA))));
      assert.equal(outcomes.filter((outcome) => outcome.status === "fulfilled").length, 2);
      for (const outcome of outcomes) {
        if (outcome.status === "rejected") assert.ok(admissionStatus(429)(outcome.reason));
      }
      await queues[0].enqueue(request(ownerB, { documentCount: 5 }));
      await assert.rejects(queues[1].enqueue(request(ownerB, { documentCount: 1 })), admissionStatus(429));
      const pending = await db.executeSql(`SELECT owner_id, count(*)::integer AS runs,
        sum(document_count)::integer AS documents FROM product.execution_dispatches GROUP BY owner_id`);
      assert.deepEqual(pending.rows.find((row) => row.owner_id === ownerA), { owner_id: ownerA, runs: 2, documents: 4 });
      assert.deepEqual(pending.rows.find((row) => row.owner_id === ownerB), { owner_id: ownerB, runs: 1, documents: 5 });
    });
  });

  await t.test("a broker publication error rolls back the dispatch and releases its admission budget", async () => {
    await withQueues(1, { maxPendingRuns: 1 }, async ([queue]) => {
      await queue.start();
      const dispatch = request(ownerA);
      const send = queue.boss.send;
      queue.boss.send = async () => { throw new Error("Injected broker publication failure"); };
      await assert.rejects(queue.enqueue(dispatch), /Injected broker publication failure/);
      queue.boss.send = send;
      assert.equal(await queue.get(ownerA, dispatch.runId), null);
      const id = await queue.enqueue(dispatch);
      assert.equal((await queue.boss.findJobs(QUEUE, { id })).length, 1);
    });
  });

  await t.test("queued work survives stop and restart and competing workers execute each run once", async () => {
    await withQueues(3, { concurrency: 2 }, async ([producer, workerA, workerB]) => {
      const dispatches = Array.from({ length: 8 }, () => request(ownerA));
      for (const dispatch of dispatches) await producer.enqueue(dispatch);
      await producer.stop();
      const persisted = await db.executeSql("SELECT count(*)::integer AS total FROM product.execution_dispatches WHERE status='queued'");
      assert.equal(persisted.rows[0].total, dispatches.length);
      const executed = new Map<string, number>();
      const failed: string[] = [];
      const execute = async (dispatch: ProductDispatch, signal: AbortSignal) => {
        assert.equal(signal.aborted, false);
        executed.set(dispatch.runId, (executed.get(dispatch.runId) ?? 0) + 1);
        await delay(20);
      };
      await Promise.all([workerA.work(execute, (dispatch) => { failed.push(dispatch.runId); }),
        workerB.work(execute, (dispatch) => { failed.push(dispatch.runId); })]);
      await eventually(async () => {
        const result = await db.executeSql("SELECT count(*)::integer AS total FROM product.execution_dispatches WHERE status='succeeded'");
        return result.rows[0].total === dispatches.length;
      }, "All durable queued runs must finish after restarting the workers.");
      assert.equal(executed.size, dispatches.length);
      assert.ok([...executed.values()].every((count) => count === 1));
      assert.deepEqual(failed, []);
      for (const dispatch of dispatches) {
        const row = await workerA.get(ownerA, dispatch.runId);
        assert.equal(row?.status, "succeeded");
        const id = await workerB.enqueue(dispatch);
        assert.equal(id, row?.broker_job_id, "Re-enqueueing a terminal identity must not create another attempt.");
      }
    });
  });

  await t.test("terminal execution failure is durable and is not retried after restart", async () => {
    await withQueues(2, { maxPendingRuns: 1 }, async ([first, restarted]) => {
      const dispatch = request(ownerA);
      const id = await first.enqueue(dispatch);
      let executions = 0;
      const failures: string[] = [];
      await first.work(async () => { executions += 1; throw new Error("Uncertain external outcome"); },
        (failed) => { failures.push(failed.runId); });
      await eventually(async () => (await first.boss.findJobs(QUEUE, { id }))[0]?.state === "failed",
        "The failed attempt must become terminal in the broker.");
      assert.equal((await first.get(ownerA, dispatch.runId))?.status, "failed");
      assert.equal(executions, 1);
      assert.deepEqual(failures, [dispatch.runId]);
      await first.stop();
      assert.equal(await restarted.enqueue(dispatch), id);
      const sentinel = request(ownerA, { jobId: dispatch.jobId });
      await restarted.enqueue(sentinel);
      const afterRestart: string[] = [];
      await restarted.work(async (next) => { afterRestart.push(next.runId); }, () => undefined);
      await eventually(async () => (await restarted.get(ownerA, sentinel.runId))?.status === "succeeded",
        "The restarted worker must process fresh work after a terminal failure.");
      assert.deepEqual(afterRestart, [sentinel.runId]);
      const job = (await restarted.boss.findJobs(QUEUE, { id }))[0];
      assert.equal(job.state, "failed");
      assert.equal(job.retryLimit, 0);
      assert.equal(job.retryCount, 0);
    });
  });

  await t.test("lost broker work is reconciled once without executing or replaying it", async () => {
    await withQueues(1, {}, async ([queue]) => {
      const dispatch = request(ownerA);
      const id = await queue.enqueue(dispatch);
      await queue.boss.deleteJob(QUEUE, id);
      const failures: string[] = [];
      assert.equal(await queue.reconcile((failed) => { failures.push(failed.runId); }), 1);
      assert.equal(await queue.reconcile((failed) => { failures.push(failed.runId); }), 0);
      assert.deepEqual(failures, [dispatch.runId]);
      assert.equal((await queue.get(ownerA, dispatch.runId))?.status, "failed");
      assert.equal(await queue.enqueue(dispatch), id);
      assert.equal((await queue.boss.findJobs(QUEUE, { id })).length, 0);
    });
  });
});
