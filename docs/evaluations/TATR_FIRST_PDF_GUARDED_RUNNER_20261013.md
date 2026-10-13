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
  character order. A page with no valid native words goes through one full-page
  pass in the separate pinned RapidOCR CPU subprocess. The detector operates
  on the full page; each retained
  `table` or `table rotated` query at score at least 0.5 becomes a five-pixel
  crop. Rotated tables receive the pinned clockwise 90-degree transform.
  The structure model runs at the pinned 1000-pixel maximum resize and the
  already tested cell adapter applies the frozen 0.5 class prefilter.
  All raw model queries, word tokens, source boxes, crop transforms and
  unassigned token IDs are retained in `raw_pages.json`.
- Each detected crop must produce exactly one retained structure `table`
  query at the frozen 0.5 threshold. Zero or multiple table queries fail the
  PDF. The worker never selects a highest-score table after observing output.
- Table and cell boxes map from crop coordinates to rendered page pixels and
  PDF page points. The worker rejects partial crop words, ambiguous cell
  grids, out-of-bounds boxes, invalid spans, duplicate word assignments, and
  failed page-coordinate round trips. It emits `ParsedDocument v2` with
  source-page boxes and no invented quote anchors. The emitted table anchor
  encloses the **refined cell union**; the raw structure-table query box is
  retained separately. `SourceUnit` dimensions are omitted because PDFium's
  raw MediaBox coordinate frame differs from the rotated/cropped page view;
  CropBox, MediaBox, rotation and rendered size are in `raw_pages.json`.
- The worker reads and hashes the selected PDF bytes once, then uses those
  same in-memory bytes for parsing and a separate PDFium rerender. It writes
  `first_nonempty_source_overlay.png` with stable table/row/column labels and
  a text/box legend. The supervisor reconstructs the parsed table contract,
  compares cell counts and text with raw details and the legend, validates the
  overlay PNG and dimensions, and stops with a **pending manual visual
  verdict**. No continuation to the other eleven is automated.

The text route follows the pre-score amendment at the top of
[`TATR_ADBUY12_RESEARCH_PROTOCOL_20261013.md`](TATR_ADBUY12_RESEARCH_PROTOCOL_20261013.md).
The handoff passes a lossless RGB PNG, not a PDF or gold, to the pinned OCR
runtime. That process verifies its package, wheel, model and notice inventory
before loading the raster. It preserves raw line tuples, word quadrilaterals,
source order and engine/revision IDs. The integrated orientation guard rejects
180-degree and uncertain lines before word-box construction. The TATR worker
checks the returned line/word consistency and accepts no mixed native/OCR page,
partial OCR result, retry or score-based word filter. An OCR failure fails the
document. The parser version for this word-route integration is
`research-word-route-first-pdf-v2`.

Child environments are allowlisted and offline; host cloud/API credentials,
proxy and cache overrides are not passed through. The supervisor records the
allowlisted environment's key set and digest, clean Git commit, source-code
hashes, and actual C:/I: volume roots/IDs. A separate committed first-PDF
research gate must match the source selection, cohort, code and CPU/OCR locks
before document inference; the earlier CPU **synthetic** receipt's
`document_inference_permitted: false` remains true for that receipt.

Failure receipts store only bounded error type/reason codes. They do not
persist arbitrary exception messages or tracebacks, which can include private
source text or secrets when this research code is reused.

## Safety limits

| Guard | Frozen value |
| --- | ---: |
| Source PDF | at most 2,000,000 bytes and 20 pages |
| Raster | 300 DPI, at most 35 million pixels per page |
| Detected tables | at most 20 active proposals per page; excess fails the PDF |
| Preflight | at least 6 GiB available RAM; 4 GiB free on host and data disks |
| During worker | at least 3 GiB available host RAM, at most 8 GiB process-tree RSS, 4 GiB free on both disks |
| Time | 180 s startup, 360 s conversion, 600 s first worker, 3,600 s full-run ceiling |
| OCR page child | 120 s; included in supervisor's 8 GiB process-tree RSS accounting |
| OCR transport | one RGB PNG at most 64 MiB and 35 million pixels; one result JSON at most 16 MiB, 10,000 lines and 50,000 words |

The 35-million-pixel and 20-proposal safety caps are declared before any
selected PDF or gold is opened. Crossing either cap fails the PDF; the runner
does not silently truncate pages or proposals. Its output directory must be
new, on the frozen I: data disk, and outside the repository, corpus and model
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

The synthetic native test draws a two-word PDF, uses controlled detector/structure
queries, and exercises PDFium rendering, native words, pinned cell functions,
source-coordinate projection, `ParsedDocument v2`, rerendered overlay,
manifest checks and artifact-tamper rejection. Blank synthetic pages fail
before detector inference. Resource floor boundaries are tested. Existing
rotation/crop and cell adapter suites also pass. A second synthetic image-only
PDF exercises the full-page OCR subprocess, pinned runtime check, word boxes,
cell adapter, `ParsedDocument v2` and source-pixel overlay. A source-free raster
test confirms four OCR words on an upright page and rejects the 180-degree
version with a bounded failure receipt. Native-word pages suppress OCR.

Both `PinnedCpuModels` calls were exercised on a synthetic 512 by 384 white
image in the pinned CPU interpreter: detection returned 15 raw queries and
structure returned 125, with the expected three unused detection buffers.
This verifies this worker's model API call path, not cell quality. No actual
TATR forward pass on a selected PDF has occurred. Before the first selected
PDF, merge and independently review this scaffold with the current CPU lock,
OCR orientation guard, OCR handoff and page-geometry corrections; then rerun
source-free tests and verify the first-PDF guard on the merged checkout. The
first selected result then needs a human
source-pixel overlay verdict. It cannot establish 219-row accuracy, product
field quality, cost, or 2,000-document performance.
