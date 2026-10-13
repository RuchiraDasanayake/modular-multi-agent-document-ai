# Schema-suggestion intake correction — 13 October 2026

## Scope and decision

This is an onboarding correction based on `1196475`, after the extraction evaluation was frozen.
It does not change either frozen benchmark checkout, run predictions, labels, scoring, or the
confirmed-schema extraction method used by that campaign. No benchmark document was opened for
this task. No paid model call or real OCR worker was used for the regression tests.

| Surface | Classification | Action | Acceptance check |
| --- | --- | --- | --- |
| `brief_draft.py` sample parsing | core | simplify | Shared PDF/image intake and configured OCR replace the duplicate parser |
| `IntakeAgent` PDF preview entry point | core | simplify | Same guard, bounded prefix; ordinary full intake retains its behavior |
| Preview regression tests and system contract | supporting | keep | Explicit source, page, engine, failure, and draft-contract checks |
| This report | research_evidence | keep | Distinguish a reproduced onboarding defect from extraction quality evidence |

## Reproduction

A self-authored PDF has a visible raster invoice and invisible text using PDF text render mode 3.
The hidden text names “Wrong Company”; the visible image contains a different invoice description.
Before the correction, `_sample_text` returned parser `pypdf-first-two-pages` with 210 characters
of hidden metadata. The visible invoice text was absent. Any nonempty, nongarbled native text
was sufficient to bypass OCR, irrespective of whether that text painted on the page.

The same shortcut also skipped a scanned second page when the first page had readable native text.
These are input-selection failures before schema generation, not evidence of model hallucination.

## Correction

- `IntakeAgent.preview_pdf` limits native-text extraction and paint inspection to the first two
  pages, after rejecting documents over the existing 50-page product limit. It calls the same
  internal parser and native-layer inspection as full intake. Ordinary intake defaults are unchanged.
- PDF/image sample parsing uses `OcrAgent`, with `IDPO_AUTO_OCR_ENGINE` selecting `rapidocr` or
  `tesseract`, matching the server's choices and default. The separate direct Tesseract and PDFium
  implementation is removed. RapidOCR keeps its pinned worker, models, image bounds, and resource
  checks. PDF rasterization uses the existing capped renderer and effective-DPI policy.
- OCR uses one pass, no quality reruns, and a 15-second per-page budget. Reported OCR failures stop
  before the schema model call; rejected native text cannot become a fallback excerpt. Empty total
  sample text also prevents a call. Input images retain the 12-million-pixel preview bound.
- Render/OCR scratch artifacts are created under the configured data directory and removed on
  normal completion or handled failure. Source hashes are still checked before and after parsing. Public provenance
  retains its existing shape, with versioned preview parser IDs indicating the configured engine.
- The draft request and response, one-call provider limit, 1,800-character per-source excerpt,
  9,000-character total, questions, editable fields, and explicit user confirmation remain unchanged.
  Text, JSON, and native-format sample routes are unchanged.

## Validation and limitations

The synthetic suite covers hidden metadata, both mixed-page orders, no inspection/OCR of page 3,
normal digital text without OCR, default full intake retaining all pages with identical prefix
metadata, 51-page rejection before extraction/rendering, missing page-count parser, invalid bounds
and engine, empty OCR, resource/time failures through the actual RapidOCR adapter with a mocked
recognizer, engine selection for images, and scratch cleanup. Existing draft-contract and paint-guard
tests are included. OCR output and model responses in these tests are controlled fixtures; this
proves routing and failure behavior, not real-world recognition or schema quality.

Validation on the product Python runtime:

- Preview, existing draft, and PDF native-layer suites: **36 passed**.
- Existing preprocessing, raster bounds, RapidOCR adapter and integration suites: **90 passed,
  2 skipped**. The skips are explicitly opt-in real OCR runtime tests; no OCR models were run.
- Direct comparison with `IntakeAgent` loaded from base commit `1196475`: all document/page fields
  and metadata were identical for digital, hidden-layer, and three-page mixed synthetic PDFs.
- Ruff passes for the changed draft module and new test module; intake retains its **two existing
  BLE001 warnings**, verified against the base revision. `git diff --check` passes.

The paint guard conservatively re-OCRs invisible text over a page image, including some legitimate
searchable OCR layers. That can add cost or yield worse recognition; invisibility alone does not
imply malicious or inaccurate text. A 15-second preview budget can reject a cold or busy worker
that would finish under extraction's longer budget. The existing 120-second outer suggestion
deadline remains; multiple difficult samples can exceed it. The page prefix and character caps
still omit later content, so suggested fields require review and may need additions. Multi-frame
images follow the configured shared engine's support limits. Abrupt process termination can leave
preview scratch files for operator cleanup. These limitations are not resolved by
the frozen extraction benchmark and are not presented as a measured schema-quality improvement.
