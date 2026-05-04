import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { resetConfigCacheForTests, loadRunnerConfig } from "./config";
import { autoReviewDocument } from "./auto-review";
import { createWorkspaceJob, getJob, mutateJob } from "./jobs";
import { listJobPolicies } from "./policies";
import { buildReviewArtifact, writeReviewArtifact } from "./review";
import { refreshJobValidationContext, readJobValidationContext, updateJobValidationContextManualInput } from "./review-context";

function writeJson(filePath: string, payload: unknown): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(payload, null, 2), "utf-8");
}

test("policy leaderboard uses human-reviewed exact F1 as the canonical score", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-policy-score-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Policy Score",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number" }],
    });

    mutateJob(job.jobId, (current) => {
      current.documents = [
        {
          fileId: "file-human",
          fileName: "invoice-human.pdf",
          storedName: "file-human__invoice-human.pdf",
          size: 10,
          selected: true,
          status: "processed",
          errorSummary: null,
          reviewState: "human_reviewed | F1 0.40",
          reviewStatus: "human_reviewed",
          reviewSource: "human",
          reviewStage: null,
          reviewConfidence: null,
          latestRoute: "standard",
          latestPolicy: "default",
          latestRunId: "run-human",
          latestDocId: "doc-human",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          outcomes: [
            {
              runId: "run-human",
              mode: "adaptive",
              docId: "doc-human",
              status: "processed",
              route: "standard",
              policy: "default",
              errorSummary: null,
              reviewState: "human_reviewed | F1 0.40",
              reviewStatus: "human_reviewed",
              reviewSource: "human",
              reviewStage: null,
              reviewConfidence: null,
              fieldValues: { invoice_number: "INV-001" },
              adviceInfluenced: true,
              feedbackLogged: true,
              fallbackReason: null,
              exactPrecision: 0.4,
              exactRecall: 0.4,
              exactF1: 0.4,
            },
          ],
        },
        {
          fileId: "file-auto",
          fileName: "invoice-auto.pdf",
          storedName: "file-auto__invoice-auto.pdf",
          size: 10,
          selected: true,
          status: "processed",
          errorSummary: null,
          reviewState: "ai_validated | F1 0.95",
          reviewStatus: "ai_validated",
          reviewSource: "ai",
          reviewStage: "local",
          reviewConfidence: 0.95,
          latestRoute: "standard",
          latestPolicy: "default",
          latestRunId: "run-auto",
          latestDocId: "doc-auto",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          outcomes: [
            {
              runId: "run-auto",
              mode: "adaptive",
              docId: "doc-auto",
              status: "processed",
              route: "standard",
              policy: "default",
              errorSummary: null,
              reviewState: "ai_validated | F1 0.95",
              reviewStatus: "ai_validated",
              reviewSource: "ai",
              reviewStage: "local",
              reviewConfidence: 0.95,
              fieldValues: { invoice_number: "INV-002" },
              adviceInfluenced: true,
              feedbackLogged: true,
              fallbackReason: null,
              exactPrecision: 0.95,
              exactRecall: 0.95,
              exactF1: 0.95,
            },
          ],
        },
      ];
      return current;
    });

    const workspace = listJobPolicies(job.jobId);
    const summary = workspace.policies.find((policy) => policy.policyId === "default");
    assert.ok(summary);
    assert.equal(summary.reviewedDocuments, 1);
    assert.equal(summary.meanExactF1, 0.4);
    assert.equal(summary.autoReviewedDocuments, 1);
    assert.equal(summary.meanAutoReviewF1, 0.95);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("auto review runs local first, escalates to cloud, and refreshes job context", async () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-auto-review-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  process.env.OPENAI_API_KEY = "test-key";
  resetConfigCacheForTests();

  const originalFetch = globalThis.fetch;
  const fetchCalls: string[] = [];
  globalThis.fetch = (async (input: string | URL | Request) => {
    const url = String(input);
    fetchCalls.push(url);
    if (url.includes("/api/generate")) {
      return new Response(
        JSON.stringify({
          response: JSON.stringify({
            confidence: 0.42,
            fields: [{ fieldKey: "invoice_number", reviewState: "wrong_value", reviewNote: "uncertain local review" }],
          }),
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    return new Response(
      JSON.stringify({
        choices: [
          {
            message: {
              content: JSON.stringify({
                confidence: 0.93,
                fields: [{ fieldKey: "invoice_number", reviewState: "correct", reviewNote: "cloud confirmed value" }],
              }),
            },
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof fetch;

  try {
    const config = loadRunnerConfig();
    const runId = "auto-review-run";
    const docId = "doc-1";
    const primaryPath = path.join(config.runsDir, runId, "primary");
    writeJson(path.join(primaryPath, "docs", docId, "preprocessing", "ocr", "text.json"), {
      pages: [{ number: 1, text: "Invoice Number: INV-001" }],
    });

    const job = createWorkspaceJob({
      jobName: "Auto Review",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "invoice_number", description: "Invoice number" }],
    });

    const detail = {
      metadata: {
        docType: "invoice",
        vendorCluster: "acme",
      },
      validationIssues: [],
      raw: {
        extract: {
          requested_field_status: {
            invoice_number: {
              value: "INV-001",
              status: "resolved",
              confidence: 0.95,
            },
          },
        },
      },
      fields: [{ key: "invoice_number", value: "INV-001", confidence: 0.95 }],
    };

    const autoReview = await autoReviewDocument({
      job,
      runId,
      docId,
      detail,
      fieldConfig: [{ name: "invoice_number", description: "Invoice number" }],
    });

    assert.equal(autoReview.reviewStage, "cloud");
    assert.equal(autoReview.reviewConfidence, 0.93);
    assert.equal(autoReview.fields[0]?.reviewState, "correct");

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
          reviewStatus: "ai_validated",
          reviewSource: "ai",
          reviewStage: "cloud",
          reviewConfidence: 0.93,
          latestRoute: "standard",
          latestPolicy: "default",
          latestRunId: runId,
          latestDocId: docId,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          outcomes: [
            {
              runId,
              mode: "adaptive",
              docId,
              status: "processed",
              route: "standard",
              policy: "default",
              errorSummary: null,
              reviewState: "human_reviewed | F1 0.00",
              reviewStatus: "human_reviewed",
              reviewSource: "human",
              reviewStage: null,
              reviewConfidence: null,
              fieldValues: { invoice_number: "N/A" },
              adviceInfluenced: true,
              feedbackLogged: true,
              fallbackReason: null,
              exactPrecision: 0,
              exactRecall: 0,
              exactF1: 0,
            },
          ],
        },
      ];
      return current;
    });

    writeReviewArtifact(
      buildReviewArtifact({
        jobId: job.jobId,
        runId,
        docId,
        detail,
        fieldConfig: [{ name: "invoice_number", description: "Invoice number" }],
        reviewSource: "ai",
        fields: autoReview.fields,
        reviewerStage: autoReview.reviewStage,
        reviewerConfidence: autoReview.reviewConfidence,
      }),
    );

    const updatedJob = mutateJob(job.jobId, (current) => {
      current.reviewContext = refreshJobValidationContext(current, current.fieldConfigCurrent ?? [], "auto_review");
      return current;
    });
    const context = readJobValidationContext(updatedJob.jobId);
    assert.ok(context);
    assert.equal(context.current.source, "auto_review");
    assert.ok(context.current.promptPreview.autoReview.includes("Job purpose"));
    assert.ok(fetchCalls.some((url) => url.includes("/api/generate")));
    assert.ok(fetchCalls.some((url) => url.includes("/chat/completions")));
  } finally {
    globalThis.fetch = originalFetch;
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    delete process.env.OPENAI_API_KEY;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("operator review context overlays user knowledge without replacing reviewed evidence", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-review-context-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const config = loadRunnerConfig();
    const runId = "context-run";
    const docId = "doc-1";
    const fieldConfig = [{ name: "invoice_number", description: "Invoice number" }];
    fs.mkdirSync(path.join(config.runsDir, runId, "primary", "docs"), { recursive: true });
    const job = createWorkspaceJob({
      jobName: "Context Job",
      mode: "adaptive",
      fieldConfigCurrent: fieldConfig,
    });

    mutateJob(job.jobId, (current) => {
      current.documents = [
        {
          fileId: "file-1",
          fileName: "invoice.pdf",
          storedName: "file-1__invoice.pdf",
          size: 10,
          selected: true,
          status: "processed",
          errorSummary: null,
          reviewState: "human_reviewed | F1 0.00",
          reviewStatus: "human_reviewed",
          reviewSource: "human",
          reviewStage: null,
          reviewConfidence: null,
          latestRoute: "standard",
          latestPolicy: "default",
          latestRunId: runId,
          latestDocId: docId,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          outcomes: [
            {
              runId,
              mode: "adaptive",
              docId,
              status: "processed",
              route: "standard",
              policy: "default",
              errorSummary: null,
              reviewState: "human_reviewed | F1 0.00",
              reviewStatus: "human_reviewed",
              reviewSource: "human",
              reviewStage: null,
              reviewConfidence: null,
              fieldValues: { invoice_number: "N/A" },
              adviceInfluenced: true,
              feedbackLogged: true,
              fallbackReason: null,
              exactPrecision: 0,
              exactRecall: 0,
              exactF1: 0,
            },
          ],
        },
      ];
      return current;
    });

    writeReviewArtifact(
      buildReviewArtifact({
        jobId: job.jobId,
        runId,
        docId,
        detail: {
          metadata: {
            vendorCluster: "acme",
          },
        },
        fieldConfig,
        reviewSource: "human",
        fields: [
          {
            fieldKey: "invoice_number",
            fieldLabel: "invoice_number",
            extractedValue: "N/A",
            correctedValue: "INV-777",
            reviewState: "missed_field",
            reviewNote: "Invoice number sits in the upper right corner.",
          },
        ],
      }),
    );

    const refreshed = refreshJobValidationContext(getJob(job.jobId) ?? job, fieldConfig, "human_review");
    assert.ok(refreshed.current.summary.knownVendors.includes("acme"));

    const updated = updateJobValidationContextManualInput(getJob(job.jobId) ?? job, fieldConfig, {
      jobPurpose: "Extract invoice identifiers for finance review",
      knownVendors: ["globex"],
      fieldClarifications: ["Invoice number may be labelled invoice #."],
      validationNotes: ["If the field is blank, leave it as missing."],
    });

    assert.equal(updated.current.source, "operator");
    assert.equal(updated.manualInput.jobPurpose, "Extract invoice identifiers for finance review");
    assert.ok(updated.current.summary.knownVendors.includes("acme"));
    assert.ok(updated.current.summary.knownVendors.includes("globex"));
    assert.ok(updated.current.summary.fieldClarifications.includes("Invoice number may be labelled invoice #."));
    assert.ok(updated.current.summary.fieldClarifications.some((entry) => entry.includes("upper right corner")));
    assert.ok(updated.current.promptPreview.autoReview.includes("Extract invoice identifiers for finance review"));
    assert.ok(updated.history.length >= 1);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("buildReviewArtifact strips synthetic vendor identities from upload metadata", () => {
  const artifact = buildReviewArtifact({
    jobId: "job-1",
    runId: "run-1",
    docId: "doc-1",
    detail: {
      metadata: {
        vendorCluster: "07bee9b0dde74ec59feb455d3eba1c31",
        docType: "receipt",
        profile: "image-heavy",
      },
    },
    fieldConfig: [{ name: "total_amount" }],
    reviewSource: "human",
    fields: [
      {
        fieldKey: "total_amount",
        fieldLabel: "total_amount",
        extractedValue: "20,000",
        correctedValue: null,
        reviewState: "correct",
        reviewNote: null,
      },
    ],
  });

  assert.equal(artifact.documentContext.vendor, null);
  assert.equal(artifact.documentContext.vendor_cluster, null);
  assert.equal(artifact.overlayKey, `unknown|receipt|image-heavy|${artifact.fieldSetHash}`);
});

test("buildReviewArtifact canonicalizes numeric matches against benchmark expected values", () => {
  const artifact = buildReviewArtifact({
    jobId: "job-1",
    runId: "run-1",
    docId: "doc-1",
    detail: {
      metadata: {
        docType: "receipt",
      },
    },
    fieldConfig: [{ name: "total_amount" }],
    reviewSource: "human",
    expectedFieldValues: {
      total_amount: "31000",
    },
    fields: [
      {
        fieldKey: "total_amount",
        fieldLabel: "total_amount",
        extractedValue: "31.000",
        correctedValue: null,
        reviewState: "wrong_value",
        reviewNote: "raw manual state was wrong",
      },
    ],
  });

  assert.equal(artifact.fields[0]?.reviewState, "correct");
  assert.equal(artifact.fields[0]?.correctedValue, "31000");
  assert.equal(artifact.metrics.tp, 1);
  assert.equal(artifact.metrics.fp, 0);
  assert.equal(artifact.metrics.fn, 0);
  assert.equal(artifact.metrics.f1, 1);
});

test("buildReviewArtifact canonicalizes fuzzy OCR text matches against corrected values", () => {
  const artifact = buildReviewArtifact({
    jobId: "job-2",
    runId: "run-2",
    docId: "doc-2",
    detail: {
      metadata: {
        docType: "form",
      },
    },
    fieldConfig: [{ name: "invoice_date" }],
    reviewSource: "human",
    fields: [
      {
        fieldKey: "invoice_date",
        fieldLabel: "invoice_date",
        extractedValue: "janry 31 1997",
        correctedValue: "January 31, 1997",
        reviewState: "wrong_value",
        reviewNote: "should normalize as equal",
      },
    ],
  });

  assert.equal(artifact.fields[0]?.reviewState, "correct");
  assert.equal(artifact.metrics.f1, 1);
});

test("review context ignores synthetic vendor identities from legacy reviewed artifacts", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-review-context-sanitize-"));
  const dataDir = path.join(tmpRoot, "idpo-data");
  process.env.IDPO_DATA_DIR = dataDir;
  resetConfigCacheForTests();

  try {
    const config = loadRunnerConfig();
    const job = createWorkspaceJob({
      jobName: "Receipt Research",
      mode: "adaptive",
      fieldConfigCurrent: [{ name: "total_amount" }],
    });
    const runId = "run-legacy";
    const docId = "doc-legacy";
    fs.mkdirSync(path.join(config.runsDir, runId, "primary", "docs", docId, "review"), { recursive: true });

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
          latestRunId: runId,
          latestDocId: docId,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          outcomes: [
            {
              runId,
              mode: "adaptive",
              docId,
              status: "processed",
              route: "heavy",
              policy: "forms",
              errorSummary: null,
              reviewState: "human_reviewed | F1 0.00",
              reviewStatus: "human_reviewed",
              reviewSource: "human",
              reviewStage: null,
              reviewConfidence: null,
              fieldValues: {
                total_amount: "12.50 USD",
              },
              adviceInfluenced: true,
              feedbackLogged: true,
              fallbackReason: null,
              exactPrecision: 0,
              exactRecall: 0,
              exactF1: 0,
            },
          ],
        },
      ];
      return current;
    });

    writeReviewArtifact({
      version: 1,
      jobId: job.jobId,
      runId,
      docId,
      reviewStatus: "human_reviewed",
      reviewSource: "human",
      reviewWeight: 1,
      reviewerStage: null,
      reviewerConfidence: null,
      reviewedAt: new Date().toISOString(),
      fieldSetHash: "4229380af6c68d3c",
      overlayKey: "07bee9b0dde74ec59feb455d3eba1c31|receipt|image-heavy|4229380af6c68d3c",
      policyIdUsed: "forms",
      adviceId: null,
      documentContext: {
        doc_type: "receipt",
        vendor: "07bee9b0dde74ec59feb455d3eba1c31",
        vendor_cluster: "07bee9b0dde74ec59feb455d3eba1c31",
        content_profile: "image-heavy",
        route_bin: "heavy",
        layout_cluster_id: "image_sparse",
      },
      metrics: {
        tp: 0,
        fp: 1,
        fn: 1,
        precision: 0,
        recall: 0,
        f1: 0,
        fieldStateCounts: {
          correct: 0,
          wrong_value: 1,
          missed_field: 0,
          correctly_skipped: 0,
          hallucinated_field: 0,
        },
      },
      fields: [
        {
          fieldKey: "total_amount",
          fieldLabel: "total_amount",
          extractedValue: "12.50 USD",
          correctedValue: "22000",
          reviewState: "wrong_value",
          reviewNote: null,
        },
      ],
      ahmnReviewFeedback: {
        logged: false,
        error: null,
        attemptedAt: null,
      },
    });

    const refreshed = refreshJobValidationContext(getJob(job.jobId) ?? job, job.fieldConfigCurrent ?? [], "human_review");
    assert.deepEqual(refreshed.current.summary.knownVendors, []);
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});
