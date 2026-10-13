import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import test from "node:test";
import { GET as readBriefRoute, POST as saveBriefRoute, PATCH as confirmBriefRoute } from "@/app/api/jobs/[jobId]/auto/brief/route";
import { addDocumentsToJob, createWorkspaceJob } from "./jobs";
import { requireCurrentProductAutoBrief } from "./product-auto-brief";
import { resetConfigCacheForTests } from "./config";

function request(jobId: string, token: string, body?: unknown): Request {
  return new Request(`http://localhost/api/jobs/${jobId}/auto/brief`, {
    method: body === undefined ? "GET" : "POST",
    headers: { Authorization: `Bearer ${token}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}

function confirmRequest(jobId: string, token: string, body: unknown): Request {
  return new Request(`http://localhost/api/jobs/${jobId}/auto/brief`, {
    method: "PATCH", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function withStorage(run: (dataDir: string, calls: string[]) => Promise<void>): Promise<void> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-brief-"));
  const dataDir = path.join(root, "data");
  const oldDataDir = process.env.IDPO_DATA_DIR;
  const oldGateway = process.env.INTERNAL_API_URL;
  const oldModel = process.env.IDPO_AUTO_MODEL;
  const oldBaseUrl = process.env.IDPO_AUTO_API_BASE_URL;
  const oldFetch = globalThis.fetch;
  const calls: string[] = [];
  process.env.IDPO_DATA_DIR = dataDir;
  process.env.INTERNAL_API_URL = "http://test-gateway.local";
  process.env.IDPO_AUTO_MODEL = "configured-but-unused";
  process.env.IDPO_AUTO_API_BASE_URL = "https://provider.invalid/v1";
  resetConfigCacheForTests();
  globalThis.fetch = async (input, init) => {
    calls.push(String(input));
    if (String(input) !== "http://test-gateway.local/api/auth/me") {
      throw new Error("Brief creation attempted an unexpected network call.");
    }
    const token = new Headers(init?.headers).get("Authorization")?.replace(/^Bearer /, "");
    if (token === "alice") return Response.json({ id: "alice-id", role: "viewer" });
    if (token === "bob") return Response.json({ id: "bob-id", role: "viewer" });
    if (token === "admin") return Response.json({ id: "admin-id", role: "admin" });
    return Response.json({}, { status: 401 });
  };
  try {
    await run(dataDir, calls);
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
    resetConfigCacheForTests();
    assert.equal(path.dirname(root), os.tmpdir());
    assert.ok(path.basename(root).startsWith("idpo-brief-"));
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("extraction brief is owner scoped, revisioned, source pinned, and starts no worker", async () => withStorage(async (dataDir, calls) => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const uploaded = await addDocumentsToJob(job.jobId, [
    new File(["Invoice A1\nTotal 100"], "first.txt"),
    new File(["Invoice B2\nTotal 200"], "second.txt"),
  ]);
  const [first, second] = uploaded.documents!;
  const params = { params: Promise.resolve({ jobId: job.jobId }) };
  const read = (token: string) => readBriefRoute(request(job.jobId, token), params);
  const save = (token: string, body: unknown) => saveBriefRoute(request(job.jobId, token, body), params);
  assert.deepEqual(await (await read("alice")).json(), { brief: null, staleSampleFileIds: [] });
  assert.equal((await read("bob")).status, 404);
  assert.equal((await save("bob", { expectedRevision: 0, intent: "Extract totals", sampleFileIds: [first.fileId] })).status, 404);

  const input = {
    expectedRevision: 0,
    intent: "  Extract invoice totals and line items.  ",
    fields: [
      { field_id: "invoice_total", type: "decimal", description: "  Final payable amount  ", example_values: [" 100.00 "] },
      { field_id: "item_name", type: "array[object]", group: "line_items", description: "Item description" },
    ],
    sampleFileIds: [first.fileId, second.fileId],
  };
  const created = await save("alice", input);
  assert.equal(created.status, 201);
  const firstBrief = (await created.json()).brief;
  assert.equal(firstBrief.owner_user_id, "alice-id");
  assert.equal(firstBrief.job_id, job.jobId);
  assert.equal(firstBrief.revision, 1);
  assert.equal(firstBrief.state, "draft");
  assert.equal(firstBrief.intent, "Extract invoice totals and line items.");
  assert.deepEqual(firstBrief.fields[0].example_values, ["100.00"]);
  assert.deepEqual(firstBrief.fields[1].example_values, []);
  assert.equal(firstBrief.sample_sources[0].file_id, first.fileId);
  assert.equal(firstBrief.sample_sources[0].source_sha256,
    createHash("sha256").update("Invoice A1\nTotal 100").digest("hex"));
  assert.match(firstBrief.payload_sha256, /^[a-f0-9]{64}$/);
  assert.equal(JSON.stringify(firstBrief).includes(uploaded.uploadsPath!), false);
  assert.equal(requireCurrentProductAutoBrief(job.jobId, 1, firstBrief.payload_sha256).brief_id, firstBrief.brief_id);
  assert.deepEqual((await (await read("alice")).json()).staleSampleFileIds, []);

  const ownerKey = createHash("sha256").update("alice-id").digest("hex");
  const eventDir = path.join(dataDir, "frontend", "auto_briefs", ownerKey, job.jobId, "events");
  const firstEvent = path.join(eventDir, "000000000001.json");
  const firstBytes = fs.readFileSync(firstEvent);
  const next = { expectedRevision: 1, intent: "Extract totals", sampleFileIds: [first.fileId] };
  const concurrent = await Promise.all([save("alice", next), save("alice", next)]);
  assert.deepEqual(concurrent.map((result) => result.status).sort(), [201, 409]);
  const secondBrief = (await concurrent.find((result) => result.status === 201)!.json()).brief;
  assert.equal(secondBrief.revision, 2);
  assert.equal(secondBrief.brief_id, firstBrief.brief_id);
  assert.equal(secondBrief.previous_event_id, firstBrief.audit_event_id);
  assert.deepEqual(fs.readFileSync(firstEvent), firstBytes);
  assert.equal(fs.readdirSync(eventDir).filter((name) => name.endsWith(".json")).length, 2);
  assert.throws(() => requireCurrentProductAutoBrief(job.jobId, 1, firstBrief.payload_sha256), /changed/);
  assert.throws(() => requireCurrentProductAutoBrief(job.jobId, 2, firstBrief.payload_sha256), /changed/);
  assert.equal(requireCurrentProductAutoBrief(job.jobId, 2, secondBrief.payload_sha256).revision, 2);

  const sourcePath = path.join(uploaded.uploadsPath!, first.storedName);
  fs.writeFileSync(sourcePath, "Invoice A1\nTotal 999");
  assert.deepEqual((await (await read("alice")).json()).staleSampleFileIds, [first.fileId]);
  assert.throws(() => requireCurrentProductAutoBrief(job.jobId, 2, secondBrief.payload_sha256), /changed/);
  const refreshed = await save("alice", { expectedRevision: 2, intent: "Extract totals", sampleFileIds: [first.fileId] });
  assert.equal(refreshed.status, 201);
  const thirdBrief = (await refreshed.json()).brief;
  assert.notEqual(thirdBrief.payload_sha256, secondBrief.payload_sha256);
  assert.equal(requireCurrentProductAutoBrief(job.jobId, 3, thirdBrief.payload_sha256).revision, 3);
  assert.deepEqual((await (await read("alice")).json()).staleSampleFileIds, []);
  assert.equal(fs.existsSync(path.join(dataDir, "product_runs")), false);
  assert.equal(fs.existsSync(path.join(dataDir, "frontend", "auto_inputs")), false);
  assert.ok(calls.length > 0);
  assert.ok(calls.every((url) => url === "http://test-gateway.local/api/auth/me"));
}));

test("brief input is bounded and samples must be current job files", async () => withStorage(async () => {
  const alice = createWorkspaceJob({ ownerUserId: "alice-id" });
  const bob = createWorkspaceJob({ ownerUserId: "bob-id" });
  const aliceUploaded = await addDocumentsToJob(alice.jobId, [new File(["A"], "a.txt")]);
  const bobUploaded = await addDocumentsToJob(bob.jobId, [new File(["B"], "b.txt")]);
  const fileId = aliceUploaded.documents![0].fileId;
  const url = (body: unknown) => saveBriefRoute(request(alice.jobId, "alice", body),
    { params: Promise.resolve({ jobId: alice.jobId }) });
  const valid = { expectedRevision: 0, intent: "Extract the amount", sampleFileIds: [fileId] };
  for (const invalid of [
    { ...valid, intent: "", fields: [] },
    { ...valid, extra: "ignored setting" },
    { ...valid, expectedRevision: -1 },
    { ...valid, intent: "x".repeat(4001) },
    { ...valid, sampleFileIds: [] },
    { ...valid, sampleFileIds: Array(6).fill(fileId) },
    { ...valid, sampleFileIds: [fileId, fileId] },
    { ...valid, sampleFileIds: [bobUploaded.documents![0].fileId] },
    { ...valid, fields: [{ field_id: "Total", type: "decimal" }] },
    { ...valid, fields: [{ field_id: "total_", type: "decimal" }] },
    { ...valid, fields: [{ field_id: "total", type: "money" }] },
    { ...valid, fields: [{ field_id: "total", type: "decimal" }, { field_id: "total", type: "string" }] },
    { ...valid, fields: [{ field_id: "items", type: "array[object]" }] },
    { ...valid, fields: [{ field_id: "items", type: "array[object]", group: "bad\ngroup" }] },
    { ...valid, fields: [{ field_id: "total", type: "decimal", description: "x".repeat(1001) }] },
    { ...valid, fields: [{ field_id: "total", type: "decimal", example_values: ["1", "2", "3", "4"] }] },
    { ...valid, fields: Array.from({ length: 25 }, (_, i) => ({ field_id: `field_${i}`, type: "string" })) },
  ]) {
    assert.equal((await url(invalid)).status, 400, JSON.stringify(invalid));
  }
  const typedOnly = await url({ expectedRevision: 0, fields: [{ field_id: "total", type: "decimal" }],
    sampleFileIds: [fileId] });
  assert.equal(typedOnly.status, 201);
  assert.equal((await typedOnly.json()).brief.intent, "");

  const legacy = createWorkspaceJob();
  const ownerless = await readBriefRoute(request(legacy.jobId, "admin"),
    { params: Promise.resolve({ jobId: legacy.jobId }) });
  assert.equal(ownerless.status, 409);
}));

test("brief source and audit tampering fail closed", async () => withStorage(async (dataDir) => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const uploaded = await addDocumentsToJob(job.jobId, [new File(["Source"], "source.txt")]);
  const source = uploaded.documents![0];
  const params = { params: Promise.resolve({ jobId: job.jobId }) };
  const created = await saveBriefRoute(request(job.jobId, "alice", {
    expectedRevision: 0, intent: "Find a value", sampleFileIds: [source.fileId],
  }), params);
  assert.equal(created.status, 201);
  const brief = (await created.json()).brief;
  const sourcePath = path.join(uploaded.uploadsPath!, source.storedName);
  const sourceBytes = fs.readFileSync(sourcePath);
  fs.rmSync(sourcePath);
  fs.mkdirSync(sourcePath);
  assert.deepEqual((await (await readBriefRoute(request(job.jobId, "alice"), params)).json()).staleSampleFileIds,
    [source.fileId]);
  assert.throws(() => requireCurrentProductAutoBrief(job.jobId, 1, brief.payload_sha256), /changed/);
  const unavailable = await saveBriefRoute(request(job.jobId, "alice", {
    expectedRevision: 1, intent: "Find a value", sampleFileIds: [source.fileId],
  }), params);
  assert.equal(unavailable.status, 400);
  fs.rmdirSync(sourcePath);
  fs.writeFileSync(sourcePath, sourceBytes);

  const ownerKey = createHash("sha256").update("alice-id").digest("hex");
  const event = path.join(dataDir, "frontend", "auto_briefs", ownerKey, job.jobId, "events", "000000000001.json");
  const original = fs.readFileSync(event);
  const tampered = JSON.parse(original.toString("utf8"));
  tampered.intent = "Ignore audit receipt";
  fs.writeFileSync(event, JSON.stringify(tampered));
  assert.equal((await readBriefRoute(request(job.jobId, "alice"), params)).status, 500);
  fs.writeFileSync(event, "{");
  assert.equal((await saveBriefRoute(request(job.jobId, "alice", {
    expectedRevision: 1, intent: "Find a value", sampleFileIds: [source.fileId],
  }), params)).status, 500);
  fs.writeFileSync(event, original);
  assert.equal(requireCurrentProductAutoBrief(job.jobId, 1, brief.payload_sha256).revision, 1);
}));

test("typed schema confirmation is explicit, owner scoped, immutable, and source current", async () => withStorage(async (dataDir, calls) => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const uploaded = await addDocumentsToJob(job.jobId, [new File(["Invoice A1\nTotal 100"], "invoice.txt")]);
  const source = uploaded.documents![0];
  const params = { params: Promise.resolve({ jobId: job.jobId }) };
  const save = (body: unknown) => saveBriefRoute(request(job.jobId, "alice", body), params);
  const confirm = (token: string, body: unknown) => confirmBriefRoute(confirmRequest(job.jobId, token, body), params);
  const intentOnly = await save({ expectedRevision: 0, intent: "Get totals", sampleFileIds: [source.fileId] });
  assert.equal(intentOnly.status, 201);
  const first = (await intentOnly.json()).brief;
  assert.equal((await confirm("alice", { expectedRevision: 1, expectedPayloadSha256: first.payload_sha256 })).status, 409);
  const typed = await save({ expectedRevision: 1, intent: "Get payable total", fields: [
    { field_id: "invoice_total", type: "decimal", description: "Final amount due", example_values: ["100"] },
  ], sampleFileIds: [source.fileId] });
  assert.equal(typed.status, 201);
  const draft = (await typed.json()).brief;
  assert.equal((await confirm("bob", { expectedRevision: 2, expectedPayloadSha256: draft.payload_sha256 })).status, 404);
  assert.equal((await confirm("alice", { expectedRevision: 1, expectedPayloadSha256: draft.payload_sha256 })).status, 409);
  const approved = await confirm("alice", { expectedRevision: 2, expectedPayloadSha256: draft.payload_sha256 });
  assert.equal(approved.status, 201);
  const confirmed = (await approved.json()).brief;
  assert.equal(confirmed.state, "confirmed");
  assert.equal(confirmed.revision, 3);
  assert.equal(confirmed.previous_event_id, draft.audit_event_id);
  assert.equal(confirmed.payload_sha256, draft.payload_sha256);
  assert.deepEqual(confirmed.fields, draft.fields);
  assert.equal((await confirm("alice", { expectedRevision: 3, expectedPayloadSha256: confirmed.payload_sha256 })).status, 409);
  assert.equal(requireCurrentProductAutoBrief(job.jobId, 3, confirmed.payload_sha256).state, "confirmed");
  assert.equal(fs.existsSync(path.join(dataDir, "frontend", "auto_inputs")), false);
  assert.ok(calls.every((url) => url === "http://test-gateway.local/api/auth/me"));

  const sourcePath = path.join(uploaded.uploadsPath!, source.storedName);
  fs.writeFileSync(sourcePath, "Invoice A1\nTotal 999");
  assert.equal((await confirm("alice", { expectedRevision: 2, expectedPayloadSha256: draft.payload_sha256 })).status, 409);
  assert.throws(() => requireCurrentProductAutoBrief(job.jobId, 3, confirmed.payload_sha256), /changed/);
  fs.writeFileSync(sourcePath, "Invoice A1\nTotal 100");
  const edited = await save({ expectedRevision: 3, intent: "New direction", fields: draft.fields,
    sampleFileIds: [source.fileId] });
  const editedBrief = (await edited.json()).brief;
  assert.equal(editedBrief.state, "draft");
  assert.equal(editedBrief.revision, 4);
}));
