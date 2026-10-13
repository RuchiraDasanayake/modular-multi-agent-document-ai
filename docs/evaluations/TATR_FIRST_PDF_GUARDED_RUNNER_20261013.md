# Guarded first-PDF TATR runner and research trial

**Status: synthetic integration passed; three separately gated first-PDF trials failed before table output.**
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
  character order. A page with no projectable native words goes through one full-page
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
document. The initial parser version was `research-word-route-first-pdf-v2`;
the amended geometry-fallback version is `research-word-route-first-pdf-v3`.

Child environments are allowlisted and offline; host cloud/API credentials,
proxy and cache overrides are not passed through. The supervisor records the
allowlisted environment's key set and digest, clean Git commit, source-code
hashes, and actual C:/I: volume roots/IDs. A separate committed first-PDF
research gate must match the source selection, cohort, code and CPU/OCR locks
before document inference; the earlier CPU **synthetic** receipt's
`document_inference_permitted: false` remains true for that receipt.
The v1 committed [research gate](../../product_eval/fixtures/tatr_first_pdf_research_gate_v1.json),
SHA-256 `3fce9f540882f9051dc0a31fa5831967bea2c7f607aa663efa23567c84c62dfc`,
permits exactly one selected PDF with no gold access, tied to every local Python
file under `product_eval` and `idpo/product_auto` (plus `idpo/__init__.py`),
**130 Python files in this checkout**,
and the unchanged selection/cohort/runtime-lock hashes. This gate is not a
product release permission or a new quality result.

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
This verifies this worker's model API call path, not cell quality. The real
first-PDF outcome and the proposed next gate are recorded below. No source
overlay, 219-row accuracy, product field quality, cost, or 2,000-document
improvement has been established.

## Immutable first-PDF attempt, v1

On the clean `2709ab95ecedb4323dc16cb4564a0b6febc938d9` checkout, the
committed one-document gate SHA-256
`3fce9f540882f9051dc0a31fa5831967bea2c7f607aa663efa23567c84c62dfc`
allowed only the first source (SHA-256
`00af9ec9594520a61f852e0ccfd93441f068b38fc120625a0571e04941eb1060`).
The new output directory was `I:\DocAI-Benchmarks\tatr-adbuy12-v1`. Model
startup succeeded offline, but the worker exited after 39.081 seconds with a
bounded `GeometryError` while projecting native PDF text. The supervisor
recorded `status: failed`, `reason: worker_failed`; no parsed document or
overlay exists, gold was not opened, and the other eleven sources were not
attempted. The immutable `first_pdf_receipt.json` SHA-256 is
`3e068faa08cd52208674d1772db1075285653e7dd01f896129ca1b952a78bdc5`.
This attempt provides no table-quality result. The v1 output must remain
untouched; any corrected trial requires a new profile and directory.

Source-only diagnosis on that same PDF found 2,576 valid non-whitespace PDFium
character boxes on page one, one character box intersecting the right edge,
and three boxes wholly outside the rendered page. Pages two and three had
3,021 and 1,094 valid boxes and no out-of-page boxes. The strict source-word
projection fails the entire PDF on the first out-of-page character. This
explains the bounded failure without consulting gold or parser scores. A
separately frozen rule for visible native characters and an independently
reviewed v2 gate are required before another model inference.

## Frozen v2 corrective trial

The correction catches `GeometryError` only while constructing native page
words. It discards that incomplete native attempt, invokes one pinned full-page
OCR pass, and records `native_route_rejected: unprojectable_native_character`
in the page detail. Detector, crop, cell and source-anchor geometry failures
still fail the document. OCR absence, empty words or failure also stops it.
The synthetic off-page-word regression verifies one OCR call and a single
source route. The parser version is `research-word-route-first-pdf-v3`.

The new committed [v2 one-document gate](../../product_eval/fixtures/tatr_first_pdf_research_gate_v2.json),
SHA-256 `699993c0b7eb10ea00737d62323795702e2a65587215a20d1efb2f7bc98ae8a1`,
binds the unchanged source selection, cohort and CPU/OCR runtime locks, all
**132 local Python files** in this checkout, the immutable v1 failure receipt
hash, and the fresh `I:\DocAI-Benchmarks\tatr-adbuy12-v2` destination. It
permits exactly one selected PDF without gold access. The first source must
produce a nonempty source-pixel overlay and pass independent visual review
before any of the other eleven may run. This gate does not authorize product
adoption or establish quality.

The clean `cafbe92b184c2683ca811823ef2e878f2234a020` v2 trial was run
once into that new directory. It reached the pinned RapidOCR page subprocess,
which stopped with `orientation_not_confidently_upright` before emitting word
boxes. The parent worker recorded `RuntimeError`; its wall time was 56.874 s,
and the supervisor recorded `status: failed`, `reason: worker_failed`. No
parsed table, cell, or overlay exists. Gold remained unopened and the other
eleven PDFs remained unattempted. The immutable v2 `first_pdf_receipt.json`
SHA-256 is
`e1736bd40e4aabfa81250c1a2f1e08fc3d7543251f2893f1d3d5b75e10c43136`;
the OCR failure receipt SHA-256 is
`6e9031d3133cdee7656f4581ef3d1666a45aebc0860e3e9d86223535f2eeaaa1`.
This is an OCR route safety failure, not a measured TATR table-quality result.
The v2 output must remain untouched. Any further trial requires a separately
declared profile and new directory.

## Prepared v3 native-word salvage profile

Source-only inspection identified exactly one affected eight-character word
on page one. A typed out-of-viewport glyph error now rejects its **whole**
word, retaining 515 other native words on that page; pages two and three
retain 658 and 206 native words with no omissions. The omitted eight
characters are 0.3101% of page-one nonspace characters. The v3 worker fails
if a page would omit more than one whole word, over 0.5% of nonspace
characters, or every native word. Malformed Unicode and other source geometry
still fail. A detected table intersecting the omitted glyph footprint fails
before cell inference. Image-only pages continue through the unchanged
pinned OCR route; the failed v2 orientation guard remains in force.

The omission ledger stores text, PDFium character span, raw and projected
glyph boxes, and page-level degradation. The worker renders each affected
page separately at 300 DPI with the visible omitted glyph footprint marked;
the supervisor validates that PNG, dimensions, hashes and legend against the
source-bound ledger. Synthetic tests cover whole-word omission, malformed
geometry, overflow bounds, table overlap and artifact tampering. The v3
parser version is `research-word-route-first-pdf-v4`. The committed
[v3 one-document gate](../../product_eval/fixtures/tatr_first_pdf_research_gate_v3.json),
SHA-256 `b797e3fba63bf31233bab2db2fc24d9b8826bd86e601533f832a0f3575f74731`,
binds **132 local Python files**, both immutable failure receipts, the
unchanged source selection and CPU/OCR locks, and fresh
`I:\DocAI-Benchmarks\tatr-adbuy12-v3` output. It permits one further
selected-PDF attempt without gold access. Its source-pixel overlays need
independent visual review before other documents or any quality claim.

The clean `9b8175305b93ccb75731598a0e52447324e6f156` v3 trial was run
once into the fresh v3 directory. Offline model startup succeeded, but the
worker stopped with a bounded `GeometryError` after 38.413 s. The supervisor
recorded `status: failed`, `reason: worker_failed`, no parsed table or overlay,
no gold access, and eleven unattempted sources. The immutable v3
`first_pdf_receipt.json` SHA-256 is
`db87a6c3d1333bf0d3f4cbf59b9a73141e01c3716f3cafc0ff6a7d2df78ed007`.
The v3 output must remain untouched. A source-only replay of all three pages
with an empty detector returned 515/658/206 native words and the expected
single page-one omission without a geometry error. Thus the observed v3
failure occurs **after** the source-word route, but the bounded receipt does
not identify whether it was the omitted-word/table overlap guard or a later
crop/cell/source-anchor check. No TATR table-quality result exists. Further
model trials require a newly declared diagnostic or candidate profile; this
arm must not enter product extraction on these receipts.
