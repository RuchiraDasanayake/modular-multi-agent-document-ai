import { NextResponse } from "next/server";
import { getJobOrThrow, mutateJob } from "@/server/jobs";
import { requireJob } from "@/server/access";
import { requireAdmin, requireUser } from "@/server/auth";
import { getRunDocument } from "@/server/artifacts";
import { apiError } from "@/server/api/response";
import {
  applyReviewToJobDocument,
  attachReviewFeedbackResult,
  buildRequestedReviewRows,
  buildReviewArtifact,
  collectJobReviewLearningStats,
  postReviewedFeedback,
  writeReviewArtifact,
} from "@/server/review";
import { autoReviewDocument } from "@/server/auto-review";
import { refreshJobValidationContext } from "@/server/review-context";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ jobId: string }>;
}

export async function POST(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId } = await params;
    requireJob(jobId, user);
    requireAdmin(user);
    const payload = (await request.json()) as Record<string, unknown>;
    const selectedFileIds = Array.isArray(payload.selectedFileIds)
      ? payload.selectedFileIds.filter((value): value is string => typeof value === "string")
      : [];
    const mode = payload.mode === "strict" ? "strict" : payload.mode === "adaptive" ? "adaptive" : undefined;
    if (selectedFileIds.length === 0) {
      throw new Error("Select at least one processed document");
    }

    const job = getJobOrThrow(jobId);
    const selectedDocuments = (job.documents ?? []).filter((document) => selectedFileIds.includes(document.fileId));
    if (selectedDocuments.length === 0) {
      throw new Error("No selected documents found");
    }
    if (selectedDocuments.some((document) => document.status !== "processed")) {
      throw new Error("Auto review only accepts processed documents");
    }

    const artifacts: Array<{
      fileId: string;
      runId: string;
      mode: "adaptive" | "strict";
      artifact: ReturnType<typeof buildReviewArtifact>;
    }> = [];
    for (const document of selectedDocuments) {
      const outcomes = mode ? document.outcomes.filter((outcome) => outcome.mode === mode) : document.outcomes;
      const outcome = outcomes[outcomes.length - 1] ?? null;
      if (!outcome?.runId || !outcome.docId || outcome.status !== "processed") {
        throw new Error(`Document ${document.fileName} has no processed run output to validate`);
      }
      const detail = getRunDocument(outcome.runId, outcome.docId);
      const autoReview = await autoReviewDocument({
        job,
        runId: outcome.runId,
        docId: outcome.docId,
        detail,
        fieldConfig: job.fieldConfigCurrent ?? [],
      });
      const artifact = buildReviewArtifact({
        jobId,
        runId: outcome.runId,
        docId: outcome.docId,
        detail,
        fieldConfig: job.fieldConfigCurrent ?? [],
        reviewSource: "ai",
        fields: autoReview.fields.length > 0 ? autoReview.fields : buildRequestedReviewRows(detail, job.fieldConfigCurrent ?? []),
        expectedFieldValues: outcome.expectedFieldValues ?? null,
        reviewerStage: autoReview.reviewStage,
        reviewerConfidence: autoReview.reviewConfidence,
      });
      const feedbackResult = await postReviewedFeedback(artifact);
      const reviewedArtifact = attachReviewFeedbackResult(artifact, feedbackResult);
      writeReviewArtifact(reviewedArtifact);
      artifacts.push({ fileId: document.fileId, runId: outcome.runId, mode: outcome.mode, artifact: reviewedArtifact });
    }

    const updated = mutateJob(jobId, (current) => {
      for (const item of artifacts) {
        const document = (current.documents ?? []).find((entry) => entry.fileId === item.fileId);
        if (!document) {
          continue;
        }
        applyReviewToJobDocument(document, item.artifact, item.runId, item.mode);
      }
      const reviewStats = collectJobReviewLearningStats(current, current.fieldConfigCurrent ?? []);
      current.reviewContext = refreshJobValidationContext(current, current.fieldConfigCurrent ?? [], "auto_review");
      if (current.ahmnSummary) {
        current.ahmnSummary.reviewedDocumentCount = reviewStats.reviewedDocumentCount;
        current.ahmnSummary.reviewedHumanCount = reviewStats.reviewedHumanCount;
        current.ahmnSummary.reviewedAiCount = reviewStats.reviewedAiCount;
        current.ahmnSummary.reviewedFeedbackLoggedCount = reviewStats.reviewedFeedbackLoggedCount;
        current.ahmnSummary.reviewedFeedbackPendingCount = reviewStats.reviewedFeedbackPendingCount;
        current.ahmnSummary.jobOverlayPolicies = reviewStats.overlayEntryCount;
        current.ahmnSummary.jobOverlayReady = reviewStats.overlayReady;
      }
      return current;
    });

    return NextResponse.json({ job: updated, validatedCount: artifacts.length }, { status: 201 });
  } catch (error) {
    return apiError(error, 400);
  }
}
