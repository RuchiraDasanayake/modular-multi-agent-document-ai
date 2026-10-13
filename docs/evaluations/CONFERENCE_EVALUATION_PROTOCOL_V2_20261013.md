# ICTAR Paper 2: final evaluation protocol v2

Status: planning only, 13 October 2026. No new inference or reserved-label access.
This updates the external `conference-evaluation-plan/PROTOCOL.txt` recommendations;
the previous protocol and every historical score remain preserved. It incorporates
the [annotation trace](VRDU_ADBUY1_ANNOTATION_TRACE_20261013.md) and the
[three-source vision result](ICORE_VISION_DEV3_V2_RESULTS_20261013.md).

## Recommendation and claim boundaries

Finish the confirmed-schema product path and run the staged 2,000 originals with
real Luna 6 value calls through that path. Keep schema discovery as a separately
measured onboarding workflow. Use the final selected OCR, response contract and
bounded document coverage policy; freeze these before the run. Do not launch
another no-model volume run as a substitute.

Four evidence lanes must remain distinct:

| Lane | Primary question | Valid output |
| --- | --- | --- |
| Derived creator-label quality | Does a proposal match the frozen mapped target labels? | Per-family strict scalar recall, one-to-one whole-row recall, complete-label precision where applicable |
| Independently adjudicated visual correctness | Is the value, field meaning and row association correct in the original? | Separate blinded adjudication; currently unavailable |
| Operational 2,000 | Did the final product actually process distinct originals with its configured model path and persist reviewable results? | Source/coverage/model-call/result receipts and terminal outcomes |
| Schema discovery and confirmation | Does onboarding capture user intent and reusable field meanings? | Semantic field/type/group agreement and actual confirmation effort; currently no final study |

The original paper's results and new implementation results need separate tables.
Evaluator-owned family schemas are research task specifications, not measured
human confirmations. A schema-conditioned extraction experiment cannot by itself
establish blind discovery, autonomous learning, arbitrary-document accuracy,
automatic release, guaranteed correctness or lower monetary cost.

## Official evaluation definitions and the current adapter

**VRDU.** The creator supplies type-specific matchers and single/mixed/unseen
template split tasks. Our source-selected cohort is not an official unseen-template
split; source-byte disjointness alone does not establish template disjointness.
[Creator task specification](https://raw.githubusercontent.com/google-research/google-research/master/vrdu/README.md)

The official evaluator reports micro and macro entity F1 and per-entity results.
Its macro average is over entity categories, not a document-macro average. Scalar
annotations may contain alternative acceptable occurrences: one predicted entity
can match any candidate. Our strict derived adapter instead represents divergent
scalar surface strings as ordered lists. Those scores remain a named project
metric, not official VRDU results. Published nested groups must be preserved;
ad-buy1's incorrect date associations are already in those groups.
[Creator evaluator](https://raw.githubusercontent.com/google-research/google-research/master/vrdu/benchmark_utils.py)

Official date matching handles several formats and day/month ambiguity; string,
price, numeric-ID and address matchers have different normalization rules. This
does not authorize arbitrary normalization of the product's literal-string
outputs. Pin and validate the official evaluator before reporting its metric as
a separate lane; do not silently replace the historical strict scorer.
[Creator matchers](https://raw.githubusercontent.com/google-research/google-research/master/vrdu/match_utils.py)

**CORD.** The creator release contains 800/100/100 train/dev/test images with
hierarchical labels; v2 corrected labels and added subgroup information. Menu
total price and unit price are distinct. Our mapping retains only five summary
fields and three menu columns and excludes ambiguous/nested cases. Absent mapped
labels are unassessed; this subset cannot claim complete-document precision.
[Creator dataset definitions](https://github.com/clovaai/cord)

The creator's Donut implementation computes normalized tree-edit accuracy and
micro field/value F1 after flattening hierarchical JSON. Flattened field/value
matches alone do not validate row associations. Our one-to-one annotated-row
recall is a useful separate product metric, not that full-parse benchmark.
Reproducing full CORD scores requires full compatible parses and the specified
test split. CORD train performance is development/operational evidence.
[JSON evaluator](https://raw.githubusercontent.com/clovaai/donut/master/donut/util.py),
[evaluation entrypoint](https://raw.githubusercontent.com/clovaai/donut/master/test.py)

Seven primary-source files were saved and hashed under external
`primary-sources-20261013/receipt.json`; none were executed or vendored into
production. The original CORD paper link required an OpenReview browser check;
the definitions above rely on accessible creator documentation and code.

## Metrics and annotation-quality flags

For each family and arm, retain all selected sources, invalid replies, failures,
unsupported documents and missing values. Report both counts and denominators:

1. Valid response structure and complete input-page coverage; distinguish HTTP
   success, parse success, non-null proposals and source-supported proposals.
2. Strict requested scalar value recall; strict precision/F1 only where the
   target annotation is complete. Keep null, missing, wrong and unassessed apart.
3. Order-independent one-to-one whole-row recall preserving duplicates and links.
   CORD requires all annotated cells of a row, with unannotated cells unassessed.
   Report cell recall separately; never join independently matching columns.
4. Source quote authenticity versus semantic/visual support. Hash-incompatible
   OCR coordinates are unassessed, not failed support. An authentic quote can
   still quote an OCR error. Image-only proposals require review.
5. Review-required rate, accepted proposal accuracy where evaluable, final
   human-corrected accuracy and active review minutes as separate outcomes.
6. Calls, retries, reported input/output tokens, API errors, parser/model/queue
   latency, p50/p95, CPU/GPU time and peak memory. USD remains unknown without
   provider billing evidence; local inference is not zero total cost.

Freeze an annotation-quality flag vocabulary before final scoring:
`date_surface_incomplete`, `scalar_alternative_occurrences`,
`row_group_geometry_inconsistent`, `source_text_span_mismatch`,
`partial_target_annotation`, and `field_meaning_unresolved`. Flags describe the
reference/source contract, never whether a prediction happened to disagree.
Automated checks only nominate audits; a partial date or multiline box is not
automatically wrong. Preserve raw labels and all-data primary scores. Publish
flag counts, coverage and separately named sensitivity views without silently
dropping hard cases. No prediction-derived relabeling or normalization is allowed.

A visual-correctness lane needs source-selected documents, fixed field meanings,
two independent source-only annotations where feasible, disagreement resolution,
explicit absence/ambiguity and source page/box evidence. Reviewers must not see
which model produced a value while establishing reference truth. Existing
model-inspected development examples cannot become a new blind holdout.

Report paired document-level uncertainty for comparable arms; cluster by template
when reliable IDs exist. Do not treat cells of one document as independent trials.
No statistical interval can resolve incorrect labels or establish a guarantee.

## Final 2,000-document model run

Reuse only the inputs from `I:/DocAI-Benchmarks/mixed-vrdu-cord-train-2000-v1`.
The cohort SHA-256 is
`3de27807196afa0aa37365f733d2d30903ffa1824420f8684922d355ea7c831d`:
897 registration PDFs, 305 ad-buy PDFs and 798 distinct CORD train PNGs,
eight existing shards of 250. All 2,000 raw hashes are distinct. Old outputs
are not final outputs and must not be relabeled as postimplementation evidence.

Use three fixed family schemas from evaluator-owned task specifications, selected
by the frozen cohort's family metadata. Do not generate fields from each target's
gold presence, filename content or expected values. Current development schema
snapshots are in `icore-confirmed-schema-dev6-paint-v1`; their hashes belong in
the final manifest. If task meanings change, version and freeze new snapshots
before inference. All rows in a family receive the same definitions.

### Coverage is a release prerequisite

An offline inventory of old product receipts found 3,418 pages: 798 receipt,
1,834 registration and 786 ad-buy pages. Ad-buy reaches 12 pages; 17 ad-buy
documents already exceed the current 24,000-character model-input limit, with
a maximum 73,101 characters. These are old parse measurements, not a current
parse preflight; corrected OCR can increase text. Receipt OCR was often sparse.

The final path therefore needs explicit complete-page/paragraph segmentation
where required, at most four value calls per source, and lossless coverage and
merge receipts. A source exceeding that bounded policy remains unsupported;
never send a prefix and call it a completed document. Until this exists, the
unchanged product cannot credibly promise 2,000 model-backed completions on this
cohort. The planner, merge policy and long-document tests must be frozen together.

### Concrete execution envelope

- Model: `innobot-luna-6`, supplied ICORE endpoint, zero SDK retries; no Sonnet.
  Use the final verified response-contract settings, not an experimental prompt
  wrapper that bypasses product parsing, evidence or review contracts.
- Use 80 checkpoint batches of 25 source references within the eight original
  shards. Select each source's fixed schema explicitly. A single mixed directory
  with one schema argument is incorrect because the families differ.
- Start with one source worker and one in-flight cloud request. The first 25
  belong to this same frozen run and verify transport/structure/resources only.
  Increase to two cloud requests only under a predeclared resource/rate policy.
  One GPU OCR/model slot; avoid simultaneous local model loads on 8-GB VRAM.
- Default one value call per source; at most four planned segments when needed.
  Suggested campaign admission bound: 2,500 calls, 8,192 output tokens/call,
  180 seconds/call. If the frozen complete-coverage plan requires more calls,
  amend the protocol before starting; never silently drop the remainder.
- Retain the product's source-size/page limits and exact source-page offsets.
  Vision is eligible only once integrated and tested in the product; ICORE image
  inputs require <=2,048 pixels each dimension and <=4 MiB whole JSON. The
  research-only three-image runner is not the final product route.
- Keep all inputs, models, outputs and private sanitized responses on I:. Bind
  each execution to source, parser, schema, prompt, code and model hashes. No keys
  or request headers enter receipts or Git.

### Resumption without duplicate billing claims

Use a durable ledger keyed by original source hash, schema hash, route, code and
segment identity. Save and fsync `attempt_started` before a request; save the
sanitized response and its digest before parsing; then atomically commit the
candidate/result receipt. A new invocation must verify the frozen manifest and
reuse only complete receipts from this same final run. It must not reuse the old
no-model run or different parser outputs as if they were fresh.

If a response is saved but parsing/commit was interrupted, replay parsing locally.
If a call started but its outcome is unknown, mark `outcome_unknown`; do not
automatically call again. Provider idempotency has not been established. Manual
reconciliation or an explicitly recorded later attempt is required, with every
attempt kept in cost totals. Auth/quota errors pause remaining dispatch; they do
not create synthetic successes. Backoff and resume must retain the same code and
schema freeze. A changed implementation is a new arm.

The current `product_eval/run_gate.py` is explicitly no-model and non-resumable.
The six-source runner is bounded to six calls and refuses a repeated run marker.
Neither can be renamed into the final runner. Reuse their receipt verification
and product entrypoint in a bounded resumable model runner, then test crash cases.

### Budget and timing estimates, not promises

The five-call confirmed-schema smoke, weighted by the 897/305/798 family mix,
projects about **4.68 million reported tokens** and **5.84 hours of serial API
latency**, before current OCR, chunking, validation, queueing, outages or review.
This is extrapolation from two registration, one ad-buy and two receipt calls;
it is not a measured throughput or cost forecast. The three-source image arm
used 11,244 tokens and 45.44 seconds and should not be blended into that estimate.

At the proposed 2,500-call cap, maximum requested completion tokens alone are
20.48 million. Input usage is additional. Calls/output limits are not monetary
caps; record actual provider usage and charges when available. A 180-second
timeout on every call would take 125 hours serially, exceeding the remaining
conference window. Re-estimate from completed early batches without changing
their extraction policy and stop publishing deadlines as runtime guarantees.

### What counts as completion

The gate must report separately: 2,000 selected original hashes; admitted files;
files with real model attempts; valid parsed proposals; full-source coverage;
non-null extraction results; failed/unsupported/review-required outputs; and
sealed product result receipts. A terminal failure or a no-call limit response
is a valid accounted outcome, but is not a successful model extraction. Do not
claim 2,000 completed model extractions unless that count actually reaches 2,000.
Do not count segmented pages, retries or duplicate uploads as new originals.

## Coverage beyond forms and receipts

The 2,000 cohort covers PDF and PNG from three families. The product also
accepts DOCX, XLSX, PPTX, HTML, EML, TXT, JSON and additional image encodings;
extension support is not demonstrated accuracy. Require source-faithfulness
fixtures and user-task tests for each advertised format, including multi-sheet
tables, formulas/merged cells, slide order, multipart mail, encoded text, Unicode,
JSON arrays and multipage TIFF where supported. Cover native/scanned/mixed PDFs,
rotations, handwriting, languages, sparse/ambiguous fields, repeated rows and
multi-page continuations separately. Mark untested categories explicitly.

Format regressions may use synthetic fixtures, but those do not enlarge the
real-original quality cohort. The staged source-only schema12 set supplies some
PDF/HTML/XLSX coverage; it has no independently adjudicated quality labels.
Additional original files need rights, task schemas and source-only annotations.

Queue durability, cancellation, cross-owner isolation, duplicate submission,
tampering, restore and review/export revision tests are separate engineering
gates. The 2,000 run on one Windows machine does not demonstrate distributed
scalability or unlimited file counts.

## Paper and deadline decision

By the stated 17 October submission date, valid claims are limited to completed,
sealed evidence: corrected PDF input selection and bounded raster allocations;
native product functionality actually tested; disclosed development extraction
results and failures; and a final model-backed volume result if it finishes.
Do not call the current small pilots state of the art or claim general accuracy.

For reviewer concerns, prioritize an auditable dataset table, per-family metrics,
full failure denominators, the paired input-guard experiment, the fixed-schema
versus discovery distinction, and explicit annotation limitations. A small honest
ablation is preferable to claiming unexecuted memory/policy benefits. A local
versus cloud comparison must use the same frozen task/source scope; no-model
output, different modality, prompt changes and unrelated corpora are confounders.

The remaining source-selected quality240 protocol stays sealed until the system
and scorer freeze. Its official labels alone do not supply the new independent
visual lane. If that lane, a sound cost comparison, or a learning ablation is not
completed in time, report it as future work and narrow the paper's claims.
