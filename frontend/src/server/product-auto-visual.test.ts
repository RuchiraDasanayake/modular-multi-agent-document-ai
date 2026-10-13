import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { GET as getDocument, POST as saveReview } from "@/app/api/jobs/[jobId]/auto/[runId]/docs/[docId]/route";
import { GET as getExport } from "@/app/api/jobs/[jobId]/auto/[runId]/docs/[docId]/export/route";
import { resetConfigCacheForTests } from "./config";
import { addDocumentsToJob, createWorkspaceJob } from "./jobs";
import { createProductAutoRecipeDraft } from "./product-auto-recipes";
import type { ProductAutoCandidate } from "@/types/product-auto";

type FixtureVariant = { candidate: ProductAutoCandidate; pages: Array<{ page: number; text: string }>;
  visual_receipt: Record<string, unknown> };
type VisualFixture = { source_name: string; source_base64: string; source_sha256: string;
  variants: Record<string, FixtureVariant> };
const fixture = JSON.parse(fs.readFileSync(path.join(process.cwd(), "src", "server", "fixtures",
  "visual-review-workflow.json"), "utf8")) as VisualFixture;

function sha(bytes: Buffer): string { return createHash("sha256").update(bytes).digest("hex"); }

async function withStorage(run: (dataDir: string) => Promise<void>): Promise<void> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "docai-visual-review-"));
  const oldData = process.env.IDPO_DATA_DIR;
  const oldGateway = process.env.INTERNAL_API_URL;
  const oldFetch = globalThis.fetch;
  process.env.IDPO_DATA_DIR = path.join(root, "data");
  process.env.INTERNAL_API_URL = "http://test-gateway.local";
  resetConfigCacheForTests();
  globalThis.fetch = async (input, init) => {
    if (String(input) === "http://test-gateway.local/api/auth/me") {
      const token = new Headers(init?.headers).get("authorization");
      return token === "Bearer alice" ? Response.json({ id: "alice-id", role: "viewer" })
        : token === "Bearer bob" ? Response.json({ id: "bob-id", role: "viewer" })
          : Response.json({}, { status: 401 });
    }
    return oldFetch(input, init);
  };
  try { await run(process.env.IDPO_DATA_DIR); } finally {
    globalThis.fetch = oldFetch;
    if (oldData === undefined) delete process.env.IDPO_DATA_DIR;
    else process.env.IDPO_DATA_DIR = oldData;
    if (oldGateway === undefined) delete process.env.INTERNAL_API_URL;
    else process.env.INTERNAL_API_URL = oldGateway;
    resetConfigCacheForTests();
    fs.rmSync(root, { recursive: true, force: true });
  }
}

function request(pathname: string, token: "alice" | "bob", init?: RequestInit): Request {
  return new Request(`http://localhost${pathname}`, { ...init,
    headers: { ...Object.fromEntries(new Headers(init?.headers)), authorization: `Bearer ${token}` } });
}

async function setup(dataDir: string, variantName: string) {
  const variant = fixture.variants[variantName]!;
  const sourceBytes = Buffer.from(fixture.source_base64, "base64");
  assert.equal(sha(sourceBytes), fixture.source_sha256);
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const uploaded = await addDocumentsToJob(job.jobId, [new File([sourceBytes], fixture.source_name, { type: "image/png" })]);
  const source = uploaded.documents![0]!;
  const sourcePath = path.join(uploaded.uploadsPath!, source.storedName);
  assert.equal(sha(fs.readFileSync(sourcePath)), fixture.source_sha256);
  const runId = `auto_${randomUUID().replaceAll("-", "")}`;
  const docId = variant.candidate.doc_id;
  const runDir = path.join(dataDir, "product_runs", runId);
  const resultDir = path.join(runDir, "docs", docId);
  fs.mkdirSync(resultDir, { recursive: true });
  const resultPath = path.join(resultDir, "result.json");
  const manifestPath = path.join(runDir, "manifest.jsonl");
  const result = { contract_version: 1, pages: variant.pages, candidate: variant.candidate,
    source_container_sha256: fixture.source_sha256, visual_document: variant.visual_receipt };
  const writeResult = (value: typeof result) => {
    const bytes = Buffer.from(JSON.stringify(value));
    fs.writeFileSync(resultPath, bytes);
    fs.writeFileSync(manifestPath, JSON.stringify({ contract_version: 1, run_id: runId,
      doc_id: docId, source_file: source.storedName,
      source_container_sha256: fixture.source_sha256, document_status: "needs_review",
      result_sha256: sha(bytes) }) + "\n");
  };
  writeResult(result);
  fs.writeFileSync(path.join(runDir, "run.json"), JSON.stringify({ contract_version: 1, run_id: runId, doc_count: 1 }));
  const metadataDir = path.join(dataDir, "frontend", "auto_runs", job.jobId);
  fs.mkdirSync(metadataDir, { recursive: true });
  fs.writeFileSync(path.join(metadataDir, `${runId}.json`), JSON.stringify({
    runId, jobId: job.jobId, status: "running", createdAt: new Date().toISOString(),
    serverInstanceId: "previous-server", selectedFiles: [{ fileId: source.fileId,
      fileName: source.fileName, storedName: source.storedName, sha256: fixture.source_sha256 }], documents: [],
  }));
  const url = `/api/jobs/${job.jobId}/auto/${runId}/docs/${docId}`;
  const params = { params: Promise.resolve({ jobId: job.jobId, runId, docId }) };
  return { jobId: job.jobId, runId, docId, url, params, sourcePath, result, writeResult };
}

test("Python visual workflow candidate remains pending until source-bound human review, then exports", async () => {
  await withStorage(async (dataDir) => {
    const flow = await setup(dataDir, "image_only");
    assert.equal((await getDocument(request(flow.url, "bob"), flow.params)).status, 404);
    const original = await getDocument(request(flow.url, "alice"), flow.params);
    assert.equal(original.status, 200);
    const initial = await original.json();
    assert.equal(initial.visualRoute, "visual");
    assert.equal(initial.candidate.extracted_values[0].value[0].visual_page, 1);
    assert.equal(initial.correctedResult.review_status, "unreviewed");
    assert.equal((await getExport(request(`${flow.url}/export`, "alice"), flow.params)).status, 409);

    const reviewed = await saveReview(request(flow.url, "alice", { method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ expected_revision: 0, fields: [
        { field_id: "item", decision: "correct", note: "Checked every cell in the original image." },
        { field_id: "total", decision: "correct", note: "Checked the original image." },
      ] }),
    }), flow.params);
    assert.equal(reviewed.status, 200);
    const saved = await reviewed.json();
    assert.equal(saved.review.status, "completed");
    assert.equal(saved.correctedResult.review_status, "completed");
    assert.equal(saved.correctedResult.fields[0].status, "accepted");
    assert.equal(saved.correctedResult.fields[0].provenance, "human_verified");
    assert.equal(saved.correctedResult.fields[0].value[0].status, "needs_review");
    assert.equal(saved.correctedResult.fields[0].value[0].visual_grounding_verified, false);
    assert.deepEqual(saved.correctedResult.fields[1].visual_pages, [1]);
    assert.equal(saved.review.source_container_sha256, fixture.source_sha256);
    assert.equal(saved.review.reviewer_user_id, "alice-id");
    const exported = await getExport(request(`${flow.url}/export`, "alice"), flow.params);
    assert.equal(exported.status, 200);
    const body = await exported.json();
    assert.equal(body.document.source_sha256, fixture.source_sha256);
    assert.equal(body.result.fields[0].provenance, "human_verified");
    assert.equal(body.result.fields[0].value[0].visual_page, 1);
    assert.equal(body.result.fields[1].visual_grounding_verified, false);
    assert.equal(body.review.revision, 1);
    assert.throws(() => createProductAutoRecipeDraft(flow.jobId, flow.runId, flow.docId,
      "alice-id", 1, "Visual invoice"), /Image-derived proposals cannot seed/);

    fs.writeFileSync(flow.sourcePath, "changed");
    assert.equal((await getExport(request(`${flow.url}/export`, "alice"), flow.params)).status, 409);
  });
});

test("Python visual OCR matches stay pending and retain text_match evidence after human review", async () => {
  await withStorage(async (dataDir) => {
    const flow = await setup(dataDir, "ocr_text_match");
    const initial = await getDocument(request(flow.url, "alice"), flow.params);
    assert.equal(initial.status, 200);
    const candidate = (await initial.json()).candidate as ProductAutoCandidate;
    assert.equal(candidate.extracted_values[0]!.status, "needs_review");
    assert.equal((candidate.extracted_values[0]!.value as Array<{ evidence: { kind: string } }>)[0]!.evidence.kind,
      "text_match");
    assert.equal(candidate.extracted_values[1]!.evidence?.kind, "text_match");
    const reviewed = await saveReview(request(flow.url, "alice", { method: "POST",
      headers: { "content-type": "application/json" }, body: JSON.stringify({ expected_revision: 0,
        fields: [{ field_id: "item", decision: "correct" }, { field_id: "total", decision: "correct" }] }),
    }), flow.params);
    assert.equal(reviewed.status, 200);
    assert.equal((await getExport(request(`${flow.url}/export`, "alice"), flow.params)).status, 200);
  });
});

test("visual metadata is confined to real distinct pages and never machine-accepted", async () => {
  await withStorage(async (dataDir) => {
    const flow = await setup(dataDir, "ocr_text_match");
    const invalid: Array<(value: typeof flow.result) => void> = [
      (value) => { (value.candidate.extracted_values[0]!.value as Array<Record<string, unknown>>)[0]!.visual_page = 99; },
      (value) => { value.candidate.extracted_values[1]!.visual_pages = [1, 1]; },
      (value) => { value.candidate.extracted_values[1]!.visual_pages = [99]; },
      (value) => { value.candidate.extracted_values[0]!.value = [{ row: 0, value: "Widget", status: "accepted",
        visual_page: 1, visual_grounding_verified: false, review_state: "pending" }]; },
      (value) => { value.candidate.extracted_values[1]!.status = "accepted"; },
      (value) => { value.candidate.extracted_values[1]!.review_state = "completed"; },
      (value) => { (value.candidate.extracted_values[1] as unknown as Record<string, unknown>).visual_grounding_verified = true; },
      (value) => { (value.candidate.extracted_values[1] as unknown as Record<string, unknown>).pixel_box = [0, 0, 1, 1]; },
      (value) => { value.candidate.extracted_values[1]!.evidence!.kind = "pixel_match" as "text_match"; },
      (value) => { value.pages.push({ page: 1, text: "duplicate" }); },
    ];
    for (const mutate of invalid) {
      const copy = structuredClone(flow.result);
      mutate(copy);
      flow.writeResult(copy);
      assert.equal((await getDocument(request(flow.url, "alice"), flow.params)).status, 500);
    }
    flow.writeResult(flow.result);
    assert.equal((await getDocument(request(flow.url, "alice"), flow.params)).status, 200);
  });
});

test("a visual run with no retained machine values still cannot seed a reusable recipe", async () => {
  await withStorage(async (dataDir) => {
    const flow = await setup(dataDir, "image_only");
    const empty = structuredClone(flow.result);
    for (const field of empty.candidate.extracted_values) {
      field.value = null;
      field.status = "missing";
      delete field.visual_grounding_verified;
      delete field.visual_pages;
    }
    flow.writeResult(empty);
    const reviewed = await saveReview(request(flow.url, "alice", { method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ expected_revision: 0, fields: [
        { field_id: "item", decision: "corrected", corrected_value: '[{"row":0,"value":"Widget"}]' },
        { field_id: "total", decision: "corrected", corrected_value: "100" },
      ] }),
    }), flow.params);
    assert.equal(reviewed.status, 200);
    assert.equal((await getExport(request(`${flow.url}/export`, "alice"), flow.params)).status, 200);
    assert.throws(() => createProductAutoRecipeDraft(flow.jobId, flow.runId, flow.docId,
      "alice-id", 1, "Visual invoice"), /Image-derived proposals cannot seed/);
  });
});
