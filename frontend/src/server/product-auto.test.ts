import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import test from "node:test";
import { GET as listAutoRoute, POST as startAutoRoute } from "@/app/api/jobs/[jobId]/auto/route";
import { POST as saveBriefRoute, PATCH as confirmBriefRoute } from "@/app/api/jobs/[jobId]/auto/brief/route";
import { GET as getAutoDocRoute, POST as reviewAutoDocRoute } from "@/app/api/jobs/[jobId]/auto/[runId]/docs/[docId]/route";
import { GET as exportAutoDocRoute } from "@/app/api/jobs/[jobId]/auto/[runId]/docs/[docId]/export/route";
import { GET as getOriginalContentRoute } from "@/app/api/jobs/[jobId]/docs/[docId]/content/route";
import { idpoApi, parseReportedActiveMinutes } from "@/lib/idpo-api";
import { loadRunnerConfig, resetConfigCacheForTests } from "./config";
import { QueueAdmissionError, type ProductExecutionQueue } from "./product-execution-queue";
import { addDocumentsToJob, createWorkspaceJob } from "./jobs";
import { deriveProductAutoCorrectedResult, getProductAutoRun, productAutoAvailability,
  recoverProductAutoRuns, startProductAutoRun } from "./product-auto";
import type { ProductAutoCandidate, ProductAutoReview } from "@/types/product-auto";

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
  const sourceText = "Invoice\nTotal: 100\nInvoice number: INV-7\nPaid: false\nTax: 12.50\nUnits: 0\nDate: 2026-02-10";
  const updated = await addDocumentsToJob(job.jobId, [new File([sourceText], "invoice.txt", { type: "text/plain" })]);
  const source = updated.documents![0];
  const sha256 = createHash("sha256").update(fs.readFileSync(path.join(updated.uploadsPath!, source.storedName))).digest("hex");
  const runId = `auto_${"a".repeat(32)}`;
  const docId = "doc1";
  const sidecarDir = path.join(dataDir, "product_runs", runId, "docs", docId);
  fs.mkdirSync(sidecarDir, { recursive: true });
  const candidate: ProductAutoCandidate = {
    contract_version: 1, doc_id: docId, document_status: "processed",
    proposed_schema: [{ field_id: "total", type: "string" }],
    extracted_values: [{ field_id: "total", value: "100", status: "accepted", review_state: "none",
      evidence: { page: 1, start: 15, end: 18, quote: "100" } }],
  };
  const privatePath = path.join(dataDir, "frontend", "auto_inputs", runId, source.storedName);
  fs.writeFileSync(path.join(sidecarDir, "result.json"), JSON.stringify({ source_path: privatePath,
    pages: [{ page: 1, text: sourceText }], candidate }));
  fs.writeFileSync(path.join(dataDir, "product_runs", runId, "run.json"), JSON.stringify({ contract_version: 1, run_id: runId, doc_count: 1 }));
  fs.writeFileSync(path.join(dataDir, "product_runs", runId, "manifest.jsonl"), JSON.stringify({
    contract_version: 1, run_id: runId, doc_id: docId, source_path: privatePath,
    source_file: source.storedName, source_container_sha256: sha256, document_status: "processed",
    result_sha256: createHash("sha256").update(fs.readFileSync(path.join(sidecarDir, "result.json"))).digest("hex"),
  }) + "\n");
  const metadataDir = path.join(dataDir, "frontend", "auto_runs", job.jobId);
  fs.mkdirSync(metadataDir, { recursive: true });
  fs.writeFileSync(path.join(metadataDir, `${runId}.json`), JSON.stringify({
    runId, jobId: job.jobId, status: "running", createdAt: new Date().toISOString(),
    serverInstanceId: "previous-server", selectedFiles: [{ fileId: source.fileId,
      fileName: source.fileName, storedName: source.storedName, sha256 }], documents: [],
  }));

  const manifestPath = path.join(dataDir, "product_runs", runId, "manifest.jsonl");
  const validManifest = fs.readFileSync(manifestPath);
  for (const invalidDigest of [undefined, "invalid-digest"]) {
    const receipt = JSON.parse(validManifest.toString("utf8"));
    if (invalidDigest === undefined) delete receipt.result_sha256;
    else receipt.result_sha256 = invalidDigest;
    fs.writeFileSync(manifestPath, JSON.stringify(receipt) + "\n");
    assert.equal(recoverProductAutoRuns(job.jobId).recovered, 0);
    assert.equal(fs.existsSync(path.join(metadataDir, `${runId}.terminal.json`)), false);
  }
  fs.writeFileSync(manifestPath, validManifest);

  const collectionUrl = `/api/jobs/${job.jobId}/auto`;
  const docUrl = `${collectionUrl}/${runId}/docs/${docId}`;
  const exportUrl = `${docUrl}/export`;
  const collectionParams = { params: Promise.resolve({ jobId: job.jobId }) };
  const detailParams = { params: Promise.resolve({ jobId: job.jobId, runId, docId }) };
  const sourceUrl = `/api/jobs/${job.jobId}/docs/${source.fileId}/content`;
  const sourceParams = { params: Promise.resolve({ jobId: job.jobId, docId: source.fileId }) };
  assert.equal((await listAutoRoute(request(collectionUrl, "bob"), collectionParams)).status, 404);
  assert.equal((await getAutoDocRoute(request(docUrl, "bob"), detailParams)).status, 404);
  assert.equal((await exportAutoDocRoute(request(exportUrl, "bob"), detailParams)).status, 404);
  assert.equal((await getOriginalContentRoute(request(sourceUrl, "bob"), sourceParams)).status, 404);
  assert.equal(await (await getOriginalContentRoute(request(sourceUrl, "alice"), sourceParams)).text(), sourceText);

  const list = await listAutoRoute(request(collectionUrl, "alice"), collectionParams);
  assert.equal(list.status, 200);
  const listBody = await list.text();
  assert.equal(listBody.includes(privatePath), false);
  assert.equal(JSON.parse(listBody).runs[0].status, "success");
  assert.equal(JSON.parse(fs.readFileSync(path.join(metadataDir, `${runId}.json`), "utf8")).status, "running");
  assert.equal(fs.existsSync(path.join(metadataDir, `${runId}.terminal.json`)), false);
  assert.equal(recoverProductAutoRuns(job.jobId).recovered, 1);
  assert.equal(JSON.parse(fs.readFileSync(path.join(metadataDir, `${runId}.terminal.json`), "utf8")).status, "success");
  const detail = await getAutoDocRoute(request(docUrl, "alice"), detailParams);
  assert.equal(detail.status, 200);
  const detailBody = await detail.text();
  assert.equal(detailBody.includes(privatePath), false);
  assert.equal(JSON.parse(detailBody).candidate.extracted_values[0].evidence.quote, "100");
  assert.equal(JSON.parse(detailBody).sourcePages[0].text, sourceText);
  assert.equal(JSON.parse(detailBody).correctedResult.fields[0].status, "needs_review");
  assert.equal(JSON.parse(detailBody).correctedResult.fields[0].provenance, "machine");
  const unfinishedExport = await exportAutoDocRoute(request(exportUrl, "alice"), detailParams);
  assert.equal(unfinishedExport.status, 409);
  assert.match((await unfinishedExport.json()).error, /Complete the document review/);

  const post = (token: string, expectedRevision: number, fields: unknown, addedFields?: unknown,
    reportedSeconds?: unknown) => reviewAutoDocRoute(request(docUrl, token, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: expectedRevision, fields,
      ...(addedFields === undefined ? {} : { added_fields: addedFields }),
      ...(reportedSeconds === undefined ? {} : { reported_active_review_seconds: reportedSeconds }) }),
  }), detailParams);
  assert.equal((await post("bob", 0, [{ field_id: "total", decision: "correct" }])).status, 404);
  assert.equal((await post("bob", 0, [{ field_id: "total", decision: "correct" }], [], 90)).status, 404);
  assert.equal((await post("alice", 0, [{ field_id: "other", decision: "correct" }])).status, 400);
  assert.equal((await post("alice", 0, [{ field_id: "total", decision: "correct", corrected_value: "999" }])).status, 400);
  for (const invalid of [null, 0, -1, 1.5, 14_401, "60"]) {
    assert.equal((await post("alice", 0, [{ field_id: "total", decision: "correct" }], [], invalid)).status, 400);
  }
  const [first, second] = await Promise.all([
    post("alice", 0, [{ field_id: "total", decision: "corrected", corrected_value: "101" }]),
    post("alice", 0, [{ field_id: "total", decision: "corrected", corrected_value: "102" }]),
  ]);
  assert.deepEqual([first.status, second.status].sort(), [200, 409]);
  const saved = first.status === 200 ? first : second;
  assert.equal(saved.status, 200);
  const savedBody = await saved.json();
  assert.equal(savedBody.review.status, "completed");
  assert.ok(savedBody.detail, "A committed review must return its refreshed document without another request.");
  assert.deepEqual(savedBody.detail.review, savedBody.review);
  assert.deepEqual(savedBody.detail.correctedResult, savedBody.correctedResult);
  assert.equal(savedBody.detail.auditTrail.length, 1);
  assert.equal(savedBody.detail.auditTrail[0].revision, savedBody.review.revision);
  assert.equal(JSON.stringify(savedBody.detail).includes(privatePath), false);
  const auditDir = path.join(dataDir, "frontend", "auto_reviews", job.jobId, runId, "events", docId);
  assert.equal(fs.readdirSync(auditDir).length, 1);
  const firstEvent = fs.readdirSync(auditDir)[0];
  const firstBytes = fs.readFileSync(path.join(auditDir, firstEvent));
  assert.equal((await post("alice", 0, [{ field_id: "total", decision: "corrected", corrected_value: "999" }])).status, 409);
  const corrected = await post("alice", 1, [{ field_id: "total", decision: "corrected", corrected_value: "103" }], [], 125);
  assert.equal(corrected.status, 200);
  const correctedBody = await corrected.json();
  assert.equal(fs.readdirSync(auditDir).length, 2);
  assert.deepEqual(fs.readFileSync(path.join(auditDir, firstEvent)), firstBytes);
  const reviewed = await getAutoDocRoute(request(docUrl, "alice"), detailParams);
  const reviewedBody = await reviewed.json();
  assert.deepEqual(correctedBody.detail, reviewedBody, "The save response includes the same verified state as a fresh read.");
  assert.equal(reviewedBody.review.revision, 2);
  assert.equal(reviewedBody.auditTrail[1].machine_fields[0].value, "100");
  assert.equal(reviewedBody.auditTrail[1].review_fields[0].corrected_value, "103");
  assert.equal(reviewedBody.auditTrail[1].reviewer_user_id, "alice-id");
  assert.equal(reviewedBody.auditTrail[0].reported_active_review_seconds, undefined);
  assert.equal(reviewedBody.auditTrail[1].reported_active_review_seconds, 125);
  assert.equal(reviewedBody.auditTrail[1].review_snapshot.reported_active_review_seconds, undefined);
  assert.equal(reviewedBody.auditTrail[1].previous_event_id, reviewedBody.auditTrail[0].audit_event_id);
  assert.equal(reviewedBody.correctedResult.fields[0].value, "103");
  assert.equal(reviewedBody.correctedResult.fields[0].provenance, "human_correction");
  assert.equal(reviewedBody.correctedResult.fields[0].evidence, undefined);
  const correctedExport = await exportAutoDocRoute(request(exportUrl, "alice"), detailParams);
  assert.equal(correctedExport.status, 200);
  const correctedExportBody = await correctedExport.json();
  assert.equal(correctedExportBody.review.revision, 2);
  assert.equal(correctedExportBody.result.fields[0].value, "103");
  assert.equal(correctedExportBody.result.fields[0].provenance, "human_correction");
  assert.equal(correctedExportBody.result.fields[0].evidence, undefined);
  const reviewedList = await listAutoRoute(request(collectionUrl, "alice"), collectionParams);
  assert.equal((await reviewedList.json()).runs[0].documents[0].reviewStatus, "completed");
  assert.equal(fs.existsSync(path.join(dataDir, "frontend", "auto_reviews", job.jobId, runId, `${docId}.json`)), false);
  const recovered = await getAutoDocRoute(request(docUrl, "alice"), detailParams);
  assert.equal((await recovered.json()).review.revision, 2);

  assert.equal((await post("alice", 2, [{ field_id: "total", decision: "remove" }],
    [{ field_id: "total", type: "string", value: "collision" }])).status, 400);
  assert.equal((await post("alice", 2, [{ field_id: "total", decision: "remove" }],
    [{ field_id: "invoice_number", type: "decimal", value: "not a number" }])).status, 400);
  assert.equal((await post("alice", 2, [{ field_id: "total", decision: "remove" }],
    [{ field_id: "invoice_date", type: "date", value: "2026-02-30" }])).status, 400);
  assert.equal((await post("alice", 2, [{ field_id: "total", decision: "remove" }],
    [{ field_id: "invoice_number", type: "string", value: "INV-7" }])).status, 400);
  assert.equal((await post("alice", 2, [{ field_id: "total", decision: "remove" }],
    [{ field_id: "invoice_number", type: "string", value: "INV-7",
      evidence: { page: 2, quote: "Invoice number: INV-7" } }])).status, 400);
  assert.equal((await post("alice", 2, [{ field_id: "total", decision: "remove" }],
    [{ field_id: "invoice_number", type: "string", value: "INV-7",
      evidence: { page: 1, quote: "Invoice number: INV-8" } }])).status, 400);
  assert.equal((await post("alice", 2, [{ field_id: "total", decision: "remove" }],
    [{ field_id: "invoice_number", type: "string", value: "OTHER",
      evidence: { page: 1, quote: "Invoice number: INV-7" } }])).status, 400);
  assert.equal((await post("alice", 2, [{ field_id: "total", decision: "remove" }],
    [{ field_id: "invoice_number", type: "string", value: "INV-7",
      evidence: { page: 1, start: 0, quote: "Invoice number: INV-7" } }])).status, 400);
  const ambiguousQuote = await post("alice", 2, [{ field_id: "total", decision: "remove" }],
    [{ field_id: "document_type", type: "string", value: "Invoice",
      evidence: { page: 1, quote: "Invoice" } }]);
  assert.equal(ambiguousQuote.status, 400);
  assert.match((await ambiguousQuote.json()).error, /more than once/);
  assert.equal((await post("alice", 2, [{ field_id: "total", decision: "remove" }],
    Array.from({ length: 25 }, (_, index) => ({ field_id: `missed_${index}`, type: "string", value: "Invoice",
      evidence: { page: 1, quote: "Invoice" } })))).status, 400);
  const quoteSource = (quote: string) => ({ page: 1, quote });
  const adjudicated = await post("alice", 2, [{ field_id: "total", decision: "remove", note: "This is a subtotal" }],
    [{ field_id: "invoice_number", type: "string", value: "INV-7", evidence: quoteSource("Invoice number: INV-7"), note: "Visible on page one" },
      { field_id: "paid", type: "boolean", value: "false", evidence: quoteSource("Paid: false") },
      { field_id: "tax", type: "decimal", value: "12.50", evidence: quoteSource("Tax: 12.50") },
      { field_id: "units", type: "integer", value: "0", evidence: quoteSource("Units: 0") },
      { field_id: "invoice_date", type: "date", value: "2026-02-10", evidence: quoteSource("Date: 2026-02-10") }]);
  assert.equal(adjudicated.status, 200);
  const adjudicatedBody = await adjudicated.json();
  assert.equal(adjudicatedBody.review.status, "completed");
  assert.deepEqual(adjudicatedBody.correctedResult.removed_field_ids, ["total"]);
  assert.deepEqual(adjudicatedBody.correctedResult.fields.map((field: { field_id: string }) => field.field_id),
    ["invoice_date", "invoice_number", "paid", "tax", "units"]);
  assert.equal(adjudicatedBody.correctedResult.fields[2].value, false);
  assert.equal(adjudicatedBody.correctedResult.fields[3].value, 12.5);
  assert.equal(adjudicatedBody.correctedResult.fields[4].value, 0);
  assert.deepEqual(adjudicatedBody.correctedResult.fields[1].evidence,
    { page: 1, start: [...sourceText.slice(0, sourceText.indexOf("Invoice number: INV-7"))].length,
      end: [...sourceText.slice(0, sourceText.indexOf("Invoice number: INV-7"))].length + "Invoice number: INV-7".length,
      quote: "Invoice number: INV-7" });
  assert.equal((await post("alice", 2, [{ field_id: "total", decision: "correct" }])).status, 409);
  assert.equal(fs.readdirSync(auditDir).length, 3);
  assert.deepEqual(fs.readFileSync(path.join(auditDir, firstEvent)), firstBytes);
  const finalDetail = await getAutoDocRoute(request(docUrl, "alice"), detailParams);
  const finalBody = await finalDetail.json();
  assert.equal(finalBody.candidate.extracted_values[0].value, "100");
  assert.equal(finalBody.auditTrail[2].machine_fields[0].value, "100");
  assert.equal(finalBody.auditTrail[2].review_added_fields[0].value, "INV-7");
  assert.deepEqual(finalBody.correctedResult, adjudicatedBody.correctedResult);
  assert.equal((await getAutoDocRoute(request(docUrl, "bob"), detailParams)).status, 404);
  const reviewedExport = await exportAutoDocRoute(request(exportUrl, "alice"), detailParams);
  assert.equal(reviewedExport.status, 200);
  assert.match(reviewedExport.headers.get("Content-Disposition") ?? "", /^attachment; filename="docai-doc1-reviewed-v1\.json"$/);
  assert.equal(reviewedExport.headers.get("Cache-Control"), "no-store, max-age=0");
  assert.equal(reviewedExport.headers.get("X-Content-Type-Options"), "nosniff");
  const exportText = await reviewedExport.text();
  assert.equal(exportText.includes(privatePath), false);
  assert.equal(exportText.includes(sourceText), false);
  const exportBody = JSON.parse(exportText);
  assert.equal(exportBody.contract_version, 1);
  assert.equal(exportBody.document.source_sha256, sha256);
  assert.equal(exportBody.document.machine_result_sha256,
    createHash("sha256").update(fs.readFileSync(path.join(sidecarDir, "result.json"))).digest("hex"));
  assert.equal(exportBody.review.revision, 3);
  assert.equal(exportBody.result.review_status, "completed");
  assert.deepEqual(exportBody.result, finalBody.correctedResult);
  fs.writeFileSync(path.join(updated.uploadsPath!, source.storedName), "changed source bytes");
  assert.equal((await exportAutoDocRoute(request(exportUrl, "alice"), detailParams)).status, 409);
  fs.writeFileSync(path.join(updated.uploadsPath!, source.storedName), sourceText);

  const afterDelete = await post("alice", 3, [{ field_id: "total", decision: "remove" }],
    [{ field_id: "paid", type: "boolean", value: "false", evidence: quoteSource("Paid: false") },
      { field_id: "tax", type: "decimal", value: "12.50", evidence: quoteSource("Tax: 12.50") }]);
  assert.equal(afterDelete.status, 200);
  assert.deepEqual((await afterDelete.json()).correctedResult.fields.map((field: { field_id: string }) => field.field_id), ["paid", "tax"]);
  assert.equal(fs.readdirSync(auditDir).length, 4);
  assert.deepEqual(fs.readFileSync(path.join(auditDir, firstEvent)), firstBytes);
  const unresolved = await post("alice", 4, [{ field_id: "total", decision: "incorrect" }], []);
  assert.equal(unresolved.status, 200);
  assert.equal((await unresolved.json()).review.status, "pending");
  assert.equal((await exportAutoDocRoute(request(exportUrl, "alice"), detailParams)).status, 409);

  const writeCandidate = () => fs.writeFileSync(path.join(sidecarDir, "result.json"), JSON.stringify({
    pages: [{ page: 1, text: sourceText }], candidate,
  }));
  const evidenceFor = (quote: string) => {
    const start = [...sourceText.slice(0, sourceText.indexOf(quote))].length;
    return { page: 1, start, end: start + [...quote].length, quote };
  };
  candidate.extracted_values[0].value = "999";
  writeCandidate();
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), detailParams)).status, 409);
  assert.equal((await exportAutoDocRoute(request(exportUrl, "alice"), detailParams)).status, 409);
  candidate.proposed_schema[0].type = "integer";
  candidate.extracted_values[0].value = 100;
  writeCandidate();
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), detailParams)).status, 409);
  candidate.extracted_values[0].value = 999;
  writeCandidate();
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), detailParams)).status, 409);
  candidate.extracted_values[0].value = "100";
  writeCandidate();
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), detailParams)).status, 409);
  candidate.proposed_schema[0].type = "decimal";
  candidate.extracted_values[0].value = 12.5;
  candidate.extracted_values[0].evidence = evidenceFor("12.50");
  writeCandidate();
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), detailParams)).status, 409);
  candidate.proposed_schema[0].type = "boolean";
  candidate.extracted_values[0].value = false;
  candidate.extracted_values[0].evidence = evidenceFor("false");
  writeCandidate();
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), detailParams)).status, 409);
  candidate.proposed_schema[0].type = "date";
  candidate.extracted_values[0].value = "2026-02-10";
  candidate.extracted_values[0].evidence = evidenceFor("2026-02-10");
  writeCandidate();
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), detailParams)).status, 409);
}));

test("failed document details expose only allowlisted outcome codes to the owner", async () => withStorage(async (dataDir) => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const uploaded = await addDocumentsToJob(job.jobId, [new File(["synthetic image bytes"], "frames.tiff")]);
  const source = uploaded.documents![0];
  const sourceHash = createHash("sha256").update(fs.readFileSync(path.join(uploaded.uploadsPath!, source.storedName))).digest("hex");
  const lengthCall = { phase: "values", finish_reason: "length", error: null, refusal: false, sdk_attempts: 1 };
  const cases: Array<{ suffix: string; status: "failed" | "unsupported"; reason: string;
    expected?: string; diagnostic?: string; sidecar?: Record<string, unknown>; omitReceipt?: boolean }> = [
    { suffix: "c", status: "unsupported", reason: "multi_frame_image_unsupported", expected: "multi_frame_image_unsupported" },
    { suffix: "d", status: "failed", reason: "provider exception: private raw diagnostic" },
    { suffix: "e", status: "failed", reason: "invalid_strict_values_model_response",
      expected: "invalid_strict_values_model_response", diagnostic: "output_token_limit",
      sidecar: { response_format_profile: "strict_confirmed_values_v1", model_calls: [lengthCall] } },
    { suffix: "f", status: "failed", reason: "long_document_segment_incomplete", diagnostic: "output_token_limit",
      sidecar: { response_format_profile: "strict_confirmed_values_v2", model_calls: [lengthCall] } },
    { suffix: "g", status: "failed", reason: "invalid_strict_values_model_response",
      expected: "invalid_strict_values_model_response",
      sidecar: { response_format_profile: "plain_json", model_calls: [lengthCall] } },
    { suffix: "h", status: "failed", reason: "invalid_strict_values_model_response",
      expected: "invalid_strict_values_model_response",
      sidecar: { response_format_profile: "strict_confirmed_values_v2",
        model_calls: [{ ...lengthCall, phase: "schema" }] } },
    { suffix: "i", status: "failed", reason: "unknown_private_reason",
      sidecar: { response_format_profile: "strict_confirmed_values_v2", model_calls: [lengthCall] } },
    { suffix: "j", status: "failed", reason: "invalid_strict_values_model_response",
      expected: "invalid_strict_values_model_response", omitReceipt: true,
      sidecar: { response_format_profile: "strict_confirmed_values_v2", model_calls: [lengthCall] } },
    { suffix: "k", status: "failed", reason: "invalid_strict_values_model_response",
      expected: "invalid_strict_values_model_response",
      sidecar: { response_format_profile: ["strict_confirmed_values_v2"], model_calls: [lengthCall] } },
    { suffix: "l", status: "failed", reason: "invalid_strict_values_model_response",
      expected: "invalid_strict_values_model_response",
      sidecar: { response_format_profile: "strict_confirmed_values_v2",
        model_calls: [{ ...lengthCall, finish_reason: "stop" }] } },
  ];
  for (const item of cases) {
    const runId = `auto_${item.suffix.repeat(32)}`;
    const docId = `doc_${item.suffix}`;
    const runDir = path.join(dataDir, "product_runs", runId);
    const resultDir = path.join(runDir, "docs", docId);
    fs.mkdirSync(resultDir, { recursive: true });
    const resultBytes = Buffer.from(JSON.stringify({ pages: [], reason: item.reason, ...item.sidecar,
      candidate: { contract_version: 1, doc_id: docId, document_status: item.status,
        proposed_schema: [], extracted_values: [] } }));
    const resultHash = createHash("sha256").update(resultBytes).digest("hex");
    fs.writeFileSync(path.join(resultDir, "result.json"), resultBytes);
    fs.writeFileSync(path.join(runDir, "run.json"), JSON.stringify({ contract_version: 1, run_id: runId, doc_count: 1 }));
    fs.writeFileSync(path.join(runDir, "manifest.jsonl"), JSON.stringify({ contract_version: 1,
      run_id: runId, doc_id: docId, source_file: source.storedName, source_container_sha256: sourceHash,
      document_status: item.status, result_sha256: resultHash }) + "\n");
    const recordDir = path.join(dataDir, "frontend", "auto_runs", job.jobId);
    fs.mkdirSync(recordDir, { recursive: true });
    fs.writeFileSync(path.join(recordDir, `${runId}.json`), JSON.stringify({
      runId, jobId: job.jobId, status: "success", createdAt: "2026-10-13T00:00:00Z",
      serverInstanceId: "synthetic", selectedFiles: [{ fileId: source.fileId, fileName: source.fileName,
        storedName: source.storedName, sha256: sourceHash }],
      documents: [{ docId, fileId: source.fileId, fileName: source.fileName, status: item.status,
        fieldCount: 0, acceptedCount: 0, reviewStatus: "unreviewed",
        ...(!item.omitReceipt ? { machineResultSha256: resultHash } : {}) }],
    }));
    const url = `/api/jobs/${job.jobId}/auto/${runId}/docs/${docId}`;
    const params = { params: Promise.resolve({ jobId: job.jobId, runId, docId }) };
    assert.equal((await getAutoDocRoute(request(url, "bob"), params)).status, 404);
    const response = await getAutoDocRoute(request(url, "alice"), params);
    assert.equal(response.status, 200);
    const body = await response.json();
    assert.equal(body.outcomeReason, item.expected);
    assert.equal(body.outcomeDiagnostic, item.diagnostic);
    assert.equal(body.sourcePages.length, 0);
    assert.equal(JSON.stringify(body).includes("private raw diagnostic"), false);
    assert.equal(JSON.stringify(body).includes("model_calls"), false);
    assert.equal(JSON.stringify(body).includes("finish_reason"), false);
    if (item.diagnostic) {
      const review = await reviewAutoDocRoute(request(url, "alice", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: 0, fields: [] }) }), params);
      assert.equal(review.status, 409);
      assert.equal((await exportAutoDocRoute(request(`${url}/export`, "alice"), params)).status, 409);
    }
    if (item.suffix === "e") {
      fs.writeFileSync(path.join(resultDir, "result.json"), Buffer.from(resultBytes.toString().replace('"finish_reason":"length"', '"finish_reason":"stop"')));
      assert.equal((await getAutoDocRoute(request(url, "alice"), params)).status, 409,
        "A modified result must not retain a truncation diagnosis");
    }
  }
}));

test("native source downloads safely and exposes only a hash-matched parsed artifact", async () => withStorage(async (dataDir) => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const updated = await addDocumentsToJob(job.jobId, [new File(["<p>Order: A1</p>"], "order.html", { type: "text/html" })]);
  const source = updated.documents![0];
  const sourcePath = path.join(updated.uploadsPath!, source.storedName);
  const sha256 = createHash("sha256").update(fs.readFileSync(sourcePath)).digest("hex");
  const sourceUrl = `/api/jobs/${job.jobId}/docs/${source.fileId}/content`;
  const sourceParams = { params: Promise.resolve({ jobId: job.jobId, docId: source.fileId }) };
  const download = await getOriginalContentRoute(request(sourceUrl, "alice"), sourceParams);
  assert.equal(download.status, 200);
  assert.match(download.headers.get("Content-Disposition") ?? "", /^attachment;/);
  assert.equal(download.headers.get("Content-Security-Policy"), "sandbox");
  assert.equal(download.headers.get("X-Content-Type-Options"), "nosniff");
  assert.equal((await getOriginalContentRoute(request(sourceUrl, "bob"), sourceParams)).status, 404);

  const runId = `auto_${"b".repeat(32)}`;
  const docId = "native1";
  const inputPath = path.join(dataDir, "frontend", "auto_inputs", runId, source.storedName);
  const runDir = path.join(dataDir, "product_runs", runId);
  const sidecarDir = path.join(runDir, "docs", docId);
  fs.mkdirSync(sidecarDir, { recursive: true });
  const parsed = { contract_version: 2, source_sha256: sha256, source_format: "html", parser_id: "lxml-html",
    parser_version: "test", units: [{ unit_id: "html-1", kind: "html", ordinal: 0, text: "Order: A1", label: "HTML document" }],
    tables: [] };
  fs.writeFileSync(path.join(sidecarDir, "result.json"), JSON.stringify({ source_path: inputPath,
    source_container_sha256: sha256, pages: [{ page: 1, text: "Order: A1" }], parsed_document: parsed,
    candidate: { contract_version: 1, doc_id: docId, document_status: "needs_review",
      proposed_schema: [], extracted_values: [] } }));
  fs.writeFileSync(path.join(runDir, "run.json"), JSON.stringify({ contract_version: 1, run_id: runId, doc_count: 1 }));
  fs.writeFileSync(path.join(runDir, "manifest.jsonl"), JSON.stringify({ contract_version: 1, run_id: runId,
    doc_id: docId, source_path: inputPath, source_file: source.storedName,
    source_container_sha256: sha256, document_status: "needs_review" }) + "\n");
  const metadataDir = path.join(dataDir, "frontend", "auto_runs", job.jobId);
  fs.mkdirSync(metadataDir, { recursive: true });
  fs.writeFileSync(path.join(metadataDir, `${runId}.json`), JSON.stringify({ runId, jobId: job.jobId,
    status: "running", createdAt: new Date().toISOString(), serverInstanceId: "previous-server",
    selectedFiles: [{ fileId: source.fileId, fileName: source.fileName, storedName: source.storedName, sha256 }],
    documents: [] }));
  fs.writeFileSync(path.join(metadataDir, `${runId}.terminal.json`), JSON.stringify({ runId, jobId: job.jobId,
    status: "success", createdAt: new Date().toISOString(), serverInstanceId: "previous-server",
    selectedFiles: [{ fileId: source.fileId, fileName: source.fileName, storedName: source.storedName, sha256 }],
    documents: [{ docId, fileId: source.fileId, fileName: source.fileName, status: "needs_review",
      fieldCount: 0, acceptedCount: 0, reviewStatus: "unreviewed" }] }));
  const detailUrl = `/api/jobs/${job.jobId}/auto/${runId}/docs/${docId}`;
  const detailParams = { params: Promise.resolve({ jobId: job.jobId, runId, docId }) };
  const detail = await getAutoDocRoute(request(detailUrl, "alice"), detailParams);
  assert.equal(detail.status, 200);
  assert.equal((await detail.json()).parsedDocument.source_sha256, sha256);
  assert.equal((await getAutoDocRoute(request(detailUrl, "bob"), detailParams)).status, 404);
  const legacyReview = await reviewAutoDocRoute(request(detailUrl, "alice", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_revision: 0, fields: [] }),
  }), detailParams);
  assert.equal(legacyReview.status, 409);
  assert.match((await legacyReview.json()).error, /predates sealed artifacts/);
  fs.writeFileSync(path.join(sidecarDir, "result.json"), JSON.stringify({ source_path: inputPath,
    source_container_sha256: sha256, pages: [{ page: 1, text: "Order: A1" }],
    parsed_document: { ...parsed, source_sha256: "a".repeat(64) },
    candidate: { contract_version: 1, doc_id: docId, document_status: "needs_review",
      proposed_schema: [], extracted_values: [] } }));
  assert.equal((await getAutoDocRoute(request(detailUrl, "alice"), detailParams)).status, 500);
}));

test("reading a run owned by another live server does not mark it failed", async () => withStorage(async (dataDir) => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const runId = `auto_${"f".repeat(32)}`;
  const directory = path.join(dataDir, "frontend", "auto_runs", job.jobId);
  fs.mkdirSync(directory, { recursive: true });
  const recordPath = path.join(directory, `${runId}.json`);
  fs.writeFileSync(recordPath, JSON.stringify({
    runId, jobId: job.jobId, status: "running", createdAt: new Date().toISOString(),
    serverInstanceId: "another-live-server", selectedFiles: [], documents: [],
  }));
  const response = await listAutoRoute(request(`/api/jobs/${job.jobId}/auto`, "alice"),
    { params: Promise.resolve({ jobId: job.jobId }) });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).runs[0].status, "running");
  assert.equal(JSON.parse(fs.readFileSync(recordPath, "utf8")).status, "running");
}));

test("a foreign live process retains its run; an expired crash lease is recovered outside GET", async () => withStorage(async (dataDir) => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const runId = `auto_${"e".repeat(32)}`;
  const directory = path.join(dataDir, "frontend", "auto_runs", job.jobId);
  fs.mkdirSync(directory, { recursive: true });
  const recordPath = path.join(directory, `${runId}.json`);
  const terminalPath = path.join(directory, `${runId}.terminal.json`);
  const leasePath = path.join(directory, `${runId}.lease.json`);
  const stagedPath = path.join(dataDir, "frontend", "auto_inputs", runId);
  fs.mkdirSync(stagedPath, { recursive: true });
  fs.writeFileSync(path.join(stagedPath, "source.txt"), "still possibly in use by the worker");
  const ownerInstanceId = "foreign-live-process";
  fs.writeFileSync(recordPath, JSON.stringify({ runId, jobId: job.jobId, status: "running",
    createdAt: new Date().toISOString(), serverInstanceId: ownerInstanceId, selectedFiles: [], documents: [] }));
  const original = fs.readFileSync(recordPath);
  const child = spawn(process.execPath, ["-e", `
    const fs = require("node:fs");
    const leasePath = process.argv[1];
    const ownerInstanceId = process.argv[2];
    const renew = () => { const now = Date.now(); fs.writeFileSync(leasePath, JSON.stringify({
      ownerInstanceId, heartbeatAt: new Date(now).toISOString(), expiresAt: new Date(now + 300000).toISOString(),
    })); };
    renew(); setInterval(renew, 100);
  `, leasePath, ownerInstanceId], { stdio: "ignore", windowsHide: true });
  try {
    const deadline = Date.now() + 5000;
    while (!fs.existsSync(leasePath) && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
    assert.equal(fs.existsSync(leasePath), true, "foreign process should publish its lease");
    const url = `/api/jobs/${job.jobId}/auto`;
    const params = { params: Promise.resolve({ jobId: job.jobId }) };
    assert.equal((await (await listAutoRoute(request(url, "alice"), params)).json()).runs[0].status, "running");
    assert.equal(recoverProductAutoRuns(job.jobId).recovered, 0);
    assert.deepEqual(fs.readFileSync(recordPath), original);
    assert.equal(fs.existsSync(terminalPath), false);
  } finally {
    child.kill();
    if (child.exitCode === null) await new Promise<void>((resolve) => child.once("close", () => resolve()));
  }
  const expired = new Date(Date.now() - 1000).toISOString();
  fs.writeFileSync(leasePath, JSON.stringify({ ownerInstanceId, heartbeatAt: expired, expiresAt: expired }));
  const url = `/api/jobs/${job.jobId}/auto`;
  const params = { params: Promise.resolve({ jobId: job.jobId }) };
  assert.equal((await (await listAutoRoute(request(url, "alice"), params)).json()).runs[0].status, "running");
  assert.equal(fs.existsSync(terminalPath), false, "GET must not recover an expired run");
  assert.equal(recoverProductAutoRuns(job.jobId).recovered, 1);
  assert.equal(recoverProductAutoRuns(job.jobId).recovered, 0, "recovery should be idempotent");
  const runs = (await (await listAutoRoute(request(url, "alice"), params)).json()).runs;
  assert.equal(runs[0].status, "failed");
  assert.match(runs[0].error, /lease/);
  assert.deepEqual(fs.readFileSync(recordPath), original);
  assert.equal(JSON.parse(fs.readFileSync(terminalPath, "utf8")).status, "failed");
  assert.equal(fs.existsSync(path.join(stagedPath, "source.txt")), true);
  const terminal = fs.readFileSync(terminalPath);
  const lateOutput = path.join(dataDir, "product_runs", runId);
  fs.mkdirSync(lateOutput, { recursive: true });
  fs.writeFileSync(path.join(lateOutput, "run.json"), JSON.stringify({ contract_version: 1, run_id: runId, doc_count: 0 }));
  fs.writeFileSync(path.join(lateOutput, "manifest.jsonl"), "");
  assert.equal(recoverProductAutoRuns(job.jobId).recovered, 0);
  assert.deepEqual(fs.readFileSync(terminalPath), terminal, "late worker output cannot overwrite the terminal decision");
}));

test("legacy not-present reviews derive a removal without added-field metadata", () => {
  const candidate: ProductAutoCandidate = { contract_version: 1, doc_id: "legacy", document_status: "processed",
    proposed_schema: [{ field_id: "old_field", type: "string" }],
    extracted_values: [{ field_id: "old_field", value: "wrong", status: "accepted", review_state: "none",
      evidence: { page: 1, start: 0, end: 5, quote: "wrong" } }] };
  const review: ProductAutoReview = { review_version: 1, job_id: "job", run_id: "run", doc_id: "legacy",
    status: "completed", reviewer_user_id: "reviewer", updated_at: "2026-01-01T00:00:00Z",
    fields: [{ field_id: "old_field", decision: "not_present" }], revision: 1, audit_event_id: "event" };
  const result = deriveProductAutoCorrectedResult(candidate, review);
  assert.deepEqual(result.fields, []);
  assert.deepEqual(result.removed_field_ids, ["old_field"]);
  assert.equal(result.scope, "document");
});

test("legacy added values without source evidence remain pending", () => {
  const candidate: ProductAutoCandidate = { contract_version: 1, doc_id: "legacy", document_status: "processed",
    proposed_schema: [], extracted_values: [] };
  const review: ProductAutoReview = { review_version: 1, job_id: "job", run_id: "run", doc_id: "legacy",
    status: "completed", reviewer_user_id: "reviewer", updated_at: "2026-01-01T00:00:00Z",
    fields: [], added_fields: [{ field_id: "invoice_id", type: "string", value: "INV-7" }],
    revision: 1, audit_event_id: "event" };
  const result = deriveProductAutoCorrectedResult(candidate, review);
  assert.equal(result.review_status, "pending");
  assert.equal(result.fields[0].status, "needs_review");
  assert.equal(result.fields[0].evidence, undefined);
});

test("a machine proposal stays pending until a reviewer verifies it", () => {
  const candidate: ProductAutoCandidate = { contract_version: 1, doc_id: "pending", document_status: "needs_review",
    proposed_schema: [{ field_id: "invoice_id", type: "string" }],
    extracted_values: [{ field_id: "invoice_id", value: "INV-7", status: "accepted", review_state: "pending",
      evidence: { page: 1, start: 0, end: 5, quote: "INV-7" } }] };
  const pending = deriveProductAutoCorrectedResult(candidate, null);
  assert.equal(pending.fields[0].status, "needs_review");
  assert.equal(pending.fields[0].provenance, "machine");
  const review: ProductAutoReview = { review_version: 1, job_id: "job", run_id: "run", doc_id: "pending",
    status: "completed", reviewer_user_id: "reviewer", updated_at: "2026-01-01T00:00:00Z",
    fields: [{ field_id: "invoice_id", decision: "correct" }], revision: 1, audit_event_id: "event" };
  const verified = deriveProductAutoCorrectedResult(candidate, review);
  assert.equal(verified.fields[0].status, "accepted");
  assert.equal(verified.fields[0].provenance, "human_verified");
  review.fields[0].decision = "incorrect";
  assert.equal(deriveProductAutoCorrectedResult(candidate, review).fields[0].status, "needs_review");
});

test("numeric corrections are typed and invalid legacy corrections remain unresolved", () => {
  const candidate: ProductAutoCandidate = { contract_version: 1, doc_id: "numeric", document_status: "needs_review",
    proposed_schema: [{ field_id: "amount", type: "decimal" }],
    extracted_values: [{ field_id: "amount", value: null, status: "needs_review", review_state: "pending" }] };
  const review: ProductAutoReview = { review_version: 1, job_id: "job", run_id: "run", doc_id: "numeric",
    status: "completed", reviewer_user_id: "reviewer", updated_at: "2026-01-01T00:00:00Z",
    fields: [{ field_id: "amount", decision: "corrected", corrected_value: "1,234.50" }], revision: 1, audit_event_id: "event" };
  const corrected = deriveProductAutoCorrectedResult(candidate, review);
  assert.equal(corrected.fields[0].value, 1234.5);
  assert.equal(corrected.fields[0].status, "accepted");
  review.fields[0].corrected_value = "not a number";
  const legacyInvalid = deriveProductAutoCorrectedResult(candidate, review);
  assert.equal(legacyInvalid.fields[0].value, null);
  assert.equal(legacyInvalid.fields[0].status, "needs_review");
});

test("linked rows require inspectable cell evidence or a typed human correction", async () => withStorage(async (dataDir) => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const updated = await addDocumentsToJob(job.jobId, [new File(["Widget 3\nGadget 4"], "items.txt")]);
  const source = updated.documents![0];
  const sourcePath = path.join(updated.uploadsPath!, source.storedName);
  const sha256 = createHash("sha256").update(fs.readFileSync(sourcePath)).digest("hex");
  const runId = `auto_${"b".repeat(32)}`;
  const docId = "linked1";
  const sidecarDir = path.join(dataDir, "product_runs", runId, "docs", docId);
  fs.mkdirSync(sidecarDir, { recursive: true });
  const candidate: ProductAutoCandidate = {
    contract_version: 1, doc_id: docId, document_status: "needs_review",
    proposed_schema: [{ field_id: "item_name", type: "array[object]", group: "items" },
      { field_id: "quantity", type: "array[object]", group: "items" }],
    extracted_values: [
      { field_id: "item_name", status: "needs_review", review_state: "pending", value: [
        { row: 0, value: "Widget", status: "accepted", evidence: { page: 1, start: 0, end: 6, quote: "Widget" } },
        { row: 1, value: "Gadget", status: "accepted", evidence: { page: 1, start: 9, end: 15, quote: "Gadget" } },
      ] },
      { field_id: "quantity", status: "needs_review", review_state: "pending", value: [
        { row: 0, value: "3", status: "accepted", evidence: { page: 1, start: 7, end: 8, quote: "3" } },
        { row: 1, value: "4", status: "needs_review" },
      ] },
    ],
  };
  const sidecarPath = path.join(sidecarDir, "result.json");
  const writeSidecar = () => fs.writeFileSync(sidecarPath, JSON.stringify({ pages: [{ page: 1, text: "Widget 3\nGadget 4" }], candidate }));
  writeSidecar();
  fs.writeFileSync(path.join(dataDir, "product_runs", runId, "run.json"), JSON.stringify({ contract_version: 1, run_id: runId, doc_count: 1 }));
  fs.writeFileSync(path.join(dataDir, "product_runs", runId, "manifest.jsonl"), JSON.stringify({
    contract_version: 1, run_id: runId, doc_id: docId, source_file: source.storedName,
    source_container_sha256: sha256, document_status: "needs_review",
    result_sha256: createHash("sha256").update(fs.readFileSync(sidecarPath)).digest("hex"),
  }) + "\n");
  const metadataDir = path.join(dataDir, "frontend", "auto_runs", job.jobId);
  fs.mkdirSync(metadataDir, { recursive: true });
  fs.writeFileSync(path.join(metadataDir, `${runId}.json`), JSON.stringify({
    runId, jobId: job.jobId, status: "running", createdAt: new Date().toISOString(),
    serverInstanceId: "previous-server", selectedFiles: [{ fileId: source.fileId,
      fileName: source.fileName, storedName: source.storedName, sha256 }], documents: [],
  }));
  const docUrl = `/api/jobs/${job.jobId}/auto/${runId}/docs/${docId}`;
  const params = { params: Promise.resolve({ jobId: job.jobId, runId, docId }) };
  const post = (expectedRevision: number, fields: unknown) => reviewAutoDocRoute(request(docUrl, "alice", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: expectedRevision, fields }),
  }), params);

  const original = await getAutoDocRoute(request(docUrl, "alice"), params);
  assert.equal(original.status, 200);
  assert.equal((await original.json()).candidate.extracted_values[0].value[0].evidence.quote, "Widget");
  const originalResultBytes = fs.readFileSync(sidecarPath);
  const initialCell = (candidate.extracted_values[0].value as Array<{
    value: string; evidence: { page: number; start: number; end: number; quote: string };
  }>)[0];
  initialCell.value = "Gadget";
  initialCell.evidence = { page: 1, start: 9, end: 15, quote: "Gadget" };
  writeSidecar();
  assert.equal((await post(0, [{ field_id: "item_name", decision: "correct" }])).status, 409);
  initialCell.value = "Widget";
  initialCell.evidence = { page: 1, start: 0, end: 6, quote: "Widget" };
  fs.writeFileSync(sidecarPath, originalResultBytes);
  assert.equal((await post(0, [{ field_id: "item_name", decision: "correct" },
    { field_id: "quantity", decision: "correct" }])).status, 400);
  for (const invalid of ["not rows", "[]", JSON.stringify([{ row: 0, value: "3" }, { row: 0, value: "4" }]),
    JSON.stringify([{ row: 128, value: "3" }]), JSON.stringify([{ row: 0, value: "3", source: "invented" }]),
    JSON.stringify([{ row: 0, value: "x".repeat(501) }]),
    JSON.stringify(Array.from({ length: 129 }, (_, row) => ({ row, value: "1" })))]) {
    assert.equal((await post(0, [{ field_id: "item_name", decision: "correct" },
      { field_id: "quantity", decision: "corrected", corrected_value: invalid }])).status, 400, invalid);
  }
  fs.writeFileSync(sourcePath, "changed source bytes");
  const changedOnApproval = await post(0, [{ field_id: "item_name", decision: "correct" }]);
  assert.equal(changedOnApproval.status, 409);
  assert.match((await changedOnApproval.json()).error, /original source changed/);
  const changedOnCorrection = await post(0, [{ field_id: "quantity", decision: "corrected",
    corrected_value: JSON.stringify([{ row: 0, value: "3" }, { row: 1, value: "4" }]) }]);
  assert.equal(changedOnCorrection.status, 409);
  fs.writeFileSync(sourcePath, "Widget 3\nGadget 4");
  const corrected = await post(0, [{ field_id: "item_name", decision: "correct" },
    { field_id: "quantity", decision: "corrected", corrected_value: JSON.stringify([
      { row: 1, value: "4" }, { row: 0, value: "3" },
    ]) }]);
  assert.equal(corrected.status, 200);
  const body = await corrected.json();
  assert.equal(body.review.status, "completed");
  assert.equal(body.correctedResult.fields[0].provenance, "human_verified");
  assert.deepEqual(body.correctedResult.fields[1].value, [{ row: 0, value: "3" }, { row: 1, value: "4" }]);
  assert.equal(body.correctedResult.fields[1].provenance, "human_correction");
  assert.equal(body.review.fields[1].corrected_value, '[{"row":0,"value":"3"},{"row":1,"value":"4"}]');
  assert.equal(body.review.source_container_sha256, sha256);
  assert.equal(body.review.source_pages_sha256, createHash("sha256")
    .update(JSON.stringify([{ page: 1, text: "Widget 3\nGadget 4" }])).digest("hex"));
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), params)).status, 200);
  const audited = await (await getAutoDocRoute(request(docUrl, "alice"), params)).json();
  assert.equal(audited.auditTrail.length, 1);
  assert.equal(audited.auditTrail[0].machine_fields[1].value[1].status, "needs_review");
  assert.equal(audited.auditTrail[0].source_container_sha256, sha256);
  assert.equal(audited.auditTrail[0].source_pages_sha256, body.review.source_pages_sha256);

  const reviewedCandidateBytes = fs.readFileSync(sidecarPath);
  fs.writeFileSync(sidecarPath, "{malformed-json");
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), params)).status, 409);
  assert.equal((await post(1, [{ field_id: "item_name", decision: "correct" }])).status, 409);
  const malformedList = await listAutoRoute(request(`/api/jobs/${job.jobId}/auto`, "alice"),
    { params: Promise.resolve({ jobId: job.jobId }) });
  assert.equal((await malformedList.json()).runs[0].documents[0].reviewStatus, "pending");
  fs.writeFileSync(sidecarPath, reviewedCandidateBytes);

  const terminalPath = path.join(metadataDir, `${runId}.terminal.json`);
  const originalTerminalBytes = fs.readFileSync(terminalPath);
  const unrelatedAuditDir = path.join(dataDir, "frontend", "auto_reviews", job.jobId, runId, "events", "other");
  const twoDocumentRecord = JSON.parse(originalTerminalBytes.toString("utf8"));
  twoDocumentRecord.documents.push({ docId: "other", fileId: "other", fileName: "other.txt", status: "needs_review",
    fieldCount: 0, acceptedCount: 0, reviewStatus: "unreviewed", machineResultSha256: "0".repeat(64) });
  fs.writeFileSync(terminalPath, JSON.stringify(twoDocumentRecord));
  fs.mkdirSync(unrelatedAuditDir, { recursive: true });
  fs.writeFileSync(path.join(unrelatedAuditDir, "000000000001.json"), "{malformed-json");
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), params)).status, 200);
  assert.equal((await post(0, [{ field_id: "item_name", decision: "correct" }])).status, 409);
  fs.writeFileSync(terminalPath, originalTerminalBytes);

  const approvedCell = (candidate.extracted_values[0].value as Array<{
    value: string; evidence: { page: number; start: number; end: number; quote: string };
  }>)[0];
  approvedCell.value = "Gadget";
  approvedCell.evidence = { page: 1, start: 9, end: 15, quote: "Gadget" };
  writeSidecar();
  const manifestPath = path.join(dataDir, "product_runs", runId, "manifest.jsonl");
  const originalManifestBytes = fs.readFileSync(manifestPath);
  const replacedManifest = JSON.parse(originalManifestBytes.toString("utf8"));
  replacedManifest.result_sha256 = createHash("sha256").update(fs.readFileSync(sidecarPath)).digest("hex");
  fs.writeFileSync(manifestPath, JSON.stringify(replacedManifest) + "\n");
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), params)).status, 409);
  assert.equal((await post(1, [{ field_id: "item_name", decision: "correct" }])).status, 409);
  const tamperedList = await listAutoRoute(request(`/api/jobs/${job.jobId}/auto`, "alice"),
    { params: Promise.resolve({ jobId: job.jobId }) });
  assert.equal((await tamperedList.json()).runs[0].documents[0].reviewStatus, "pending");
  fs.writeFileSync(manifestPath, originalManifestBytes);
  approvedCell.value = "Widget";
  approvedCell.evidence = { page: 1, start: 0, end: 6, quote: "Widget" };
  fs.writeFileSync(sidecarPath, reviewedCandidateBytes);

  fs.writeFileSync(sourcePath, "changed source bytes");
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), params)).status, 409);
  const changedSourceList = await listAutoRoute(request(`/api/jobs/${job.jobId}/auto`, "alice"),
    { params: Promise.resolve({ jobId: job.jobId }) });
  assert.equal((await changedSourceList.json()).runs[0].documents[0].reviewStatus, "pending");
  fs.writeFileSync(sourcePath, "Widget 3\nGadget 4");
  const originalSidecar = fs.readFileSync(sidecarPath);
  const changedPages = JSON.parse(originalSidecar.toString("utf8"));
  changedPages.pages[0].text += "\nUnreviewed text";
  fs.writeFileSync(sidecarPath, JSON.stringify(changedPages));
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), params)).status, 409);
  fs.writeFileSync(sidecarPath, originalSidecar);
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), params)).status, 200);
  const removed = await post(1, [{ field_id: "item_name", decision: "remove" },
    { field_id: "quantity", decision: "remove" }]);
  assert.equal(removed.status, 200);
  const removedReview = (await removed.json()).review;
  assert.equal(removedReview.source_container_sha256, sha256);
  assert.equal(removedReview.source_pages_sha256, body.review.source_pages_sha256);
  fs.writeFileSync(sourcePath, "changed source bytes");
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), params)).status, 409);
  fs.writeFileSync(sourcePath, "Widget 3\nGadget 4");
  const secondEventPath = path.join(dataDir, "frontend", "auto_reviews", job.jobId,
    runId, "events", docId, "000000000002.json");
  const firstEventPath = path.join(dataDir, "frontend", "auto_reviews", job.jobId,
    runId, "events", docId, "000000000001.json");
  const originalFirstEventBytes = fs.readFileSync(firstEventPath);
  const originalSecondEventBytes = fs.readFileSync(secondEventPath);
  for (const eventPath of [firstEventPath, secondEventPath]) {
    const unsealed = JSON.parse(fs.readFileSync(eventPath, "utf8"));
    delete unsealed.machine_result_sha256;
    delete unsealed.review_snapshot.machine_result_sha256;
    fs.writeFileSync(eventPath, JSON.stringify(unsealed));
  }
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), params)).status, 409);
  fs.writeFileSync(firstEventPath, originalFirstEventBytes);
  fs.writeFileSync(secondEventPath, originalSecondEventBytes);
  const legacySecondEvent = JSON.parse(fs.readFileSync(secondEventPath, "utf8"));
  delete legacySecondEvent.source_container_sha256;
  delete legacySecondEvent.source_pages_sha256;
  delete legacySecondEvent.machine_result_sha256;
  delete legacySecondEvent.review_snapshot.source_container_sha256;
  delete legacySecondEvent.review_snapshot.source_pages_sha256;
  delete legacySecondEvent.review_snapshot.machine_result_sha256;
  fs.writeFileSync(secondEventPath, JSON.stringify(legacySecondEvent));
  fs.writeFileSync(sourcePath, "changed source bytes");
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), params)).status, 409);
  fs.writeFileSync(sourcePath, "Widget 3\nGadget 4");
  const carriedFromHistory = await post(2, [{ field_id: "item_name", decision: "remove" },
    { field_id: "quantity", decision: "remove" }]);
  assert.equal(carriedFromHistory.status, 200);
  assert.equal((await carriedFromHistory.json()).review.source_container_sha256, sha256);

  const nameCells = candidate.extracted_values[0].value as Array<{ evidence: { quote: string }; value: string }>;
  nameCells[0].evidence.quote = "Tampered";
  writeSidecar();
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), params)).status, 409);
  nameCells[0].evidence.quote = "Widget";
  nameCells[0].value = "Invented";
  writeSidecar();
  assert.equal((await getAutoDocRoute(request(docUrl, "alice"), params)).status, 409);
}));

test("legacy linked-row approval stays pending when a cell is unverified", () => {
  const candidate: ProductAutoCandidate = { contract_version: 1, doc_id: "rows", document_status: "needs_review",
    proposed_schema: [{ field_id: "items", type: "array[object]" }],
    extracted_values: [{ field_id: "items", status: "needs_review", review_state: "pending",
      value: [{ row: 0, value: "A", status: "needs_review" }] }] };
  const review: ProductAutoReview = { review_version: 1, job_id: "job", run_id: "run", doc_id: "rows",
    status: "completed", reviewer_user_id: "reviewer", updated_at: "2026-01-01T00:00:00Z",
    fields: [{ field_id: "items", decision: "correct" }], revision: 1, audit_event_id: "event" };
  const derived = deriveProductAutoCorrectedResult(candidate, review);
  assert.equal(derived.review_status, "pending");
  assert.equal(derived.fields[0].status, "needs_review");
});

test("machine schema artifacts enforce normalized IDs, types, field limits, and bounded groups", async () => withStorage(async (dataDir) => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const updated = await addDocumentsToJob(job.jobId, [new File(["😀 Café"], "source.txt")]);
  const source = updated.documents![0];
  const sha256 = createHash("sha256").update(fs.readFileSync(path.join(updated.uploadsPath!, source.storedName))).digest("hex");
  const runId = `auto_${"c".repeat(32)}`;
  const docId = "schema1";
  const output = path.join(dataDir, "product_runs", runId);
  const sidecarDir = path.join(output, "docs", docId);
  fs.mkdirSync(sidecarDir, { recursive: true });
  fs.writeFileSync(path.join(output, "run.json"), JSON.stringify({ contract_version: 1, run_id: runId, doc_count: 1 }));
  fs.writeFileSync(path.join(output, "manifest.jsonl"), JSON.stringify({
    contract_version: 1, run_id: runId, doc_id: docId, source_file: source.storedName,
    source_container_sha256: sha256, document_status: "needs_review",
  }) + "\n");
  const metadataDir = path.join(dataDir, "frontend", "auto_runs", job.jobId);
  fs.mkdirSync(metadataDir, { recursive: true });
  fs.writeFileSync(path.join(metadataDir, `${runId}.json`), JSON.stringify({
    runId, jobId: job.jobId, status: "running", createdAt: new Date().toISOString(),
    serverInstanceId: "previous-server", selectedFiles: [{ fileId: source.fileId,
      fileName: source.fileName, storedName: source.storedName, sha256 }], documents: [],
  }));
  const docUrl = `/api/jobs/${job.jobId}/auto/${runId}/docs/${docId}`;
  const params = { params: Promise.resolve({ jobId: job.jobId, runId, docId }) };
  const readSchema = async (schema: Array<Record<string, unknown>>) => {
    const schemaArtifactPath = path.join(sidecarDir, "result.json");
    fs.writeFileSync(schemaArtifactPath, JSON.stringify({
      pages: [{ page: 1, text: "😀 Café" }],
      candidate: { contract_version: 1, doc_id: docId, document_status: "needs_review",
        proposed_schema: schema, extracted_values: schema.map((field) => ({
          field_id: field.field_id, value: null, status: "missing", review_state: "pending",
        })) },
    }));
    const schemaManifestPath = path.join(output, "manifest.jsonl");
    const schemaReceipt = JSON.parse(fs.readFileSync(schemaManifestPath, "utf8"));
    schemaReceipt.result_sha256 = createHash("sha256").update(fs.readFileSync(schemaArtifactPath)).digest("hex");
    fs.writeFileSync(schemaManifestPath, JSON.stringify(schemaReceipt) + "\n");
    return getAutoDocRoute(request(docUrl, "alice"), params);
  };

  assert.equal((await readSchema([{ field_id: "café", type: "string", group: "header" },
    { field_id: "line_item", type: "array[object]", group: "line items" }])).status, 200);
  assert.equal((await readSchema([{ field_id: "line_item", type: "array[object]" }])).status, 200);
  assert.equal((await readSchema(Array.from({ length: 24 }, (_, index) => ({
    field_id: `field_${index}`, type: "integer",
  })))).status, 200);
  const invalidSchemas: Array<Array<Record<string, unknown>>> = [
    [{ field_id: "Total", type: "string" }],
    [{ field_id: "line-item", type: "string" }],
    [{ field_id: "field_", type: "string" }],
    [{ field_id: "x".repeat(65), type: "string" }],
    [{ field_id: "total", type: "array[string]" }],
    [{ field_id: "total", type: "object" }],
    [{ field_id: "line_item", type: "array[object]", group: "" }],
    [{ field_id: "line_item", type: "array[object]", group: " items" }],
    [{ field_id: "line_item", type: "array[object]", group: "x".repeat(65) }],
    [{ field_id: "line_item", type: "array[object]", group: { name: "items" } }],
    Array.from({ length: 25 }, (_, index) => ({ field_id: `field_${index}`, type: "string" })),
  ];
  for (const schema of invalidSchemas) {
    assert.equal((await readSchema(schema)).status, 500, JSON.stringify(schema));
  }
  assert.equal((await readSchema([])).status, 200);
  const humanAdded = await reviewAutoDocRoute(request(docUrl, "alice", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: 0, fields: [],
      added_fields: [{ field_id: "vendor_name", type: "string", value: "Café",
        evidence: { page: 1, quote: "Café" } }] }) }), params);
  assert.equal(humanAdded.status, 200);
  assert.deepEqual((await humanAdded.json()).correctedResult.fields[0].evidence,
    { page: 1, start: 2, end: 6, quote: "Café" });
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

test("invalid server model budgets reject admission before any extraction run", async () => withStorage(async () => {
  const oldTokens = process.env.IDPO_AUTO_MAX_OUTPUT_TOKENS;
  const oldTimeout = process.env.IDPO_AUTO_TIMEOUT_S;
  try {
    process.env.IDPO_AUTO_MODEL = "local-open-model";
    process.env.IDPO_AUTO_API_BASE_URL = "http://127.0.0.1:1/v1";
    const job = createWorkspaceJob({ ownerUserId: "admin-id" });
    const uploaded = await addDocumentsToJob(job.jobId, [new File(["Total: 100"], "invoice.txt")]);
    const url = `/api/jobs/${job.jobId}/auto`;
    for (const [tokens, timeout] of [["0", ""], ["16385", ""], ["1.5", ""],
      ["", "0"], ["", "601"], ["", "1e2"]]) {
      process.env.IDPO_AUTO_MAX_OUTPUT_TOKENS = tokens;
      process.env.IDPO_AUTO_TIMEOUT_S = timeout;
      const response = await startAutoRoute(request(url, "admin", { method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": "f".repeat(32) },
        body: JSON.stringify({ selectedFileIds: [uploaded.documents![0].fileId] }),
      }), { params: Promise.resolve({ jobId: job.jobId }) });
      assert.equal(response.status, 503, `${tokens}/${timeout}`);
    }
    process.env.IDPO_AUTO_MAX_OUTPUT_TOKENS = "";
    process.env.IDPO_AUTO_TIMEOUT_S = "";
    const browserOverride = await startAutoRoute(request(url, "admin", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selectedFileIds: [uploaded.documents![0].fileId], maxOutputTokens: 1 }),
    }), { params: Promise.resolve({ jobId: job.jobId }) });
    assert.equal(browserOverride.status, 400);
    const runsDir = path.join(process.env.IDPO_DATA_DIR!, "frontend", "auto_runs", job.jobId);
    assert.equal(fs.existsSync(runsDir), false);
  } finally {
    if (oldTokens === undefined) delete process.env.IDPO_AUTO_MAX_OUTPUT_TOKENS;
    else process.env.IDPO_AUTO_MAX_OUTPUT_TOKENS = oldTokens;
    if (oldTimeout === undefined) delete process.env.IDPO_AUTO_TIMEOUT_S;
    else process.env.IDPO_AUTO_TIMEOUT_S = oldTimeout;
  }
}));

test("direct product execution forwards the server model budget to its child", async () => withStorage(async (dataDir) => {
  const oldMode = process.env.PRODUCT_EXECUTION_MODE;
  const oldTokens = process.env.IDPO_AUTO_MAX_OUTPUT_TOKENS;
  const oldTimeout = process.env.IDPO_AUTO_TIMEOUT_S;
  try {
    process.env.PRODUCT_EXECUTION_MODE = "direct";
    process.env.IDPO_AUTO_MODEL = "local-open-model";
    process.env.IDPO_AUTO_API_BASE_URL = "http://127.0.0.1:1/v1";
    process.env.IDPO_AUTO_MAX_OUTPUT_TOKENS = "3072";
    process.env.IDPO_AUTO_TIMEOUT_S = "75";
    const command = loadRunnerConfig().commands.find((item) => item.id === "idpo_process_auto")!;
    const capturePath = path.join(path.dirname(dataDir), "direct-args.json");
    const workerPath = path.join(path.dirname(dataDir), "capture-direct.cjs");
    fs.writeFileSync(workerPath, "require('node:fs').writeFileSync(process.env.CAPTURE_PATH, JSON.stringify(process.argv.slice(2))); process.exit(1);");
    command.program = process.execPath;
    command.args = [workerPath, "--input", "{input_dir}", "--run-id", "{run_id}"];
    command.cwd = path.dirname(dataDir);
    command.env = { CAPTURE_PATH: capturePath };
    const job = createWorkspaceJob({ ownerUserId: "admin-id" });
    const uploaded = await addDocumentsToJob(job.jobId, [new File(["Total: 100"], "invoice.txt")]);
    const run = await startProductAutoRun(job.jobId, [uploaded.documents![0].fileId], true);
    const deadline = Date.now() + 5000;
    while (!fs.existsSync(capturePath) && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
    assert.equal(fs.existsSync(capturePath), true);
    const args = JSON.parse(fs.readFileSync(capturePath, "utf8")) as string[];
    assert.deepEqual(args.slice(args.indexOf("--max-tokens"), args.indexOf("--max-tokens") + 4),
      ["--max-tokens", "3072", "--timeout-s", "75"]);
    while (getProductAutoRun(job.jobId, run.runId).status !== "failed" && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
    assert.equal(getProductAutoRun(job.jobId, run.runId).status, "failed");
  } finally {
    if (oldMode === undefined) delete process.env.PRODUCT_EXECUTION_MODE;
    else process.env.PRODUCT_EXECUTION_MODE = oldMode;
    if (oldTokens === undefined) delete process.env.IDPO_AUTO_MAX_OUTPUT_TOKENS;
    else process.env.IDPO_AUTO_MAX_OUTPUT_TOKENS = oldTokens;
    if (oldTimeout === undefined) delete process.env.IDPO_AUTO_TIMEOUT_S;
    else process.env.IDPO_AUTO_TIMEOUT_S = oldTimeout;
  }
}));

test("a paid run key returns its failed admission once and rejects changed payload, source, and owner", async () => withStorage(async (dataDir) => {
  const oldMode = process.env.PRODUCT_EXECUTION_MODE;
  const oldQueueUrl = process.env.PRODUCT_QUEUE_DATABASE_URL;
  const holder = globalThis as typeof globalThis & { __productQueue?: ProductExecutionQueue };
  const oldQueue = holder.__productQueue;
  try {
    process.env.PRODUCT_EXECUTION_MODE = "postgres";
    process.env.PRODUCT_QUEUE_DATABASE_URL = "postgresql://unused.example/unused";
    process.env.IDPO_AUTO_MODEL = "local-test-model";
    process.env.IDPO_AUTO_API_BASE_URL = "http://127.0.0.1:1/v1";
    let admissions = 0;
    holder.__productQueue = { enqueue: async () => {
      admissions += 1;
      throw new QueueAdmissionError("Synthetic queue admission failure.", 409);
    } } as unknown as ProductExecutionQueue;
    const job = createWorkspaceJob({ ownerUserId: "admin-id" });
    const uploaded = await addDocumentsToJob(job.jobId, [
      new File(["Invoice total 100"], "first.txt"), new File(["Invoice total 200"], "second.txt"),
    ]);
    const first = uploaded.documents![0];
    const second = uploaded.documents![1];
    const key = "a".repeat(32);
    const pathName = `/api/jobs/${job.jobId}/auto`;
    const params = { params: Promise.resolve({ jobId: job.jobId }) };
    const unkeyed = await startAutoRoute(request(pathName, "admin", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selectedFileIds: [first.fileId] }),
    }), params);
    assert.equal(unkeyed.status, 400);
    assert.equal(admissions, 0);
    const start = (token: string, fileIds: string[]) => startAutoRoute(request(pathName, token, {
      method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify({ selectedFileIds: fileIds }),
    }), params);
    const failedAdmission = await start("admin", [first.fileId]);
    assert.equal(failedAdmission.status, 409);
    const runId = fs.readdirSync(path.join(dataDir, "frontend", "auto_runs", job.jobId))
      .find((name) => /^auto_[a-f0-9]{32}\.json$/.test(name))?.replace(/\.json$/, "");
    assert.ok(runId);
    assert.match(runId, /^auto_[a-f0-9]{32}$/);
    assert.equal(getProductAutoRun(job.jobId, runId).status, "failed");
    const replay = await start("admin", [first.fileId]);
    assert.equal(replay.status, 202);
    assert.deepEqual(await replay.json(), getProductAutoRun(job.jobId, runId));
    assert.equal(admissions, 1);
    assert.equal((await start("admin", [second.fileId])).status, 409);
    assert.equal((await start("bob", [first.fileId])).status, 404);
    fs.writeFileSync(path.join(uploaded.uploadsPath!, first.storedName), "Changed source bytes");
    assert.equal((await start("admin", [first.fileId])).status, 409);
    assert.equal(admissions, 1);
  } finally {
    if (oldMode === undefined) delete process.env.PRODUCT_EXECUTION_MODE;
    else process.env.PRODUCT_EXECUTION_MODE = oldMode;
    if (oldQueueUrl === undefined) delete process.env.PRODUCT_QUEUE_DATABASE_URL;
    else process.env.PRODUCT_QUEUE_DATABASE_URL = oldQueueUrl;
    holder.__productQueue = oldQueue;
  }
}));

test("concurrent exact paid run requests claim one attempt and preserve the key after completion", async () => withStorage(async () => {
  const oldMode = process.env.PRODUCT_EXECUTION_MODE;
  const oldQueueUrl = process.env.PRODUCT_QUEUE_DATABASE_URL;
  const holder = globalThis as typeof globalThis & { __productQueue?: ProductExecutionQueue };
  const oldQueue = holder.__productQueue;
  try {
    process.env.PRODUCT_EXECUTION_MODE = "postgres";
    process.env.PRODUCT_QUEUE_DATABASE_URL = "postgresql://unused.example/unused";
    process.env.IDPO_AUTO_MODEL = "local-test-model";
    process.env.IDPO_AUTO_API_BASE_URL = "http://127.0.0.1:1/v1";
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    let admissions = 0;
    const queueStub = { enqueue: async () => { admissions += 1; await gate; return "synthetic-broker-id"; } };
    holder.__productQueue = queueStub as unknown as ProductExecutionQueue;
    const job = createWorkspaceJob({ ownerUserId: "admin-id" });
    const uploaded = await addDocumentsToJob(job.jobId, [new File(["Invoice total 100"], "invoice.txt")]);
    const key = "b".repeat(32);
    const params = { params: Promise.resolve({ jobId: job.jobId }) };
    const start = () => startAutoRoute(request(`/api/jobs/${job.jobId}/auto`, "admin", {
      method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify({ selectedFileIds: [uploaded.documents![0].fileId] }),
    }), params);
    const first = start();
    const deadline = Date.now() + 3000;
    while (admissions === 0 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(admissions, 1);
    const second = await start();
    assert.equal(second.status, 202);
    const secondRun = await second.json();
    assert.match(secondRun.runId, /^auto_[a-f0-9]{32}$/);
    assert.equal(secondRun.idempotencyKey, key);
    release();
    const admitted = await first;
    assert.equal(admitted.status, 202);
    assert.equal((await admitted.json()).runId, secondRun.runId);
    const recordPath = path.join(process.env.IDPO_DATA_DIR!, "frontend", "auto_runs", job.jobId, `${secondRun.runId}.json`);
    const terminalPath = recordPath.replace(/\.json$/, ".terminal.json");
    const record = JSON.parse(fs.readFileSync(recordPath, "utf8"));
    fs.writeFileSync(terminalPath, JSON.stringify({ ...record, status: "success", documents: [],
      endedAt: "2026-10-13T00:00:00Z" }));
    const terminalReplay = await start();
    assert.equal(terminalReplay.status, 202);
    assert.equal((await terminalReplay.json()).status, "success");
    assert.equal(admissions, 1);
  } finally {
    if (oldMode === undefined) delete process.env.PRODUCT_EXECUTION_MODE;
    else process.env.PRODUCT_EXECUTION_MODE = oldMode;
    if (oldQueueUrl === undefined) delete process.env.PRODUCT_QUEUE_DATABASE_URL;
    else process.env.PRODUCT_QUEUE_DATABASE_URL = oldQueueUrl;
    holder.__productQueue = oldQueue;
  }
}));

test("an interrupted paid admission keeps its claim and cannot enqueue on replay", async () => withStorage(async (dataDir) => {
  const oldMode = process.env.PRODUCT_EXECUTION_MODE;
  const oldQueueUrl = process.env.PRODUCT_QUEUE_DATABASE_URL;
  const holder = globalThis as typeof globalThis & { __productQueue?: ProductExecutionQueue };
  const oldQueue = holder.__productQueue;
  try {
    process.env.PRODUCT_EXECUTION_MODE = "postgres";
    process.env.PRODUCT_QUEUE_DATABASE_URL = "postgresql://unused.example/unused";
    process.env.IDPO_AUTO_MODEL = "local-test-model";
    process.env.IDPO_AUTO_API_BASE_URL = "http://127.0.0.1:1/v1";
    let admissions = 0;
    holder.__productQueue = { enqueue: async () => { admissions += 1; return "broker"; } } as unknown as ProductExecutionQueue;
    const job = createWorkspaceJob({ ownerUserId: "admin-id" });
    const uploaded = await addDocumentsToJob(job.jobId, [new File(["Will disappear"], "source.txt")]);
    fs.unlinkSync(path.join(uploaded.uploadsPath!, uploaded.documents![0].storedName));
    const key = "e".repeat(32);
    const start = () => startAutoRoute(request(`/api/jobs/${job.jobId}/auto`, "admin", {
      method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify({ selectedFileIds: [uploaded.documents![0].fileId] }),
    }), { params: Promise.resolve({ jobId: job.jobId }) });
    assert.equal((await start()).status, 400);
    assert.equal(fs.readdirSync(path.join(dataDir, "frontend", "auto_run_requests", job.jobId)).length, 1);
    assert.equal((await start()).status, 409);
    assert.equal(admissions, 0);
  } finally {
    if (oldMode === undefined) delete process.env.PRODUCT_EXECUTION_MODE;
    else process.env.PRODUCT_EXECUTION_MODE = oldMode;
    if (oldQueueUrl === undefined) delete process.env.PRODUCT_QUEUE_DATABASE_URL;
    else process.env.PRODUCT_QUEUE_DATABASE_URL = oldQueueUrl;
    holder.__productQueue = oldQueue;
  }
}));

test("the same paid request key on different jobs has separate global staging and run identities", async () => withStorage(async (dataDir) => {
  const oldMode = process.env.PRODUCT_EXECUTION_MODE;
  const oldQueueUrl = process.env.PRODUCT_QUEUE_DATABASE_URL;
  const holder = globalThis as typeof globalThis & { __productQueue?: ProductExecutionQueue };
  const oldQueue = holder.__productQueue;
  try {
    process.env.PRODUCT_EXECUTION_MODE = "postgres";
    process.env.PRODUCT_QUEUE_DATABASE_URL = "postgresql://unused.example/unused";
    process.env.IDPO_AUTO_MODEL = "local-test-model";
    process.env.IDPO_AUTO_API_BASE_URL = "http://127.0.0.1:1/v1";
    let admissions = 0;
    holder.__productQueue = { enqueue: async () => { admissions += 1; return `broker-${admissions}`; } } as unknown as ProductExecutionQueue;
    const jobA = createWorkspaceJob({ ownerUserId: "admin-id" });
    const jobB = createWorkspaceJob({ ownerUserId: "admin-id" });
    const uploadedA = await addDocumentsToJob(jobA.jobId, [new File(["Job A distinct bytes"], "source.txt")]);
    const uploadedB = await addDocumentsToJob(jobB.jobId, [new File(["Job B distinct bytes"], "source.txt")]);
    const key = "d".repeat(32);
    const start = (jobId: string, fileId: string) => startAutoRoute(request(`/api/jobs/${jobId}/auto`, "admin", {
      method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify({ selectedFileIds: [fileId] }),
    }), { params: Promise.resolve({ jobId }) });
    const [responseA, responseB] = await Promise.all([
      start(jobA.jobId, uploadedA.documents![0].fileId),
      start(jobB.jobId, uploadedB.documents![0].fileId),
    ]);
    assert.equal(responseA.status, 202);
    assert.equal(responseB.status, 202);
    const runA = await responseA.json();
    const runB = await responseB.json();
    assert.notEqual(runA.runId, runB.runId);
    assert.equal(runA.idempotencyKey, key);
    assert.equal(runB.idempotencyKey, key);
    assert.equal(admissions, 2);
    assert.equal(fs.readFileSync(path.join(dataDir, "frontend", "auto_inputs", runA.runId,
      uploadedA.documents![0].storedName), "utf8"), "Job A distinct bytes");
    assert.equal(fs.readFileSync(path.join(dataDir, "frontend", "auto_inputs", runB.runId,
      uploadedB.documents![0].storedName), "utf8"), "Job B distinct bytes");
    assert.equal((await (await start(jobA.jobId, uploadedA.documents![0].fileId)).json()).runId, runA.runId);
    assert.equal((await (await start(jobB.jobId, uploadedB.documents![0].fileId)).json()).runId, runB.runId);
    assert.equal(admissions, 2);
  } finally {
    if (oldMode === undefined) delete process.env.PRODUCT_EXECUTION_MODE;
    else process.env.PRODUCT_EXECUTION_MODE = oldMode;
    if (oldQueueUrl === undefined) delete process.env.PRODUCT_QUEUE_DATABASE_URL;
    else process.env.PRODUCT_QUEUE_DATABASE_URL = oldQueueUrl;
    holder.__productQueue = oldQueue;
  }
}));

test("a paid run key refuses replay after the confirmed brief revision changes", async () => withStorage(async () => {
  const oldMode = process.env.PRODUCT_EXECUTION_MODE;
  const oldQueueUrl = process.env.PRODUCT_QUEUE_DATABASE_URL;
  const holder = globalThis as typeof globalThis & { __productQueue?: ProductExecutionQueue };
  const oldQueue = holder.__productQueue;
  try {
    process.env.PRODUCT_EXECUTION_MODE = "postgres";
    process.env.PRODUCT_QUEUE_DATABASE_URL = "postgresql://unused.example/unused";
    process.env.IDPO_AUTO_MODEL = "local-test-model";
    process.env.IDPO_AUTO_API_BASE_URL = "http://127.0.0.1:1/v1";
    let admissions = 0;
    const queueStub = { enqueue: async () => { admissions += 1; return "synthetic-broker-id"; } };
    holder.__productQueue = queueStub as unknown as ProductExecutionQueue;
    const job = createWorkspaceJob({ ownerUserId: "admin-id" });
    const uploaded = await addDocumentsToJob(job.jobId, [new File(["Invoice total 100"], "invoice.txt")]);
    const fileId = uploaded.documents![0].fileId;
    const params = { params: Promise.resolve({ jobId: job.jobId }) };
    const fields = [{ field_id: "total", type: "string", description: "Printed invoice total", example_values: ["100"] }];
    const save = (expectedRevision: number, description: string) => saveBriefRoute(request(
      `/api/jobs/${job.jobId}/auto/brief`, "admin", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expectedRevision, intent: "Extract the printed total", fields: fields.map((field) =>
          ({ ...field, description })), sampleFileIds: [fileId] }), }), params);
    const draft = (await (await save(0, "Printed invoice total")).json()).brief;
    const confirmed = (await (await confirmBriefRoute(request(`/api/jobs/${job.jobId}/auto/brief`, "admin", {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expectedRevision: draft.revision, expectedPayloadSha256: draft.payload_sha256 }),
    }), params)).json()).brief;
    const key = "c".repeat(32);
    const start = () => startAutoRoute(request(`/api/jobs/${job.jobId}/auto`, "admin", {
      method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify({ selectedFileIds: [fileId], confirmedBrief: {
        expectedRevision: confirmed.revision, payloadSha256: confirmed.payload_sha256, phase: "preview",
      } }),
    }), params);
    assert.equal((await start()).status, 202);
    assert.equal(admissions, 1);
    assert.equal((await save(confirmed.revision, "Revised printed invoice total")).status, 201);
    assert.equal((await start()).status, 409);
    assert.equal(admissions, 1);
  } finally {
    if (oldMode === undefined) delete process.env.PRODUCT_EXECUTION_MODE;
    else process.env.PRODUCT_EXECUTION_MODE = oldMode;
    if (oldQueueUrl === undefined) delete process.env.PRODUCT_QUEUE_DATABASE_URL;
    else process.env.PRODUCT_QUEUE_DATABASE_URL = oldQueueUrl;
    holder.__productQueue = oldQueue;
  }
}));

test("only exact loopback HTTP model endpoints can run without a server API key", async () => withStorage(async () => {
  process.env.IDPO_AUTO_MODEL = "local-open-model";
  delete process.env.ICORE_API_KEY;
  for (const baseUrl of ["http://localhost:8000/v1", "http://127.0.0.1:8000/v1", "http://[::1]:8000/v1"]) {
    process.env.IDPO_AUTO_API_BASE_URL = baseUrl;
    assert.equal(productAutoAvailability().modelConfigured, true, baseUrl);
  }
  for (const baseUrl of ["https://model.example/v1", "http://localhost.evil.example/v1", "http://192.168.1.4:8000/v1"]) {
    process.env.IDPO_AUTO_API_BASE_URL = baseUrl;
    assert.equal(productAutoAvailability().modelConfigured, false, baseUrl);
  }
  process.env.IDPO_AUTO_API_BASE_URL = "https://model.example/v1";
  process.env.ICORE_API_KEY = "test-key";
  assert.equal(productAutoAvailability().modelConfigured, true);
  process.env.IDPO_AUTO_API_BASE_URL = "http://localhost:8000/v1";
  delete process.env.ICORE_API_KEY;
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const updated = await addDocumentsToJob(job.jobId, [new File(["Local model"], "source.txt")]);
  const response = await startAutoRoute(request(`/api/jobs/${job.jobId}/auto`, "alice", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selectedFileIds: [updated.documents![0].fileId] }),
  }), { params: Promise.resolve({ jobId: job.jobId }) });
  assert.equal(response.status, 403);
}));

test("review client submits only an explicit self-reported active duration", async () => {
  assert.equal(parseReportedActiveMinutes(""), undefined);
  assert.equal(parseReportedActiveMinutes("2.5"), 150);
  for (const invalid of ["0", "0.01", "241", "n/a", "Infinity"]) {
    assert.throws(() => parseReportedActiveMinutes(invalid));
  }
  const originalFetch = globalThis.fetch;
  const bodies: Array<Record<string, unknown>> = [];
  globalThis.fetch = async (_input, init) => {
    bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
    return Response.json({ review: {}, correctedResult: {} });
  };
  try {
    await idpoApi.saveProductAutoReview("job", "run", "doc", 0, [], [], "2.5");
    await idpoApi.saveProductAutoReview("job", "run", "doc", 1, [], [], "");
    assert.equal(bodies[0].reported_active_review_seconds, 150);
    assert.equal(Object.hasOwn(bodies[1], "reported_active_review_seconds"), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
