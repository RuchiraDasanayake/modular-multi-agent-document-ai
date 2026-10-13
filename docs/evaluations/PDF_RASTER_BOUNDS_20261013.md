# Bounded PDF raster sizing

IDPO `core`, action `keep` with a targeted resource/correctness fix. The preceding
[paired diagnostic](ICORE_PDF_PAINT_GUARD_DEV6_RESULTS_20261013.md) found a
2,200 x 1,700 scan expanded to 9,429 x 7,286 pixels by an oversized PDF canvas.

The renderer now chooses dimensions **before** bitmap allocation. PDFium output
is bounded by 4,096 pixels on either edge and 12,000,000 pixels total. A single
page-level image covering at least 95% of the page can additionally cap rendering
to its intrinsic resolution. Its transform vectors account for quarter-turn
image rotation. Skewed, multiple and nested images do not supply a guessed native
DPI; geometry caps still apply. A one-percent tolerance retains ordinary
300-DPI rendering despite tiny PDF coordinate round-off. Object inspection is
bounded at 10,000 objects.

Poppler receives bounded target dimensions too. If its page geometry is unknown,
its long edge is capped at 3,464 pixels, which keeps even a square below 12 MP.
The direct OCR fallback now reuses this renderer rather than a second unbounded
Poppler/Pillow PDF path. The source PDF remains unchanged.

Page provenance retains requested/effective DPI, render scale, page box and
dimensions in points, page rotation, planned/actual pixel dimensions, geometry
source and limit reasons. Unknown fallback scale is null, not a fabricated DPI.
Product `ocr_pages` includes this plan. These describe raster geometry; later OCR
normalization and line recognition do not establish verified spatial field boxes.

Source-only inspection/rendering of the same development originals confirms:

| Page | Before | After | Effective DPI |
| --- | --- | --- | --- |
| Registration first page | 2,546 x 3,325 | 2,546 x 3,325 | 300 |
| Oversized ad-buy scan | 9,429 x 7,286 | 2,201 x 1,700 | Approximately 70 |

The extra ad-buy pixel follows the PDF page boundary's rounding; it is not a new
detail claim. The receipt is `bounded-raster-source-only-receipt.json` in the
protected `icore-confirmed-schema-dev6-paint-v1` external directory. This check
made no model call and did not score labels.

The focused raster/native-layer/product/OCR suites pass **82 tests**, including
actual PDF scans with and without rotation, preserved ordinary DPI, oversized
geometry, invalid dimensions, bounded fallback, source receipts and serialized
PDFium calls. New raster helper/tests pass Ruff. Output bitmap caps do not bound
all PDF decoder internals or later OCR working memory; worker isolation and
timeouts remain necessary. Large vector pages may lose small text at the cap and
need explicit targeted regions. No extraction-quality gain is claimed yet.
