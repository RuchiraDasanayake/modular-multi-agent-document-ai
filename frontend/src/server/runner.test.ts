import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import type { AddressInfo } from "node:net";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { resetConfigCacheForTests } from "./config";
import { createWorkspaceJob, getJob, mutateJob } from "./jobs";
import { maybeInstallLocalModel, patchConfig, syncActiveJobProgress } from "./runner";

test("viewer runtime settings disable cloud paths even when the base config enables them", () => {
  const config = patchConfig({
    llm: {
      default_mode: "cloud",
      history_mode: "cloud",
      provider: "openai",
      allow_cloud_fallback: true,
      enable_flagship_fallback: true,
      description_refinement_use_cloud: true,
    },
    escalation: { enabled: true },
  }, { forceLocalOnly: true }, "viewer-job");
  assert.deepEqual(config.llm, {
    default_mode: "local",
    history_mode: "local",
    provider: "ollama",
    allow_cloud_fallback: false,
    enable_flagship_fallback: false,
    description_refinement_use_cloud: false,
  });
  assert.deepEqual(config.escalation, { enabled: false });
});

interface FakeOllama {
  baseUrl: string;
  pulls: Array<Record<string, unknown>>;
  close: () => Promise<void>;
}

async function startFakeOllama(installed: string[]): Promise<FakeOllama> {
  const pulls: Array<Record<string, unknown>> = [];
  const server = http.createServer((request, response) => {
    if (request.method === "GET" && request.url === "/api/tags") {
      response.setHeader("Content-Type", "application/json");
      response.end(JSON.stringify({ models: installed.map((name) => ({ name })) }));
      return;
    }
    if (request.method === "POST" && request.url === "/api/pull") {
      let body = "";
      request.on("data", (chunk) => (body += chunk));
      request.on("end", () => {
        pulls.push(JSON.parse(body) as Record<string, unknown>);
        response.setHeader("Content-Type", "application/x-ndjson");
        response.write(`${JSON.stringify({ status: "pulling manifest" })}\n`);
        response.end(`${JSON.stringify({ status: "success" })}\n`);
      });
      return;
    }
    response.statusCode = 404;
    response.end();
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return {
    baseUrl: `http://127.0.0.1:${port}`,
    pulls,
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

async function withJob(run: (jobId: string, runtimeConfigFor: (baseUrl: string) => string) => Promise<void>) {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-runner-model-"));
  process.env.IDPO_DATA_DIR = path.join(tmpRoot, "idpo-data");
  resetConfigCacheForTests();
  try {
    const job = createWorkspaceJob({ jobName: "Model Job", mode: "adaptive" });
    const runtimeConfigFor = (baseUrl: string) => {
      const configPath = path.join(tmpRoot, "runtime_config.json");
      fs.writeFileSync(configPath, JSON.stringify({ llm: { base_url: `${baseUrl}/` } }), "utf-8");
      return configPath;
    };
    await run(job.jobId, runtimeConfigFor);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
}

test("a local model that is already installed is not pulled again", async () => {
  const ollama = await startFakeOllama(["qwen3.5:9b", "phi3:mini"]);
  try {
    await withJob(async (jobId, runtimeConfigFor) => {
      await maybeInstallLocalModel(
        jobId,
        { llmLocalModel: "phi3:mini", autoInstallLocalModel: true },
        runtimeConfigFor(ollama.baseUrl),
      );

      assert.equal(ollama.pulls.length, 0);
      assert.ok(getJob(jobId)?.logs.some((line) => line.includes("local model already present: phi3:mini")));
    });
  } finally {
    await ollama.close();
  }
});

test("progress sync waits quietly until the pipeline creates the run folder", async () => {
  await withJob(async (jobId) => {
    mutateJob(jobId, (job) => {
      job.status = "running";
      job.documents = [
        {
          fileId: "file1",
          fileName: "receipt.png",
          storedName: "file1__receipt.png",
          size: 10,
          selected: true,
          status: "processing",
          errorSummary: null,
          reviewState: null,
          reviewStatus: "unreviewed",
          reviewSource: null,
          latestRoute: null,
          latestPolicy: null,
          latestRunId: null,
          latestDocId: null,
          createdAt: job.createdAt,
          updatedAt: job.createdAt,
          outcomes: [],
        },
      ];
      job.runs = [
        {
          jobRunId: "jobrun1",
          runId: "run_not_created_yet",
          mode: "adaptive",
          status: "running",
          createdAt: job.createdAt,
          fieldSnapshot: [],
          selectedFileIds: ["file1"],
          runPath: null,
          error: null,
        },
      ];
      return job;
    });

    const synced = syncActiveJobProgress(jobId);
    assert.equal(synced.status, "running");
    assert.equal(synced.documents?.[0]?.status, "processing");
  });
});

test("a missing local model is pulled through the Ollama HTTP API", async () => {
  const ollama = await startFakeOllama(["qwen3.5:9b"]);
  try {
    await withJob(async (jobId, runtimeConfigFor) => {
      await maybeInstallLocalModel(
        jobId,
        { llmLocalModel: "phi3:mini", autoInstallLocalModel: true },
        runtimeConfigFor(ollama.baseUrl),
      );

      assert.deepEqual(ollama.pulls, [{ model: "phi3:mini", stream: true }]);
      assert.ok(getJob(jobId)?.logs.some((line) => line.includes("model pull complete: phi3:mini")));
    });
  } finally {
    await ollama.close();
  }
});
