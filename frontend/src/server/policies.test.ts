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
  getJobPolicyTemplates,
  getSuggestedJobPolicyMatching,
  getJobPolicyDetail,
  listJobPolicies,
  setJobPolicyRuntimeEnabled,
  summarizeJobPolicyLearning,
} from "./policies";

test("job policy workspace merges custom policies and reports usage", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-job-policies-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const config = loadRunnerConfig();
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

    fs.mkdirSync(path.join(config.runsDir, "run-1", "primary", "docs", "doc-1", "provenance"), { recursive: true });
    fs.writeFileSync(
      path.join(config.runsDir, "run-1", "primary", "docs", "doc-1", "provenance", "transparency.json"),
      JSON.stringify(
        {
          routing: {
            advice_source: "ahmn_http",
            advice_status: "accepted",
            advice_confidence: 0.82,
          },
        },
        null,
        2,
      ),
      "utf-8",
    );

    const workspace = listJobPolicies(job.jobId);
    const customSummary = workspace.policies.find((policy) => policy.policyId === "vendor_fast_local");
    assert.ok(customSummary);
    assert.equal(customSummary.source, "custom");
    assert.equal(customSummary.documentsProcessed, 1);
    assert.equal(customSummary.reviewedDocuments, 1);
    assert.equal(customSummary.meanExactF1, 1);
    assert.equal(customSummary.ahmnConfidence, 0.82);
    assert.equal(customSummary.learningState, "watch");
    assert.equal(customSummary.learning.selectionMode, "thompson_sampling");
    assert.equal(customSummary.learning.reviewedLearningPendingCount, 1);
    assert.equal(customSummary.leaderboardRank, 1);

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

test("job custom policy can be created as an explicit cloud extension", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-job-cloud-policy-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Cloud Extension",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

    const created = createJobCustomPolicy(job.jobId, {
      policyId: "vendor_cloud_extension",
      name: "Vendor Cloud Extension",
      executionProfile: "cloud_extension",
      instructions: "Only use this when the operator has enabled paid inference for this job.",
      vendorClusters: ["acme"],
      explicitEntities: ["invoice_number", "total_amount"],
    });

    assert.equal(created.policyId, "vendor_cloud_extension");
    const extraction = created.actions.extraction as Record<string, unknown>;
    assert.equal(extraction.model_tier, "cloud");
    assert.equal(extraction.ruleset, "job_custom_cloud_extension");
    assert.equal(created.metadata.execution_profile, "cloud_extension");
    assert.equal(created.metadata.extension_type, "cloud_optional");
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("inactive cloud extensions are visible in the workspace but excluded from the effective policy store", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-inactive-extensions-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Inactive Extensions",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

    const workspace = listJobPolicies(job.jobId);
    const extension = workspace.policies.find((policy) => policy.policyId === "forms_cloud");
    assert.ok(extension);
    assert.equal(extension.source, "default");
    assert.equal(extension.availability, "inactive_extension");
    assert.equal(extension.runtimeEnabled, false);
    assert.equal(extension.runtimeToggleAllowed, true);

    const detail = getJobPolicyDetail(job.jobId, "forms_cloud");
    assert.ok(detail);
    assert.equal(detail.policy.availability, "inactive_extension");
    assert.equal(detail.policy.runtimeEnabled, false);

    const effectivePath = ensureJobEffectivePolicyStore(job.jobId);
    const effective = JSON.parse(fs.readFileSync(effectivePath, "utf-8")) as { policies: Array<{ policy_id: string }> };
    assert.equal(effective.policies.some((policy) => policy.policy_id === "forms_cloud"), false);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("cloud extensions can be enabled and disabled per job from the policy workspace", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-policy-activation-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Policy Activation",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

    let workspace = listJobPolicies(job.jobId);
    let extension = workspace.policies.find((policy) => policy.policyId === "forms_cloud");
    assert.ok(extension);
    assert.equal(extension.availability, "inactive_extension");
    assert.equal(extension.runtimeEnabled, false);

    const enabled = setJobPolicyRuntimeEnabled(job.jobId, "forms_cloud", true);
    assert.equal(enabled.availability, "active_extension");
    assert.equal(enabled.runtimeEnabled, true);

    workspace = listJobPolicies(job.jobId);
    extension = workspace.policies.find((policy) => policy.policyId === "forms_cloud");
    assert.ok(extension);
    assert.equal(extension.availability, "active_extension");
    assert.equal(extension.runtimeEnabled, true);

    let effective = JSON.parse(fs.readFileSync(ensureJobEffectivePolicyStore(job.jobId), "utf-8")) as {
      policies: Array<{ policy_id: string }>;
    };
    assert.equal(effective.policies.some((policy) => policy.policy_id === "forms_cloud"), true);

    const disabled = setJobPolicyRuntimeEnabled(job.jobId, "forms_cloud", false);
    assert.equal(disabled.availability, "inactive_extension");
    assert.equal(disabled.runtimeEnabled, false);

    workspace = listJobPolicies(job.jobId);
    extension = workspace.policies.find((policy) => policy.policyId === "forms_cloud");
    assert.ok(extension);
    assert.equal(extension.availability, "inactive_extension");
    assert.equal(extension.runtimeEnabled, false);

    effective = JSON.parse(fs.readFileSync(ensureJobEffectivePolicyStore(job.jobId), "utf-8")) as {
      policies: Array<{ policy_id: string }>;
    };
    assert.equal(effective.policies.some((policy) => policy.policy_id === "forms_cloud"), false);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("default and local policies can also be disabled and re-enabled per job", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-local-policy-activation-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Local Policy Activation",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

    let workspace = listJobPolicies(job.jobId);
    let defaultPolicy = workspace.policies.find((policy) => policy.policyId === "default");
    assert.ok(defaultPolicy);
    assert.equal(defaultPolicy.availability, "active");
    assert.equal(defaultPolicy.runtimeEnabled, true);

    const disabled = setJobPolicyRuntimeEnabled(job.jobId, "default", false);
    assert.equal(disabled.availability, "inactive");
    assert.equal(disabled.runtimeEnabled, false);

    workspace = listJobPolicies(job.jobId);
    defaultPolicy = workspace.policies.find((policy) => policy.policyId === "default");
    assert.ok(defaultPolicy);
    assert.equal(defaultPolicy.availability, "inactive");
    assert.equal(defaultPolicy.runtimeEnabled, false);

    let effective = JSON.parse(fs.readFileSync(ensureJobEffectivePolicyStore(job.jobId), "utf-8")) as {
      default_policy_id: string;
      policies: Array<{ policy_id: string }>;
    };
    assert.equal(effective.policies.some((policy) => policy.policy_id === "default"), false);
    assert.notEqual(effective.default_policy_id, "default");

    const enabled = setJobPolicyRuntimeEnabled(job.jobId, "default", true);
    assert.equal(enabled.availability, "active");
    assert.equal(enabled.runtimeEnabled, true);

    effective = JSON.parse(fs.readFileSync(ensureJobEffectivePolicyStore(job.jobId), "utf-8")) as {
      default_policy_id: string;
      policies: Array<{ policy_id: string }>;
    };
    assert.equal(effective.policies.some((policy) => policy.policy_id === "default"), true);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("the last active policy cannot be disabled", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-last-policy-guard-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Last Policy Guard",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

    const enabledPolicies = listJobPolicies(job.jobId)
      .policies.filter((policy) => policy.runtimeEnabled)
      .map((policy) => policy.policyId);

    assert.ok(enabledPolicies.length > 1);
    for (const policyId of enabledPolicies.slice(1)) {
      setJobPolicyRuntimeEnabled(job.jobId, policyId, false);
    }

    assert.throws(
      () => setJobPolicyRuntimeEnabled(job.jobId, enabledPolicies[0]!, false),
      /At least one policy must stay enabled/,
    );
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("policy enable and disable state is isolated per job", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-job-policy-isolation-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    loadRunnerConfig();
    const firstJob = createWorkspaceJob({
      jobName: "Policy Isolation A",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });
    const secondJob = createWorkspaceJob({
      jobName: "Policy Isolation B",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

    setJobPolicyRuntimeEnabled(firstJob.jobId, "forms_cloud", true);
    setJobPolicyRuntimeEnabled(firstJob.jobId, "default", false);

    const firstWorkspace = listJobPolicies(firstJob.jobId);
    const secondWorkspace = listJobPolicies(secondJob.jobId);

    assert.equal(firstWorkspace.policies.find((policy) => policy.policyId === "forms_cloud")?.runtimeEnabled, true);
    assert.equal(firstWorkspace.policies.find((policy) => policy.policyId === "default")?.runtimeEnabled, false);
    assert.equal(secondWorkspace.policies.find((policy) => policy.policyId === "forms_cloud")?.runtimeEnabled, false);
    assert.equal(secondWorkspace.policies.find((policy) => policy.policyId === "default")?.runtimeEnabled, true);

    const firstEffective = JSON.parse(fs.readFileSync(ensureJobEffectivePolicyStore(firstJob.jobId), "utf-8")) as {
      policies: Array<{ policy_id: string }>;
    };
    const secondEffective = JSON.parse(fs.readFileSync(ensureJobEffectivePolicyStore(secondJob.jobId), "utf-8")) as {
      policies: Array<{ policy_id: string }>;
    };

    assert.equal(firstEffective.policies.some((policy) => policy.policy_id === "forms_cloud"), true);
    assert.equal(firstEffective.policies.some((policy) => policy.policy_id === "default"), false);
    assert.equal(secondEffective.policies.some((policy) => policy.policy_id === "forms_cloud"), false);
    assert.equal(secondEffective.policies.some((policy) => policy.policy_id === "default"), true);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("job custom policy can clone and customize executable settings from an existing policy", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-job-policy-customize-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Policy Customize",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

    const templates = getJobPolicyTemplates(job.jobId);
    const forms = templates.find((policy) => policy.policyId === "forms");
    assert.ok(forms);

    const created = createJobCustomPolicy(job.jobId, {
      policyId: "forms_custom_local",
      name: "Forms Custom Local",
      basePolicyId: "forms",
      executionProfile: forms.executionProfile,
      explicitEntities: ["invoice_number", "total_amount"],
      executionSettings: {
        ...forms.executionSettings,
        ocrPasses: 4,
        ruleset: "forms_custom_rules",
        chunkSize: 410,
        denseK: 11,
      },
      instructions: "Customized from forms for this job.",
    });

    const preprocess = created.actions.preprocess as Record<string, unknown>;
    const ocr = preprocess.ocr as Record<string, unknown>;
    const extraction = created.actions.extraction as Record<string, unknown>;
    const chunking = created.actions.chunking as Record<string, unknown>;
    const retrieval = created.actions.retrieval as Record<string, unknown>;

    assert.equal(ocr.passes, 4);
    assert.equal(extraction.ruleset, "forms_custom_rules");
    assert.equal(chunking.chunk_size, 410);
    assert.equal(retrieval.dense_k, 11);
    assert.equal(created.metadata.base_policy_id, "forms");
    assert.equal((created.metadata.execution_settings as Record<string, unknown>).ocrPasses, 4);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("suggested policy matching is prefilled from current job context", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-policy-matching-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const config = loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Matching Context",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

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
          reviewState: null,
          reviewStatus: "unreviewed",
          reviewSource: null,
          latestRoute: "standard",
          latestPolicy: "forms",
          latestRunId: "run-1",
          latestDocId: "doc-1",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          outcomes: [],
        },
      ];
      return current;
    });

    fs.mkdirSync(path.join(config.runsDir, "run-1", "primary", "docs", "doc-1", "dae"), { recursive: true });
    fs.writeFileSync(
      path.join(config.runsDir, "run-1", "primary", "docs", "doc-1", "dae", "output.json"),
      JSON.stringify(
        {
          doc_type: "invoice",
          vendor_cluster: "acme",
          content_profile: "table-heavy",
        },
        null,
        2,
      ),
      "utf-8",
    );

    const matching = getSuggestedJobPolicyMatching(job.jobId);
    assert.deepEqual(matching.vendorClusters, ["acme"]);
    assert.deepEqual(matching.docTypes, ["invoice"]);
    assert.deepEqual(matching.contentProfiles, ["table-heavy"]);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("policy learning summary groups route sources and warm-start evidence", () => {
  const learning = summarizeJobPolicyLearning([
    {
      fileId: "f1",
      fileName: "a.pdf",
      runId: "run-1",
      docId: "doc-1",
      mode: "adaptive",
      status: "processed",
      route: "standard",
      exactF1: 0.9,
      reviewStatus: "human_reviewed",
      adviceSource: "ahmn_http",
      adviceStatus: "accepted",
      retrievalSource: "LTM",
      rabiUsed: true,
      nNeighbors: 4,
      reviewedLearningLogged: true,
      reviewedLearningError: null,
      updatedAt: new Date().toISOString(),
    },
    {
      fileId: "f2",
      fileName: "b.pdf",
      runId: "run-2",
      docId: "doc-2",
      mode: "adaptive",
      status: "processed",
      route: "heavy",
      exactF1: 0.7,
      reviewStatus: "ai_validated",
      adviceSource: "job_overlay",
      adviceStatus: "accepted",
      retrievalSource: "JOB",
      rabiUsed: false,
      nNeighbors: null,
      reviewedLearningLogged: false,
      reviewedLearningError: "http_500",
      updatedAt: new Date().toISOString(),
    },
    {
      fileId: "f3",
      fileName: "c.pdf",
      runId: "run-3",
      docId: "doc-3",
      mode: "strict",
      status: "processed",
      route: "standard",
      exactF1: null,
      reviewStatus: "unreviewed",
      adviceSource: "static",
      adviceStatus: "static",
      retrievalSource: null,
      rabiUsed: false,
      nNeighbors: null,
      reviewedLearningLogged: null,
      reviewedLearningError: null,
      updatedAt: new Date().toISOString(),
    },
  ]);

  assert.equal(learning.selectionMode, "thompson_sampling");
  assert.equal(learning.ahmnRouteCount, 1);
  assert.equal(learning.jobOverlayRouteCount, 1);
  assert.equal(learning.staticRouteCount, 1);
  assert.equal(learning.fallbackRouteCount, 0);
  assert.equal(learning.warmStartCount, 1);
  assert.equal(learning.meanNeighborCount, 4);
  assert.equal(learning.maxNeighborCount, 4);
  assert.equal(learning.reviewedLearningLoggedCount, 1);
  assert.equal(learning.reviewedLearningPendingCount, 1);
  assert.equal(learning.rabiDecayState, "active");
  assert.equal(learning.driftAwarenessState, "active");
});

test("suggested policy matching ignores synthetic vendor clusters", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-policy-matching-sanitize-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const config = loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Receipt Matching",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "total_amount" }],
    });

    mutateJob(job.jobId, (current) => {
      current.documents = [
        {
          fileId: "file-1",
          fileName: "receipt.png",
          storedName: "file-1__receipt.png",
          size: 10,
          selected: true,
          status: "processed",
          errorSummary: null,
          reviewState: "human_reviewed | F1 0.00",
          reviewStatus: "human_reviewed",
          reviewSource: "human",
          reviewStage: null,
          reviewConfidence: null,
          latestRoute: "heavy",
          latestPolicy: "forms",
          latestRunId: "run-1",
          latestDocId: "doc-1",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          outcomes: [],
        },
      ];
      return current;
    });

    fs.mkdirSync(path.join(config.runsDir, "run-1", "primary", "docs", "doc-1", "dae"), { recursive: true });
    fs.writeFileSync(
      path.join(config.runsDir, "run-1", "primary", "docs", "doc-1", "dae", "output.json"),
      JSON.stringify(
        {
          doc_type: "receipt",
          vendor_cluster: "07bee9b0dde74ec59feb455d3eba1c31",
          content_profile: "image-heavy",
        },
        null,
        2,
      ),
      "utf-8",
    );

    const matching = getSuggestedJobPolicyMatching(job.jobId);
    assert.deepEqual(matching.vendorClusters, []);
    assert.deepEqual(matching.docTypes, ["receipt"]);
    assert.deepEqual(matching.contentProfiles, ["image-heavy"]);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("leaderboard ranks by human-reviewed exact F1 before AHMN confidence", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-job-policies-trend-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const config = loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Policy Trend",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

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
          reviewState: "human_reviewed | F1 0.60",
          reviewStatus: "human_reviewed",
          reviewSource: "human",
          latestRoute: "standard",
          latestPolicy: "forms",
          latestRunId: "run-1",
          latestDocId: "doc-1",
          createdAt: "2026-04-20T10:00:00.000Z",
          updatedAt: "2026-04-20T10:00:00.000Z",
          outcomes: [
            {
              runId: "run-1",
              mode: "adaptive",
              docId: "doc-1",
              status: "processed",
              route: "standard",
              policy: "forms",
              errorSummary: null,
              reviewState: "human_reviewed | F1 0.60",
              reviewStatus: "human_reviewed",
              reviewSource: "human",
              fieldValues: { invoice_number: "INV-001" },
              adviceInfluenced: true,
              feedbackLogged: true,
              fallbackReason: null,
              exactPrecision: 0.6,
              exactRecall: 0.6,
              exactF1: 0.6,
            },
          ],
        },
        {
          fileId: "file-2",
          fileName: "invoice-2.pdf",
          storedName: "file-2__invoice-2.pdf",
          size: 10,
          selected: true,
          status: "processed",
          errorSummary: null,
          reviewState: "human_reviewed | F1 0.70",
          reviewStatus: "human_reviewed",
          reviewSource: "human",
          latestRoute: "standard",
          latestPolicy: "default",
          latestRunId: "run-2",
          latestDocId: "doc-2",
          createdAt: "2026-04-21T10:00:00.000Z",
          updatedAt: "2026-04-21T10:00:00.000Z",
          outcomes: [
            {
              runId: "run-2",
              mode: "adaptive",
              docId: "doc-2",
              status: "processed",
              route: "standard",
              policy: "default",
              errorSummary: null,
              reviewState: "human_reviewed | F1 0.70",
              reviewStatus: "human_reviewed",
              reviewSource: "human",
              fieldValues: { invoice_number: "INV-002" },
              adviceInfluenced: true,
              feedbackLogged: true,
              fallbackReason: null,
              exactPrecision: 0.7,
              exactRecall: 0.7,
              exactF1: 0.7,
            },
          ],
        },
      ];
      return current;
    });

    fs.mkdirSync(path.join(config.runsDir, "run-1", "primary", "docs", "doc-1", "provenance"), { recursive: true });
    fs.writeFileSync(
      path.join(config.runsDir, "run-1", "primary", "docs", "doc-1", "provenance", "transparency.json"),
      JSON.stringify(
        {
          routing: {
            advice_source: "ahmn_http",
            advice_status: "accepted",
            advice_confidence: 0.91,
          },
        },
        null,
        2,
      ),
      "utf-8",
    );
    fs.mkdirSync(path.join(config.runsDir, "run-2", "primary", "docs", "doc-2", "provenance"), { recursive: true });
    fs.writeFileSync(
      path.join(config.runsDir, "run-2", "primary", "docs", "doc-2", "provenance", "transparency.json"),
      JSON.stringify(
        {
          routing: {
            advice_source: "ahmn_http",
            advice_status: "accepted",
            advice_confidence: 0.34,
          },
        },
        null,
        2,
      ),
      "utf-8",
    );

    const workspace = listJobPolicies(job.jobId);
    const forms = workspace.policies.find((policy) => policy.policyId === "forms");
    const defaultPolicy = workspace.policies.find((policy) => policy.policyId === "default");
    assert.ok(forms);
    assert.ok(defaultPolicy);
    assert.equal(forms.meanExactF1, 0.6);
    assert.equal(forms.ahmnConfidence, 0.91);
    assert.equal(defaultPolicy.meanExactF1, 0.7);
    assert.equal(defaultPolicy.ahmnConfidence, 0.34);
    assert.ok((defaultPolicy.leaderboardRank ?? 999) < (forms.leaderboardRank ?? 999));
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});
