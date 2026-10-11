import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { GET as getJobDocumentTextRoute } from "@/app/api/jobs/[jobId]/docs/[docId]/text/route";
import { POST as postJobDocumentsRoute } from "@/app/api/jobs/[jobId]/documents/route";
import { PATCH as patchJobRoute } from "@/app/api/jobs/[jobId]/route";
import { loadRunnerConfig, resetConfigCacheForTests } from "./config";
import { createWorkspaceJob, getJob, listJobs, setJobRunning } from "./jobs";

const originalFetch = globalThis.fetch;
const originalGatewayUrl = process.env.INTERNAL_API_URL;

test.before(() => {
  process.env.INTERNAL_API_URL = "http://test-gateway.local";
  globalThis.fetch = async (input, init) => {
    if (String(input) === "http://test-gateway.local/api/auth/me") {
      const token = new Headers(init?.headers).get("authorization");
      return token === "Bearer test-token"
        ? Response.json({ id: "test-user", role: "admin" })
        : Response.json({ detail: "Invalid token" }, { status: 401 });
    }
    return originalFetch(input, init);
  };
});

test.after(() => {
  globalThis.fetch = originalFetch;
  if (originalGatewayUrl === undefined) delete process.env.INTERNAL_API_URL;
  else process.env.INTERNAL_API_URL = originalGatewayUrl;
});

function authenticatedRequest(input: string, init?: RequestInit): Request {
  const headers = new Headers(init?.headers);
  headers.set("Authorization", "Bearer test-token");
  return new Request(input, { ...init, headers });
}

test("listJobs ignores non-job artifacts in the jobs directory", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-jobs-list-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const config = loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Real Job",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

    const artifactPayload = {
      jobId: job.jobId,
      source: "artifact",
      current: { version: 1 },
    };
    fs.writeFileSync(
      path.join(config.jobsDir, `${job.jobId}_validation_context.json`),
      JSON.stringify(artifactPayload, null, 2),
      "utf-8",
    );
    fs.writeFileSync(
      path.join(config.jobsDir, `${job.jobId}_effective_policies.json`),
      JSON.stringify({ default_policy_id: "default", policies: [] }, null, 2),
      "utf-8",
    );
    fs.writeFileSync(
      path.join(config.jobsDir, `${job.jobId}_runtime_config.json`),
      JSON.stringify({ commandId: "idpo-research" }, null, 2),
      "utf-8",
    );

    const jobs = listJobs(100);
    const matches = jobs.filter((entry) => entry.jobId === job.jobId);
    assert.equal(matches.length, 1);
    assert.equal(matches[0]?.jobName, "Real Job");
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("job patch stores and clears the local model override", async () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-job-settings-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const job = createWorkspaceJob({
      jobName: "Local Model Job",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

    const setResponse = await patchJobRoute(
      authenticatedRequest(`http://localhost/api/jobs/${job.jobId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          settings: {
            llmLocalModel: "qwen3:8b",
          },
        }),
      }),
      { params: Promise.resolve({ jobId: job.jobId }) },
    );

    assert.equal(setResponse.status, 200);
    const updated = (await setResponse.json()) as { settings: Record<string, unknown> };
    assert.equal(updated.settings.llmLocalModel, "qwen3:8b");

    const clearResponse = await patchJobRoute(
      authenticatedRequest(`http://localhost/api/jobs/${job.jobId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          settings: {
            llmLocalModel: "",
          },
        }),
      }),
      { params: Promise.resolve({ jobId: job.jobId }) },
    );

    assert.equal(clearResponse.status, 200);
    const cleared = (await clearResponse.json()) as { settings: Record<string, unknown> };
    assert.equal("llmLocalModel" in cleared.settings, false);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("job documents route accepts octet-stream file uploads", async () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-job-upload-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const job = createWorkspaceJob({
      jobName: "Upload Job",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "total_amount" }],
    });

    const response = await postJobDocumentsRoute(
      authenticatedRequest(`http://localhost/api/jobs/${job.jobId}/documents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-File-Name": "receipt.txt",
          "X-File-Type": "text/plain",
        },
        body: Buffer.from("Total Amount: 10.00", "utf-8"),
      }),
      { params: Promise.resolve({ jobId: job.jobId }) },
    );

    assert.equal(response.status, 201);
    const updated = (await response.json()) as { documents: Array<{ fileName: string; storedName: string }>; uploadsPath: string };
    assert.equal(updated.documents.length, 1);
    assert.equal(updated.documents[0]?.fileName, "receipt.txt");
    const uploadedPath = path.join(updated.uploadsPath, updated.documents[0]!.storedName);
    assert.equal(fs.existsSync(uploadedPath), true);
    assert.equal(fs.readFileSync(uploadedPath, "utf-8"), "Total Amount: 10.00");
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("listJobs preserves benchmark expected field values on saved outcomes", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-job-expected-values-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const config = loadRunnerConfig();
    const jobId = "11111111111111111111111111111111";
    const createdAt = "2026-04-24T12:00:00.000Z";
    const uploadsPath = path.join(config.uploadsDir, `job_${jobId}`);
    fs.mkdirSync(uploadsPath, { recursive: true });

    fs.writeFileSync(
      path.join(config.jobsDir, `${jobId}.json`),
      JSON.stringify(
        {
          jobId,
          status: "success",
          createdAt,
          startedAt: createdAt,
          endedAt: createdAt,
          commandId: config.defaultCommandId,
          runId: "run-1",
          runPath: null,
          logs: [],
          settings: {},
          jobName: "Benchmark Review Job",
          mode: "adaptive",
          fieldConfigCurrent: [{ name: "total_amount" }, { name: "cash_amount" }],
          documents: [
            {
              fileId: "doc-1",
              fileName: "receipt.png",
              storedName: "receipt.png",
              size: 10,
              selected: true,
              status: "processed",
              errorSummary: null,
              reviewState: "human_reviewed | F1 1.00",
              reviewStatus: "human_reviewed",
              reviewSource: "human",
              reviewStage: null,
              reviewConfidence: null,
              latestRoute: "heavy",
              latestPolicy: "noisy_ocr_rescue",
              latestRunId: "run-1",
              latestDocId: "doc-runtime-1",
              createdAt,
              updatedAt: createdAt,
              outcomes: [
                {
                  runId: "run-1",
                  mode: "adaptive",
                  docId: "doc-runtime-1",
                  status: "processed",
                  route: "heavy",
                  policy: "noisy_ocr_rescue",
                  errorSummary: null,
                  reviewState: "human_reviewed | F1 1.00",
                  reviewStatus: "human_reviewed",
                  reviewSource: "human",
                  reviewStage: null,
                  reviewConfidence: null,
                  fieldValues: {
                    total_amount: "28,000",
                    cash_amount: "28,000",
                  },
                  expectedFieldValues: {
                    total_amount: "28,000",
                    cash_amount: "28,000",
                  },
                  adviceInfluenced: false,
                  feedbackLogged: true,
                  fallbackReason: "policy_gate_violation",
                  exactPrecision: 1,
                  exactRecall: 1,
                  exactF1: 1,
                },
              ],
            },
          ],
          runs: [],
          ahmnSummary: {
            jobProfile: "benchmark",
            memoryMatched: false,
            documentsWithAdvice: 1,
            documentsLoggedBack: 1,
            adviceInfluencedCount: 0,
            reviewedDocumentCount: 1,
            reviewedHumanCount: 1,
            reviewedAiCount: 0,
            reviewedFeedbackLoggedCount: 1,
            reviewedFeedbackPendingCount: 0,
            jobOverlayPolicies: 0,
            jobOverlayReady: false,
            adaptationSummary: "Benchmark-backed review",
          },
          counts: {
            loadedCount: 0,
            processingCount: 0,
            processedCount: 1,
            failedCount: 0,
          },
          latestRunId: "run-1",
          uploadsPath,
        },
        null,
        2,
      ),
      "utf-8",
    );

    const jobs = listJobs(10);
    const job = jobs.find((entry) => entry.jobId === jobId);
    assert.ok(job);
    assert.deepEqual(job.documents?.[0]?.outcomes[0]?.expectedFieldValues, {
      total_amount: "28,000",
      cash_amount: "28,000",
    });
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("a running job left behind by a previous server process is marked interrupted", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-jobs-interrupted-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const config = loadRunnerConfig();
    const live = createWorkspaceJob({ jobName: "Live", mode: "adaptive", fieldConfigCurrent: [] });
    setJobRunning(live.jobId);
    assert.equal(getJob(live.jobId)?.status, "running");

    const orphan = createWorkspaceJob({ jobName: "Orphan", mode: "adaptive", fieldConfigCurrent: [] });
    const orphanFile = path.join(config.jobsDir, `${orphan.jobId}.json`);
    const stored = JSON.parse(fs.readFileSync(orphanFile, "utf-8")) as Record<string, unknown>;
    fs.writeFileSync(
      orphanFile,
      JSON.stringify({
        ...stored,
        status: "running",
        serverInstanceId: "previous-process",
        runs: [{ jobRunId: "jr-1", mode: "adaptive", status: "running", createdAt: stored.createdAt, selectedFileIds: [] }],
      }),
      "utf-8",
    );

    const reloaded = getJob(orphan.jobId);
    assert.equal(reloaded?.status, "failed");
    assert.match(String(reloaded?.error), /Interrupted/);
    assert.equal(reloaded?.runs?.[0]?.status, "failed");
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("getJob refuses ids that point outside the jobs folder", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-jobs-traversal-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const config = loadRunnerConfig();
    const real = createWorkspaceJob({ jobName: "Real", mode: "adaptive", fieldConfigCurrent: [] });
    const outsideFile = path.join(config.jobsDir, "..", "outside.json");
    fs.writeFileSync(outsideFile, JSON.stringify({ jobId: "outside", status: "draft", documents: [] }), "utf-8");

    assert.equal(getJob("../outside"), null);
    assert.equal(getJob(real.jobId)?.jobName, "Real");
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("document text route returns the OCR text of the latest run", async () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-job-doc-text-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const config = loadRunnerConfig();
    const job = createWorkspaceJob({ jobName: "Text Job", mode: "adaptive", fieldConfigCurrent: [] });
    const jobFile = path.join(config.jobsDir, `${job.jobId}.json`);
    const stored = JSON.parse(fs.readFileSync(jobFile, "utf-8")) as Record<string, unknown>;
    const createdAt = String(stored.createdAt);
    fs.writeFileSync(
      jobFile,
      JSON.stringify({
        ...stored,
        documents: [
          {
            fileId: "doc-1",
            fileName: "receipt.png",
            storedName: "receipt.png",
            size: 10,
            selected: true,
            status: "processed",
            errorSummary: null,
            reviewState: null,
            latestRoute: "light",
            latestPolicy: "default",
            latestRunId: "run-ocr",
            latestDocId: "doc-runtime-1",
            createdAt,
            updatedAt: createdAt,
            outcomes: [],
          },
        ],
      }),
      "utf-8",
    );
    const ocrDir = path.join(config.runsDir, "run-ocr", "primary", "docs", "doc-runtime-1", "preprocessing", "ocr");
    fs.mkdirSync(ocrDir, { recursive: true });
    fs.writeFileSync(
      path.join(ocrDir, "text.json"),
      JSON.stringify({ pages: [{ text: " TOTAL 28,000 " }, { text: "" }, { text: "Thank you" }] }),
      "utf-8",
    );

    const response = await getJobDocumentTextRoute(authenticatedRequest("http://localhost/api/jobs/x/docs/doc-1/text"), {
      params: Promise.resolve({ jobId: job.jobId, docId: "doc-1" }),
    });
    assert.equal(response.status, 200);
    const payload = (await response.json()) as Record<string, unknown>;
    assert.equal(payload.fileName, "receipt.png");
    assert.equal(payload.text, "TOTAL 28,000\n\nThank you");
    assert.equal(payload.truncated, false);

    const missing = await getJobDocumentTextRoute(authenticatedRequest("http://localhost/api/jobs/x/docs/nope/text"), {
      params: Promise.resolve({ jobId: job.jobId, docId: "nope" }),
    });
    assert.equal(missing.status, 404);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});
