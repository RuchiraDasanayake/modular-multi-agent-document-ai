import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import test from "node:test";
import { GET as listRecipes, POST as createDraft } from "@/app/api/jobs/[jobId]/auto/recipes/route";
import { GET as getRecipe, POST as changeRecipe } from "@/app/api/jobs/[jobId]/auto/recipes/[recipeId]/route";
import { POST as saveReview } from "@/app/api/jobs/[jobId]/auto/[runId]/docs/[docId]/route";
import { resetConfigCacheForTests } from "./config";
import { addDocumentsToJob, createWorkspaceJob } from "./jobs";
import type { ProductAutoCandidate } from "@/types/product-auto";

function request(url: string, token: string, body?: unknown): Request {
  return new Request(`http://localhost${url}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { Authorization: `Bearer ${token}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}

async function withStorage(run: (dataDir: string) => Promise<void>): Promise<void> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-recipes-"));
  const dataDir = path.join(root, "data");
  const oldDataDir = process.env.IDPO_DATA_DIR;
  const oldGateway = process.env.INTERNAL_API_URL;
  const oldFetch = globalThis.fetch;
  process.env.IDPO_DATA_DIR = dataDir;
  process.env.INTERNAL_API_URL = "http://test-gateway.local";
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
    resetConfigCacheForTests();
    if (path.dirname(root) !== os.tmpdir() || !path.basename(root).startsWith("idpo-recipes-")) {
      throw new Error("Unsafe recipe test cleanup path.");
    }
    fs.rmSync(root, { recursive: true, force: true });
  }
}

async function fixture(dataDir: string, candidate: ProductAutoCandidate, text: string) {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const uploaded = await addDocumentsToJob(job.jobId, [new File([text], "source.txt", { type: "text/plain" })]);
  const source = uploaded.documents![0];
  const sourcePath = path.join(uploaded.uploadsPath!, source.storedName);
  const sha256 = createHash("sha256").update(fs.readFileSync(sourcePath)).digest("hex");
  const runId = `auto_${randomUUID().replaceAll("-", "")}`;
  const docId = "doc1";
  candidate.doc_id = docId;
  const sidecarDir = path.join(dataDir, "product_runs", runId, "docs", docId);
  const resultPath = path.join(sidecarDir, "result.json");
  fs.mkdirSync(sidecarDir, { recursive: true });
  fs.writeFileSync(resultPath, JSON.stringify({
    pages: [{ page: 1, text }], candidate,
  }));
  fs.writeFileSync(path.join(dataDir, "product_runs", runId, "run.json"), JSON.stringify({
    contract_version: 1, run_id: runId, doc_count: 1,
  }));
  fs.writeFileSync(path.join(dataDir, "product_runs", runId, "manifest.jsonl"), JSON.stringify({
    contract_version: 1, run_id: runId, doc_id: docId, source_file: source.storedName,
    source_container_sha256: sha256, document_status: candidate.document_status,
  }) + "\n");
  const runMetaDir = path.join(dataDir, "frontend", "auto_runs", job.jobId);
  fs.mkdirSync(runMetaDir, { recursive: true });
  fs.writeFileSync(path.join(runMetaDir, `${runId}.json`), JSON.stringify({
    runId, jobId: job.jobId, status: "running", createdAt: new Date().toISOString(),
    serverInstanceId: "previous-server", selectedFiles: [{
      fileId: source.fileId, fileName: source.fileName, storedName: source.storedName, sha256,
    }], documents: [],
  }));
  return { jobId: job.jobId, runId, docId, sourcePath, resultPath };
}

function scalarCandidate(type = "string"): ProductAutoCandidate {
  return {
    contract_version: 1, doc_id: "doc1", document_status: "needs_review",
    proposed_schema: [{ field_id: "total", type }],
    extracted_values: [{ field_id: "total", value: "100", status: "accepted", review_state: "pending",
      evidence: { page: 1, start: 15, end: 18, quote: "100" } }],
  };
}

async function reviewFields(jobId: string, runId: string, docId: string, fields: unknown[], expectedRevision = 0,
  addedFields?: unknown[]) {
  return saveReview(request(`/api/jobs/${jobId}/auto/${runId}/docs/${docId}`, "alice", {
    expected_revision: expectedRevision, fields, ...(addedFields === undefined ? {} : { added_fields: addedFields }),
  }), { params: Promise.resolve({ jobId, runId, docId }) });
}

async function draft(jobId: string, runId: string, docId: string, expectedReviewRevision = 1) {
  return createDraft(request(`/api/jobs/${jobId}/auto/recipes`, "alice", {
    runId, docId, expectedReviewRevision, familyName: "Invoice family",
  }), { params: Promise.resolve({ jobId }) });
}

test("approved shadow recipes are owner scoped, immutable, and audited with the actor", async () => withStorage(async (dataDir) => {
  const { jobId, runId, docId } = await fixture(dataDir, scalarCandidate(), "Invoice\nTotal: 100");
  const bobJob = createWorkspaceJob({ ownerUserId: "bob-id" });
  assert.equal((await reviewFields(jobId, runId, docId, [{ field_id: "total", decision: "correct" }])).status, 200);
  const created = await draft(jobId, runId, docId);
  assert.equal(created.status, 201);
  const draftBody = await created.json();
  const recipeId: string = draftBody.recipe.recipe_id;
  assert.equal(draftBody.recipe.state, "draft");
  assert.equal(draftBody.recipe.owner_user_id, "alice-id");

  const bobList = await listRecipes(request(`/api/jobs/${bobJob.jobId}/auto/recipes`, "bob"),
    { params: Promise.resolve({ jobId: bobJob.jobId }) });
  assert.deepEqual((await bobList.json()).recipes, []);
  const bobRead = await getRecipe(request(`/api/jobs/${bobJob.jobId}/auto/recipes/${recipeId}`, "bob"),
    { params: Promise.resolve({ jobId: bobJob.jobId, recipeId }) });
  assert.equal(bobRead.status, 404);
  const bobCrossJob = await getRecipe(request(`/api/jobs/${jobId}/auto/recipes/${recipeId}`, "bob"),
    { params: Promise.resolve({ jobId, recipeId }) });
  assert.equal(bobCrossJob.status, 404);

  const approve = await changeRecipe(request(`/api/jobs/${jobId}/auto/recipes/${recipeId}`, "alice", {
    action: "approve", expectedRevision: 1, confirmedRowGroups: [],
  }), { params: Promise.resolve({ jobId, recipeId }) });
  assert.equal(approve.status, 200);
  assert.equal((await approve.json()).recipe.state, "approved_shadow");
  const conflict = await changeRecipe(request(`/api/jobs/${jobId}/auto/recipes/${recipeId}`, "alice", {
    action: "approve", expectedRevision: 1, confirmedRowGroups: [],
  }), { params: Promise.resolve({ jobId, recipeId }) });
  assert.equal(conflict.status, 409);

  const disable = await changeRecipe(request(`/api/jobs/${jobId}/auto/recipes/${recipeId}`, "admin", {
    action: "disable", expectedRevision: 2,
  }), { params: Promise.resolve({ jobId, recipeId }) });
  assert.equal(disable.status, 200);
  const detail = await getRecipe(request(`/api/jobs/${jobId}/auto/recipes/${recipeId}`, "alice"),
    { params: Promise.resolve({ jobId, recipeId }) });
  const body = await detail.json();
  assert.equal(body.recipe.state, "disabled");
  assert.deepEqual(body.auditTrail.map((event: { action: string }) => event.action),
    ["draft_created", "approved_shadow", "disabled"]);
  assert.deepEqual(body.auditTrail.map((event: { actor_user_id: string }) => event.actor_user_id),
    ["alice-id", "alice-id", "admin-id"]);
  assert.equal(body.auditTrail[1].previous_event_id, body.auditTrail[0].audit_event_id);
  assert.equal(body.auditTrail[2].previous_event_id, body.auditTrail[1].audit_event_id);
  assert.deepEqual(body.auditTrail[0].fields, body.auditTrail[2].fields);
}));

test("approval rejects a source review updated after the draft", async () => withStorage(async (dataDir) => {
  const { jobId, runId, docId } = await fixture(dataDir, scalarCandidate(), "Invoice\nTotal: 100");
  assert.equal((await reviewFields(jobId, runId, docId, [{ field_id: "total", decision: "correct" }])).status, 200);
  const created = await draft(jobId, runId, docId);
  assert.equal(created.status, 201);
  const recipeId = (await created.json()).recipe.recipe_id;
  assert.equal((await reviewFields(jobId, runId, docId,
    [{ field_id: "total", decision: "correct", note: "rechecked" }], 1)).status, 200);
  const approve = await changeRecipe(request(`/api/jobs/${jobId}/auto/recipes/${recipeId}`, "alice", {
    action: "approve", expectedRevision: 1, confirmedRowGroups: [],
  }), { params: Promise.resolve({ jobId, recipeId }) });
  assert.equal(approve.status, 409);
}));

test("drafts reject a control-character group and missing typed value", async () => withStorage(async (dataDir) => {
  const badGroup = scalarCandidate();
  badGroup.proposed_schema[0].group = "Header\nGroup";
  const badGroupSource = await fixture(dataDir, badGroup, "Invoice\nTotal: 100");
  assert.equal((await reviewFields(badGroupSource.jobId, badGroupSource.runId, badGroupSource.docId,
    [{ field_id: "total", decision: "correct" }])).status, 200);
  assert.equal((await draft(badGroupSource.jobId, badGroupSource.runId, badGroupSource.docId)).status, 400);

  const missing = scalarCandidate();
  missing.extracted_values[0] = { field_id: "total", value: null, status: "missing", review_state: "pending" };
  const missingSource = await fixture(dataDir, missing, "Invoice\nTotal: 100");
  assert.equal((await reviewFields(missingSource.jobId, missingSource.runId, missingSource.docId,
    [{ field_id: "total", decision: "correct" }])).status, 200);
  assert.equal((await draft(missingSource.jobId, missingSource.runId, missingSource.docId)).status, 400);

  const absentSource = await fixture(dataDir, scalarCandidate(), "Invoice\nTotal: 100");
  assert.equal((await reviewFields(absentSource.jobId, absentSource.runId, absentSource.docId,
    [{ field_id: "total", decision: "not_present" }])).status, 200);
  assert.equal((await draft(absentSource.jobId, absentSource.runId, absentSource.docId)).status, 400);
}));

test("drafts preserve reviewed field types without copying corrected values", async () => withStorage(async (dataDir) => {
  const numeric = scalarCandidate("integer");
  numeric.extracted_values[0].value = 100;
  const { jobId, runId, docId } = await fixture(dataDir, numeric, "Invoice\nTotal: 100\nReference: PRIVATE-ABC");
  const review = await saveReview(request(`/api/jobs/${jobId}/auto/${runId}/docs/${docId}`, "alice", {
    expected_revision: 0,
    fields: [{ field_id: "total", decision: "corrected", corrected_value: "0" }],
    added_fields: [{ field_id: "reference", type: "string", value: "PRIVATE-ABC",
      evidence: { page: 1, quote: "PRIVATE-ABC" } }],
  }), { params: Promise.resolve({ jobId, runId, docId }) });
  assert.equal(review.status, 200);
  const created = await draft(jobId, runId, docId);
  assert.equal(created.status, 201);
  const recipe = (await created.json()).recipe;
  assert.deepEqual(recipe.fields, [
    { field_id: "total", type: "integer" },
    { field_id: "reference", type: "string" },
  ]);
  assert.equal(Object.hasOwn(recipe.fields[0], "value"), false);
  assert.equal(JSON.stringify(recipe).includes("PRIVATE-ABC"), false);
}));

test("ownerless legacy jobs cannot create or access an owner-scoped recipe catalog", async () => withStorage(async () => {
  const legacy = createWorkspaceJob();
  const response = await listRecipes(request(`/api/jobs/${legacy.jobId}/auto/recipes`, "admin"),
    { params: Promise.resolve({ jobId: legacy.jobId }) });
  assert.equal(response.status, 409);
}));

test("reviewed Unicode field IDs and group labels can seed a recipe", async () => withStorage(async (dataDir) => {
  const text = "請求書\n合計金額: 100";
  const start = [...text.slice(0, text.indexOf("100"))].length;
  const candidate: ProductAutoCandidate = {
    contract_version: 1, doc_id: "doc1", document_status: "needs_review",
    proposed_schema: [{ field_id: "合計金額", type: "integer", group: "請求書 ヘッダー" }],
    extracted_values: [{ field_id: "合計金額", value: 100, status: "accepted", review_state: "pending",
      evidence: { page: 1, start, end: start + 3, quote: "100" } }],
  };
  const { jobId, runId, docId } = await fixture(dataDir, candidate, text);
  assert.equal((await reviewFields(jobId, runId, docId,
    [{ field_id: "合計金額", decision: "correct" }])).status, 200);
  const created = await draft(jobId, runId, docId);
  assert.equal(created.status, 201);
  const recipe = (await created.json()).recipe;
  assert.deepEqual(recipe.fields, [{ field_id: "合計金額", type: "integer", group: "請求書 ヘッダー" }]);
  const approved = await changeRecipe(request(`/api/jobs/${jobId}/auto/recipes/${recipe.recipe_id}`, "alice", {
    action: "approve", expectedRevision: 1, confirmedRowGroups: [],
  }), { params: Promise.resolve({ jobId, recipeId: recipe.recipe_id }) });
  assert.equal(approved.status, 200);
}));

test("linked-row groups require two aligned columns and explicit approval confirmation", async () => withStorage(async (dataDir) => {
  const linked: ProductAutoCandidate = {
    contract_version: 1, doc_id: "doc1", document_status: "needs_review",
    proposed_schema: [
      { field_id: "item_name", type: "array[object]", group: "line_items" },
      { field_id: "quantity", type: "array[object]", group: "line_items" },
    ],
    extracted_values: [
      { field_id: "item_name", value: [{ row: 0, value: "A", status: "accepted",
        evidence: { page: 1, start: 9, end: 10, quote: "A" } }],
      status: "needs_review", review_state: "pending" },
      { field_id: "quantity", value: [{ row: 0, value: "2", status: "accepted",
        evidence: { page: 1, start: 11, end: 12, quote: "2" } }],
      status: "needs_review", review_state: "pending" },
    ],
  };
  const { jobId, runId, docId } = await fixture(dataDir, linked, "Item Qty\nA 2\n");
  assert.equal((await reviewFields(jobId, runId, docId, [
    { field_id: "item_name", decision: "correct" },
    { field_id: "quantity", decision: "correct" },
  ])).status, 200);
  const created = await draft(jobId, runId, docId);
  assert.equal(created.status, 201);
  const recipeId = (await created.json()).recipe.recipe_id;
  const missingConfirmation = await changeRecipe(request(`/api/jobs/${jobId}/auto/recipes/${recipeId}`, "alice", {
    action: "approve", expectedRevision: 1, confirmedRowGroups: [],
  }), { params: Promise.resolve({ jobId, recipeId }) });
  assert.equal(missingConfirmation.status, 400);
  const approved = await changeRecipe(request(`/api/jobs/${jobId}/auto/recipes/${recipeId}`, "alice", {
    action: "approve", expectedRevision: 1, confirmedRowGroups: ["line_items"],
  }), { params: Promise.resolve({ jobId, recipeId }) });
  assert.equal(approved.status, 200);
  assert.deepEqual((await approved.json()).recipe.confirmed_row_groups, ["line_items"]);

  const oneColumn = structuredClone(linked);
  oneColumn.proposed_schema.pop();
  oneColumn.extracted_values.pop();
  const oneColumnSource = await fixture(dataDir, oneColumn, "Item Qty\nA 2\n");
  assert.equal((await reviewFields(oneColumnSource.jobId, oneColumnSource.runId, oneColumnSource.docId,
    [{ field_id: "item_name", decision: "correct" }])).status, 200);
  assert.equal((await draft(oneColumnSource.jobId, oneColumnSource.runId, oneColumnSource.docId)).status, 400);
}));

test("human-added linked columns require unique source-backed cells and aligned rows for recipe approval", async () => withStorage(async (dataDir) => {
  const text = "🧾\nTea 2\nBread 2\nPrice 2.50\nRepeated 2 2\n";
  const candidate: ProductAutoCandidate = {
    contract_version: 1, doc_id: "doc1", document_status: "needs_review",
    proposed_schema: [], extracted_values: [],
  };
  const { jobId, runId, docId, sourcePath, resultPath } = await fixture(dataDir, candidate, text);
  const url = `/api/jobs/${jobId}/auto/${runId}/docs/${docId}`;
  const params = { params: Promise.resolve({ jobId, runId, docId }) };
  const post = (token: string, expectedRevision: number, addedFields: unknown[]) => saveReview(
    request(url, token, { expected_revision: expectedRevision, fields: [], added_fields: addedFields }), params);
  const cell = (row: number, value: string, quote: string) => ({ row, value, evidence: { page: 1, quote } });
  const name = { field_id: "item_name", type: "array[object]", group: "line_items", value: [
    cell(0, "Tea", "Tea 2"), cell(1, "Bread", "Bread 2"),
  ] };
  const count = { field_id: "quantity", type: "array[object]", group: "line_items", value: [
    cell(0, "2", "Tea 2"),
  ] };
  assert.equal((await post("bob", 0, [name, count])).status, 404);
  assert.equal((await post("alice", 0, [{ ...name, field_id: "item_name_" }, count])).status, 400);
  assert.equal((await post("alice", 0, [{ ...name, group: "line\nitems" }, count])).status, 400);
  assert.equal((await post("alice", 0, [{ ...name, value: [] }, count])).status, 400);
  assert.equal((await post("alice", 0, [{ ...name, value: Array.from({ length: 129 }, (_, row) =>
    cell(row, "Tea", "Tea 2")) }, count])).status, 400);
  assert.equal((await post("alice", 0, [{ ...name, value: [cell(0, "Tea", "Tea 2"), cell(0, "Bread", "Bread 2")] }, count])).status, 400);
  assert.equal((await post("alice", 0, [{ ...name, value: [cell(0, "Tea", "Tea 2"), cell(1, "Bread", "Tea 2")] }, count])).status, 400);
  assert.equal((await post("alice", 0, [{ ...name, value: [cell(0, "Coffee", "Tea 2")] }, count])).status, 400);
  assert.equal((await post("alice", 0, [{ ...count, value: [cell(0, "2", "Price 2.50")] }, name])).status, 400);
  assert.equal((await post("alice", 0, [{ ...count, value: [cell(0, "2", "Repeated 2 2")] }, name])).status, 400);
  assert.equal((await post("alice", 0, [{ ...name, value: [cell(0, "Tea", "Tea 2"),
    { ...cell(1, "Bread", "Bread 2"), evidence: { page: 2, quote: "Bread 2" } }] }, count])).status, 400);
  const ambiguous = await post("alice", 0, [{ ...count, value: [cell(0, "2", "2")] }, name]);
  assert.equal(ambiguous.status, 400);
  assert.match((await ambiguous.json()).error, /more than once/);

  const first = await post("alice", 0, [name, count]);
  assert.equal(first.status, 200);
  const firstBody = await first.json();
  assert.equal(firstBody.review.status, "completed");
  assert.equal(firstBody.review.source_container_sha256.length, 64);
  assert.equal(firstBody.review.source_pages_sha256.length, 64);
  assert.deepEqual(firstBody.correctedResult.fields.map((field: { field_id: string }) => field.field_id),
    ["item_name", "quantity"]);
  assert.deepEqual(firstBody.correctedResult.fields[0].value.map((entry: { row: number; status: string }) =>
    [entry.row, entry.status]), [[0, "accepted"], [1, "accepted"]]);
  assert.equal(firstBody.correctedResult.fields[0].group, "line_items");
  assert.equal(firstBody.review.added_fields[0].value[0].evidence.start, 2);
  assert.equal(firstBody.review.added_fields[0].value[0].evidence.quote, "Tea 2");
  assert.equal((await draft(jobId, runId, docId)).status, 400);

  const auditDir = path.join(dataDir, "frontend", "auto_reviews", jobId, runId, "events", docId);
  const firstAudit = path.join(auditDir, "000000000001.json");
  const firstBytes = fs.readFileSync(firstAudit);
  const alignedCount = { ...count, value: [...count.value, cell(1, "2", "Bread 2")] };
  const second = await post("alice", 1, [name, alignedCount]);
  assert.equal(second.status, 200);
  assert.deepEqual(fs.readFileSync(firstAudit), firstBytes);
  const secondBody = await second.json();
  assert.equal(secondBody.review.revision, 2);
  const created = await draft(jobId, runId, docId, 2);
  assert.equal(created.status, 201);
  const recipe = (await created.json()).recipe;
  assert.deepEqual(recipe.fields, [
    { field_id: "item_name", type: "array[object]", group: "line_items" },
    { field_id: "quantity", type: "array[object]", group: "line_items" },
  ]);
  assert.deepEqual(recipe.row_groups, [{ group: "line_items", field_ids: ["item_name", "quantity"],
    alignment: "shared_ordinal" }]);
  assert.equal(JSON.stringify(recipe).includes("Tea 2"), false);
  const rejected = await changeRecipe(request(`/api/jobs/${jobId}/auto/recipes/${recipe.recipe_id}`, "alice", {
    action: "approve", expectedRevision: 1, confirmedRowGroups: [],
  }), { params: Promise.resolve({ jobId, recipeId: recipe.recipe_id }) });
  assert.equal(rejected.status, 400);
  const approved = await changeRecipe(request(`/api/jobs/${jobId}/auto/recipes/${recipe.recipe_id}`, "alice", {
    action: "approve", expectedRevision: 1, confirmedRowGroups: ["line_items"],
  }), { params: Promise.resolve({ jobId, recipeId: recipe.recipe_id }) });
  assert.equal(approved.status, 200);

  const originalResult = fs.readFileSync(resultPath);
  const alteredResult = JSON.parse(originalResult.toString("utf8"));
  alteredResult.pages[0].text = alteredResult.pages[0].text.replace("Tea 2", "Tea 3");
  fs.writeFileSync(resultPath, JSON.stringify(alteredResult));
  const changedOcr = await post("alice", 2, [name, alignedCount]);
  assert.equal(changedOcr.status, 409);
  assert.match((await changedOcr.json()).error, /OCR text no longer matches/);
  fs.writeFileSync(resultPath, originalResult);
  fs.writeFileSync(sourcePath, "changed source bytes");
  const changed = await post("alice", 2, [name, alignedCount]);
  assert.equal(changed.status, 409);
  assert.match((await changed.json()).error, /original source changed/);
}));
