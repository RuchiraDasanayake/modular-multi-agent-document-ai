import assert from "node:assert/strict";
import test from "node:test";
import { productAutoReviewReadiness } from "./product-auto-review-readiness";
import type { ProductAutoRun } from "@/types/product-auto";

function run(reviewStatuses: Array<"unreviewed" | "completed">, selectedCount = reviewStatuses.length): ProductAutoRun {
  return {
    runId: "auto_test", status: "success", createdAt: "2026-10-13T00:00:00Z", selectedCount,
    documents: reviewStatuses.map((reviewStatus, index) => ({
      docId: `doc-${index}`, fileId: `file-${index}`, fileName: `sample-${index}.txt`,
      status: "needs_review", fieldCount: 1, acceptedCount: 0, reviewStatus,
    })),
  };
}

test("fresh run snapshot enables batch and preview only after every selected result is reviewed", () => {
  const before = productAutoReviewReadiness(run(["completed", "unreviewed"]));
  assert.deepEqual(before, { reviewedCount: 1, batchReady: false, previewReady: false });
  const refreshed = productAutoReviewReadiness(run(["completed", "completed"]));
  assert.deepEqual(refreshed, { reviewedCount: 2, batchReady: true, previewReady: true });
});

test("missing and failed results never become a ready preview or reviewed batch", () => {
  assert.deepEqual(productAutoReviewReadiness(run(["completed"], 2)),
    { reviewedCount: 1, batchReady: false, previewReady: false });
  const failed = run(["completed", "completed"]);
  failed.documents[1].status = "failed";
  assert.deepEqual(productAutoReviewReadiness(failed),
    { reviewedCount: 1, batchReady: false, previewReady: false });
});

test("one JSON original can complete review and export for all of its logical results", () => {
  const json = run(["completed", "completed"], 1);
  json.documents = json.documents.map((document) => ({ ...document, fileId: "json-original", fileName: "two.json" }));
  assert.deepEqual(productAutoReviewReadiness(json),
    { reviewedCount: 2, batchReady: true, previewReady: true });
  json.documents[1].reviewStatus = "unreviewed";
  assert.deepEqual(productAutoReviewReadiness(json),
    { reviewedCount: 1, batchReady: false, previewReady: false });
});

test("logical results require distinct IDs and complete selected-original coverage", () => {
  const missingOriginal = run(["completed", "completed"], 2);
  missingOriginal.documents[1].fileId = missingOriginal.documents[0].fileId;
  assert.deepEqual(productAutoReviewReadiness(missingOriginal),
    { reviewedCount: 2, batchReady: false, previewReady: false });

  const extraOriginal = run(["completed", "completed"], 1);
  assert.deepEqual(productAutoReviewReadiness(extraOriginal),
    { reviewedCount: 2, batchReady: false, previewReady: false });

  const duplicatedResult = run(["completed", "completed"], 2);
  duplicatedResult.documents[1].docId = duplicatedResult.documents[0].docId;
  assert.deepEqual(productAutoReviewReadiness(duplicatedResult),
    { reviewedCount: 2, batchReady: false, previewReady: false });
  // Exact membership and completeness within each original are verified by the
  // server manifest; the public UI snapshot exposes only the selected file count.
});

test("failed logical rows prevent a ready batch even when their original is covered", () => {
  const json = run(["completed", "completed"], 1);
  json.documents[1].fileId = json.documents[0].fileId;
  json.documents[1].status = "failed";
  assert.deepEqual(productAutoReviewReadiness(json),
    { reviewedCount: 1, batchReady: false, previewReady: false });
});
