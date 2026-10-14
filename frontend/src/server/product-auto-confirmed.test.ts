import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { POST as startAuto } from "@/app/api/jobs/[jobId]/auto/route";
import { POST as saveBrief, PATCH as confirmBrief } from "@/app/api/jobs/[jobId]/auto/brief/route";
import { POST as saveReview } from "@/app/api/jobs/[jobId]/auto/[runId]/docs/[docId]/route";
import { getProductAutoDocument, getProductAutoRun } from "./product-auto";
import { loadRunnerConfig, resetConfigCacheForTests } from "./config";
import { addDocumentsToJob, createWorkspaceJob } from "./jobs";

function request(url: string, token: string, method: string, body: unknown): Request {
  return new Request(`http://localhost${url}`, {
    method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json",
      ...(url.endsWith("/auto") && method === "POST"
        ? { "Idempotency-Key": randomUUID().replaceAll("-", "") } : {}) },
    body: JSON.stringify(body),
  });
}

async function withStorage(run: (dataDir: string) => Promise<void>): Promise<void> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-confirmed-"));
  const dataDir = path.join(root, "data");
  const previous = {
    data: process.env.IDPO_DATA_DIR, gateway: process.env.INTERNAL_API_URL,
    model: process.env.IDPO_AUTO_MODEL, baseUrl: process.env.IDPO_AUTO_API_BASE_URL,
  };
  const oldFetch = globalThis.fetch;
  process.env.IDPO_DATA_DIR = dataDir;
  process.env.INTERNAL_API_URL = "http://test-gateway.local";
  process.env.IDPO_AUTO_MODEL = "synthetic-model";
  process.env.IDPO_AUTO_API_BASE_URL = "http://127.0.0.1:1/v1";
  resetConfigCacheForTests();
  globalThis.fetch = async (input, init) => {
    if (String(input) !== "http://test-gateway.local/api/auth/me") {
      throw new Error("Unexpected network request in confirmed-schema test.");
    }
    const token = new Headers(init?.headers).get("Authorization")?.replace(/^Bearer /, "");
    if (token === "alice") return Response.json({ id: "alice-id", role: "viewer" });
    if (token === "admin") return Response.json({ id: "admin-id", role: "admin" });
    if (token === "bob") return Response.json({ id: "bob-id", role: "viewer" });
    return Response.json({}, { status: 401 });
  };
  try { await run(dataDir); }
  finally {
    globalThis.fetch = oldFetch;
    for (const [key, value] of Object.entries({ IDPO_DATA_DIR: previous.data,
      INTERNAL_API_URL: previous.gateway, IDPO_AUTO_MODEL: previous.model,
      IDPO_AUTO_API_BASE_URL: previous.baseUrl })) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
    resetConfigCacheForTests();
    assert.equal(path.dirname(root), os.tmpdir());
    assert.ok(path.basename(root).startsWith("idpo-confirmed-"));
    fs.rmSync(root, { recursive: true, force: true });
  }
}

async function waitForStatus(dataDir: string, jobId: string, runId: string, expected: string): Promise<void> {
  const terminal = path.join(dataDir, "frontend", "auto_runs", jobId, `${runId}.terminal.json`);
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (fs.existsSync(terminal) && getProductAutoRun(jobId, runId).status === expected) return;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  assert.equal(getProductAutoRun(jobId, runId).status, expected);
}

test("confirmed sample preview gates remaining batch on source review and pins worker schema", async () => withStorage(async (dataDir) => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const uploaded = await addDocumentsToJob(job.jobId, [
    new File(["Invoice A\nTotal: 100"], "sample.txt"),
    new File(["Invoice B\nTotal: 200"], "remaining.txt"),
  ]);
  const [sample, remaining] = uploaded.documents!;
  const params = { params: Promise.resolve({ jobId: job.jobId }) };
  const briefUrl = `/api/jobs/${job.jobId}/auto/brief`;
  const draftResponse = await saveBrief(request(briefUrl, "alice", "POST", {
    expectedRevision: 0, intent: "Extract the final amount due", sampleFileIds: [sample.fileId],
    fields: [{ field_id: "total", type: "integer", description: "Final payable amount", example_values: ["100"] }],
  }), params);
  assert.equal(draftResponse.status, 201);
  const draft = (await draftResponse.json()).brief;
  const confirmedResponse = await confirmBrief(request(briefUrl, "alice", "PATCH", {
    expectedRevision: draft.revision, expectedPayloadSha256: draft.payload_sha256,
  }), params);
  assert.equal(confirmedResponse.status, 201);
  const confirmed = (await confirmedResponse.json()).brief;
  const selection = { expectedRevision: confirmed.revision, payloadSha256: confirmed.payload_sha256 };
  const start = (fileIds: string[], phase: "preview" | "batch", previewRunId?: string) =>
    startAuto(request(`/api/jobs/${job.jobId}/auto`, "admin", "POST", {
      selectedFileIds: fileIds, confirmedBrief: { ...selection, phase, ...(previewRunId ? { previewRunId } : {}) },
    }), params);
  assert.equal((await start([remaining.fileId], "preview")).status, 400);
  assert.equal((await start([remaining.fileId], "batch")).status, 400);

  const workerScript = path.join(dataDir, "fixture-worker.cjs");
  fs.mkdirSync(dataDir, { recursive: true });
  fs.writeFileSync(workerScript, `const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const args = process.argv.slice(2);
const get = flag => args[args.indexOf(flag) + 1];
const runId = get('--run-id');
const inputDir = get('--input');
const schemaBytes = fs.readFileSync(get('--confirmed-schema-file'));
const digest = crypto.createHash('sha256').update(schemaBytes).digest('hex');
if (digest !== get('--confirmed-schema-sha256')) process.exit(2);
const schema = JSON.parse(schemaBytes);
const schemaReceipt = { brief_id: schema.brief_id, revision: schema.revision,
  audit_event_id: schema.audit_event_id, payload_sha256: schema.payload_sha256, snapshot_sha256: digest };
const fileName = fs.readdirSync(inputDir)[0];
const bytes = fs.readFileSync(path.join(inputDir, fileName));
const text = bytes.toString('utf8');
const sourceHash = crypto.createHash('sha256').update(bytes).digest('hex');
const match = /Total: (\\d+)/.exec(text);
const candidate = { contract_version: 1, doc_id: 'doc1', document_status: 'needs_review',
  proposed_schema: schema.fields.map(({ field_id, type, group }) => ({ field_id, type, ...(group ? { group } : {}) })),
  extracted_values: [{ field_id: 'total', value: match ? Number(match[1]) : null,
    status: match ? 'accepted' : 'missing', review_state: 'pending',
    ...(match ? { evidence: { page: 1, start: match.index + 7, end: match.index + 7 + match[1].length,
      quote: match[1] } } : {}) }] };
const output = path.join(process.env.IDPO_DATA_DIR, 'product_runs', runId);
const docDir = path.join(output, 'docs', 'doc1');
fs.mkdirSync(docDir, { recursive: true });
const result = { pages: [{ page: 1, text }], candidate, source_container_sha256: sourceHash,
  confirmed_schema: schemaReceipt };
const resultBytes = Buffer.from(JSON.stringify(result));
fs.writeFileSync(path.join(docDir, 'result.json'), resultBytes);
fs.writeFileSync(path.join(output, 'manifest.jsonl'), JSON.stringify({ contract_version: 1, run_id: runId,
  doc_id: 'doc1', source_file: fileName, source_container_sha256: sourceHash,
  result_sha256: crypto.createHash('sha256').update(resultBytes).digest('hex'),
  document_status: 'needs_review', confirmed_schema: schemaReceipt }) + '\\n');
fs.writeFileSync(path.join(output, 'run.json'), JSON.stringify({ contract_version: 1, run_id: runId,
  doc_count: 1, approved_recipe: null, confirmed_schema: schemaReceipt }));
fs.writeFileSync(path.join(process.env.CAPTURE_DIR, runId + '.json'), JSON.stringify({ schema, digest, args }));`);
  const command = loadRunnerConfig().commands.find((item) => item.id === "idpo_process_auto")!;
  const original = { program: command.program, args: command.args, cwd: command.cwd, env: command.env };
  command.program = process.execPath;
  command.args = [workerScript, "--input", "{input_dir}", "--run-id", "{run_id}"];
  command.cwd = process.cwd();
  const captureDir = path.join(dataDir, "captures");
  fs.mkdirSync(captureDir);
  command.env = { CAPTURE_DIR: captureDir };
  try {
    const previewResponse = await start([sample.fileId], "preview");
    assert.equal(previewResponse.status, 202);
    const preview = await previewResponse.json();
    await waitForStatus(dataDir, job.jobId, preview.runId, "success");
    const capture = JSON.parse(fs.readFileSync(path.join(captureDir, `${preview.runId}.json`), "utf8"));
    assert.equal(capture.schema.state, "confirmed");
    assert.equal(capture.schema.intent, "Extract the final amount due");
    assert.deepEqual(capture.schema.fields, confirmed.fields);
    assert.equal(capture.digest, preview.confirmedBrief.snapshotSha256);
    assert.equal(capture.args[capture.args.indexOf("--confirmed-schema-sha256") + 1], capture.digest);
    assert.equal((await start([remaining.fileId], "batch", preview.runId)).status, 409);

    const detail = getProductAutoDocument(job.jobId, preview.runId, "doc1");
    assert.equal(detail.candidate.extracted_values[0].evidence?.quote, "100");
    const review = await saveReview(request(`/api/jobs/${job.jobId}/auto/${preview.runId}/docs/doc1`,
      "alice", "POST", { expected_revision: 0, fields: [{ field_id: "total", decision: "correct" }] }),
    { params: Promise.resolve({ jobId: job.jobId, runId: preview.runId, docId: "doc1" }) });
    assert.equal(review.status, 200);
    assert.equal(getProductAutoRun(job.jobId, preview.runId).documents[0].reviewStatus, "completed");

    // Older workers sealed invalid model replies as reviewable nulls. A historical
    // completed audit of such a result must not admit the remaining paid batch.
    const previewRunDir = path.join(dataDir, "product_runs", preview.runId);
    const previewResultPath = path.join(previewRunDir, "docs", "doc1", "result.json");
    const previewManifestPath = path.join(previewRunDir, "manifest.jsonl");
    const previewTerminalPath = path.join(dataDir, "frontend", "auto_runs", job.jobId,
      `${preview.runId}.terminal.json`);
    const reviewEventPath = path.join(dataDir, "frontend", "auto_reviews", job.jobId,
      preview.runId, "events", "doc1", "000000000001.json");
    const originals = [previewResultPath, previewManifestPath, previewTerminalPath, reviewEventPath]
      .map((file) => fs.readFileSync(file));
    try {
      const legacyResult = JSON.parse(originals[0].toString("utf8"));
      legacyResult.reason = "invalid_strict_values_model_response";
      legacyResult.candidate.extracted_values = [{ field_id: "total", value: null,
        status: "missing", review_state: "pending" }];
      const resultBytes = Buffer.from(JSON.stringify(legacyResult));
      const resultHash = createHash("sha256").update(resultBytes).digest("hex");
      fs.writeFileSync(previewResultPath, resultBytes);
      const manifest = JSON.parse(originals[1].toString("utf8"));
      manifest.result_sha256 = resultHash;
      fs.writeFileSync(previewManifestPath, `${JSON.stringify(manifest)}\n`);
      const terminal = JSON.parse(originals[2].toString("utf8"));
      terminal.documents[0].machineResultSha256 = resultHash;
      fs.writeFileSync(previewTerminalPath, JSON.stringify(terminal));
      const event = JSON.parse(originals[3].toString("utf8"));
      event.machine_result_sha256 = resultHash;
      event.review_snapshot.machine_result_sha256 = resultHash;
      fs.writeFileSync(reviewEventPath, JSON.stringify(event));
      assert.equal((await start([remaining.fileId], "batch", preview.runId)).status, 409);
    } finally {
      for (const [index, file] of [previewResultPath, previewManifestPath, previewTerminalPath,
        reviewEventPath].entries()) fs.writeFileSync(file, originals[index]);
    }

    const sourcePath = path.join(uploaded.uploadsPath!, sample.storedName);
    const originalSource = fs.readFileSync(sourcePath);
    fs.writeFileSync(sourcePath, "Invoice A\nTotal: 999");
    assert.equal((await start([remaining.fileId], "batch", preview.runId)).status, 409);
    fs.writeFileSync(sourcePath, originalSource);
    const previewManifest = path.join(dataDir, "product_runs", preview.runId, "manifest.jsonl");
    const originalManifest = fs.readFileSync(previewManifest);
    const changedReceipt = JSON.parse(originalManifest.toString("utf8"));
    changedReceipt.confirmed_schema.snapshot_sha256 = "0".repeat(64);
    fs.writeFileSync(previewManifest, JSON.stringify(changedReceipt) + "\n");
    assert.equal((await start([remaining.fileId], "batch", preview.runId)).status, 409);
    fs.writeFileSync(previewManifest, originalManifest);
    const batchResponse = await start([remaining.fileId], "batch", preview.runId);
    assert.equal(batchResponse.status, 202);
    const batch = await batchResponse.json();
    assert.equal(batch.confirmedBrief.phase, "batch");
    assert.equal(batch.confirmedBrief.previewRunId, preview.runId);
    await waitForStatus(dataDir, job.jobId, batch.runId, "success");
    assert.equal(getProductAutoDocument(job.jobId, batch.runId, "doc1").candidate.extracted_values[0].evidence?.quote, "200");
    assert.equal(JSON.parse(fs.readFileSync(path.join(captureDir, `${batch.runId}.json`), "utf8")).digest,
      preview.confirmedBrief.snapshotSha256);
    const batchResult = path.join(dataDir, "product_runs", batch.runId, "docs", "doc1", "result.json");
    const originalResult = fs.readFileSync(batchResult);
    const changedResult = JSON.parse(originalResult.toString("utf8"));
    changedResult.confirmed_schema.snapshot_sha256 = "0".repeat(64);
    fs.writeFileSync(batchResult, JSON.stringify(changedResult));
    assert.throws(() => getProductAutoDocument(job.jobId, batch.runId, "doc1"), /machine result/i);
    fs.writeFileSync(batchResult, originalResult);

    const edited = await saveBrief(request(briefUrl, "alice", "POST", {
      expectedRevision: confirmed.revision, intent: "New schema", fields: confirmed.fields,
      sampleFileIds: [sample.fileId],
    }), params);
    assert.equal(edited.status, 201);
    assert.equal((await start([remaining.fileId], "batch", preview.runId)).status, 409);
  } finally {
    command.program = original.program;
    command.args = original.args;
    command.cwd = original.cwd;
    command.env = original.env;
  }
}));
