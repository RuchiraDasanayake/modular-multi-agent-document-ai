import { compareFieldValues } from "@/lib/idpo/exact-comparison";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatReviewSummary(review: Record<string, unknown>): string | null {
  const status = typeof review.reviewStatus === "string" ? review.reviewStatus : null;
  const metrics = asRecord(review.metrics);
  const f1 = asNumber(metrics?.f1);
  if (!status || f1 == null) {
    return status;
  }
  return `${status} | F1 ${f1.toFixed(2)}`;
}

export interface DocumentReviewRow {
  fieldKey: string;
  fieldLabel: string;
  extractedValue: string;
  correctedValue: string;
  reviewState: string;
  reviewNote: string;
}

function normalizeFieldKey(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}

export function reviewRowsFromReviewArtifact(review: unknown): DocumentReviewRow[] {
  const reviewRecord = asRecord(review);
  const fields = Array.isArray(reviewRecord?.fields) ? reviewRecord.fields : [];
  return fields.map((item) => {
    const entry = asRecord(item) ?? {};
    return {
      fieldKey: String(entry.fieldKey ?? ""),
      fieldLabel: String(entry.fieldLabel ?? entry.fieldKey ?? ""),
      extractedValue: String(entry.extractedValue ?? "N/A"),
      correctedValue: typeof entry.correctedValue === "string" ? entry.correctedValue : "",
      reviewState: String(entry.reviewState ?? "correct"),
      reviewNote: typeof entry.reviewNote === "string" ? entry.reviewNote : "",
    };
  });
}

export function suggestedReviewRowsFromDocumentPayload(payload: Record<string, unknown> | null): DocumentReviewRow[] {
  if (!payload) {
    return [];
  }

  const requestedFields = Array.isArray(payload.requestedFields) ? payload.requestedFields : [];
  const fieldValues = asRecord(payload.fieldValues) ?? {};
  const expectedFieldValues = asRecord(payload.expectedFieldValues) ?? {};
  const savedRows = reviewRowsFromReviewArtifact(payload.review);
  const savedByKey = new Map(savedRows.map((row) => [normalizeFieldKey(row.fieldKey || row.fieldLabel), row] as const));

  const labelsByKey = new Map<string, string>();
  for (const item of requestedFields) {
    const entry = asRecord(item) ?? {};
    const fieldLabel = String(entry.name ?? "").trim();
    if (!fieldLabel) {
      continue;
    }
    labelsByKey.set(normalizeFieldKey(fieldLabel), fieldLabel);
  }

  const allKeys = new Set<string>([
    ...labelsByKey.keys(),
    ...Object.keys(fieldValues).map((key) => normalizeFieldKey(key)),
    ...Object.keys(expectedFieldValues).map((key) => normalizeFieldKey(key)),
    ...savedByKey.keys(),
  ]);

  const rows: DocumentReviewRow[] = [];
  for (const key of allKeys) {
    const saved = savedByKey.get(key);
    if (saved) {
      rows.push(saved);
      continue;
    }

    const fieldLabel = labelsByKey.get(key) ?? key;
    const extractedValue =
      String(fieldValues[key] ?? fieldValues[fieldLabel] ?? "N/A").trim() || "N/A";
    const expectedValue =
      typeof expectedFieldValues[key] === "string"
        ? String(expectedFieldValues[key]).trim()
        : typeof expectedFieldValues[fieldLabel] === "string"
          ? String(expectedFieldValues[fieldLabel]).trim()
          : "";

    let reviewState: DocumentReviewRow["reviewState"] = "correct";
    let correctedValue = "";

    if (expectedValue) {
      correctedValue = expectedValue;
      if (extractedValue === "N/A" || extractedValue === "") {
        reviewState = "missed_field";
      } else if (compareFieldValues(key, extractedValue, expectedValue)) {
        reviewState = "correct";
      } else {
        reviewState = "wrong_value";
      }
    } else if (extractedValue !== "N/A" && extractedValue !== "") {
      reviewState = "hallucinated_field";
    } else {
      reviewState = "correctly_skipped";
    }

    rows.push({
      fieldKey: key,
      fieldLabel,
      extractedValue,
      correctedValue,
      reviewState,
      reviewNote: "",
    });
  }

  return rows.sort((left, right) => left.fieldLabel.localeCompare(right.fieldLabel));
}

export function mergeSavedReviewIntoDocumentPayload(
  payload: Record<string, unknown> | null,
  review: unknown,
): Record<string, unknown> | null {
  if (!payload) {
    return payload;
  }

  const reviewRecord = asRecord(review);
  if (!reviewRecord) {
    return payload;
  }

  const metrics = asRecord(reviewRecord.metrics) ?? {};
  const detail = asRecord(payload.detail) ?? {};
  const metadata = asRecord(detail.metadata) ?? {};
  const support = asRecord(payload.support) ?? {};
  const ahmn = asRecord(support.ahmn) ?? {};
  const hitl = asRecord(support.hitl) ?? {};
  const feedback = asRecord(reviewRecord.ahmnReviewFeedback) ?? {};
  const reviewSummary = formatReviewSummary(reviewRecord);

  return {
    ...payload,
    review: reviewRecord,
    reviewState: reviewSummary ?? payload.reviewState,
    support: {
      ...support,
      ahmn: {
        ...ahmn,
        reviewedFeedbackLogged:
          typeof feedback.logged === "boolean" ? feedback.logged : ahmn.reviewedFeedbackLogged ?? false,
        reviewedFeedbackError:
          typeof feedback.error === "string" || feedback.error === null ? feedback.error : ahmn.reviewedFeedbackError ?? null,
      },
      hitl: {
        ...hitl,
        reviewState: reviewRecord.reviewStatus ?? reviewSummary ?? hitl.reviewState ?? payload.reviewState ?? null,
        reviewSource: reviewRecord.reviewSource ?? hitl.reviewSource ?? null,
      },
    },
    detail: {
      ...detail,
      review: reviewRecord,
      metadata: {
        ...metadata,
        exactPrecision: metrics.precision ?? metadata.exactPrecision ?? null,
        exactRecall: metrics.recall ?? metadata.exactRecall ?? null,
        exactF1: metrics.f1 ?? metadata.exactF1 ?? null,
      },
    },
  };
}
