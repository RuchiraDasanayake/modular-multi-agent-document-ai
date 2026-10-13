import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { loadRunnerConfig, resetConfigCacheForTests } from "./config";
import { addDocumentsToJob, createWorkspaceJob } from "./jobs";
import { executePreparedProductAutoRun, getProductAutoRun,
  failQueuedProductAutoRun, recoverQueuedProductAutoAdmissions, startProductAutoRun } from "./product-auto";
import { confirmProductAutoBrief, saveProductAutoBrief } from "./product-auto-brief";
import type { ProductDispatch, ProductExecutionQueue } from "./product-execution-queue";

const digest = (bytes: string | Buffer) => createHash("sha256").update(bytes).digest("hex");
const holder = globalThis as typeof globalThis & { __productQueue?: ProductExecutionQueue };

interface StoredRecord {
  selectedFiles: Array<{ fileId: string; fileName: string; storedName: string; sha256: string }>;
  confirmedBrief?: { snapshotSha256: string };
  approvedRecipe?: Record<string, unknown>;
}

async function withQueuedRun(
  run: (fixture: {
    dataDir: string; request: ProductDispatch; recordPath: string; inputDir: string;
    schemaPath: string; capturePath: string; sourcePath: string;
    command: ReturnType<typeof loadRunnerConfig>["commands"][number];
    admissions: ProductDispatch[];
  }) => Promise<void>,
  options: { schema?: boolean; admissionError?: boolean; holdChild?: boolean } = {},
): Promise<void> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-queue-dispatch-"));
  const dataDir = path.join(root, "data");
  const env = { IDPO_DATA_DIR: dataDir, PRODUCT_EXECUTION_MODE: "postgres",
    PRODUCT_QUEUE_DATABASE_URL: "postgresql://127.0.0.1:1/unused_test_database",
    IDPO_AUTO_MODEL: options.schema ? "fixture-model" : "",
    IDPO_AUTO_API_BASE_URL: options.schema ? "http://127.0.0.1:1/v1" : "", ICORE_API_KEY: "" };
  const previousEnv = Object.fromEntries(Object.keys(env).map((key) => [key, process.env[key]]));
  const previousQueue = holder.__productQueue;
  const previousFetch = globalThis.fetch;
  const admissions: ProductDispatch[] = [];
  Object.assign(process.env, env);
  resetConfigCacheForTests();
  globalThis.fetch = async () => { throw new Error("Queue dispatch tests must not use a network provider."); };
  holder.__productQueue = {
    enqueue: async (request: ProductDispatch) => {
      admissions.push(structuredClone(request));
      if (options.admissionError && admissions.length === 1) throw new Error("Lost commit acknowledgement.");
      return randomUUID();
    },
    get: async () => null,
  } as unknown as ProductExecutionQueue;
  try {
    const job = createWorkspaceJob({ ownerUserId: randomUUID() });
    const uploaded = await addDocumentsToJob(job.jobId, [new File(["Invoice A\nTotal: 100"], "sample.txt")]);
    const document = uploaded.documents![0];
    const command = loadRunnerConfig().commands.find((item) => item.id === "idpo_process_auto")!;
    const capturePath = path.join(root, "executed.json");
    const workerPath = path.join(root, "capture-worker.cjs");
    // A real harmless subprocess proves whether validation stopped execution.
    // It deliberately emits no extraction result and can never call a provider.
    fs.writeFileSync(workerPath, `const fs = require('node:fs');
const args = process.argv.slice(2);
const input = args[args.indexOf('--input') + 1];
fs.writeFileSync(process.env.CAPTURE_PATH, JSON.stringify({ pid: process.pid, args, files: fs.readdirSync(input) }));
${options.holdChild ? "setInterval(() => {}, 1000);" : "process.exit(1);"}`);
    command.program = process.execPath;
    command.args = [workerPath, "--input", "{input_dir}", "--run-id", "{run_id}"];
    command.cwd = root;
    command.env = { CAPTURE_PATH: capturePath };
    let selection: Parameters<typeof startProductAutoRun>[4];
    if (options.schema) {
      const draft = saveProductAutoBrief(job.jobId, job.ownerUserId!, {
        expectedRevision: 0, intent: "Extract final amount due", sampleFileIds: [document.fileId],
        fields: [{ field_id: "total", type: "integer", description: "Final payable amount", example_values: ["100"] }],
      });
      const confirmed = confirmProductAutoBrief(job.jobId, job.ownerUserId!, {
        expectedRevision: draft.revision, expectedPayloadSha256: draft.payload_sha256,
      });
      selection = { expectedRevision: confirmed.revision, payloadSha256: confirmed.payload_sha256, phase: "preview" };
    }
    const started = await startProductAutoRun(job.jobId, [document.fileId], true, undefined, selection);
    assert.equal(started.status, "queued");
    assert.equal(admissions.length, 1);
    assert.equal(fs.existsSync(capturePath), false, "admission must not spawn extraction in the web process");
    await run({ dataDir, request: admissions[0], admissions, command, capturePath,
      recordPath: path.join(dataDir, "frontend", "auto_runs", job.jobId, `${started.runId}.json`),
      inputDir: path.join(dataDir, "frontend", "auto_inputs", started.runId),
      schemaPath: path.join(dataDir, "frontend", "auto_inputs", `${started.runId}.schema.json`),
      sourcePath: path.join(uploaded.uploadsPath!, document.storedName) });
  } finally {
    if (previousQueue === undefined) delete holder.__productQueue; else holder.__productQueue = previousQueue;
    globalThis.fetch = previousFetch;
    for (const [key, value] of Object.entries(previousEnv)) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
    resetConfigCacheForTests();
    assert.equal(path.dirname(root), os.tmpdir());
    assert.ok(path.basename(root).startsWith("idpo-queue-dispatch-"));
    fs.rmSync(root, { recursive: true, force: true });
  }
}

const readRecord = (file: string) => JSON.parse(fs.readFileSync(file, "utf8")) as StoredRecord;

test("queued execution validates admitted inputs before starting a subprocess", async (t) => {
  await t.test("admission snapshots original uploads rather than linking their bytes", async () => withQueuedRun(async (f) => {
    const source = readRecord(f.recordPath).selectedFiles[0];
    fs.writeFileSync(f.sourcePath, "Changed after admission");
    assert.equal(digest(fs.readFileSync(path.join(f.inputDir, source.storedName))), source.sha256);
    await assert.rejects(executePreparedProductAutoRun(f.request, new AbortController().signal), /output not verified/i);
    assert.equal(fs.existsSync(f.capturePath), true, "unchanged admitted snapshot must reach the harmless child");
  }));

  await t.test("rejects a different owner without execution", async () => withQueuedRun(async (f) => {
    await assert.rejects(executePreparedProductAutoRun({ ...f.request, ownerId: randomUUID() },
      new AbortController().signal), /ownership|identity/i);
    assert.equal(fs.existsSync(f.capturePath), false);
  }));

  await t.test("rejects changed dispatch profile without execution", async () => withQueuedRun(async (f) => {
    const profile = f.recordPath.replace(/\.json$/, ".dispatch.json");
    fs.appendFileSync(profile, " ");
    await assert.rejects(executePreparedProductAutoRun(f.request, new AbortController().signal), /profile|dispatch/i);
    assert.equal(fs.existsSync(f.capturePath), false);
  }));

  await t.test("rejects changed command configuration and pre-aborted attempts", async () => withQueuedRun(async (f) => {
    const aborted = new AbortController();
    aborted.abort();
    await assert.rejects(executePreparedProductAutoRun(f.request, aborted.signal), /startable|interrupt|abort/i);
    f.command.env = { ...f.command.env, CHANGED_CONFIGURATION: "yes" };
    await assert.rejects(executePreparedProductAutoRun(f.request, new AbortController().signal), /configuration/i);
    assert.equal(fs.existsSync(f.capturePath), false);
  }));

  await t.test("rejects staged source byte changes", async () => withQueuedRun(async (f) => {
    fs.writeFileSync(path.join(f.inputDir, readRecord(f.recordPath).selectedFiles[0].storedName), "Changed source");
    await assert.rejects(executePreparedProductAutoRun(f.request, new AbortController().signal));
    assert.equal(fs.existsSync(f.capturePath), false);
  }));

  await t.test("rejects source bytes and mutable run hash changed together", async () => withQueuedRun(async (f) => {
    const record = readRecord(f.recordPath);
    const bytes = "Changed source and its local receipt";
    fs.writeFileSync(path.join(f.inputDir, record.selectedFiles[0].storedName), bytes);
    record.selectedFiles[0].sha256 = digest(bytes);
    fs.writeFileSync(f.recordPath, JSON.stringify(record));
    await assert.rejects(executePreparedProductAutoRun(f.request, new AbortController().signal));
    assert.equal(fs.existsSync(f.capturePath), false, "the admitted database digest must seal source identity");
  }));

  await t.test("rejects unselected files added to the staged input directory", async () => withQueuedRun(async (f) => {
    fs.writeFileSync(path.join(f.inputDir, "unselected.txt"), "This was not admitted for extraction");
    await assert.rejects(executePreparedProductAutoRun(f.request, new AbortController().signal));
    assert.equal(fs.existsSync(f.capturePath), false, "directory input must not send extra files to an extraction provider");
  }));

  await t.test("rejects schema byte changes", async () => withQueuedRun(async (f) => {
    fs.appendFileSync(f.schemaPath, " ");
    await assert.rejects(executePreparedProductAutoRun(f.request, new AbortController().signal));
    assert.equal(fs.existsSync(f.capturePath), false);
  }, { schema: true }));

  await t.test("rejects schema bytes and mutable run hash changed together", async () => withQueuedRun(async (f) => {
    const record = readRecord(f.recordPath);
    const schema = JSON.parse(fs.readFileSync(f.schemaPath, "utf8"));
    schema.fields[0].description = "A meaning the user never confirmed";
    const bytes = JSON.stringify(schema);
    fs.writeFileSync(f.schemaPath, bytes);
    record.confirmedBrief!.snapshotSha256 = digest(bytes);
    fs.writeFileSync(f.recordPath, JSON.stringify(record));
    await assert.rejects(executePreparedProductAutoRun(f.request, new AbortController().signal));
    assert.equal(fs.existsSync(f.capturePath), false, "the admitted database digest must seal confirmed schema identity");
  }, { schema: true }));

  await t.test("rejects removal of the confirmed schema from a mutable run record", async () => withQueuedRun(async (f) => {
    const record = readRecord(f.recordPath);
    delete record.confirmedBrief;
    fs.writeFileSync(f.recordPath, JSON.stringify(record));
    await assert.rejects(executePreparedProductAutoRun(f.request, new AbortController().signal));
    assert.equal(fs.existsSync(f.capturePath), false, "an admitted confirmed-schema run must not degrade to automatic schema inference");
  }, { schema: true }));

  await t.test("rejects a recipe and matching local receipt introduced after admission", async () => withQueuedRun(async (f) => {
    const record = readRecord(f.recordPath);
    const bytes = JSON.stringify({ contract_version: 1, fields: [{ field_id: "unexpected", type: "string" }] });
    fs.writeFileSync(f.schemaPath.replace(/\.schema\.json$/, ".recipe.json"), bytes);
    record.approvedRecipe = { recipeId: `recipe_${"1".repeat(32)}`, revision: 2,
      auditEventId: "2".repeat(32), ownerUserId: f.request.ownerId,
      familyName: "Unadmitted recipe", snapshotSha256: digest(bytes) };
    fs.writeFileSync(f.recordPath, JSON.stringify(record));
    await assert.rejects(executePreparedProductAutoRun(f.request, new AbortController().signal));
    assert.equal(fs.existsSync(f.capturePath), false, "a valid local digest does not authorize a new recipe");
  }));

  await t.test("recovers an uncertain admission using its original identity without web execution", async () => withQueuedRun(async (f) => {
    assert.equal(getProductAutoRun(f.request.jobId, f.request.runId).status, "queued");
    assert.equal(await recoverQueuedProductAutoAdmissions(), 1);
    assert.deepEqual(f.admissions, [f.request, f.request]);
    assert.equal(fs.existsSync(f.capturePath), false);
  }, { admissionError: true }));

  await t.test("recovery fails a changed dispatch without readmitting it", async () => withQueuedRun(async (f) => {
    fs.appendFileSync(f.recordPath.replace(/\.json$/, ".dispatch.json"), " ");
    assert.equal(await recoverQueuedProductAutoAdmissions(), 0);
    assert.equal(getProductAutoRun(f.request.jobId, f.request.runId).status, "failed");
    assert.deepEqual(f.admissions, [f.request]);
    assert.equal(fs.existsSync(f.capturePath), false);
  }));

  await t.test("recovery exposes database failure without discarding an uncertain admission", async () => withQueuedRun(async (f) => {
    holder.__productQueue!.get = async () => { throw new Error("Fixture database unavailable"); };
    await assert.rejects(recoverQueuedProductAutoAdmissions(), /database unavailable/i);
    assert.equal(getProductAutoRun(f.request.jobId, f.request.runId).status, "queued");
    assert.deepEqual(f.admissions, [f.request]);
    assert.equal(fs.existsSync(f.capturePath), false);
  }));

  await t.test("a malformed unrelated run cannot prevent recovery of a valid admission", async () => withQueuedRun(async (f) => {
    const unrelated = path.join(f.dataDir, "frontend", "auto_runs", "0".repeat(32));
    fs.mkdirSync(unrelated);
    fs.writeFileSync(path.join(unrelated, `auto_${"0".repeat(32)}.json`), "{broken");
    assert.equal(await recoverQueuedProductAutoAdmissions(), 1);
    assert.deepEqual(f.admissions, [f.request, f.request]);
    assert.equal(fs.existsSync(f.capturePath), false);
  }));

  await t.test("a structurally invalid run cannot prevent recovery of a valid admission", async () => withQueuedRun(async (f) => {
    const jobId = "0".repeat(32);
    const runId = `auto_${"0".repeat(32)}`;
    const unrelated = path.join(f.dataDir, "frontend", "auto_runs", jobId);
    fs.mkdirSync(unrelated);
    fs.writeFileSync(path.join(unrelated, `${runId}.json`), JSON.stringify({
      jobId, runId, status: "queued", queueDispatch: { ownerId: f.request.ownerId, sha256: "0".repeat(64) },
    }));
    assert.equal(await recoverQueuedProductAutoAdmissions(), 1);
    assert.deepEqual(f.admissions, [f.request, f.request]);
    assert.equal(fs.existsSync(f.capturePath), false);
  }));

  await t.test("an abort stops the active child and is projected as terminal failure", async () => withQueuedRun(async (f) => {
    const controller = new AbortController();
    const execution = executePreparedProductAutoRun(f.request, controller.signal);
    const rejected = assert.rejects(execution, /interrupt|abort/i);
    try {
      const deadline = Date.now() + 10000;
      while (!fs.existsSync(f.capturePath) && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 20));
      }
      assert.equal(fs.existsSync(f.capturePath), true, "fixture child must start before cancellation");
      const { pid } = JSON.parse(fs.readFileSync(f.capturePath, "utf8")) as { pid: number };
      controller.abort();
      await rejected;
      assert.throws(() => process.kill(pid, 0), { code: "ESRCH" });
      failQueuedProductAutoRun(f.request);
      assert.equal(getProductAutoRun(f.request.jobId, f.request.runId).status, "failed");
      await assert.rejects(executePreparedProductAutoRun(f.request, new AbortController().signal), /startable/i);
    } finally {
      controller.abort();
      await rejected;
    }
  }, { holdChild: true }));
});
