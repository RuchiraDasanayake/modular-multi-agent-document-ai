import type { ProductAutoRun } from "@/types/product-auto";

export function productAutoReviewReadiness(run: ProductAutoRun | null): {
  reviewedCount: number;
  batchReady: boolean;
  previewReady: boolean;
} {
  if (!run) return { reviewedCount: 0, batchReady: false, previewReady: false };
  const reviewedCount = run.documents.filter((document) => document.reviewStatus === "completed" &&
    document.status !== "failed" && document.status !== "unsupported").length;
  const completeRun = run.status === "success" && run.selectedCount > 0 &&
    run.documents.length === run.selectedCount;
  return {
    reviewedCount,
    batchReady: completeRun && reviewedCount === run.selectedCount,
    previewReady: completeRun && run.documents.every((document) =>
      document.status === "needs_review" && document.reviewStatus === "completed"),
  };
}
