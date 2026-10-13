# Reserved quality240: offline scoring assembly

## Scope and status

Classification: `research_evidence`; action: `keep`.

`product_eval.quality_scoring` prepares the preregistered analysis of the two
frozen arms. Implementation and tests use self-authored fixtures. The real
reserved predictions, source contents, reference contents and reference hashes
have not been read for this work. No OCR or provider call is made by this tool.
The extraction implementation and both frozen benchmark checkouts are unchanged.

This is comparative research validation on a source-only split, not a template
holdout or an accuracy certification. The frozen plan has no practical quality
or USD release threshold. Neither a complete request nor human-review status
establishes correct extraction.

## Verification before reference access

The operator must supply the independently retained prediction-seal SHA. Before
opening or hashing reference inputs, the verifier checks:

1. The seal, every listed artifact, absence of additional unsealed artifacts,
   and the durable `seal-started.json` marker that closes paid execution.
2. Exact preregistered protocol, analysis plan, zero-attempt preregistration,
   source inventory, schedule and three confirmed schema hashes.
3. All 240 original file byte hashes, including sources whose processing failed.
4. The immutable arm ledger snapshots, all 480 source slots, exported candidates,
   outcomes, nested product manifests/results, saved requests and provider replies.
5. Original identity, request schema, strict response format, text segment
   contents or visual image/selected-page receipts, ledger usage and call caps.
6. Recomputed strict parsing and source coverage, using the frozen receipt
   verifier. Interrupted or unstarted sources must have empty placeholder results.

The implementation writes `verified-before-labels.json` only after all checks
succeed. It then hashes and loads the supplied creator references. No live SQLite
ledger is queried or modified. Derived output must be a new directory outside
the sealed campaign. Inputs are reverified after scoring before publishing results.

Fourteen scorer, converter and receipt-verification modules are compared with
the frozen code receipt. An exact raw-byte match is preferred. The only allowed
checkout difference is CRLF to LF conversion anchored to the Git blob at the
registered frozen commit; the receipt records both raw hashes, the Git blob hash,
canonical SHA and comparison mode. Other whitespace and code changes fail.
Protocol, source, schema, prediction and reference files always require exact
bytes; they receive no newline normalization.

## Fixed analysis semantics

- VRDU references use the unchanged `_load_meta` and `_gold_record` conversion.
  CORD uses the existing reserved gold file. No reference repairs, exclusions,
  prediction-driven schema changes or independent visual adjudication are added.
- Every original remains in both arm denominators. Failed, uncertain, invalid or
  incomplete results receive zero value/row matches against their full references.
- Strict scalar agreement preserves historical typed equality. Ordered lists,
  scalar strings, null targets and list/schema incompatibilities are reported
  separately. Historical lists are not silently sorted or coerced to strings.
- Whole-row agreement uses the existing order-independent one-to-one matcher;
  duplicate references cannot reuse one prediction. Ordinal cell comparison is
  a separate diagnostic. CORD labels are positive-only: unmatched predictions
  remain unassessed, and precision, false-positive and F1 claims are unavailable.
- Evidence coordinate incompatibility remains explicit. Matching values do not
  imply that native text coordinates authenticate a model's image observations.
- Each metric uses 10,000 paired source bootstrap samples, seed 20261013, within
  family strata, with percentile 95% intervals. Scalar macro has three families;
  row/cell macro has the two families with rows. Undefined denominators stay
  undefined. Failed originals are never removed by complete-pair filtering.
- Provider attempts, finish reasons, strict validity, complete source coverage,
  scalar conflicts, all-null results, review status, known/unknown tokens and
  latency are reported independently. Observed source routes remain visible.
- The optional all-assessed-positive-targets diagnostic is not whole-document
  truth. There is no oracle best-of-two score, USD price, cost per truly correct
  document or automatic release-pass claim.

## Invocation after predictions are sealed

Run from a reviewed analysis checkout containing the registered Git objects.
Do not run this command while either arm remains open:

```powershell
& $ProductPython -s -m product_eval.quality_scoring `
  --run $FrozenQualityRun `
  --prediction-seal-sha256 $IndependentlyRecordedPredictionSealSha `
  --output $NewExternalDerivedDirectory `
  --vrdu-root $OriginalVrduCreatorDirectory `
  --cord-gold $ExistingCordReservedGoldJsonl
```

The output includes verification, reference input/conversion and scoring receipts;
the creator-derived gold; per-source, family and paired bootstrap results. These
are private research artifacts and may contain reference values. Failed integrity
checks must be investigated rather than bypassed by changing expected hashes.

## Validation

Synthetic tests execute the real two-arm product workflow with fake OCR/providers
and seal its results. They exercise text and visual requests, all-reference
denominators after an uncertain request, unknown usage, tampered source and
artifact bytes, schema/ledger/result corruption even after recomputing the outer
seal, historical ordered lists, duplicate rows, strict creator conversion and
zero matches for failed results with leftover values. Reference access is trapped
in every integrity-failure test. A separate test accepts only Git-anchored newline
conversion and rejects code changes, whitespace changes and added blank lines.
