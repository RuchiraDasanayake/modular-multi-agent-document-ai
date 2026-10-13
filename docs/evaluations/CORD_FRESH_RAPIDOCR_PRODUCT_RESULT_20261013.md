# Fresh product OCR: working integration, color fix, unresolved rows

Classification: research_evidence; action: keep.

The [frozen two-original protocol](CORD_FRESH_RAPIDOCR_PRODUCT_PROTOCOL_20261013.md)
completed two Luna 6 calls through actual intake, fresh local OCR and supplied-schema
product extraction. Both documents remained `needs_review`. Source, raster, model,
line-offset and product-manifest checks passed; 33 output files were hash-sealed and
verified before development-label scoring.

## Measured extraction: initial adapter revision

| Same two development originals | Prior product Tesseract | Prior cached RapidOCR replay | Fresh product `lines-v1` |
| --- | ---: | ---: | ---: |
| Exact proposed scalar strings | 2/7 | 4/7 | 4/7 |
| Exact machine-accepted scalar strings | 2/7 | 4/7 | 4/7 |
| Complete proposed annotated menu rows | 1/7 | 0/7 | 0/7 |
| Proposed linked cells | 11 | 3 | 15 |
| Documents requiring review | 2/2 | 2/2 | 2/2 |

These are raw-string, positive-only-label results from the unchanged scoped scorer.
They do not establish precision, false-positive rates or F1. More proposed cells
did not recover a single complete annotated row. The first receipt still differed
from three scalar labels by comma/period amount separators; two incorrect scalar
strings passed machine text validation. Its subtotal required review because the
supporting text was ambiguous. The second receipt still lacked quantities and had
incorrect row joins across wrapped item names.

This initial fresh run used 1,322 reported prompt tokens and 1,684 completion tokens,
two SDK attempts and no retries. Total runtime was 22.38 seconds. The two isolated
OCR children took 2.80 and 2.83 seconds with sampled peaks of about 213 and 243 MiB.
No provider dollar prices were verified; dollar cost remains unknown.

## Post-run defect and corrected adapter

Review of the changed page strings exposed an input-color boundary defect.
RapidOCR 3.10.0 treats NumPy arrays as BGR. The initial adapter reused an older
research worker's RGB-array pattern, swapping the red and blue channels. Grayscale
synthetic OCR tests did not detect it.

Commit `69b410b` corrects the boundary by passing a typed Pillow RGB image so the
library performs its own RGB-to-BGR conversion. The processing revision is now
`rgb-pil-lines-v2`, recorded in provenance. A red/blue pixel regression and the real
synthetic OCR, CLI image and scanned-PDF tests pass: 47 adapter/integration tests.
The earlier sealed measurement remains associated with its original `lines-v1`
revision and is not a measurement of the corrected worker.

Two additional **local-only** product runs on the same original receipts verified
the corrected version, with zero model calls. Both current page strings exactly
match the earlier cached RapidOCR replay:

- First text SHA: `0387627a8d7d794a41356717adb0c301c3c71eac68b44321832532b5f865b433`.
- Second text SHA: `32198ecc8e82eb60dba11a89eef550f4c1074a2f01384454ecbe671182adbe93`.

Corrected OCR took 2.43 and 2.89 seconds, with sampled peaks of about 240 and 213 MiB.
The source hashes, two distinct execution receipts, model revision and every exact
line offset were verified. The previous replay offers downstream evidence for the
same text and schema, but its cached timing is not fresh OCR timing and no new
model result is claimed for these corrected local-only runs.

## Receipts and decision

- Frozen inference code: `30a4244`.
- Frozen protocol SHA: `3828cdbe6894b8e96030efa95f4fbfc987259fd21409d9c2e946402fc3cf3a35`.
- Initial summary SHA: `dbeaf691c69e2f45b796c81eacc983565d66a9dd96ebcb6b7b87dd037d894066`.
- Private experiment directories: `cord-rapidocr-product-dev2-v1` and
  `cord-rapidocr-product-rgbfix-local-v2`; originals and earlier frozen studies
  remain untouched. Raw requests, replies, images and gold stay outside Git.
- No reserved documents were opened. These repeated development receipts do not
  contribute new unique documents to the final 2,000-document requirement.

Keep the corrected adapter available explicitly and retain the current default
pending a broader frozen evaluation. The next quality candidate should preserve
layout or image context for row reconstruction and test explicit partial-row
handling. More OCR engineering alone has not solved linked-field extraction, and
matching an OCR quotation remains insufficient evidence of image-level correctness.
