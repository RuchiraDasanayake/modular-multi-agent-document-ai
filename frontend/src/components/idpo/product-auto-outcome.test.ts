import assert from "node:assert/strict";
import test from "node:test";
import { productAutoOutcomeCopy } from "./product-auto-outcome";

test("multi-frame rejection gives a bounded split action without inviting corrections", () => {
  const copy = productAutoOutcomeCopy("unsupported", "multi_frame_image_unsupported", 0);
  assert.match(copy?.cause ?? "", /multiple frames/);
  assert.match(copy?.action ?? "", /Split the frames/);
  assert.match(copy?.sourceNote ?? "", /nothing to review or correct/);
});

test("unknown backend failure text never becomes user-facing copy", () => {
  const secret = "provider exception with credentials";
  const copy = productAutoOutcomeCopy("failed", secret as never, 2);
  assert.ok(copy);
  assert.equal(JSON.stringify(copy).includes(secret), false);
  assert.match(copy.sourceNote, /unavailable for review or export/);
  assert.equal(productAutoOutcomeCopy("needs_review", "parse_failed", 0), null);
});
