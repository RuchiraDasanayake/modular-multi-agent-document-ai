import type { ProductAutoRun } from "@/types/product-auto";

export function productAutoReviewReadiness(run: ProductAutoRun | null): {
  reviewedCount: number;
  batchReady: boolean;
  previewReady: boolean;
} {
  if (!run) return { reviewedCount: 0, batchReady: false, previewReady: false };
  const reviewedCount = run.documents.filter((document) => document.reviewStatus === "completed" &&
    document.status !== "failed" && document.status !== "unsupported").length;
  // selectedCount counts original uploads; a JSON original can yield many results.
  // The server verifies exact selected-source membership and its full manifest.
  const completeRun = run.status === "success" && Number.isSafeInteger(run.selectedCount) && run.selectedCount > 0 &&
    run.documents.length >= run.selectedCount &&
    new Set(run.documents.map((document) => document.docId)).size === run.documents.length &&
    new Set(run.documents.map((document) => document.fileId)).size === run.selectedCount;
  return {
    reviewedCount,
    batchReady: completeRun && reviewedCount === run.documents.length,
    previewReady: completeRun && run.documents.every((document) =>
      document.status === "needs_review" && document.reviewStatus === "completed"),
  };
}
