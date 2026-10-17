import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createHash } from "node:crypto";
import { POST as saveBriefRoute } from "@/app/api/jobs/[jobId]/auto/brief/route";
import { POST as suggestRoute } from "@/app/api/jobs/[jobId]/auto/brief/suggest/route";
import { resetConfigCacheForTests } from "./config";
import { addDocumentsToJob, createWorkspaceJob } from "./jobs";
import { getProductAutoBrief } from "./product-auto-brief";
import { suggestProductAutoBrief, suggestionFailureMessage } from "./product-auto-brief-suggest";

test("sample failures give a bounded recovery action without claiming unknown attempts were free", () => {
  for (const code of ["budget_exhausted", "ocr_timeout"]) {
    assert.match(suggestionFailureMessage("sample", code), /Choose fewer or smaller samples/);
    assert.match(suggestionFailureMessage("sample", code), /No schema model request was started/);
  }
  assert.match(suggestionFailureMessage("sample", "ocr_no_text"), /enter the fields manually/);
  for (const [stage, code] of [["helper", "timeout"], ["model", "ocr_timeout"], ["sample", "secret_value"]]) {
    const message = suggestionFailureMessage(stage, code);
    assert.match(message, /may already have been charged/);
    assert.doesNotMatch(message, /No schema model request|secret_value/);
  }
});

type HelperInput = Parameters<NonNullable<Parameters<typeof suggestProductAutoBrief>[3]>>[0];

function request(jobId: string, token: string, body: unknown, suffix = ""): Request {
  return new Request(`http://localhost/api/jobs/${jobId}/auto/brief${suffix}`, {
    method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function withStorage(run: () => Promise<void>): Promise<void> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-suggest-"));
  const previous = {
    data: process.env.IDPO_DATA_DIR, gateway: process.env.INTERNAL_API_URL,
    model: process.env.IDPO_AUTO_MODEL, baseUrl: process.env.IDPO_AUTO_API_BASE_URL,
  };
  const oldFetch = globalThis.fetch;
  process.env.IDPO_DATA_DIR = path.join(root, "data");
  process.env.INTERNAL_API_URL = "http://test-gateway.local";
  process.env.IDPO_AUTO_MODEL = "fake-model";
  process.env.IDPO_AUTO_API_BASE_URL = "http://127.0.0.1:1/v1";
  resetConfigCacheForTests();
  globalThis.fetch = async (input, init) => {
    assert.equal(String(input), "http://test-gateway.local/api/auth/me");
    const token = new Headers(init?.headers).get("Authorization")?.replace(/^Bearer /, "");
    if (token === "alice") return Response.json({ id: "alice-id", role: "viewer" });
    if (token === "bob") return Response.json({ id: "bob-id", role: "viewer" });
    if (token === "admin") return Response.json({ id: "admin-id", role: "admin" });
    return Response.json({}, { status: 401 });
  };
  try { await run(); }
  finally {
    globalThis.fetch = oldFetch;
    for (const [key, value] of Object.entries({ IDPO_DATA_DIR: previous.data,
      INTERNAL_API_URL: previous.gateway, IDPO_AUTO_MODEL: previous.model,
      IDPO_AUTO_API_BASE_URL: previous.baseUrl })) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
    resetConfigCacheForTests();
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("AI suggestion checks owner, admin, draft revision, sources, and leaves draft unconfirmed", async () => withStorage(async () => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const upload = await addDocumentsToJob(job.jobId, [new File(["Invoice A\nAmount due 123.45"], "invoice.txt")]);
  const fileId = upload.documents![0].fileId;
  const params = { params: Promise.resolve({ jobId: job.jobId }) };
  const saved = await saveBriefRoute(request(job.jobId, "alice", {
    expectedRevision: 0, intent: "Extract final amount due", fields: [], sampleFileIds: [fileId],
  }), params);
  assert.equal(saved.status, 201);
  const brief = (await saved.json()).brief;
  const pin = { expectedRevision: brief.revision, expectedPayloadSha256: brief.payload_sha256 };
  assert.equal((await suggestRoute(request(job.jobId, "bob", pin, "/suggest"), params)).status, 404);
  assert.equal((await suggestRoute(request(job.jobId, "alice", pin, "/suggest"), params)).status, 403);
  assert.equal((await suggestRoute(request(job.jobId, "admin", { ...pin, extra: true }, "/suggest"), params)).status, 400);
  assert.equal((await suggestRoute(request(job.jobId, "admin", { ...pin, padding: "x".repeat(3000) }, "/suggest"), params)).status, 413);
  let calls = 0;
  const helper = async (input: HelperInput) => {
    calls += 1;
    assert.equal(input.samples.length, 1);
    assert.ok(fs.existsSync(input.samples[0].path));
    return { fields: [{ field_id: "amount_due", type: "decimal", description: "Final payable amount",
      example_values: ["123.45"] }], clarification_questions: ["Does the amount include tax?"],
    provenance: { brief_revision: input.brief_revision, brief_payload_sha256: input.brief_payload_sha256,
      samples: input.samples.map((sample) => ({ file_id: sample.file_id,
        source_sha256: sample.source_sha256, parser_id: "utf8-text", excerpt_chars: 25,
        truncated: false, path: "must-not-escape" })), model: input.model,
      prompt_sha256: "c".repeat(64), input_chars: 500, max_output_tokens: 1800,
      prompt_tokens: 80, completion_tokens: 30, latency_ms: 5, sdk_attempts: 1 } };
  };
  const admin = { id: "admin-id", role: "admin" };
  await assert.rejects(suggestProductAutoBrief(job.jobId, admin,
    { expectedRevision: 9, expectedPayloadSha256: brief.payload_sha256 }, helper), /changed/);
  assert.equal(calls, 0);
  const result = await suggestProductAutoBrief(job.jobId, admin, pin, helper);
  assert.equal(calls, 1);
  assert.deepEqual(result.fields.map((field) => field.field_id), ["amount_due"]);
  assert.equal(JSON.stringify(result).includes("must-not-escape"), false);
  assert.equal(JSON.stringify(result).includes(".txt"), false);
  assert.equal(getProductAutoBrief(job.jobId).brief?.state, "draft");
  assert.deepEqual(getProductAutoBrief(job.jobId).brief?.fields, []);
  const diagnostics = path.join(process.env.IDPO_DATA_DIR!, "frontend", "auto_briefs",
    createHash("sha256").update("alice-id").digest("hex"), job.jobId, "suggestions");
  const completed = fs.readdirSync(diagnostics).filter((name) => name.endsWith(".diagnostic.json"))
    .map((name) => JSON.parse(fs.readFileSync(path.join(diagnostics, name), "utf8")));
  assert.equal(completed.length, 1);
  assert.equal(completed[0].status, "completed");
  assert.equal(JSON.stringify(completed).includes("Invoice A"), false);
  assert.equal(JSON.stringify(completed).includes(".txt"), false);
  await assert.rejects(suggestProductAutoBrief(job.jobId, admin, pin,
    async () => ({ fields: [{ field_id: "invalid", type: "made-up", description: "Bad", example_values: [] }],
      clarification_questions: [], provenance: {} })),
  (error: unknown) => error instanceof Error && "statusCode" in error && error.statusCode === 502);
  const afterInvalid = fs.readdirSync(diagnostics).filter((name) => name.endsWith(".diagnostic.json"))
    .map((name) => JSON.parse(fs.readFileSync(path.join(diagnostics, name), "utf8")));
  assert.equal(afterInvalid.filter((receipt) => receipt.status === "failed" && receipt.stage === "node_validation").length, 1);

  const sample = inputSource(job.jobId, fileId);
  fs.writeFileSync(sample, "Invoice B\nAmount due 999.99");
  await assert.rejects(suggestProductAutoBrief(job.jobId, admin, pin, helper), /changed/);
  assert.equal(calls, 1);
}));

function inputSource(jobId: string, fileId: string): string {
  const job = getProductAutoBrief(jobId);
  assert.equal(job.brief?.sample_sources[0].file_id, fileId);
  const uploads = path.join(process.env.IDPO_DATA_DIR!, "frontend", "uploads", `job_${jobId}`);
  const names = fs.readdirSync(uploads);
  assert.equal(names.length, 1);
  return path.join(uploads, names[0]);
}

test("suggestion response is rejected if source changes while the helper runs", async () => withStorage(async () => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const upload = await addDocumentsToJob(job.jobId, [new File(["Total 100"], "sample.txt")]);
  const fileId = upload.documents![0].fileId;
  const saved = await saveBriefRoute(request(job.jobId, "alice", {
    expectedRevision: 0, intent: "Find total", fields: [], sampleFileIds: [fileId],
  }), { params: Promise.resolve({ jobId: job.jobId }) });
  const brief = (await saved.json()).brief;
  const pin = { expectedRevision: brief.revision, expectedPayloadSha256: brief.payload_sha256 };
  const helper = async (input: HelperInput) => {
    fs.writeFileSync(input.samples[0].path, "Total 900");
    return { fields: [{ field_id: "total", type: "integer", description: "Total", example_values: [] }],
      clarification_questions: [], provenance: {
        brief_revision: input.brief_revision, brief_payload_sha256: input.brief_payload_sha256,
        samples: input.samples.map((sample) => ({ file_id: sample.file_id, source_sha256: sample.source_sha256,
          parser_id: "utf8-text", excerpt_chars: 9, truncated: false })), model: input.model,
        prompt_sha256: "d".repeat(64), input_chars: 100, max_output_tokens: 1800,
        prompt_tokens: null, completion_tokens: null, latency_ms: 1, sdk_attempts: 1,
      } };
  };
  await assert.rejects(suggestProductAutoBrief(job.jobId, { id: "admin-id", role: "admin" }, pin, helper), /changed/);
}));

test("AI suggestion keeps a draft repeated field's group in the helper context", async () => withStorage(async () => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const upload = await addDocumentsToJob(job.jobId, [new File(["Widget A 2 12.00"], "order.txt")]);
  const fileId = upload.documents![0].fileId;
  const params = { params: Promise.resolve({ jobId: job.jobId }) };
  const saved = await saveBriefRoute(request(job.jobId, "alice", {
    expectedRevision: 0, intent: "Extract each printed order line", fields: [
      { field_id: "item_name", type: "array[object]", group: "order_lines",
        description: "Item name in each row", example_values: ["Widget A"] },
    ], sampleFileIds: [fileId],
  }), params);
  assert.equal(saved.status, 201);
  const brief = (await saved.json()).brief;
  const result = await suggestProductAutoBrief(job.jobId, { id: "admin-id", role: "admin" },
    { expectedRevision: brief.revision, expectedPayloadSha256: brief.payload_sha256 },
    async (input) => {
      assert.deepEqual(input.existing_fields, [{ field_id: "item_name", type: "array[object]",
        group: "order_lines", description: "Item name in each row", example_values: ["Widget A"] }]);
      return { fields: brief.fields, clarification_questions: [], provenance: {
        brief_revision: input.brief_revision, brief_payload_sha256: input.brief_payload_sha256,
        samples: input.samples.map((sample) => ({ file_id: sample.file_id,
          source_sha256: sample.source_sha256, parser_id: "utf8-text", excerpt_chars: 16,
          truncated: false })), model: input.model, prompt_sha256: "a".repeat(64),
        input_chars: 200, max_output_tokens: 1800, prompt_tokens: 50,
        completion_tokens: 20, latency_ms: 2, sdk_attempts: 1,
      } };
    });
  assert.equal(result.fields[0].group, "order_lines");
  assert.equal(getProductAutoBrief(job.jobId).brief?.state, "draft");
}));
