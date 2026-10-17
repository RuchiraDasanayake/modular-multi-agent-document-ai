import assert from "node:assert/strict";
import test from "node:test";
import { productAutoOutcomeCopy } from "./product-auto-outcome";

test("isolated processing errors preserve uncertainty and do not invite blind retries", () => {
  const copy = productAutoOutcomeCopy("failed", "document_processing_failed", 1);
  assert.match(copy?.cause ?? "", /Other documents can continue/);
  assert.match(copy?.action ?? "", /may already have been charged/);
  assert.match(copy?.action ?? "", /inspect this attempt/);
  assert.match(copy?.sourceNote ?? "", /unavailable for review or export/);
});

test("multi-frame rejection gives a bounded split action without inviting corrections", () => {
  const copy = productAutoOutcomeCopy("unsupported", "multi_frame_image_unsupported", 0);
  assert.match(copy?.cause ?? "", /multiple frames/);
  assert.match(copy?.action ?? "", /Split the frames/);
  assert.match(copy?.sourceNote ?? "", /nothing to review or correct/);
});

test("oversized JSON explains logical-document batching and keeps the result unavailable", () => {
  const copy = productAutoOutcomeCopy("unsupported", "json_document_limit_exceeded", 0);
  assert.match(copy?.cause ?? "", /JSON.*5,000 logical documents/);
  assert.match(copy?.action ?? "", /at most 5,000 logical documents/);
  assert.match(copy?.action ?? "", /each batch in a separate run/);
  assert.match(copy?.sourceNote ?? "", /nothing to review or correct/);
  assert.equal(productAutoOutcomeCopy("needs_review", "json_document_limit_exceeded", 1), null);
});

test("unknown backend failure text never becomes user-facing copy", () => {
  const secret = "provider exception with credentials";
  const copy = productAutoOutcomeCopy("failed", secret as never, 2);
  assert.ok(copy);
  assert.equal(JSON.stringify(copy).includes(secret), false);
  assert.match(copy.sourceNote, /unavailable for review or export/);
  assert.equal(productAutoOutcomeCopy("needs_review", "parse_failed", 0), null);
});

test("incomplete model output is explained as a failed attempt, not missing source values", () => {
  const copy = productAutoOutcomeCopy("failed", "invalid_strict_values_model_response", 1);
  assert.match(copy?.cause ?? "", /every required field/);
  assert.match(copy?.sourceNote ?? "", /unavailable for review or export/);
  assert.equal(productAutoOutcomeCopy("needs_review", "invalid_strict_values_model_response", 1), null);
});

test("verified output truncation has a specific action without making the failed result reviewable", () => {
  const copy = productAutoOutcomeCopy("failed", "invalid_strict_values_model_response", 1, "output_token_limit");
  assert.match(copy?.cause ?? "", /output length limit/);
  assert.match(copy?.action ?? "", /Reduce the requested fields or split a long document/);
  assert.match(copy?.action ?? "", /may cost money.*not retried automatically/);
  assert.match(copy?.sourceNote ?? "", /unavailable for review or export/);
  assert.equal(productAutoOutcomeCopy("needs_review", undefined, 1, "output_token_limit"), null);
  assert.match(productAutoOutcomeCopy("failed", "invalid_strict_values_model_response", 1,
    "untrusted provider text" as never)?.cause ?? "", /every required field/);
});
