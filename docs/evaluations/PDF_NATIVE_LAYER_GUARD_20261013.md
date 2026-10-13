# PDF native text guard and paired development check

## Defect and change

Owning service: IDPO. Classification: `core`, action: `keep` with a targeted
correctness fix. The [six-source smoke](ICORE_CONFIRMED_SCHEMA_DEV6_RESULTS_20261013.md)
reproduced two PDFs whose visible completed forms were replaced by unrelated
invisible administrative text at intake. A long, legible string is insufficient
to authorize the native-text shortcut.

`idpo/core/pdf_native.py` uses the existing PDFium dependency to inspect text
render mode, fill/stroke alpha, object bounds and clipped raster image coverage.
Invisible (mode 3), clip-only (mode 7), transparent and off-page text does not
count as painting text. Raster coverage is an area union, not a sum of overlaps.
If a raster covers at least half the page and fewer than 40 painting text
characters exist, intake requires OCR. Other nonpainting text also triggers OCR
so it cannot enter source quotes alongside otherwise valid digital text.

An uninspectable layer fails closed to OCR. Nested forms have inherited paint
state and transforms that this small guard does not interpret; they are reported
as unassessed and require OCR. Inspection is bounded at 10,000 objects, 1,000,000
text characters, 256 image objects and form recursion depth 8. Inspection and
rendering share the same process-wide PDFium lock. Handles close explicitly.

Intake removes rejected native text from both text fields, retains its SHA-256
and the inspection reason/counts in page provenance, and preserves the original
PDF bytes. OCR never falls back to rejected text. Product `ocr_pages` retains the
guard metadata with its existing renderer provenance; evidence offsets refer to
the selected fresh OCR pages.

Ordinary searchable scanned PDFs often contain useful invisible OCR. This guard
does not classify invisible text as malicious or necessarily wrong; fresh OCR
costs CPU and can be less accurate than an existing layer. It also does not prove
pixel correspondence or detect every clip, occluding object, blend or optional
content state. Native digital pages without rejected content retain their path.
Missing PDFium now requires OCR instead of silently trusting an unchecked layer.

The implementation uses the documented
[PDFium-backed object API](https://pypdfium2.readthedocs.io/en/stable/python_api.html)
and [PDFium text inspection API](https://pdfium.googlesource.com/pdfium/+/refs/heads/main/public/fpdf_text.h).
PDFium requires serialized calls even for different documents; this guard follows
that restriction. It is a bounded routing check, not a complete PDF renderer.

## Validation before inference

Synthetic real PDF fixtures cover full-page raster plus hidden metadata (modes 3
and 7 and alpha 0), off-page text, an ordinary digital PDF that never invokes OCR,
fresh OCR provenance, failure without metadata fallback, inspection limits,
missing PDFium and overlapping raster coverage. The product/OCR regression
suites also check rendering serialization and source receipts. The focused run
passes 72 tests; the new module/tests pass Ruff. Existing unrelated lint debt in
the large preprocessing module remains.

Source-only inspection of the same four development PDFs rejects both
registration first pages and the one-page ad-buy native OCR layer. It retains the
ordinary digital six-page ad-buy's first page, including its small logo.

## Frozen paired check

After committing this guard, run `product_eval.icore_confirmed_dev prepare` into
a new private external directory, `icore-confirmed-schema-dev6-paint-v1`. Verify
its six source hashes and three schema payload hashes equal the prior arm;
record the new clean commit and protocol SHA before inference. Keep the same
six sources, field meanings, model, OCR configuration, prompt/response budgets,
zero retries, source receipts and post-seal scoring as the original protocol.
Use at most six Luna 6 value calls; no discovery, vision, response repair, source
substitution, cap increase or holdout access. Preserve all six denominators.

Compare input page text/route, exact string values, annotated one-to-one rows,
review outcomes, latency and tokens. Repeated model sampling prevents attributing
every response difference causally to the parser; report this small paired
development check as a diagnostic. The unchanged 24,000-character cap, scalar-list
limitation and known date-definition mismatch remain. Successful page recovery
does not by itself qualify the product for the final quality experiment.
