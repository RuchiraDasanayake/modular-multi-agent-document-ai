# Three-source Luna 6 image and OCR diagnostic

This retained `research_evidence` experiment tests whether full-page image input
can recover information that the existing OCR stream loses. It does not add a
production vision route or establish production accuracy.

## Frozen scope

- Exactly the one-page ad-buy and two CORD development originals used in the
  [paired paint-guard diagnostic](ICORE_PDF_PAINT_GUARD_DEV6_RESULTS_20261013.md).
- Byte-identical confirmed family schemas and cached OCR pages from that arm.
  No discovery, schema tuning, gold prompts, holdout access, image crops or
  automatic retries. Existing development labels may be read only after sealing
  this arm's candidates and receipts.
- At most three serial `innobot-luna-6` calls to the supplied ICORE endpoint,
  8,192 output tokens and 180 seconds per call. The first API error stops later
  calls; all three sources remain in the result denominator. No Sonnet calls.
- Images show the entire original page, preserve aspect ratio and never upscale.
  Bounds are 3,072 pixels per edge, six million pixels, five million PNG bytes and
  eight million request bytes. PDF preparation uses the bounded raster renderer.
- Every non-null proposal requires review. A verified quote proves a match in
  cached OCR only; it does not authenticate pixels. No invented visual boxes or
  product execution receipts.

| Source | SHA-256 of original |
| --- | --- |
| Ad-buy `1bf0c61dbd517c9d5c1d2684c2788497` | `0112d54415d968cd438207ddbd423fb64b636354f29c72f0c6defe3cef14729a` |
| CORD `eb053d7caa8fe79a8c410269eca5ca23` | `28a8c9e154f9971aaae01212e395618460e610da9eca8f82d05b9b5277eb8c7c` |
| CORD `10bb0bc78b323e60ce130c26de192848` | `4322ab5ec4f0b1365e08af0c31288e65e8cbd2c8eb5241adfb329244acbbb30b` |

The machine-readable protocol captures the clean commit, tracked Python hashes,
original/image/schema/request/cached-result hashes and source-to-render geometry.
Raw requests and sanitized full HTTP and SDK response bodies stay in a protected
external directory. Credentials and response headers are never saved. API token,
latency, finish-reason and error receipts are sealed before scoring. Dollar cost
is unknown unless independently supported by the provider.

## Capability and comparison limits

The saved authenticated provider inventory advertises image input for Luna 6.
The feature-surface audit did not actually send Luna 6 an image; this first call
tests the exact inline-image Chat Completions path. Historical image results from
another model do not establish this capability.

The prompt explicitly permits readable cells from partially missing rows and
optional OCR quotes for visual proposals. Therefore the diagnostic changes both
input modality and those extraction instructions. An improvement is evidence for
this combined candidate, not a causal estimate of image input alone. These three
known development sources cannot support a model ranking or generalization claim.

Score exact proposed scalar strings and one-to-one whole rows, keeping the
positive-only CORD annotation scope and the ad-buy scope explicit. Preserve old
scores. Distinguish parser format failure, extraction error, annotation mismatch
and missing evidence; all image values still require review. Report actual
coverage, failed/skipped calls and the full denominator.

Implementation: `product_eval/icore_vision_dev3.py`. Source-free tests cover
bounded images, unchanged field definitions, review-only projections and a first
image rejection stopping the remaining calls.
