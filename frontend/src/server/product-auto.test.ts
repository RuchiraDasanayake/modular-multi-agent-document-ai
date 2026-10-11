import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import test from "node:test";
import { GET as listAutoRoute, POST as startAutoRoute } from "@/app/api/jobs/[jobId]/auto/route";
import { GET as getAutoDocRoute, POST as reviewAutoDocRoute } from "@/app/api/jobs/[jobId]/auto/[runId]/docs/[docId]/route";
import { GET as getOriginalContentRoute } from "@/app/api/jobs/[jobId]/docs/[docId]/content/route";
import { resetConfigCacheForTests } from "./config";
import { addDocumentsToJob, createWorkspaceJob } from "./jobs";

function request(pathname: string, token: string, init?: RequestInit): Request {
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return new Request(`http://localhost${pathname}`, { ...init, headers });
}

async function withStorage(run: (dataDir: string) => Promise<void>): Promise<void> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-product-auto-"));
  const dataDir = path.join(root, "data");
  const oldDataDir = process.env.IDPO_DATA_DIR;
  const oldGateway = process.env.INTERNAL_API_URL;
  const oldModel = process.env.IDPO_AUTO_MODEL;
  const oldBaseUrl = process.env.IDPO_AUTO_API_BASE_URL;
  const oldKey = process.env.ICORE_API_KEY;
  const oldFetch = globalThis.fetch;
  process.env.IDPO_DATA_DIR = dataDir;
  process.env.INTERNAL_API_URL = "http://test-gateway.local";
  delete process.env.IDPO_AUTO_MODEL;
  delete process.env.IDPO_AUTO_API_BASE_URL;
  delete process.env.ICORE_API_KEY;
  resetConfigCacheForTests();
  globalThis.fetch = async (input, init) => {
    if (String(input) === "http://test-gateway.local/api/auth/me") {
      const token = new Headers(init?.headers).get("Authorization")?.replace(/^Bearer /, "");
      if (token === "alice") return Response.json({ id: "alice-id", role: "viewer" });
      if (token === "bob") return Response.json({ id: "bob-id", role: "viewer" });
      if (token === "admin") return Response.json({ id: "admin-id", role: "admin" });
      return Response.json({}, { status: 401 });
    }
    return oldFetch(input, init);
  };
  try {
    await run(dataDir);
  } finally {
    globalThis.fetch = oldFetch;
    if (oldDataDir === undefined) delete process.env.IDPO_DATA_DIR;
    else process.env.IDPO_DATA_DIR = oldDataDir;
    if (oldGateway === undefined) delete process.env.INTERNAL_API_URL;
    else process.env.INTERNAL_API_URL = oldGateway;
    if (oldModel === undefined) delete process.env.IDPO_AUTO_MODEL;
    else process.env.IDPO_AUTO_MODEL = oldModel;
    if (oldBaseUrl === undefined) delete process.env.IDPO_AUTO_API_BASE_URL;
    else process.env.IDPO_AUTO_API_BASE_URL = oldBaseUrl;
    if (oldKey === undefined) delete process.env.ICORE_API_KEY;
    else process.env.ICORE_API_KEY = oldKey;
    resetConfigCacheForTests();
    if (path.dirname(root) !== os.tmpdir() || !path.basename(root).startsWith("idpo-product-auto-")) {
      throw new Error("Unsafe test cleanup path.");
    }
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("automatic extraction keeps source access private and rejects conflicting reviews", async () => withStorage(async (dataDir) => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const updated = await addDocumentsToJob(job.jobId, [new File(["Invoice\nTotal: 100"], "invoice.txt", { type: "text/plain" })]);
  const source = updated.documents![0];
  const sha256 = createHash("sha256").update(fs.readFileSync(path.join(updated.uploadsPath!, source.storedName))).digest("hex");
  const runId = `auto_${"a".repeat(32)}`;
  const docId = "doc1";
  const sidecarDir = path.join(dataDir, "product_runs", runId, "docs", docId);
  fs.mkdirSync(sidecarDir, { recursive: true });
  const candidate = {
    contract_version: 1, doc_id: docId, document_status: "processed",
    proposed_schema: [{ field_id: "total", type: "string" }],
    extracted_values: [{ field_id: "total", value: "100", status: "accepted", review_state: "none",
      evidence: { page: 1, start: 15, end: 18, quote: "100" } }],
  };
  const privatePath = path.join(dataDir, "frontend", "auto_inputs", runId, source.storedName);
  fs.writeFileSync(path.join(sidecarDir, "result.json"), JSON.stringify({ source_path: privatePath,
    pages: [{ page: 1, text: "Invoice\nTotal: 100" }], candidate }));
  fs.writeFileSync(path.join(dataDir, "product_runs", runId, "run.json"), JSON.stringify({ contract_version: 1, run_id: runId, doc_count: 1 }));
  fs.writeFileSync(path.join(dataDir, "product_runs", runId, "manifest.jsonl"), JSON.stringify({
    contract_version: 1, run_id: runId, doc_id: docId, source_path: privatePath,
    source_file: source.storedName, source_container_sha256: sha256, document_status: "processed",
  }) + "\n");
  const metadataDir = path.join(dataDir, "frontend", "auto_runs", job.jobId);
  fs.mkdirSync(metadataDir, { recursive: true });
  fs.writeFileSync(path.join(metadataDir, `${runId}.json`), JSON.stringify({
    runId, jobId: job.jobId, status: "running", createdAt: new Date().toISOString(),
    serverInstanceId: "previous-server", selectedFiles: [{ fileId: source.fileId,
      fileName: source.fileName, storedName: source.storedName, sha256 }], documents: [],
  }));

  const collectionUrl = `/api/jobs/${job.jobId}/auto`;
  const docUrl = `${collectionUrl}/${runId}/docs/${docId}`;
  const collectionParams = { params: Promise.resolve({ jobId: job.jobId }) };
  const detailParams = { params: Promise.resolve({ jobId: job.jobId, runId, docId }) };
  const sourceUrl = `/api/jobs/${job.jobId}/docs/${source.fileId}/content`;
  const sourceParams = { params: Promise.resolve({ jobId: job.jobId, docId: source.fileId }) };
  assert.equal((await listAutoRoute(request(collectionUrl, "bob"), collectionParams)).status, 404);
  assert.equal((await getAutoDocRoute(request(docUrl, "bob"), detailParams)).status, 404);
  assert.equal((await getOriginalContentRoute(request(sourceUrl, "bob"), sourceParams)).status, 404);
  assert.equal(await (await getOriginalContentRoute(request(sourceUrl, "alice"), sourceParams)).text(), "Invoice\nTotal: 100");

  const list = await listAutoRoute(request(collectionUrl, "alice"), collectionParams);
  assert.equal(list.status, 200);
  const listBody = await list.text();
  assert.equal(listBody.includes(privatePath), false);
  assert.equal(JSON.parse(listBody).runs[0].status, "success");
  const detail = await getAutoDocRoute(request(docUrl, "alice"), detailParams);
  assert.equal(detail.status, 200);
  const detailBody = await detail.text();
  assert.equal(detailBody.includes(privatePath), false);
  assert.equal(JSON.parse(detailBody).candidate.extracted_values[0].evidence.quote, "100");

  const post = (token: string, expectedRevision: number, fields: unknown) => reviewAutoDocRoute(request(docUrl, token, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: expectedRevision, fields }),
  }), detailParams);
  assert.equal((await post("bob", 0, [{ field_id: "total", decision: "correct" }])).status, 404);
  assert.equal((await post("alice", 0, [{ field_id: "other", decision: "correct" }])).status, 400);
  assert.equal((await post("alice", 0, [{ field_id: "total", decision: "correct", corrected_value: "999" }])).status, 400);
  const [first, second] = await Promise.all([
    post("alice", 0, [{ field_id: "total", decision: "corrected", corrected_value: "101" }]),
    post("alice", 0, [{ field_id: "total", decision: "corrected", corrected_value: "102" }]),
  ]);
  assert.deepEqual([first.status, second.status].sort(), [200, 409]);
  const saved = first.status === 200 ? first : second;
  assert.equal(saved.status, 200);
  assert.equal((await saved.json()).review.status, "completed");
  const auditDir = path.join(dataDir, "frontend", "auto_reviews", job.jobId, runId, "events", docId);
  assert.equal(fs.readdirSync(auditDir).length, 1);
  const firstEvent = fs.readdirSync(auditDir)[0];
  const firstBytes = fs.readFileSync(path.join(auditDir, firstEvent));
  assert.equal((await post("alice", 0, [{ field_id: "total", decision: "corrected", corrected_value: "999" }])).status, 409);
  const corrected = await post("alice", 1, [{ field_id: "total", decision: "corrected", corrected_value: "103" }]);
  assert.equal(corrected.status, 200);
  assert.equal(fs.readdirSync(auditDir).length, 2);
  assert.deepEqual(fs.readFileSync(path.join(auditDir, firstEvent)), firstBytes);
  const reviewed = await getAutoDocRoute(request(docUrl, "alice"), detailParams);
  const reviewedBody = await reviewed.json();
  assert.equal(reviewedBody.review.revision, 2);
  assert.equal(reviewedBody.auditTrail[1].machine_fields[0].value, "100");
  assert.equal(reviewedBody.auditTrail[1].review_fields[0].corrected_value, "103");
  assert.equal(reviewedBody.auditTrail[1].reviewer_user_id, "alice-id");
  assert.equal(reviewedBody.auditTrail[1].previous_event_id, reviewedBody.auditTrail[0].audit_event_id);
  const reviewedList = await listAutoRoute(request(collectionUrl, "alice"), collectionParams);
  assert.equal((await reviewedList.json()).runs[0].documents[0].reviewStatus, "completed");
  assert.equal(fs.existsSync(path.join(dataDir, "frontend", "auto_reviews", job.jobId, runId, `${docId}.json`)), false);
  const recovered = await getAutoDocRoute(request(docUrl, "alice"), detailParams);
  assert.equal((await recovered.json()).review.revision, 2);
}));

test("a viewer cannot trigger operator configured model calls", async () => withStorage(async () => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const updated = await addDocumentsToJob(job.jobId, [new File(["Total: 100"], "invoice.txt")]);
  process.env.IDPO_AUTO_MODEL = "operator-model";
  process.env.IDPO_AUTO_API_BASE_URL = "https://example.invalid/v1";
  process.env.ICORE_API_KEY = "test-key";
  const response = await startAutoRoute(request(`/api/jobs/${job.jobId}/auto`, "alice", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selectedFileIds: [updated.documents![0].fileId] }),
  }), { params: Promise.resolve({ jobId: job.jobId }) });
  assert.equal(response.status, 403);
}));
