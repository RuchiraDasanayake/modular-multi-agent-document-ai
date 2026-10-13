import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import test from "node:test";
import { GET as exportBatchRoute } from "@/app/api/jobs/[jobId]/auto/[runId]/export/route";
import { POST as reviewDocumentRoute } from "@/app/api/jobs/[jobId]/auto/[runId]/docs/[docId]/route";
import { resetConfigCacheForTests } from "./config";
import { addDocumentsToJob, createWorkspaceJob } from "./jobs";

const sha256 = (bytes: Buffer) => createHash("sha256").update(bytes).digest("hex");

function request(pathname: string, token: string, init?: RequestInit): Request {
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return new Request(`http://localhost${pathname}`, { ...init, headers });
}

async function withStorage(run: (dataDir: string) => Promise<void>): Promise<void> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-bulk-export-"));
  const dataDir = path.join(root, "data");
  const previousDataDir = process.env.IDPO_DATA_DIR;
  const previousGateway = process.env.INTERNAL_API_URL;
  const originalFetch = globalThis.fetch;
  process.env.IDPO_DATA_DIR = dataDir;
  process.env.INTERNAL_API_URL = "http://test-gateway.local";
  resetConfigCacheForTests();
  globalThis.fetch = async (input, init) => {
    if (String(input) === "http://test-gateway.local/api/auth/me") {
      const token = new Headers(init?.headers).get("Authorization")?.replace(/^Bearer /, "");
      if (token === "alice") return Response.json({ id: "alice-id", role: "viewer" });
      if (token === "bob") return Response.json({ id: "bob-id", role: "viewer" });
      return Response.json({}, { status: 401 });
    }
    return originalFetch(input, init);
  };
  try { await run(dataDir); }
  finally {
    globalThis.fetch = originalFetch;
    if (previousDataDir === undefined) delete process.env.IDPO_DATA_DIR;
    else process.env.IDPO_DATA_DIR = previousDataDir;
    if (previousGateway === undefined) delete process.env.INTERNAL_API_URL;
    else process.env.INTERNAL_API_URL = previousGateway;
    resetConfigCacheForTests();
    if (path.dirname(root) !== os.tmpdir() || !path.basename(root).startsWith("idpo-bulk-export-")) {
      throw new Error("Unsafe test cleanup path.");
    }
    fs.rmSync(root, { recursive: true, force: true });
  }
}

async function fixture(dataDir: string) {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const texts = ["Invoice number: INV-1\nTotal: 10", "Invoice number: INV-2\nTotal: 20"];
  const updated = await addDocumentsToJob(job.jobId, texts.map((text, index) =>
    new File([text], `invoice-${index + 1}.txt`, { type: "text/plain" })));
  const sources = updated.documents!;
  const runId = `auto_${"d".repeat(32)}`;
  const runDir = path.join(dataDir, "product_runs", runId);
  fs.mkdirSync(runDir, { recursive: true });
  const receipts = [];
  const documents = [];
  const selectedFiles = [];
  for (let index = 0; index < sources.length; index += 1) {
    const source = sources[index];
    const docId = `doc${index + 1}`;
    const sourceHash = sha256(fs.readFileSync(path.join(updated.uploadsPath!, source.storedName)));
    const quote = `INV-${index + 1}`;
    const start = texts[index].indexOf(quote);
    const result = { pages: [{ page: 1, text: texts[index] }], candidate: {
      contract_version: 1, doc_id: docId, document_status: "processed",
      proposed_schema: [{ field_id: "invoice_number", type: "string" }],
      extracted_values: [{ field_id: "invoice_number", value: quote, status: "accepted", review_state: "none",
        evidence: { page: 1, start, end: start + quote.length, quote } }],
    } };
    const resultPath = path.join(runDir, "docs", docId, "result.json");
    fs.mkdirSync(path.dirname(resultPath), { recursive: true });
    fs.writeFileSync(resultPath, JSON.stringify(result));
    const resultHash = sha256(fs.readFileSync(resultPath));
    receipts.push({ contract_version: 1, run_id: runId, doc_id: docId,
      source_file: source.storedName, source_container_sha256: sourceHash,
      document_status: "processed", result_sha256: resultHash });
    documents.push({ docId, fileId: source.fileId, fileName: source.fileName, status: "processed",
      fieldCount: 1, acceptedCount: 1, reviewStatus: "unreviewed", machineResultSha256: resultHash });
    selectedFiles.push({ fileId: source.fileId, fileName: source.fileName,
      storedName: source.storedName, sha256: sourceHash });
  }
  fs.writeFileSync(path.join(runDir, "run.json"), JSON.stringify({ contract_version: 1, run_id: runId, doc_count: 2 }));
  fs.writeFileSync(path.join(runDir, "manifest.jsonl"), receipts.map((receipt) => JSON.stringify(receipt)).join("\n") + "\n");
  const record = { runId, jobId: job.jobId, status: "success", createdAt: new Date().toISOString(),
    serverInstanceId: "fixture", selectedFiles: [...selectedFiles].reverse(), documents };
  const recordDir = path.join(dataDir, "frontend", "auto_runs", job.jobId);
  fs.mkdirSync(recordDir, { recursive: true });
  fs.writeFileSync(path.join(recordDir, `${runId}.json`), JSON.stringify(record));
  fs.writeFileSync(path.join(recordDir, `${runId}.terminal.json`), JSON.stringify(record));
  const batchUrl = `/api/jobs/${job.jobId}/auto/${runId}/export`;
  const batchParams = { params: Promise.resolve({ jobId: job.jobId, runId }) };
  const review = (docId: string) => reviewDocumentRoute(request(
    `/api/jobs/${job.jobId}/auto/${runId}/docs/${docId}`, "alice", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_revision: 0, fields: [{ field_id: "invoice_number", decision: "correct" }] }),
    }), { params: Promise.resolve({ jobId: job.jobId, runId, docId }) });
  return { batchUrl, batchParams, review, sources, updated, runDir, recordDir, runId };
}

test("reviewed JSONL batch refuses nonowners and partial reviews, then preserves selected order", async () =>
  withStorage(async (dataDir) => {
    const setup = await fixture(dataDir);
    assert.equal((await exportBatchRoute(request(setup.batchUrl, "bob"), setup.batchParams)).status, 404);
    assert.equal((await setup.review("doc1")).status, 200);
    const partial = await exportBatchRoute(request(setup.batchUrl, "alice"), setup.batchParams);
    assert.equal(partial.status, 409);
    assert.match((await partial.json()).error, /2 selected, 1 reviewed, 1 unreviewed/);
    assert.equal((await setup.review("doc2")).status, 200);
    const complete = await exportBatchRoute(request(setup.batchUrl, "alice"), setup.batchParams);
    assert.equal(complete.status, 200);
    assert.equal(complete.headers.get("Content-Type"), "application/x-ndjson; charset=utf-8");
    assert.equal(complete.headers.get("Cache-Control"), "no-store, max-age=0");
    assert.match(complete.headers.get("Content-Disposition") ?? "", /reviewed-v1\.jsonl"$/);
    const body = await complete.text();
    const lines = body.trimEnd().split("\n").map((line) => JSON.parse(line));
    assert.equal(lines.length, 2);
    assert.deepEqual(lines.map((line) => line.document.doc_id), ["doc2", "doc1"]);
    assert.deepEqual(lines.map((line) => line.result.fields[0].value), ["INV-2", "INV-1"]);
    assert.ok(lines.every((line) => line.contract_version === 1 && line.result.review_status === "completed"));
    assert.equal(body.includes(dataDir), false);
    assert.equal(body.includes("Invoice number:"), false);
  }));

test("reviewed JSONL batch refuses changed sources and incomplete run receipts", async () =>
  withStorage(async (dataDir) => {
    const setup = await fixture(dataDir);
    assert.equal((await setup.review("doc1")).status, 200);
    assert.equal((await setup.review("doc2")).status, 200);
    const sourcePath = path.join(setup.updated.uploadsPath!, setup.sources[0].storedName);
    const original = fs.readFileSync(sourcePath);
    fs.writeFileSync(sourcePath, "changed source bytes");
    const changed = await exportBatchRoute(request(setup.batchUrl, "alice"), setup.batchParams);
    assert.equal(changed.status, 409);
    assert.match((await changed.json()).error, /1 stale or unverifiable/);
    fs.writeFileSync(sourcePath, original);
    const manifestPath = path.join(setup.runDir, "manifest.jsonl");
    const firstReceipt = fs.readFileSync(manifestPath, "utf8").split("\n")[0];
    fs.writeFileSync(manifestPath, `${firstReceipt}\n`);
    const missing = await exportBatchRoute(request(setup.batchUrl, "alice"), setup.batchParams);
    assert.equal(missing.status, 409);
    assert.match((await missing.json()).error, /2 selected, 2 unverifiable run artifacts/);
  }));
