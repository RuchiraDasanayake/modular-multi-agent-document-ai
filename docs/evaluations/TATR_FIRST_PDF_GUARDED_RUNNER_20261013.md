# Guarded first-PDF TATR runner: source-free integration result

**Status: synthetic integration passed; selected PDF and gold remain unopened.**
This is a research-only runner for the first source in the frozen VRDU ad-buy
selection. It is not wired into product extraction, human review, or the
2,000-document quality gate. The owning surfaces are `product_eval/`
(`research_evidence`, keep) and the shared PDFium projection helper
(`supporting`, simplify). No product contract changed.

## Implemented boundary

- The supervisor checks the unchanged 12-source selection and each original
  source hash using the existing `verify_selection` function. It then starts
  **one** child process for the first PDF. The worker has no gold path, import,
  or score function. The other eleven are explicitly unattempted.
- The worker independently verifies the full installed TATR CPU runtime lock,
  staged model assets, source hash and file limit before opening the PDF.
  Both safetensors load offline with remote code disabled on CPU/four threads.
  It writes the runtime/package/notice manifest and a startup-ready marker
  before document conversion.
- Pages render with PDFium at 300 DPI. Native PDFium words follow source
  character order. The detector operates on the full page; each retained
  `table` or `table rotated` query at score at least 0.5 becomes a five-pixel
  crop. Rotated tables receive the pinned clockwise 90-degree transform.
  The structure model runs at the pinned 1000-pixel maximum resize and the
  already tested cell adapter applies the frozen 0.5 class prefilter.
  All raw model queries, word tokens, source boxes, crop transforms and
  unassigned token IDs are retained in `raw_pages.json`.
- Table and cell boxes map from crop coordinates to rendered page pixels and
  PDF page points. The worker rejects partial crop words, ambiguous cell
  grids, out-of-bounds boxes, invalid spans, duplicate word assignments, and
  failed page-coordinate round trips. It emits `ParsedDocument v2` with
  source-page boxes and no invented quote anchors.
- A separate PDFium reopen/rerender produces `first_nonempty_source_overlay.png`
  with cell boxes drawn over source pixels. The supervisor verifies artifact
  hashes and at least one nonempty table cell, then stops with a **pending
  manual visual verdict**. No continuation to the other eleven is automated.

The text route follows the pre-score amendment at the top of
[`TATR_ADBUY12_RESEARCH_PROTOCOL_20261013.md`](TATR_ADBUY12_RESEARCH_PROTOCOL_20261013.md).
That amendment supersedes the older step 2 sentence saying OCR granularity
and native word extraction remain unfrozen. This first runner is **native-only**:
an image-only page raises `MissingOcrRoute` before model inference and fails
the whole document. The pinned RapidOCR word adapter and its 180-degree
orientation guard still need an isolated subprocess handoff. That handoff
must pass a full-page raster to the OCR runtime, return raw line tuples and
word polygons with engine/revision IDs, verify the OCR lock, and never mix OCR
and native words on one page. An OCR failure must remain a document failure.

## Safety limits

| Guard | Frozen value |
| --- | ---: |
| Source PDF | at most 2,000,000 bytes and 20 pages |
| Raster | 300 DPI, at most 35 million pixels per page |
| Detected tables | at most 20 active proposals per page; excess fails the PDF |
| Preflight | at least 6 GiB available RAM; 4 GiB free on host and data disks |
| During worker | at least 3 GiB available host RAM, at most 8 GiB process-tree RSS, 4 GiB free on both disks |
| Time | 180 s startup, 360 s conversion, 600 s first worker, 3,600 s full-run ceiling |

The 35-million-pixel and 20-proposal safety caps are declared before any
selected PDF or gold is opened. Crossing either cap fails the PDF; the runner
does not silently truncate pages or proposals. Its output directory must be
new, on the declared data disk, and outside the repository, corpus and model
stage. Any child failure or resource violation leaves a failure receipt and
does not trigger a retry.

PDFium's `FPDF_DeviceToPage` takes integer bitmap coordinates while model
boxes have fractional edges. The shared adapter expands each edge outward to
its enclosing integer pixel. This adds **less than one source raster pixel per
edge**. At 300 DPI that is nominally less than 0.24 PDF point per edge;
the exact point bound depends on the rendered page's pixel-to-point ratio
(`page_width_points / rendered_width_pixels` or the corresponding height).
The worker separately rejects any box whose reverse projection differs by
more than 1.01 source pixels per coordinate. This is a geometry bound, not
evidence that a cell contains the correct text.

## Evidence and next gate

The synthetic test draws a two-word PDF, uses controlled detector/structure
queries, and exercises PDFium rendering, native words, pinned cell functions,
source-coordinate projection, `ParsedDocument v2`, rerendered overlay,
manifest checks and artifact-tamper rejection. Blank synthetic pages fail
before detector inference. Resource floor boundaries are tested. Existing
rotation/crop and cell adapter suites also pass.

Both `PinnedCpuModels` calls were exercised on a synthetic 512 by 384 white
image in the pinned CPU interpreter: detection returned 15 raw queries and
structure returned 125, with the expected three unused detection buffers.
This verifies this worker's model API call path, not cell quality. No actual
TATR forward pass on a selected PDF has occurred. Before the first selected
PDF, merge and review
this scaffold with the current CPU lock and OCR orientation guard, complete
the isolated OCR handoff, rerun source-free tests, and verify the first-PDF
guard on the merged checkout. The first selected result then needs a human
source-pixel overlay verdict. It cannot establish 219-row accuracy, product
field quality, cost, or 2,000-document performance.
