import { NextResponse } from "next/server";
import { getJobOrThrow, mutateJob } from "@/server/jobs";
import { requireJob } from "@/server/access";
import { requireUser } from "@/server/auth";
import { getRunDocument } from "@/server/artifacts";
import { apiError } from "@/server/api/response";
import type { JobDocumentRunOutcome } from "@/types/idpo";
import {
  applyReviewToJobDocument,
  attachReviewFeedbackResult,
  buildReviewArtifact,
  collectJobReviewLearningStats,
  postReviewedFeedback,
  readReviewArtifact,
  writeReviewArtifact,
} from "@/server/review";
import { refreshJobValidationContext } from "@/server/review-context";
import type { ReviewFieldResult } from "@/server/review";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
};

interface Params {
  params: Promise<{ jobId: string; docId: string }>;
}

function pickOutcome(
  outcomes: JobDocumentRunOutcome[],
  requestedMode: string | null,
  requestedRunId: string | null,
): JobDocumentRunOutcome | null {
  const filtered = outcomes.filter((outcome) => {
    if (requestedRunId && outcome.runId !== requestedRunId) {
      return false;
    }
    if (requestedMode && outcome.mode !== requestedMode) {
      return false;
    }
    return true;
  });
  if (filtered.length > 0) {
    return filtered[filtered.length - 1] ?? null;
  }
  if (requestedMode || requestedRunId) return null;
  return outcomes[outcomes.length - 1] ?? null;
}

export async function GET(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId, docId } = await params;
    requireJob(jobId, user);
    const job = getJobOrThrow(jobId);
    const document = (job.documents ?? []).find((entry) => entry.fileId === docId);
    if (!document) {
      return NextResponse.json({ error: "Document not found" }, { status: 404 });
    }

    const url = new URL(request.url);
    const requestedMode = url.searchParams.get("mode");
    const requestedRunId = url.searchParams.get("runId");
    const outcome = pickOutcome(document.outcomes, requestedMode, requestedRunId);

    let detail: Record<string, unknown> | null = null;
    if (outcome?.runId && outcome.docId) {
      try {
        detail = getRunDocument(outcome.runId, outcome.docId);
      } catch {
        detail = null;
      }
    }
    // Load review for the selected outcome. If none exists (e.g. document was reprocessed
    // after being reviewed), walk backwards through all outcomes to surface the most recent
    // human review artifact so it is never silently lost from the UI.
    let review = outcome?.runId && outcome?.docId ? readReviewArtifact(outcome.runId, outcome.docId) : null;
    if (!review && document.reviewStatus === "human_reviewed") {
      const reversed = [...document.outcomes].reverse();
      for (const o of reversed) {
        if (!o.runId || !o.docId) continue;
        const candidate = readReviewArtifact(o.runId, o.docId);
        if (candidate?.reviewSource === "human") {
          review = candidate;
          break;
        }
      }
    }
    const transparency = detail && typeof detail === "object" && detail !== null && "transparency" in detail
      ? ((detail as Record<string, unknown>).transparency as Record<string, unknown> | null)
      : null;
    const provenanceEvents =
      detail && typeof detail === "object" && detail !== null && Array.isArray((detail as Record<string, unknown>).provenanceEvents)
        ? ((detail as Record<string, unknown>).provenanceEvents as unknown[])
        : [];

    // Build expected values: human/AI review corrections take priority,
    // then benchmark pack ground truth, then nothing.
    const expectedFieldValues: Record<string, string> = {};
    const expectedFieldSource: Record<string, "review" | "benchmark"> = {};
    // 1. Benchmark pack expected values (lowest priority)
    const outcomeAny = outcome as unknown as Record<string, unknown> | null;
    const benchmarkExpected =
      outcomeAny &&
      typeof outcomeAny.expectedFieldValues === "object" &&
      outcomeAny.expectedFieldValues !== null
        ? (outcomeAny.expectedFieldValues as Record<string, string>)
        : null;
    if (benchmarkExpected) {
      for (const [k, v] of Object.entries(benchmarkExpected)) {
        if (typeof v === "string" && v.trim()) {
          expectedFieldValues[k] = v.trim();
          expectedFieldSource[k] = "benchmark";
        }
      }
    }
    // 2. Review corrected values override benchmark (highest priority)
    if (review?.fields && Array.isArray(review.fields)) {
      for (const field of review.fields as ReviewFieldResult[]) {
        const key = field.fieldKey.trim();
        const corrected = typeof field.correctedValue === "string" ? field.correctedValue.trim() : null;
        const extracted = field.extractedValue.trim();
        if (!key) continue;
        if (corrected) {
          expectedFieldValues[key] = corrected;
          expectedFieldSource[key] = "review";
        } else if (field.reviewState === "correct" && extracted && extracted !== "N/A") {
          // Reviewer confirmed correct — the extracted value IS the expected value
          expectedFieldValues[key] = extracted;
          expectedFieldSource[key] = "review";
        }
      }
    }

    return NextResponse.json(
      {
        jobId,
        fileId: document.fileId,
        fileName: document.fileName,
        status: document.status,
        selected: document.selected,
        errorSummary: document.errorSummary,
        reviewState: document.reviewState,
        latestRoute: document.latestRoute,
        latestPolicy: document.latestPolicy,
        latestRunId: document.latestRunId,
        latestDocId: document.latestDocId,
        requestedFields: job.fieldConfigCurrent ?? [],
        outcome,
        fieldValues: outcome?.fieldValues ?? {},
        expectedFieldValues: Object.keys(expectedFieldValues).length > 0 ? expectedFieldValues : null,
        expectedFieldSource: Object.keys(expectedFieldSource).length > 0 ? expectedFieldSource : null,
        review,
        support: {
          ahmn: {
            adviceInfluenced: outcome?.adviceInfluenced ?? false,
            feedbackLogged: outcome?.feedbackLogged ?? false,
            reviewedFeedbackLogged: review?.ahmnReviewFeedback?.logged ?? false,
            reviewedFeedbackError: review?.ahmnReviewFeedback?.error ?? null,
          },
          xai: {
            available: provenanceEvents.length > 0 || Boolean(transparency),
            mode: provenanceEvents.length > 0 || Boolean(transparency) ? "compact_runtime_trace" : "not_wired_on_canonical_path",
          },
          hitl: {
            reviewState: review?.reviewStatus ?? outcome?.reviewState ?? document.reviewState,
            reviewSource: review?.reviewSource ?? null,
          },
        },
        detail,
      },
      { headers: NO_STORE_HEADERS },
    );
  } catch (error) {
    return apiError(error, 400);
  }
}

export async function POST(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId, docId } = await params;
    requireJob(jobId, user);
    const payload = (await request.json()) as Record<string, unknown>;
    const runId = typeof payload.runId === "string" ? payload.runId : "";
    const mode = payload.mode === "strict" ? "strict" : payload.mode === "adaptive" ? "adaptive" : undefined;
    if (!runId) {
      throw new Error("runId is required");
    }

    const job = getJobOrThrow(jobId);
    const document = (job.documents ?? []).find((entry) => entry.fileId === docId);
    if (!document) {
      return NextResponse.json({ error: "Document not found" }, { status: 404 });
    }
    const outcome = pickOutcome(document.outcomes, mode ?? null, runId);
    if (!outcome?.docId || outcome.runId !== runId || outcome.status !== "processed") {
      throw new Error("Only processed documents can be reviewed");
    }

    const detail = getRunDocument(runId, outcome.docId);
    const fieldsPayload = Array.isArray(payload.fields) ? payload.fields : [];
    const fields: ReviewFieldResult[] = fieldsPayload.map((item) => {
      const entry = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
      return {
        fieldKey: String(entry.fieldKey ?? "").trim(),
        fieldLabel: String(entry.fieldLabel ?? entry.fieldKey ?? "").trim(),
        extractedValue: String(entry.extractedValue ?? "N/A").trim() || "N/A",
        correctedValue: typeof entry.correctedValue === "string" && entry.correctedValue.trim() ? entry.correctedValue.trim() : null,
        reviewState: String(entry.reviewState ?? "wrong_value") as ReviewFieldResult["reviewState"],
        reviewNote: typeof entry.reviewNote === "string" && entry.reviewNote.trim() ? entry.reviewNote.trim() : null,
      };
    });
    if (fields.length === 0) {
      throw new Error("Review requires at least one field");
    }
    const artifact = buildReviewArtifact({
      jobId,
      runId,
      docId: outcome.docId,
      detail,
      fieldConfig: job.fieldConfigCurrent ?? [],
      reviewSource: "human",
      fields,
      expectedFieldValues: outcome.expectedFieldValues ?? null,
    });
    const feedbackResult = await postReviewedFeedback(artifact);
    const reviewedArtifact = attachReviewFeedbackResult(artifact, feedbackResult);
    writeReviewArtifact(reviewedArtifact);

    const updated = mutateJob(jobId, (current) => {
      const currentDocument = (current.documents ?? []).find((entry) => entry.fileId === docId);
      if (currentDocument) {
        applyReviewToJobDocument(currentDocument, reviewedArtifact, runId, mode);
      }
      const reviewStats = collectJobReviewLearningStats(current, current.fieldConfigCurrent ?? []);
      current.reviewContext = refreshJobValidationContext(current, current.fieldConfigCurrent ?? [], "human_review");
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

    return NextResponse.json({ job: updated, review: reviewedArtifact }, { headers: NO_STORE_HEADERS });
  } catch (error) {
    return apiError(error, 400);
  }
}
