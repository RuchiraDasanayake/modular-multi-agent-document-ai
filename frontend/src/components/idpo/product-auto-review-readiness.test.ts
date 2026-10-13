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
