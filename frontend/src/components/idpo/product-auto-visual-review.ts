import type { ProductAutoDocumentDetail, ProductAutoLinkedCell, ProductAutoValue } from "@/types/product-auto";

export function sourceTextPanelCopy(
  visualRoute: ProductAutoDocumentDetail["visualRoute"], isNative: boolean,
  sourcePages: readonly { text: string }[],
): { introduction: string; summary: string; emptyMessage: string | null } {
  const visual = visualRoute === "visual";
  return {
    introduction: visual
      ? "Compare image-derived values with the original source. Record the page you observed for added values."
      : "Compare each proposed value and source quote against the uploaded document.",
    summary: `${isNative ? "Native source text by unit" : "OCR text by page"} · ${visual
      ? "image additions use a reviewer-observed page" : "copy exact quotes for added fields"}`,
    emptyMessage: sourcePages.length === 0
      ? "No source pages were recorded. Source-backed additions require a valid page."
      : sourcePages.every((page) => !page.text.trim())
        ? visual
          ? "No OCR text was extracted. Inspect the original image and record its page for additions."
          : "No source text was extracted. Exact-quote additions require source text."
        : null,
  };
}

export function isVisualProposal(value: ProductAutoValue | undefined): boolean {
  return value?.visual_grounding_verified === false;
}

export function machineProposalLabel(value: ProductAutoValue | undefined): string {
  if (isVisualProposal(value)) return "Image-derived — review required";
  if (value?.status === "accepted") return "Text matched";
  return value?.status?.replaceAll("_", " ") ?? "no value";
}

export function visualLinkedCellsReviewable(
  cells: readonly ProductAutoLinkedCell[], sourcePages: readonly { page: number }[],
): boolean {
  const pages = new Set(sourcePages.map((page) => page.page));
  return cells.length > 0 && cells.every((cell) => cell.status === "needs_review" &&
    cell.review_state === "pending" && cell.visual_grounding_verified === false &&
    Number.isSafeInteger(cell.visual_page) && pages.has(cell.visual_page!));
}

export function pdfSourcePageUrl(sourceUrl: string, fileName: string, page: number,
  sourcePages: readonly { page: number }[]): string | null {
  if (!/\.pdf$/i.test(fileName) || !Number.isSafeInteger(page) || page < 1 ||
    !sourcePages.some((source) => source.page === page)) return null;
  return `${sourceUrl}#page=${page}`;
}
