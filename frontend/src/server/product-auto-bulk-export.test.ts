import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import test from "node:test";
import { GET as exportBatchRoute } from "@/app/api/jobs/[jobId]/auto/[runId]/export/route";
import { GET as getDocumentRoute, POST as reviewDocumentRoute } from "@/app/api/jobs/[jobId]/auto/[runId]/docs/[docId]/route";
import { GET as exportDocumentRoute } from "@/app/api/jobs/[jobId]/auto/[runId]/docs/[docId]/export/route";
import { GET as getOriginalContentRoute } from "@/app/api/jobs/[jobId]/docs/[docId]/content/route";
import { POST as createRecipeDraftRoute } from "@/app/api/jobs/[jobId]/auto/recipes/route";
import type { ProductAutoAuditEvent, ProductAutoReview } from "@/types/product-auto";
import { resetConfigCacheForTests } from "./config";
import { addDocumentsToJob, createWorkspaceJob } from "./jobs";
import { getProductAutoRun, recoverProductAutoRuns, startProductAutoRun } from "./product-auto";
import { confirmProductAutoBrief, saveProductAutoBrief } from "./product-auto-brief";
import type { ProductExecutionQueue } from "./product-execution-queue";

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

async function fixture(dataDir: string, status: "processed" | "needs_review" | "failed" | "unsupported" = "processed",
  runStatus: "success" | "running" = "success", reason?: string, multiEntryJson = false) {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const texts = ["Invoice number: INV-1\nTotal: 10", "Invoice number: INV-2\nTotal: 20"];
  if (multiEntryJson) texts.push("Invoice number: INV-3\nTotal: 30");
  const files = multiEntryJson
    ? [new File([JSON.stringify(texts.slice(0, 2).map((text, index) => ({ doc_id: `entry${index}`, pages: [{ text }] })))],
      "invoices.json", { type: "application/json" }), new File([texts[2]], "invoice-3.txt")]
    : texts.map((text, index) => new File([text], `invoice-${index + 1}.txt`, { type: "text/plain" }));
  const updated = await addDocumentsToJob(job.jobId, files);
  const sources = updated.documents!;
  const runId = `auto_${"d".repeat(32)}`;
  const runDir = path.join(dataDir, "product_runs", runId);
  fs.mkdirSync(runDir, { recursive: true });
  const receipts = [];
  const documents = [];
  const selectedFiles = sources.map((source) => ({ fileId: source.fileId, fileName: source.fileName,
    storedName: source.storedName,
    sha256: sha256(fs.readFileSync(path.join(updated.uploadsPath!, source.storedName))) }));
  for (let index = 0; index < texts.length; index += 1) {
    const source = sources[multiEntryJson ? Math.max(0, index - 1) : index];
    const docId = `doc${index + 1}`;
    const sourceHash = sha256(fs.readFileSync(path.join(updated.uploadsPath!, source.storedName)));
    const quote = `INV-${index + 1}`;
    const start = texts[index].indexOf(quote);
    const result = { pages: [{ page: 1, text: texts[index] }], ...(reason ? { reason } : {}), candidate: {
      contract_version: 1, doc_id: docId, document_status: status,
      proposed_schema: [{ field_id: "invoice_number", type: "string" }],
      extracted_values: status === "processed"
        ? [{ field_id: "invoice_number", value: quote, status: "accepted", review_state: "none",
          evidence: { page: 1, start, end: start + quote.length, quote } }]
        : [{ field_id: "invoice_number", value: null, status: "missing", review_state: "pending" }],
    } };
    const resultPath = path.join(runDir, "docs", docId, "result.json");
    fs.mkdirSync(path.dirname(resultPath), { recursive: true });
    fs.writeFileSync(resultPath, JSON.stringify(result));
    const resultHash = sha256(fs.readFileSync(resultPath));
    receipts.push({ contract_version: 1, run_id: runId, doc_id: docId,
      source_file: source.storedName, source_container_sha256: sourceHash,
      document_status: status, result_sha256: resultHash });
    documents.push({ docId, fileId: source.fileId, fileName: source.fileName, status,
      fieldCount: 1, acceptedCount: status === "processed" ? 1 : 0,
      reviewStatus: "unreviewed", machineResultSha256: resultHash });
  }
  fs.writeFileSync(path.join(runDir, "run.json"), JSON.stringify({ contract_version: 1, run_id: runId,
    doc_count: documents.length }));
  fs.writeFileSync(path.join(runDir, "manifest.jsonl"), receipts.map((receipt) => JSON.stringify(receipt)).join("\n") + "\n");
  const record = { runId, jobId: job.jobId, status: runStatus, createdAt: new Date().toISOString(),
    serverInstanceId: "fixture", selectedFiles: [...selectedFiles].reverse(),
    documents: runStatus === "running" ? [] : documents };
  const recordDir = path.join(dataDir, "frontend", "auto_runs", job.jobId);
  fs.mkdirSync(recordDir, { recursive: true });
  fs.writeFileSync(path.join(recordDir, `${runId}.json`), JSON.stringify(record));
  if (runStatus === "success") fs.writeFileSync(path.join(recordDir, `${runId}.terminal.json`), JSON.stringify(record));
  const batchUrl = `/api/jobs/${job.jobId}/auto/${runId}/export`;
  const batchParams = { params: Promise.resolve({ jobId: job.jobId, runId }) };
  const review = (docId: string, revision = 0) => reviewDocumentRoute(request(
    `/api/jobs/${job.jobId}/auto/${runId}/docs/${docId}`, "alice", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_revision: revision, fields: [{ field_id: "invoice_number",
        ...(status === "processed" ? { decision: "correct" }
          : { decision: "corrected", corrected_value: `INV-${docId.slice(-1)}` }) }] }),
    }), { params: Promise.resolve({ jobId: job.jobId, runId, docId }) });
  return { batchUrl, batchParams, review, sources, updated, runDir, recordDir, runId, job, texts, documents, selectedFiles };
}

for (const outcome of [
  { status: "failed", reason: undefined },
  { status: "unsupported", reason: undefined },
  { status: "needs_review", reason: "invalid_strict_values_model_response" },
  { status: "needs_review", reason: "document_processing_failed" },
] as const) {
  const { status, reason } = outcome;
  for (const runStatus of ["success", "running"] as const) {
    test(`${status}${reason ? " with legacy invalid model reply" : ""} refuses review and export without writes in a ${runStatus} run`, async () =>
      withStorage(async (dataDir) => {
        const setup = await fixture(dataDir, status, runStatus, reason);
        const recordPath = path.join(setup.recordDir, `${setup.runId}.json`);
        const recordBefore = fs.readFileSync(recordPath);
        const terminalPath = path.join(setup.recordDir, `${setup.runId}.terminal.json`);
        const terminalBefore = fs.existsSync(terminalPath) ? fs.readFileSync(terminalPath) : null;
        const docUrl = `/api/jobs/${setup.job.jobId}/auto/${setup.runId}/docs/doc1`;
        const params = { params: Promise.resolve({ jobId: setup.job.jobId, runId: setup.runId, docId: "doc1" }) };
        const detail = await getDocumentRoute(request(docUrl, "alice"), params);
        assert.equal(detail.status, 200);
        const detailBody = await detail.json();
        assert.equal(detailBody.sourcePages[0].text, setup.texts[0]);
        if (reason) {
          assert.equal(detailBody.candidate.document_status, "failed");
          assert.equal(detailBody.outcomeReason, reason);
          assert.equal(detailBody.candidate.extracted_values[0].status, "missing");
        }
        assert.equal((await exportDocumentRoute(request(`${docUrl}/export`, "bob"), params)).status, 404);
        const rejectedReview = await setup.review("doc1");
        const rejectedExport = await exportDocumentRoute(request(`${docUrl}/export`, "alice"), params);
        for (const response of [rejectedReview, rejectedExport]) {
          assert.equal(response.status, 409);
          assert.match((await response.json()).error, /Failed or unsupported documents cannot be reviewed or exported/);
        }
        const batch = await exportBatchRoute(request(setup.batchUrl, "alice"), setup.batchParams);
        assert.equal(batch.status, 409);
        assert.match((await batch.json()).error, runStatus === "success" ? /2 failed or unsupported/ : /Complete the run/);
        assert.equal(fs.existsSync(path.join(dataDir, "frontend", "auto_reviews")), false);
        assert.deepEqual(fs.readFileSync(recordPath), recordBefore);
        assert.deepEqual(fs.existsSync(terminalPath) ? fs.readFileSync(terminalPath) : null, terminalBefore);
        const sourceParams = { params: Promise.resolve({ jobId: setup.job.jobId, docId: setup.sources[0].fileId }) };
        const source = await getOriginalContentRoute(request(
          `/api/jobs/${setup.job.jobId}/docs/${setup.sources[0].fileId}/content`, "alice"), sourceParams);
        assert.equal(source.status, 200);
        assert.equal(await source.text(), setup.texts[0]);
      }));
  }

  test(`${status}${reason ? " with legacy invalid model reply" : ""} and completed old review still cannot export`, async () =>
    withStorage(async (dataDir) => {
      const setup = await fixture(dataDir, status, "success", reason);
      const auditPaths: string[] = [];
      for (const [index, document] of setup.documents.entries()) {
        const review: ProductAutoReview = {
          review_version: 1, job_id: setup.job.jobId, run_id: setup.runId, doc_id: document.docId,
          status: "completed", reviewer_user_id: "alice-id", updated_at: "2026-10-13T00:00:00Z",
          fields: [{ field_id: "invoice_number", decision: "corrected", corrected_value: `INV-${index + 1}`, note: null }],
          source_container_sha256: setup.selectedFiles[index].sha256,
          source_pages_sha256: sha256(Buffer.from(JSON.stringify([{ page: 1, text: setup.texts[index] }]))),
          machine_result_sha256: document.machineResultSha256, revision: 1, audit_event_id: "a".repeat(32),
        };
        const event: ProductAutoAuditEvent = {
          audit_event_id: review.audit_event_id, revision: 1, previous_event_id: null,
          created_at: review.updated_at, reviewer_user_id: review.reviewer_user_id, review_snapshot: review,
          machine_fields: [{ field_id: "invoice_number", value: null, status: "missing" }],
          review_fields: review.fields, source_container_sha256: review.source_container_sha256,
          source_pages_sha256: review.source_pages_sha256, machine_result_sha256: review.machine_result_sha256,
        };
        const auditPath = path.join(dataDir, "frontend", "auto_reviews", setup.job.jobId,
          setup.runId, "events", document.docId, "000000000001.json");
        fs.mkdirSync(path.dirname(auditPath), { recursive: true });
        fs.writeFileSync(auditPath, JSON.stringify(event));
        auditPaths.push(auditPath);
      }
      const auditBefore = auditPaths.map((file) => fs.readFileSync(file));
      const docUrl = `/api/jobs/${setup.job.jobId}/auto/${setup.runId}/docs/doc1`;
      const params = { params: Promise.resolve({ jobId: setup.job.jobId, runId: setup.runId, docId: "doc1" }) };
      const detail = await getDocumentRoute(request(docUrl, "alice"), params);
      assert.equal(detail.status, 200);
      assert.equal((await detail.json()).correctedResult.review_status, "completed");
      for (const response of [await setup.review("doc1", 1),
        await exportDocumentRoute(request(`${docUrl}/export`, "alice"), params)]) {
        assert.equal(response.status, 409);
        assert.match((await response.json()).error, /Failed or unsupported documents cannot be reviewed or exported/);
      }
      if (reason) {
        const recipeUrl = `/api/jobs/${setup.job.jobId}/auto/recipes`;
        const recipeDraft = await createRecipeDraftRoute(request(recipeUrl, "alice", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ runId: setup.runId, docId: "doc1", expectedReviewRevision: 1,
            familyName: "Legacy failed example" }),
        }), { params: Promise.resolve({ jobId: setup.job.jobId }) });
        assert.equal(recipeDraft.status, 409);
        assert.match((await recipeDraft.json()).error, /Failed or unsupported documents cannot seed a recipe/);
      }
      const batch = await exportBatchRoute(request(setup.batchUrl, "alice"), setup.batchParams);
      assert.equal(batch.status, 409);
      assert.match((await batch.json()).error, /0 reviewed, 0 unreviewed, 2 failed or unsupported/);
      for (const [index, auditPath] of auditPaths.entries()) {
        assert.deepEqual(fs.readFileSync(auditPath), auditBefore[index]);
        assert.deepEqual(fs.readdirSync(path.dirname(auditPath)), ["000000000001.json"]);
      }
    }));
}

test("a sealed complete all-null reply remains reviewable instead of a model failure", async () =>
  withStorage(async (dataDir) => {
    const setup = await fixture(dataDir, "needs_review", "success", "confirmed_schema_no_grounded_values");
    const url = `/api/jobs/${setup.job.jobId}/auto/${setup.runId}/docs/doc1`;
    const params = { params: Promise.resolve({ jobId: setup.job.jobId, runId: setup.runId, docId: "doc1" }) };
    const detail = await getDocumentRoute(request(url, "alice"), params);
    assert.equal(detail.status, 200);
    const body = await detail.json();
    assert.equal(body.candidate.document_status, "needs_review");
    assert.equal(body.outcomeReason, undefined);
    assert.equal(body.candidate.extracted_values[0].status, "missing");
    assert.equal((await setup.review("doc1")).status, 200);
    assert.equal((await exportDocumentRoute(request(`${url}/export`, "alice"), params)).status, 200);
  }));

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

test("reviewed JSONL batch exports every logical JSON document in selected-original order", async () =>
  withStorage(async (dataDir) => {
    const setup = await fixture(dataDir, "processed", "success", undefined, true);
    assert.equal((await exportBatchRoute(request(setup.batchUrl, "bob"), setup.batchParams)).status, 404);
    assert.equal((await setup.review("doc1")).status, 200);
    assert.equal((await setup.review("doc3")).status, 200);
    const partial = await exportBatchRoute(request(setup.batchUrl, "alice"), setup.batchParams);
    assert.equal(partial.status, 409);
    assert.match((await partial.json()).error, /2 selected, 2 reviewed, 1 unreviewed/);
    assert.equal((await setup.review("doc2")).status, 200);
    const response = await exportBatchRoute(request(setup.batchUrl, "alice"), setup.batchParams);
    assert.equal(response.status, 200);
    const text = await response.text();
    const lines = text.trimEnd().split("\n").map((line) => JSON.parse(line));
    assert.deepEqual(lines.map((line) => line.document.doc_id), ["doc3", "doc1", "doc2"]);
    assert.deepEqual(lines.map((line) => line.document.file_id),
      [setup.sources[1].fileId, setup.sources[0].fileId, setup.sources[0].fileId]);
    assert.deepEqual(lines.map((line) => line.result.fields[0].value), ["INV-3", "INV-1", "INV-2"]);
    assert.ok(lines.every((line) => line.contract_version === 1 && line.result.review_status === "completed"));
    assert.equal(text.includes(dataDir), false);
  }));

for (const mutation of ["missing_original", "missing_document", "duplicate_manifest_id",
  "unselected_source", "duplicate_sealed_id", "extra_sealed_document", "changed_result"] as const) {
  test(`multi-document JSON export refuses ${mutation} receipts`, async () => withStorage(async (dataDir) => {
    const setup = await fixture(dataDir, "processed", "success", undefined, true);
    for (const document of setup.documents) assert.equal((await setup.review(document.docId)).status, 200);
    const manifestPath = path.join(setup.runDir, "manifest.jsonl");
    let receipts = fs.readFileSync(manifestPath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
    const recordFiles = [".json", ".terminal.json"].map((suffix) => path.join(setup.recordDir, setup.runId + suffix));
    for (const file of recordFiles) {
      const record = JSON.parse(fs.readFileSync(file, "utf8"));
      if (mutation === "missing_original") record.documents = record.documents.filter((item: { docId: string }) => item.docId !== "doc3");
      if (mutation === "duplicate_sealed_id") record.documents[1] = record.documents[0];
      if (mutation === "extra_sealed_document") record.documents.push({ ...record.documents[0], docId: "extra" });
      fs.writeFileSync(file, JSON.stringify(record));
    }
    if (mutation === "missing_original") receipts = receipts.filter((receipt) => receipt.doc_id !== "doc3");
    if (mutation === "missing_document") receipts = receipts.filter((receipt) => receipt.doc_id !== "doc2");
    if (mutation === "duplicate_manifest_id") receipts.push(receipts[0]);
    if (mutation === "unselected_source") receipts[1].source_file = "unselected.json";
    if (mutation === "changed_result") {
      const resultPath = path.join(setup.runDir, "docs", "doc2", "result.json");
      fs.appendFileSync(resultPath, " ");
      receipts[1].result_sha256 = sha256(fs.readFileSync(resultPath));
    }
    fs.writeFileSync(manifestPath, receipts.map((receipt) => JSON.stringify(receipt)).join("\n") + "\n");
    fs.writeFileSync(path.join(setup.runDir, "run.json"), JSON.stringify({ contract_version: 1,
      run_id: setup.runId, doc_count: receipts.length }));
    const response = await exportBatchRoute(request(setup.batchUrl, "alice"), setup.batchParams);
    assert.equal(response.status, 409);
    assert.match((await response.json()).error, /unverifiable run artifacts|missing or inconsistent run receipts/);
  }));
}

test("reviewed JSONL batch bounds logical documents rather than only uploaded originals", async () =>
  withStorage(async (dataDir) => {
    const setup = await fixture(dataDir, "processed", "success", undefined, true);
    const file = path.join(setup.recordDir, `${setup.runId}.terminal.json`);
    const record = JSON.parse(fs.readFileSync(file, "utf8"));
    record.documents = Array.from({ length: 5001 }, (_, index) => ({ ...record.documents[0], docId: `doc${index}` }));
    fs.writeFileSync(file, JSON.stringify(record));
    const response = await exportBatchRoute(request(setup.batchUrl, "alice"), setup.batchParams);
    assert.equal(response.status, 413);
    assert.match((await response.json()).error, /5000 documents/);
  }));

test("reviewed JSONL batch retains its cumulative byte limit with several documents per original", async () =>
  withStorage(async (dataDir) => {
    const setup = await fixture(dataDir, "processed", "success", undefined, true);
    for (const document of setup.documents) assert.equal((await setup.review(document.docId)).status, 200);
    const stringify = JSON.stringify;
    let serializedDocuments = 0;
    try {
      // Valid trailing JSON whitespace makes two large lines without large source or result fixtures.
      JSON.stringify = ((value: unknown) => {
        const text = stringify(value);
        if (value && typeof value === "object" && "document" in value && "result" in value) {
          serializedDocuments += 1;
          return text.padEnd(33 * 1024 * 1024, " ");
        }
        return text;
      }) as typeof JSON.stringify;
      const response = await exportBatchRoute(request(setup.batchUrl, "alice"), setup.batchParams);
      assert.equal(response.status, 413);
      assert.match((await response.json()).error, /64 MiB/);
      assert.equal(serializedDocuments, 2);
    } finally { JSON.stringify = stringify; }
  }));

test("recovery cannot seal a self-consistent manifest that omits a selected original", async () =>
  withStorage(async (dataDir) => {
    const setup = await fixture(dataDir, "processed", "running", undefined, true);
    const manifestPath = path.join(setup.runDir, "manifest.jsonl");
    const receipts = fs.readFileSync(manifestPath, "utf8").trim().split("\n")
      .map((line) => JSON.parse(line)).filter((receipt) => receipt.doc_id !== "doc3");
    fs.writeFileSync(manifestPath, receipts.map((receipt) => JSON.stringify(receipt)).join("\n") + "\n");
    fs.writeFileSync(path.join(setup.runDir, "run.json"), JSON.stringify({ contract_version: 1,
      run_id: setup.runId, doc_count: receipts.length }));
    const recordPath = path.join(setup.recordDir, `${setup.runId}.json`);
    const record = JSON.parse(fs.readFileSync(recordPath, "utf8"));
    record.createdAt = "2000-01-01T00:00:00Z";
    fs.writeFileSync(recordPath, JSON.stringify(record));
    assert.equal(recoverProductAutoRuns(setup.job.jobId).recovered, 1);
    assert.equal(getProductAutoRun(setup.job.jobId, setup.runId).status, "failed");
  }));

test("confirmed batch admission requires review of every logical document in a JSON sample", async () =>
  withStorage(async (dataDir) => {
    const setup = await fixture(dataDir, "needs_review", "success", undefined, true);
    const draft = saveProductAutoBrief(setup.job.jobId, "alice-id", { expectedRevision: 0,
      intent: "Extract invoice numbers", sampleFileIds: [setup.sources[0].fileId],
      fields: [{ field_id: "invoice_number", type: "string", description: "Printed invoice identifier" }] });
    const brief = confirmProductAutoBrief(setup.job.jobId, "alice-id", {
      expectedRevision: draft.revision, expectedPayloadSha256: draft.payload_sha256 });
    const schema = { brief_id: brief.brief_id, revision: brief.revision, audit_event_id: brief.audit_event_id,
      payload_sha256: brief.payload_sha256, snapshot_sha256: "f".repeat(64) };
    const manifestPath = path.join(setup.runDir, "manifest.jsonl");
    const receipts = fs.readFileSync(manifestPath, "utf8").trim().split("\n").map((line) => JSON.parse(line)).slice(0, 2);
    for (const receipt of receipts) {
      const resultPath = path.join(setup.runDir, "docs", receipt.doc_id, "result.json");
      const result = JSON.parse(fs.readFileSync(resultPath, "utf8"));
      result.confirmed_schema = schema;
      fs.writeFileSync(resultPath, JSON.stringify(result));
      receipt.confirmed_schema = schema;
      receipt.result_sha256 = sha256(fs.readFileSync(resultPath));
    }
    fs.writeFileSync(manifestPath, receipts.map((receipt) => JSON.stringify(receipt)).join("\n") + "\n");
    fs.writeFileSync(path.join(setup.runDir, "run.json"), JSON.stringify({ contract_version: 1,
      run_id: setup.runId, doc_count: 2, confirmed_schema: schema }));
    for (const suffix of [".json", ".terminal.json"]) {
      const file = path.join(setup.recordDir, setup.runId + suffix);
      const record = JSON.parse(fs.readFileSync(file, "utf8"));
      record.selectedFiles = [setup.selectedFiles[0]];
      record.documents = record.documents.slice(0, 2).map((document: { docId: string }) => ({ ...document,
        machineResultSha256: receipts.find((receipt) => receipt.doc_id === document.docId).result_sha256 }));
      record.confirmedBrief = { briefId: brief.brief_id, revision: brief.revision, auditEventId: brief.audit_event_id,
        ownerUserId: "alice-id", jobId: setup.job.jobId, payloadSha256: brief.payload_sha256,
        snapshotSha256: schema.snapshot_sha256, phase: "preview" };
      fs.writeFileSync(file, JSON.stringify(record));
    }
    const environment = { IDPO_AUTO_MODEL: "fixture-model", IDPO_AUTO_API_BASE_URL: "http://127.0.0.1:1/v1",
      PRODUCT_EXECUTION_MODE: "postgres", PRODUCT_QUEUE_DATABASE_URL: "postgresql://127.0.0.1:1/unused_test_database" };
    const previous = Object.fromEntries(Object.keys(environment).map((key) => [key, process.env[key]]));
    const holder = globalThis as typeof globalThis & { __productQueue?: ProductExecutionQueue };
    const oldQueue = holder.__productQueue;
    let admissions = 0;
    holder.__productQueue = { enqueue: async () => { admissions += 1; return "fixture-broker-id"; } } as unknown as ProductExecutionQueue;
    Object.assign(process.env, environment);
    const selection = { expectedRevision: brief.revision, payloadSha256: brief.payload_sha256,
      phase: "batch" as const, previewRunId: setup.runId };
    try {
      assert.equal((await setup.review("doc1")).status, 200);
      await assert.rejects(startProductAutoRun(setup.job.jobId, [setup.sources[1].fileId], true,
        undefined, selection), /every preview document/);
      assert.equal(admissions, 0);
      assert.equal((await setup.review("doc2")).status, 200);
      const batch = await startProductAutoRun(setup.job.jobId, [setup.sources[1].fileId], true, undefined, selection);
      assert.equal(batch.status, "queued");
      assert.equal(admissions, 1);
    } finally {
      if (oldQueue === undefined) delete holder.__productQueue; else holder.__productQueue = oldQueue;
      for (const [key, value] of Object.entries(previous)) {
        if (value === undefined) delete process.env[key]; else process.env[key] = value;
      }
    }
  }));
