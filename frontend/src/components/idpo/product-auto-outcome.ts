import type { ProductAutoDocumentStatus, ProductAutoOutcomeReason } from "@/types/product-auto";

const KNOWN_OUTCOMES: Record<ProductAutoOutcomeReason, { cause: string; action: string }> = {
  document_processing_failed: {
    cause: "An unexpected processing error stopped this document. Other documents can continue.",
    action: "A model request may already have been charged. Ask an administrator to inspect this attempt before starting a separate extraction for this file.",
  },
  unsupported_file_type: {
    cause: "This file type is not supported for extraction.",
    action: "Convert it to a supported format shown on the upload page, then upload and run it again.",
  },
  file_too_large: {
    cause: "This file exceeds the extraction size limit.",
    action: "Split or reduce the file, then upload the smaller parts and run them again.",
  },
  too_many_pages: {
    cause: "This file has more pages than one extraction run accepts.",
    action: "Split it into smaller files, then upload and run each part.",
  },
  json_document_limit_exceeded: {
    cause: "This JSON file contains more than 5,000 logical documents, the limit for one extraction run.",
    action: "Split the JSON into batches of at most 5,000 logical documents, then upload and extract each batch in a separate run.",
  },
  native_limit_exceeded: {
    cause: "This document exceeds a native parser limit.",
    action: "Split or simplify the document, then upload and run the parts again.",
  },
  multi_frame_image_unsupported: {
    cause: "This image contains multiple frames, which this image route does not extract together.",
    action: "Split the frames into separate images or convert them to a multipage PDF, then upload and run them again.",
  },
  native_parser_unavailable: {
    cause: "The parser needed for this file is unavailable on this deployment.",
    action: "Ask an administrator to enable the parser, or convert the file to another supported format and try again.",
  },
  parse_failed: {
    cause: "The source file could not be prepared for extraction.",
    action: "Open the original file, check that it is valid, and upload a fresh copy before trying again.",
  },
  ocr_failed: {
    cause: "Text preparation failed before a reviewable result could be produced.",
    action: "Check the original image or PDF and retry with a clearer copy. Ask an administrator to inspect OCR if it repeats.",
  },
  schema_provider_error: {
    cause: "The model service did not complete schema discovery.",
    action: "A model call may have been charged. Ask an administrator to check the service before starting a separate attempt.",
  },
  invalid_schema_model_response: {
    cause: "The model did not return a complete, valid schema proposal.",
    action: "Enter and confirm the required fields, or start a separate attempt. The failed model call may have been charged.",
  },
  values_provider_error: {
    cause: "The model service did not complete value extraction.",
    action: "A model call may have been charged. Ask an administrator to check the service before starting a separate attempt.",
  },
  invalid_values_model_response: {
    cause: "The model did not return a complete, valid extraction result.",
    action: "The model call may have been charged. Start a separate attempt only after reviewing this failure.",
  },
  invalid_strict_values_model_response: {
    cause: "The model did not return every required field in a complete, valid result.",
    action: "The model call may have been charged. Start a separate attempt only after reviewing this failure.",
  },
};

export function productAutoOutcomeCopy(status: ProductAutoDocumentStatus,
  reason: ProductAutoOutcomeReason | undefined, sourcePageCount: number): {
    title: string; cause: string; action: string; sourceNote: string;
  } | null {
  if (status !== "failed" && status !== "unsupported") return null;
  const known = reason ? KNOWN_OUTCOMES[reason] : undefined;
  return {
    title: status === "unsupported" ? "Document could not be extracted" : "Extraction failed for this document",
    cause: known?.cause ?? "This run did not produce a complete, reviewable result.",
    action: known?.action ?? "Open the original, upload a valid supported copy, and start a new run. Ask an administrator to inspect server logs if it repeats.",
    sourceNote: sourcePageCount === 0
      ? "No source pages were prepared, so there is nothing to review or correct in this run."
      : "Any partial machine values from this failed run are unavailable for review or export. Start a new run after resolving the issue.",
  };
}
