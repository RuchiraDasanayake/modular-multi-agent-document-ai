# Paired six-source check after the PDF paint guard

This retained `research_evidence` diagnostic follows the
[guard protocol](PDF_NATIVE_LAYER_GUARD_20261013.md) and compares with the
[initial supplied-schema smoke](ICORE_CONFIRMED_SCHEMA_DEV6_RESULTS_20261013.md).
It uses the same six development originals and byte-identical family schema
payloads. The clean code commit is `33789c4b20cd8e6ff9481cfd09e90637b1e5ffd3`;
protocol SHA-256 is
`2900c5d167825d1924e2b90ee225f8e16007cfdc370d57d01b8be7d2404d83fa`.
Artifacts are in the protected external `icore-confirmed-schema-dev6-paint-v1`
directory. No holdout sources or labels were accessed. All six original hashes,
six product result receipts and five request/schema/page pairs verified before
the new candidates were scored against the already-known development labels.

## Results, without promotion

| Measure | Initial arm | Guard arm |
| --- | ---: | ---: |
| Original documents | 6 | 6 |
| Luna 6 value calls | 5 | 5 |
| Reported prompt/completion tokens | 5,535 / 5,777 | 6,757 / 5,119 |
| Reported total tokens | 11,312 | 11,876 |
| End-to-end elapsed seconds | 94.6 | 201.4 |
| Exact proposed scalar strings | 8/32 | 12/32 |
| Exact accepted scalar strings | 7/32 | 11/32 |
| Exact scalar-list fields | 0/2 | 0/2 |
| VRDU registration proposed strings | 4/10 | 5/10 |
| VRDU ad-buy proposed strings | 2/15 | 5/15 |
| CORD proposed strings | 2/7 | 2/7 |
| Ad-buy annotated whole rows | 1/36 | 0/36 |
| CORD annotated whole rows | 1/7 | 1/7 |
| Final review-required documents | 6 | 6 |
| Automatically released documents | 0 | 0 |

Neither arm had a provider error, SDK retry, schema-discovery call or response
repair. Dollar cost remains unknown. The long ad-buy still hits the unchanged
24,000-character cap, now with 28,883 characters; it makes no model call and keeps
its 30 rows in the denominator. Other differences include ordinary model
sampling, so this small paired development run is not a causal model ranking.

Order-independent row scoring, positive-only CORD scope and incompatible
gold/candidate OCR-coordinate handling remain unchanged. All 15 guard-arm
accepted VRDU scalar quotes exist in the candidate text; all gold-coordinate
comparisons are incompatible. This establishes quote authenticity only.

## What the repeat established

The registration scans' visible first-page content now reaches the model. Their
total extracted text grew from approximately 3,886 to 7,062 and 1,700 to 4,203
characters. Previously missing foreign-principal text is proposed, but one model
chooses only the current principal where the annotation includes previous ones;
another copies OCR spelling corruption. One short-form registrant name becomes
the individual instead of the primary organization. These are remaining scope,
field-meaning and OCR problems. A correct organization proposal in the second
registration stays review-required because its quote repeats.

Fresh ad-buy OCR improves several headers and both visible flight dates, but
destroys enough table relationships that the model returns no rows. The selected
OCR candidate is PSM 4 with a median filter, confidence 65.1, after nine bounded
candidates. The model receives damaged table text, so no row quality improvement
can be claimed. The low-quality CORD image remains unreadable; the other receipt
still has spelling and multiline grouping errors. Receipt inputs are unchanged,
and response differences there demonstrate sampling variability.

The ad-buy PDF embeds a **2,200 x 1,700** image but declares a
**2,262.86 x 1,748.57 point** page. Fixed 300-DPI rendering expands it to
**9,429 x 7,286** pixels, about 18.4 times the original pixel count. Both
registration scans instead already have approximately 2,550 x 3,300 pixels on
letter-sized pages. The oversized canvas therefore incurs unnecessary work and
resampling; page points alone are not a reliable useful-resolution target.

## Next decision

Keep the reproduced native-text correctness fix, subject to its documented
conservative OCR tradeoff. It does not deliver sufficient extraction quality.
Bound rendering by image dimensions/effective resolution, preserve spatial table
relationships, and provide bounded coverage for long documents. A useful next
diagnostic is a maximum three-call Luna 6 vision-plus-OCR comparison on the
entire one-page ad-buy and both entire one-page CORD originals, using the same
schemas. Freeze the image hashes, sizing and provenance before those calls.
Values recovered only from pixels must remain review-required; an absent OCR
quote must not be invented or accepted as verified support. No such vision call
is included in this result, and the final 2,000-source quality run remains gated.
