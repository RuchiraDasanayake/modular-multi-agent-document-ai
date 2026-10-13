# Luna 6 image and OCR diagnostic v2: successful transport, mixed extraction

The [revised protocol](ICORE_VISION_DEV3_V2_PROTOCOL_20261013.md) completed all
three authorized calls. This establishes that ICORE Luna 6 accepts the tested
inline PNG Chat Completions request within its disclosed limits. It does not
establish production extraction quality.

Code commit: `27b46f4`. Protocol SHA-256:
`a4408ec5256f31ddd2fefd71eb5c9f7537097981e3aa2c7fd2f16eb7780770df`.
Protected external artifacts: `icore-luna6-vision-dev3-v2`. All 26 sealed files,
original hashes, schemas, requests and image hashes verified before opening the
already-used development labels. Actual SDK request sizes matched preflight:
1,449,966, 1,864,806 and 1,101,462 bytes. No holdout labels were accessed.

## Strict results

| Measure | Cached OCR baseline, same three sources | Image plus cached OCR |
| --- | ---: | ---: |
| Exact proposed ad-buy scalar strings | 5/9 | 4/9 |
| Exact proposed CORD scalar strings | 2/7 | 2/7 |
| Exact annotated ad-buy whole rows | 0/6 | 0/6 |
| Exact annotated CORD whole rows | 1/7 | 0/7 |
| Structurally valid replies | 3/3 | 2/3 |

The image arm used three calls, 8,190 prompt tokens and 3,054 completion tokens
(11,244 total), taking 45.44 seconds. All finished with `stop`; there were no
provider errors or SDK retries. Dollar cost is unknown. The separate v1 rejected
attempt remains recorded with unknown token usage. Every image-arm proposal is
review-required; automatically released documents and accepted values are zero.

The strict scores above are preserved. Their interpretation requires the
following separate diagnoses.

## Three distinct failure types

**Malformed output, CORD 0017.** The reply omits the `field_id` key and object
boundaries before two linked columns. It is invalid JSON, despite an ordinary
`stop` finish reason. The actual product parser rejects the whole reply; no
repair was applied and all proposals remain null. Inspection of the raw text
shows the correct two totals and all six quantities/prices, plus five complete
item names. The last name omits the printed `Take Away` continuation. These are
diagnostic observations, not scored or released extraction results.

**Literal transcription errors, CORD 0083.** The model reads the item and its
quantity, but changes printed commas to periods in the subtotal, tax, total and
item price. The cash and change values are exact. The frozen schema asks for
printed strings, so numerical equivalence does not excuse these errors. The
image does contain both separator styles; silently normalizing all values would
erase source distinctions.

**Annotation and interpretation differences, ad-buy.** Visual inspection shows
that the model proposed the six visible table rows, including complete dates,
station, descriptions and amounts. The existing gold contains truncated date
strings and date row associations that differ from the visible table. The trace
from original VRDU annotation groups to imported gold must determine whether
these differences originate in the dataset or the importer. This report does
not rewrite labels or assert that the importer caused them.

The ad-buy scalar mismatches also have different causes: two gold flight dates
are truncated; the printed product has a hyphen absent from gold; the model
replaces an address line break with punctuation; and it selects the station
designation for `property` where the annotation selects the publisher/location
name. That last choice is a remaining field-meaning error. A zero whole-row score
alone is therefore inadequate evidence that visual table extraction failed.

## Decision

Keep vision as a research candidate with review-only output. First require a
validated JSON response contract and trace the original VRDU grouping for this
one development source. Preserve the historical strict scores while separating
annotation limitations from model errors. A new product route needs image
provenance, complete-page coverage and explicit visual-review behavior.

These three known development documents, with both image input and partial-row
prompt changes, cannot support a causal modality claim or a quality ranking.
The final 2,000-document run should follow corrected implementation and a frozen,
auditable evaluation protocol.
