import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { GET as listJobsRoute, POST as createJobRoute } from "@/app/api/jobs/route";
import { GET as getJobRoute, PATCH as patchJobRoute } from "@/app/api/jobs/[jobId]/route";
import { POST as uploadDocumentsRoute } from "@/app/api/jobs/[jobId]/documents/route";
import { GET as getDocumentContentRoute } from "@/app/api/jobs/[jobId]/docs/[docId]/content/route";
import { GET as getRunSummaryRoute } from "@/app/api/runs/[runId]/summary/route";
import { POST as startRunsRoute } from "@/app/api/jobs/[jobId]/runs/route";
import { POST as createPolicyRoute, PATCH as togglePolicyRoute } from "@/app/api/jobs/[jobId]/policies/route";
import { POST as autoReviewRoute } from "@/app/api/jobs/[jobId]/validate/route";
import { GET as listBenchmarksRoute } from "@/app/api/benchmarks/route";
import { GET as getSystemStatusRoute } from "@/app/api/system/status/route";
import { resetConfigCacheForTests } from "./config";
import { createWorkspaceJob, getJob, mutateJob, updateJob } from "./jobs";

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
