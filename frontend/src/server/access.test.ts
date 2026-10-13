import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { GET as listJobsRoute, POST as createJobRoute } from "@/app/api/jobs/route";
import { GET as getJobRoute, PATCH as patchJobRoute } from "@/app/api/jobs/[jobId]/route";
import { POST as uploadDocumentsRoute } from "@/app/api/jobs/[jobId]/documents/route";
import { GET as getDocumentContentRoute } from "@/app/api/jobs/[jobId]/docs/[docId]/content/route";
import { GET as getJobDocumentRoute, POST as reviewJobDocumentRoute } from "@/app/api/jobs/[jobId]/docs/[docId]/route";
import { GET as getRunSummaryRoute } from "@/app/api/runs/[runId]/summary/route";
import { POST as startRunsRoute } from "@/app/api/jobs/[jobId]/runs/route";
import { POST as createPolicyRoute, PATCH as togglePolicyRoute } from "@/app/api/jobs/[jobId]/policies/route";
import { POST as autoReviewRoute } from "@/app/api/jobs/[jobId]/validate/route";
import { GET as listBenchmarksRoute } from "@/app/api/benchmarks/route";
import { GET as getSystemStatusRoute } from "@/app/api/system/status/route";
import { resetConfigCacheForTests } from "./config";
import { getRunDocument, readRunOcrText } from "./artifacts";
import { createWorkspaceJob, getJob, mutateJob, updateJob } from "./jobs";
import { readReviewArtifact, writeReviewArtifact, type ReviewArtifact } from "./review";
import { sanitizeDocumentId, sanitizeRunId } from "./paths";

const users: Record<string, { id: string; role: string }> = {
  alice: { id: "alice-id", role: "viewer" },
  bob: { id: "bob-id", role: "viewer" },
  admin: { id: "admin-id", role: "admin" },
};

function request(pathname: string, token?: keyof typeof users, init?: RequestInit): Request {
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return new Request(`http://localhost${pathname}`, { ...init, headers });
}

async function withStorage(run: () => Promise<void>): Promise<void> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-access-"));
  const oldDataDir = process.env.IDPO_DATA_DIR;
  const oldGateway = process.env.INTERNAL_API_URL;
  const oldFetch = globalThis.fetch;
  process.env.IDPO_DATA_DIR = path.join(root, "data");
  process.env.INTERNAL_API_URL = "http://test-gateway.local";
  resetConfigCacheForTests();
  globalThis.fetch = async (input, init) => {
    if (String(input) === "http://test-gateway.local/api/auth/me") {
      const token = new Headers(init?.headers).get("Authorization")?.replace(/^Bearer /, "") ?? "";
      return users[token] ? Response.json(users[token]) : Response.json({ detail: "Invalid token" }, { status: 401 });
    }
    return oldFetch(input, init);
  };
  try {
    await run();
  } finally {
    globalThis.fetch = oldFetch;
    if (oldGateway === undefined) delete process.env.INTERNAL_API_URL;
    else process.env.INTERNAL_API_URL = oldGateway;
    if (oldDataDir === undefined) delete process.env.IDPO_DATA_DIR;
    else process.env.IDPO_DATA_DIR = oldDataDir;
    resetConfigCacheForTests();
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("jobs are owned, isolated, and cannot be reassigned by a patch", async () => withStorage(async () => {
  const unauthenticated = await createJobRoute(request("/api/jobs", undefined, { method: "POST" }));
  assert.equal(unauthenticated.status, 401);

  const created = await createJobRoute(request("/api/jobs", "alice", { method: "POST" }));
  assert.equal(created.status, 201);
  const job = await created.json() as { jobId: string; ownerUserId: string };
  assert.equal(job.ownerUserId, "alice-id");
  assert.equal(getJob(job.jobId)?.ownerUserId, "alice-id");

  const aliceList = await listJobsRoute(request("/api/jobs", "alice"));
  assert.deepEqual((await aliceList.json()).jobs.map((item: { jobId: string }) => item.jobId), [job.jobId]);
  const bobList = await listJobsRoute(request("/api/jobs", "bob"));
  assert.deepEqual((await bobList.json()).jobs, []);
  assert.equal((await getJobRoute(request(`/api/jobs/${job.jobId}`, "bob"),
    { params: Promise.resolve({ jobId: job.jobId }) })).status, 404);

  const deniedPatch = await patchJobRoute(request(`/api/jobs/${job.jobId}`, "bob", {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ jobName: "stolen" }),
  }), { params: Promise.resolve({ jobId: job.jobId }) });
  assert.equal(deniedPatch.status, 404);
  assert.notEqual(getJob(job.jobId)?.jobName, "stolen");

  updateJob(job.jobId, { ownerUserId: "bob-id" });
  mutateJob(job.jobId, (current) => ({ ...current, ownerUserId: "bob-id" }));
  assert.equal(getJob(job.jobId)?.ownerUserId, "alice-id");
}));

test("original documents and run IDs are private to the job owner", async () => withStorage(async () => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const upload = await uploadDocumentsRoute(request(`/api/jobs/${job.jobId}/documents`, "alice", {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream", "X-File-Name": "invoice.txt" },
    body: "Total: 100",
  }), { params: Promise.resolve({ jobId: job.jobId }) });
  assert.equal(upload.status, 201);
  const documentId = (await upload.json()).documents[0].fileId as string;
  const params = { params: Promise.resolve({ jobId: job.jobId, docId: documentId }) };
  assert.equal((await getDocumentContentRoute(request(`/api/jobs/${job.jobId}/docs/${documentId}/content`, "bob"), params)).status, 404);
  const original = await getDocumentContentRoute(request(`/api/jobs/${job.jobId}/docs/${documentId}/content`, "alice"), params);
  assert.equal(original.status, 200);
  assert.equal(await original.text(), "Total: 100");

  updateJob(job.jobId, { runId: "alice-run", latestRunId: "alice-run" });
  const runParams = { params: Promise.resolve({ runId: "alice-run" }) };
  assert.equal((await getRunSummaryRoute(request("/api/runs/alice-run/summary", "bob"), runParams)).status, 404);
}));

test("original document content stays inside the configured uploads root", async (t) => withStorage(async () => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const upload = await uploadDocumentsRoute(request(`/api/jobs/${job.jobId}/documents`, "alice", {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream", "X-File-Name": "invoice.txt" },
    body: "ORIGINAL",
  }), { params: Promise.resolve({ jobId: job.jobId }) });
  assert.equal(upload.status, 201);
  const uploadedJob = await upload.json();
  const document = uploadedJob.documents[0] as { fileId: string; storedName: string };
  const uploadsPath = uploadedJob.uploadsPath as string;
  const url = `/api/jobs/${job.jobId}/docs/${document.fileId}/content`;
  const params = { params: Promise.resolve({ jobId: job.jobId, docId: document.fileId }) };
  const original = await getDocumentContentRoute(request(url, "alice"), params);
  assert.equal(original.status, 200);
  assert.equal(await original.text(), "ORIGINAL");

  const outsideDir = path.join(process.env.IDPO_DATA_DIR!, "outside-uploads");
  fs.mkdirSync(outsideDir);
  fs.writeFileSync(path.join(outsideDir, document.storedName), "OUTSIDE_PRIVATE_BYTES");
  const movedUploadsPath = `${uploadsPath}.audit-original`;
  fs.renameSync(uploadsPath, movedUploadsPath);
  try {
    try {
      fs.symlinkSync(outsideDir, uploadsPath, process.platform === "win32" ? "junction" : "dir");
    } catch (error) {
      if (error && typeof error === "object" && "code" in error &&
        ["EPERM", "EACCES", "ENOTSUP"].includes(String(error.code))) {
        t.skip(`Directory links unavailable: ${String(error.code)}`);
        return;
      }
      throw error;
    }
    const denied = await getDocumentContentRoute(request(url, "alice"), params);
    assert.equal(denied.status, 400);
    assert.doesNotMatch(await denied.text(), /OUTSIDE_PRIVATE_BYTES/);
    assert.equal((await getDocumentContentRoute(request(url, "bob"), params)).status, 404);
  } finally {
    if (fs.existsSync(uploadsPath)) fs.unlinkSync(uploadsPath);
    fs.renameSync(movedUploadsPath, uploadsPath);
  }
}));

test("run artifact paths cannot cross owners through a decoded document ID", async () => withStorage(async () => {
  const aliceJob = createWorkspaceJob({ ownerUserId: "alice-id" });
  const bobJob = createWorkspaceJob({ ownerUserId: "bob-id" });
  const aliceRun = "alice-run";
  const bobRun = "bob-run";
  updateJob(aliceJob.jobId, { runId: aliceRun, latestRunId: aliceRun });
  updateJob(bobJob.jobId, { runId: bobRun, latestRunId: bobRun });
  const dataDir = process.env.IDPO_DATA_DIR!;
  const aliceDocDir = path.join(dataDir, "runs", aliceRun, "primary", "docs", "alice-doc", "structuring");
  const bobDocDir = path.join(dataDir, "runs", bobRun, "primary", "docs", "bob-doc", "structuring");
  fs.mkdirSync(aliceDocDir, { recursive: true });
  fs.mkdirSync(bobDocDir, { recursive: true });
  fs.writeFileSync(path.join(aliceDocDir, "extracted.json"), JSON.stringify({ fields: [{ key: "id", value: "ALICE" }] }));
  fs.writeFileSync(path.join(bobDocDir, "extracted.json"), JSON.stringify({ fields: [{ key: "id", value: "BOB_PRIVATE" }] }));

  const { requireRun } = await import("./access");
  requireRun(aliceRun, users.alice);
  assert.throws(() => requireRun(bobRun, users.alice), /Run not found/);
  assert.match(JSON.stringify(getRunDocument(aliceRun, "alice-doc")), /ALICE/);

  const traversal = `../../../${bobRun}/primary/docs/bob-doc`;
  const twiceEncoded = encodeURIComponent(encodeURIComponent(traversal));
  const decodedRouteParam = decodeURIComponent(decodeURIComponent(twiceEncoded));
  assert.equal(decodedRouteParam, traversal);
  for (const maliciousId of [traversal, decodedRouteParam, "..\\..\\..\\bob-run\\primary\\docs\\bob-doc", ".", ".."]) {
    assert.throws(() => getRunDocument(aliceRun, maliciousId), /Invalid docId/);
    assert.equal(readRunOcrText(aliceRun, maliciousId), "");
    assert.equal(readReviewArtifact(aliceRun, maliciousId), null);
    assert.throws(() => writeReviewArtifact({ runId: aliceRun, docId: maliciousId } as ReviewArtifact), /Invalid docId/);
  }
  assert.throws(() => sanitizeRunId(".."), /Invalid runId/);
  const legacyPrimary = path.join(dataDir, "runs", "legacy-run", "primary");
  fs.mkdirSync(path.join(legacyPrimary, "extract"), { recursive: true });
  fs.writeFileSync(path.join(legacyPrimary, "extract", "safe.json"), JSON.stringify({ fields: [] }));
  assert.match(JSON.stringify(getRunDocument("legacy-run", "safe")), /safe/);
  assert.throws(() => getRunDocument("legacy-run", traversal), /Invalid docId/);
  assert.equal(fs.existsSync(path.join(dataDir, "runs", bobRun, "primary", "docs", "bob-doc", "review", "results.json")), false);
}));

test("run artifact paths reject a document-directory link outside the run", async (t) => withStorage(async () => {
  const dataDir = process.env.IDPO_DATA_DIR!;
  const ownDocs = path.join(dataDir, "runs", "own-run", "primary", "docs");
  const otherDoc = path.join(dataDir, "runs", "other-run", "primary", "docs", "private-doc");
  fs.mkdirSync(ownDocs, { recursive: true });
  fs.mkdirSync(otherDoc, { recursive: true });
  try {
    fs.symlinkSync(otherDoc, path.join(ownDocs, "linked-doc"), process.platform === "win32" ? "junction" : "dir");
  } catch (error) {
    if (error && typeof error === "object" && "code" in error &&
      ["EPERM", "EACCES", "ENOTSUP"].includes(String(error.code))) {
      t.skip(`Directory links unavailable: ${String(error.code)}`);
      return;
    }
    throw error;
  }
  assert.throws(() => getRunDocument("own-run", "linked-doc"), /Path traversal blocked/);
  assert.throws(() => writeReviewArtifact({ runId: "own-run", docId: "linked-doc" } as ReviewArtifact),
    /Path traversal blocked/);
}));

test("document IDs reject Windows device names and blank aliases while preserving ordinary IDs", () => {
  for (const docId of ["CON", "con.txt", "NUL.tar.gz", "PrN.json", "AUX", "COM1", "com9.pdf",
    "LPT1", "lpt9.txt", "COM¹.txt", "lpt²", "CON .txt", " ", "\u00a0", "receipt "]) {
    assert.throws(() => sanitizeDocumentId(docId), /Invalid docId/, docId);
  }
  for (const docId of ["COM10", "LPT0", "invoice_con.txt", "context", " leading-doc", "a".repeat(32)]) {
    assert.equal(sanitizeDocumentId(docId), docId);
  }
});

test("document detail and human review routes enforce the job owner", async () => withStorage(async () => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id", fieldConfigCurrent: [{ name: "invoice_number" }] });
  const upload = await uploadDocumentsRoute(request(`/api/jobs/${job.jobId}/documents`, "alice", {
    method: "POST", headers: { "Content-Type": "application/octet-stream", "X-File-Name": "invoice.txt" },
    body: "Invoice number: INV-001",
  }), { params: Promise.resolve({ jobId: job.jobId }) });
  assert.equal(upload.status, 201);
  const fileId = (await upload.json()).documents[0].fileId as string;
  const runId = "alice-review-run";
  const docId = "alice-review-doc";
  const documentDir = path.join(process.env.IDPO_DATA_DIR!, "runs", runId, "primary", "docs", docId);
  fs.mkdirSync(path.join(documentDir, "structuring"), { recursive: true });
  fs.writeFileSync(path.join(documentDir, "structuring", "extracted.json"),
    JSON.stringify({ fields: [{ key: "invoice_number", value: "INV-001" }] }));
  mutateJob(job.jobId, (current) => {
    const document = current.documents!.find((entry) => entry.fileId === fileId)!;
    document.status = "processed";
    document.latestRunId = runId;
    document.latestDocId = docId;
    document.outcomes = [{
      runId, mode: "adaptive", docId, status: "processed", route: null, policy: null,
      errorSummary: null, reviewState: null, fieldValues: { invoice_number: "INV-001" },
      adviceInfluenced: false, feedbackLogged: false,
    }];
    return current;
  });
  const route = `/api/jobs/${job.jobId}/docs/${fileId}`;
  const params = { params: Promise.resolve({ jobId: job.jobId, docId: fileId }) };
  assert.equal((await getJobDocumentRoute(request(route, "bob"), params)).status, 404);
  assert.equal((await getJobDocumentRoute(request(route, "alice"), params)).status, 200);

  const reviewRequest = (token: keyof typeof users) => request(route, token, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ runId, fields: [{ fieldKey: "invoice_number", extractedValue: "INV-001", reviewState: "correct" }] }),
  });
  assert.equal((await reviewJobDocumentRoute(reviewRequest("bob"), params)).status, 404);
  assert.equal(readReviewArtifact(runId, docId), null);
  assert.equal((await reviewJobDocumentRoute(reviewRequest("alice"), params)).status, 200);
  assert.equal(readReviewArtifact(runId, docId)?.reviewSource, "human");
}));

test("unowned legacy jobs and research diagnostics require admin access", async () => withStorage(async () => {
  const legacy = createWorkspaceJob();
  assert.equal((await getJobRoute(request(`/api/jobs/${legacy.jobId}`, "alice"),
    { params: Promise.resolve({ jobId: legacy.jobId }) })).status, 404);
  assert.equal((await getJobRoute(request(`/api/jobs/${legacy.jobId}`, "admin"),
    { params: Promise.resolve({ jobId: legacy.jobId }) })).status, 200);
  assert.equal((await listBenchmarksRoute(request("/api/benchmarks", "alice"))).status, 403);
  assert.equal((await getSystemStatusRoute(request("/api/system/status", "alice"))).status, 403);
}));

test("viewers cannot select paid or unbounded run settings or change policies", async () => withStorage(async () => {
  const job = createWorkspaceJob({ ownerUserId: "alice-id" });
  const params = { params: Promise.resolve({ jobId: job.jobId }) };
  const run = (settings: Record<string, unknown>, token: keyof typeof users = "alice") =>
    startRunsRoute(request(`/api/jobs/${job.jobId}/runs`, token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selectedFileIds: [], settings }),
    }), params);

  for (const settings of [
    { llmDefaultMode: "cloud" },
    { llmCloudModel: "gpt-4.1" },
    { flagshipModel: "gpt-4.1" },
    { llmLocalModel: "oversized:latest" },
    { autoInstallLocalModel: true },
    { escalationEnabled: true },
    { apiKeys: { openai: "secret" } },
    { configPath: "configs/another_config.json" },
  ]) {
    assert.equal((await run(settings)).status, 403, JSON.stringify(settings));
  }
  assert.equal((await run({ configPath: "configs/idpo_research_config.json", escalationEnabled: false })).status, 400);
  assert.equal((await run({ llmDefaultMode: "cloud" }, "admin")).status, 400);

  const viewerModelPatch = await patchJobRoute(request(`/api/jobs/${job.jobId}`, "alice", {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ settings: { llmLocalModel: "oversized:latest" } }),
  }), params);
  assert.equal(viewerModelPatch.status, 403);

  const createPolicy = (token: keyof typeof users) => createPolicyRoute(request(`/api/jobs/${job.jobId}/policies`, token, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policyId: "cloud_custom", name: "Cloud", executionProfile: "cloud_extension" }),
  }), params);
  assert.equal((await createPolicy("alice")).status, 403);

  const togglePolicy = await togglePolicyRoute(request(`/api/jobs/${job.jobId}/policies`, "alice", {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policyId: "cloud_custom", enabled: true }),
  }), params);
  assert.equal(togglePolicy.status, 403);
  assert.equal((await autoReviewRoute(request(`/api/jobs/${job.jobId}/validate`, "alice", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ selectedFileIds: [] }),
  }), params)).status, 403);
}));
