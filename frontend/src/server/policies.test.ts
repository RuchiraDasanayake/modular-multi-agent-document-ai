import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { loadRunnerConfig, resetConfigCacheForTests } from "./config";
import { createWorkspaceJob, mutateJob } from "./jobs";
import {
  createJobCustomPolicy,
  ensureJobEffectivePolicyStore,
  getJobPolicyDetail,
  listJobPolicies,
} from "./policies";

test("job policy workspace merges custom policies and reports usage", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-job-policies-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Policy Workspace",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

    const created = createJobCustomPolicy(job.jobId, {
      policyId: "vendor_fast_local",
      name: "Vendor Fast Local",
      executionProfile: "fast_local",
      instructions: "Prefer the local path for this vendor.",
      routeBins: ["standard"],
      vendorClusters: ["acme"],
      explicitEntities: ["invoice_number", "total_amount"],
    });

    assert.equal(created.policyId, "vendor_fast_local");
    assert.equal(created.source, "custom");

    mutateJob(job.jobId, (current) => {
      current.documents = [
        {
          fileId: "file-1",
          fileName: "invoice-1.pdf",
          storedName: "file-1__invoice-1.pdf",
          size: 10,
          selected: true,
          status: "processed",
          errorSummary: null,
          reviewState: "human_reviewed | F1 1.00",
          reviewStatus: "human_reviewed",
          reviewSource: "human",
          latestRoute: "standard",
          latestPolicy: "vendor_fast_local",
          latestRunId: "run-1",
          latestDocId: "doc-1",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          outcomes: [
            {
              runId: "run-1",
              mode: "adaptive",
              docId: "doc-1",
              status: "processed",
              route: "standard",
              policy: "vendor_fast_local",
              errorSummary: null,
              reviewState: "human_reviewed | F1 1.00",
              reviewStatus: "human_reviewed",
              reviewSource: "human",
              fieldValues: { invoice_number: "INV-001" },
              adviceInfluenced: true,
              feedbackLogged: true,
              fallbackReason: null,
              exactPrecision: 1,
              exactRecall: 1,
              exactF1: 1,
            },
          ],
        },
      ];
      return current;
    });

    const workspace = listJobPolicies(job.jobId);
    const customSummary = workspace.policies.find((policy) => policy.policyId === "vendor_fast_local");
    assert.ok(customSummary);
    assert.equal(customSummary.source, "custom");
    assert.equal(customSummary.documentsProcessed, 1);
    assert.equal(customSummary.reviewedDocuments, 1);
    assert.equal(customSummary.meanExactF1, 1);
    assert.equal(customSummary.learningState, "watch");

    const detail = getJobPolicyDetail(job.jobId, "vendor_fast_local");
    assert.ok(detail);
    assert.equal(detail.usages.length, 1);
    assert.equal(detail.usages[0]?.fileId, "file-1");

    const mergedPath = ensureJobEffectivePolicyStore(job.jobId);
    const merged = JSON.parse(fs.readFileSync(mergedPath, "utf-8")) as { policies: Array<{ policy_id: string }> };
    assert.ok(merged.policies.some((policy) => policy.policy_id === "vendor_fast_local"));
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});
