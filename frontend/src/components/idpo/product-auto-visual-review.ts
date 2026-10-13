import type { ProductAutoLinkedCell, ProductAutoValue } from "@/types/product-auto";

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
