import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { loadRunnerConfig, resetConfigCacheForTests } from "./config";
import { createWorkspaceJob, listJobs } from "./jobs";

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
