import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import type { ProductAutoCandidate, ProductAutoLinkedCell } from "@/types/product-auto";
import { machineProposalLabel, pdfSourcePageUrl, sourceTextPanelCopy, visualLinkedCellsReviewable } from "./product-auto-visual-review";

const fixture = JSON.parse(fs.readFileSync(path.join(process.cwd(), "src", "server", "fixtures",
  "visual-review-workflow.json"), "utf8")) as { variants: Record<string, {
    candidate: ProductAutoCandidate; pages: Array<{ page: number; text: string }> }> };

test("actual Python image candidate displays a review warning and keeps page-referenced cells confirmable", () => {
  for (const variant of Object.values(fixture.variants)) {
    const linked = variant.candidate.extracted_values[0]!;
    const scalar = variant.candidate.extracted_values[1]!;
    assert.equal(machineProposalLabel(linked), "Image-derived — review required");
    assert.equal(machineProposalLabel(scalar), "Image-derived — review required");
    assert.equal(visualLinkedCellsReviewable(linked.value as ProductAutoLinkedCell[], variant.pages), true);
  }
});

test("review control disables visual confirmation without complete source page references", () => {
  const variant = fixture.variants.image_only!;
  const cells = (variant.candidate.extracted_values[0]!.value as ProductAutoLinkedCell[]);
  assert.equal(visualLinkedCellsReviewable([], variant.pages), false);
  assert.equal(visualLinkedCellsReviewable([{ ...cells[0]!, visual_page: 99 }], variant.pages), false);
  assert.equal(visualLinkedCellsReviewable([{ ...cells[0]!, status: "accepted" }], variant.pages), false);
  assert.equal(machineProposalLabel({ field_id: "text", value: "x", status: "accepted", review_state: "none" }), "Text matched");
});

test("PDF page navigation only uses validated source page numbers", () => {
  const url = "/api/jobs/job/docs/file/content";
  const pages = [{ page: 1 }, { page: 3 }];
  assert.equal(pdfSourcePageUrl(url, "scan.pdf", 3, pages), `${url}#page=3`);
  assert.equal(pdfSourcePageUrl(url, "scan.pdf", 2, pages), null);
  assert.equal(pdfSourcePageUrl(url, "scan.pdf", -1, pages), null);
  assert.equal(pdfSourcePageUrl(url, "scan.png", 1, pages), null);
});

test("source guidance distinguishes reviewer-observed image pages from exact text quotes", () => {
  const visual = sourceTextPanelCopy("visual", false, [{ text: "" }]);
  assert.match(visual.summary, /reviewer-observed page/);
  assert.match(visual.introduction, /Record the page/);
  assert.match(visual.emptyMessage!, /No OCR text was extracted/);
  assert.doesNotMatch(visual.emptyMessage!, /exact quote/i);

  const text = sourceTextPanelCopy("text", false, [{ text: "Invoice ABC" }]);
  assert.match(text.summary, /copy exact quotes/);
  assert.equal(text.emptyMessage, null);
  assert.match(sourceTextPanelCopy("text", false, [{ text: "  " }]).emptyMessage!, /No source text was extracted/);
  assert.match(sourceTextPanelCopy("visual", false, []).emptyMessage!, /No source pages were recorded/);
});
