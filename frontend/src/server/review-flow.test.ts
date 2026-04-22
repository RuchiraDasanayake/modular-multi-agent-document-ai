import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { resetConfigCacheForTests, loadRunnerConfig } from "./config";
import { createWorkspaceJob, mutateJob } from "./jobs";
import {
  applyReviewToJobDocument,
  attachReviewFeedbackResult,
  buildJobOverlay,
  buildReviewArtifact,
  collectJobReviewLearningStats,
  writeReviewArtifact,
} from "./review";

test("review flow updates job state, emits overlay, and next route consumes it", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-review-flow-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const config = loadRunnerConfig();
    const runId = "review-flow-run";
    const runPrimary = path.join(config.runsDir, runId, "primary");
    fs.mkdirSync(path.join(runPrimary, "docs"), { recursive: true });

    const fieldConfig = [{ name: "invoice_number", description: "Invoice identifier" }];
    const job = createWorkspaceJob({
      jobName: "Review Flow",
      mode: "adaptive",
      fieldConfigCurrent: fieldConfig,
    });

    const baseDetail = {
      metadata: {
        docType: "invoice",
        vendorCluster: "acme",
        profile: "table-heavy",
        policyId: "overlay_policy",
        adviceId: "123e4567-e89b-12d3-a456-426614174000",
      },
    };

    mutateJob(job.jobId, (current) => {
      current.documents = [
        {
          fileId: "file-1",
          fileName: "invoice-1.txt",
          storedName: "file-1__invoice-1.txt",
          size: 10,
          selected: true,
          status: "processed",
          errorSummary: null,
          reviewState: null,
          reviewStatus: "unreviewed",
          reviewSource: null,
          latestRoute: "heavy",
          latestPolicy: "overlay_policy",
          latestRunId: runId,
          latestDocId: "doc-1",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          outcomes: [
            {
              runId,
              mode: "adaptive",
              docId: "doc-1",
              status: "processed",
              route: "heavy",
              policy: "overlay_policy",
              errorSummary: null,
              reviewState: null,
              reviewStatus: "unreviewed",
              reviewSource: null,
              fieldValues: { invoice_number: "INV-001" },
              adviceInfluenced: true,
              feedbackLogged: true,
              fallbackReason: null,
              exactPrecision: null,
              exactRecall: null,
              exactF1: null,
            },
          ],
        },
        {
          fileId: "file-2",
          fileName: "invoice-2.txt",
          storedName: "file-2__invoice-2.txt",
          size: 10,
          selected: true,
          status: "processed",
          errorSummary: null,
          reviewState: null,
          reviewStatus: "unreviewed",
          reviewSource: null,
          latestRoute: "heavy",
          latestPolicy: "overlay_policy",
          latestRunId: runId,
          latestDocId: "doc-2",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          outcomes: [
            {
              runId,
              mode: "adaptive",
              docId: "doc-2",
              status: "processed",
              route: "heavy",
              policy: "overlay_policy",
              errorSummary: null,
              reviewState: null,
              reviewStatus: "unreviewed",
              reviewSource: null,
              fieldValues: { invoice_number: "INV-002" },
              adviceInfluenced: true,
              feedbackLogged: true,
              fallbackReason: null,
              exactPrecision: null,
              exactRecall: null,
              exactF1: null,
            },
          ],
        },
      ];
      return current;
    });

    const artifactOne = attachReviewFeedbackResult(buildReviewArtifact({
      jobId: job.jobId,
      runId,
      docId: "doc-1",
      detail: baseDetail,
      fieldConfig,
      reviewSource: "human",
      fields: [
        {
          fieldKey: "invoice_number",
          fieldLabel: "invoice_number",
          extractedValue: "INV-001",
          correctedValue: null,
          reviewState: "correct",
          reviewNote: null,
        },
      ],
    }), { logged: true });
    const artifactTwo = attachReviewFeedbackResult(buildReviewArtifact({
      jobId: job.jobId,
      runId,
      docId: "doc-2",
      detail: baseDetail,
      fieldConfig,
      reviewSource: "human",
      fields: [
        {
          fieldKey: "invoice_number",
          fieldLabel: "invoice_number",
          extractedValue: "INV-002",
          correctedValue: null,
          reviewState: "correct",
          reviewNote: null,
        },
      ],
    }), { logged: true });

    writeReviewArtifact(artifactOne);
    writeReviewArtifact(artifactTwo);

    const updated = mutateJob(job.jobId, (current) => {
      const first = current.documents?.find((document) => document.fileId === "file-1");
      const second = current.documents?.find((document) => document.fileId === "file-2");
      if (first) {
        applyReviewToJobDocument(first, artifactOne, runId, "adaptive");
      }
      if (second) {
        applyReviewToJobDocument(second, artifactTwo, runId, "adaptive");
      }
      return current;
    });

    const reviewedDocument = updated.documents?.find((document) => document.fileId === "file-1");
    assert.ok(reviewedDocument);
    assert.equal(reviewedDocument.reviewStatus, "human_reviewed");
    assert.equal(reviewedDocument.reviewSource, "human");
    assert.equal(reviewedDocument.outcomes[0]?.exactF1, 1);
    assert.equal(artifactOne.ahmnReviewFeedback.logged, true);

    const reviewStats = collectJobReviewLearningStats(updated, fieldConfig);
    assert.equal(reviewStats.reviewedDocumentCount, 2);
    assert.equal(reviewStats.reviewedHumanCount, 2);
    assert.equal(reviewStats.reviewedFeedbackLoggedCount, 2);
    assert.equal(reviewStats.reviewedFeedbackPendingCount, 0);

    const overlay = buildJobOverlay(updated, fieldConfig);
    assert.equal(overlay.entries.length, 1);
    fs.writeFileSync(
      overlay.path,
      JSON.stringify(
        {
          job_id: updated.jobId,
          generated_at: new Date().toISOString(),
          entries: overlay.entries,
        },
        null,
        2,
      ),
      "utf-8",
    );
    assert.ok(fs.existsSync(overlay.path));

    const policyPath = path.join(tmpRoot, "policies.json");
    fs.writeFileSync(
      policyPath,
      JSON.stringify(
        {
          default_policy_id: "default",
          policies: [
            { policy_id: "default", name: "Default", conditions: {}, actions: {} },
            { policy_id: "overlay_policy", name: "Overlay Policy", conditions: {}, actions: {} },
          ],
        },
        null,
        2,
      ),
      "utf-8",
    );

    const pythonScript = `
import json
from idpo.core.config import PipelineConfig
from idpo.core.policy_store import PolicyStore
from idpo.core.types import DAEOutput, SystemConstraints
from idpo.pipeline.planning import PlanRouter

config = PipelineConfig()
config.ahmn.policy_mode = "adaptive"
config.structuring.requested_fields = ["invoice_number"]
store = PolicyStore(r"${policyPath.replace(/\\/g, "\\\\")}", default_policy_id="default")
router = PlanRouter(config, store)
dae = DAEOutput(
    doc_id="next-doc",
    doc_type="invoice",
    vendor_cluster="acme",
    quality_bin="B",
    complexity_bin="2",
    content_profile="table-heavy",
    quality_score=0.8,
    complexity_score=0.4,
)
decision = router.route(dae, SystemConstraints(max_cost_units=5, max_latency_ms=2000))
print(json.dumps({"policy_id": decision.policy.policy_id, "plan_source": decision.plan_source}))
`;
    const python = spawnSync("python", ["-c", pythonScript], {
      cwd: path.resolve(process.cwd(), ".."),
      env: {
        ...process.env,
        IDPO_JOB_OVERLAY_PATH: overlay.path,
      },
      encoding: "utf-8",
    });

    assert.equal(python.status, 0, python.stderr || python.stdout);
    const routed = JSON.parse((python.stdout || "").trim()) as { policy_id: string; plan_source: string };
    assert.equal(routed.policy_id, "overlay_policy");
    assert.equal(routed.plan_source, "job_overlay");
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});
