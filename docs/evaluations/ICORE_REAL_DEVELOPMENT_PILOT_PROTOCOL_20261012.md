# ICORE public-document extraction diagnostic protocol

**Frozen before any real-document ICORE call, 12 October 2026.** This is a
small development diagnostic of the current `process_auto` two-call route.
The six raw public sources and model assignments are fixed in
[`icore_real_dev_six_sources.json`](../../product_eval/fixtures/icore_real_dev_six_sources.json).
It is not an official VRDU/CORD result, a camera-ready paper result, or a
production promotion gate.

## Sources and leakage boundary

The four VRDU sources are raw-source-SHA ranks 5 and 6 from each family in
the pre-existing frozen twelve. This avoids the ranks 1-3 used in the earlier
ICORE public-PDF pilot. The two CORD receipts are the prior Graph pilot's
source-locked scored **development** receipts. Their source hashes are
disjoint from the 40 internally reserved CORD receipts. Each raw source,
completed Tesseract OCR sidecar, parent cohort, and positive gold file has a
SHA-256 receipt. Gold files were hashed but **not parsed when selecting the
sources**. No private or user file is eligible.

The runner will pass each original PDF or PNG through the current product
`process_auto` intake, Tesseract OCR, schema prompt, value prompt, exact
source-quote verifier, and review gate. The older OCR sidecar is an integrity
and selection receipt; the runner does not feed its text as a prompt. Fresh
OCR text hashes and any drift will be recorded. Raw files, OCR text, provider
reply text, gold records, and candidates stay outside Git.

## Model assignment and spending limits

`innobot-luna-6` runs on all six sources. `innobot-sonnet-5` runs on the
lower selected source SHA in each family. Assignment is frozen and does not
depend on the first model's outputs. Nine document-model cells imply at most
18 chat attempts, because the product makes at most one schema and one value
request per cell. There is no retry, parallel call, or automatic model
fallback.

| Limit | Fixed value |
| --- | ---: |
| Attempted billable chat requests | 18 maximum |
| Output tokens per request | 1,536 maximum |
| Prompt length | 12,000 characters and 14,000 UTF-8 bytes maximum |
| Aggregate returned prompt + completion tokens | 100,000 maximum |
| Timeout and concurrency | 60 seconds; one call at a time |
| SDK retries | 0 |

Every request will have a source hash, requested model ID, phase,
credential-free canonical request hash and response hash, elapsed time, safe
error class/category, finish reason,
and reported token usage. A transport timeout, ambiguous connection failure,
missing token usage, or aggregate token-cap breach stops further calls. A
model response truncated at the
1,536-token cap remains a failure in the document denominator. No request is
retried when its charge is uncertain. ICORE has no verified rate card,
settled-charge ledger, or enforceable account hard cap available to this
project; actual USD cost remains unknown and is reported as `null`.
ICORE does not expose a verifiable remote model-weights hash, so model ID and
request/response hashes do not identify the model revision.

## Scoring and decision

For VRDU, the existing `score_records` scorer compares exact published field
IDs, types, accepted typed values, evidence, and linked arrays to the derived
product gold. The two families remain separate. The `linked_row_counts`
components report exact proposed and accepted cells and complete rows. For
CORD, the existing `score_cord_positive` scorer reports exact positive-only
summary scalar, menu cell, and complete-row recall; extra CORD fields are
unjudged, so precision and F1 are undefined. Missing, failed, truncated,
unsupported, and stopped cells stay in their denominators.

A secondary schema view uses the already frozen
[`graph_schema_aliases_v1.json`](../../product_eval/fixtures/graph_schema_aliases_v1.json)
ontology. It preserves raw proposed names, maps only predeclared aliases, and
reports unmatched proposals separately. No post-hoc synonym expansion changes
the primary exact score; source-grounded accepted values are reported
separately from raw proposals.

Report source-level success, transport and provider failures, OCR status,
known token totals, model latency, review-required documents, and source
grounding. Compare quality only within each family and model's frozen source
subset. The three-source Sonnet arm and six-source Luna arm are **not** paired
overall; the Sonnet subset may be compared directly only with Luna on those
same three sources. Nothing from this nine-cell development test supports
an arbitrary-document or lower-cost claim. Any extraction implementation
later promoted into the product requires the separate 2,000-distinct-source
regression gate plus diverse held-out evaluation.
