import assert from "node:assert/strict";
import test from "node:test";
import {
  mergeSavedReviewIntoDocumentPayload,
  reviewRowsFromReviewArtifact,
  suggestedReviewRowsFromDocumentPayload,
} from "./job-document-review";

test("manual review merge keeps the latest corrected value and metrics", () => {
  const payload = {
    reviewState: "human_reviewed | F1 0.00",
    support: {
      ahmn: {
        reviewedFeedbackLogged: false,
        reviewedFeedbackError: "pending",
      },
      hitl: {
        reviewState: "human_reviewed | F1 0.00",
        reviewSource: "human",
      },
    },
    detail: {
      metadata: {
        exactPrecision: 0,
        exactRecall: 0,
        exactF1: 0,
      },
      review: {
        fields: [
          {
            fieldKey: "invoice_number",
            fieldLabel: "invoice_number",
            extractedValue: "N/A",
            correctedValue: "INV-001",
            reviewState: "missed_field",
            reviewNote: "old value",
          },
        ],
      },
    },
    review: {
      fields: [
        {
          fieldKey: "invoice_number",
          fieldLabel: "invoice_number",
          extractedValue: "N/A",
          correctedValue: "INV-001",
          reviewState: "missed_field",
          reviewNote: "old value",
        },
      ],
    },
  } satisfies Record<string, unknown>;

  const latestReview = {
    reviewStatus: "human_reviewed",
    reviewSource: "human",
    metrics: {
      precision: 1,
      recall: 1,
      f1: 1,
    },
    ahmnReviewFeedback: {
      logged: true,
      error: null,
    },
    fields: [
      {
        fieldKey: "invoice_number",
        fieldLabel: "invoice_number",
        extractedValue: "N/A",
        correctedValue: "INV-777",
        reviewState: "missed_field",
        reviewNote: "new value",
      },
    ],
  } satisfies Record<string, unknown>;

  const merged = mergeSavedReviewIntoDocumentPayload(payload, latestReview);
  assert.ok(merged);
  assert.equal(merged.reviewState, "human_reviewed | F1 1.00");

  const mergedReview = merged.review as Record<string, unknown>;
  const rows = reviewRowsFromReviewArtifact(mergedReview);
  assert.equal(rows[0]?.correctedValue, "INV-777");
  assert.equal(rows[0]?.reviewNote, "new value");

  const mergedSupport = merged.support as Record<string, unknown>;
  const mergedAhmn = mergedSupport.ahmn as Record<string, unknown>;
  const mergedHitl = mergedSupport.hitl as Record<string, unknown>;
  assert.equal(mergedAhmn.reviewedFeedbackLogged, true);
  assert.equal(mergedAhmn.reviewedFeedbackError, null);
  assert.equal(mergedHitl.reviewState, "human_reviewed");
  assert.equal(mergedHitl.reviewSource, "human");

  const mergedDetail = merged.detail as Record<string, unknown>;
  const mergedMetadata = mergedDetail.metadata as Record<string, unknown>;
  assert.equal(mergedMetadata.exactPrecision, 1);
  assert.equal(mergedMetadata.exactRecall, 1);
  assert.equal(mergedMetadata.exactF1, 1);
});

test("benchmark payload pre-fills review rows with benchmark-aware states", () => {
  const rows = suggestedReviewRowsFromDocumentPayload({
    requestedFields: [
      { name: "total_amount" },
      { name: "cash_amount" },
      { name: "change_amount" },
    ],
    fieldValues: {
      total_amount: "31.000",
      cash_amount: "40.000",
      extra_label: "TOTAL SALES",
    },
    expectedFieldValues: {
      total_amount: "31000",
      cash_amount: "40,000",
      change_amount: "9.000",
    },
  });

  const byKey = new Map(rows.map((row) => [row.fieldKey, row] as const));
  assert.equal(byKey.get("total_amount")?.reviewState, "correct");
  assert.equal(byKey.get("total_amount")?.correctedValue, "31000");
  assert.equal(byKey.get("cash_amount")?.reviewState, "correct");
  assert.equal(byKey.get("change_amount")?.reviewState, "missed_field");
  assert.equal(byKey.get("change_amount")?.correctedValue, "9.000");
  assert.equal(byKey.get("extra_label")?.reviewState, "hallucinated_field");
});

test("benchmark payload treats fuzzy OCR text matches as correct", () => {
  const rows = suggestedReviewRowsFromDocumentPayload({
    requestedFields: [{ name: "invoice_date" }],
    fieldValues: { invoice_date: "janry 31 1997" },
    expectedFieldValues: { invoice_date: "January 31, 1997" },
  });

  assert.equal(rows[0]?.reviewState, "correct");
  assert.equal(rows[0]?.correctedValue, "January 31, 1997");
});

test("saved review rows override benchmark draft rows", () => {
  const rows = suggestedReviewRowsFromDocumentPayload({
    requestedFields: [{ name: "total_amount" }],
    fieldValues: { total_amount: "208.00" },
    expectedFieldValues: { total_amount: "308,000" },
    review: {
      fields: [
        {
          fieldKey: "total_amount",
          fieldLabel: "total_amount",
          extractedValue: "208.00",
          correctedValue: "308,000",
          reviewState: "wrong_value",
          reviewNote: "reviewed manually",
        },
      ],
    },
  });

  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.reviewState, "wrong_value");
  assert.equal(rows[0]?.correctedValue, "308,000");
  assert.equal(rows[0]?.reviewNote, "reviewed manually");
});
