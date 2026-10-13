# Distinct-original union after both studies are verified

Classification: `research_evidence`; action: `keep`. This helper accounts for
completed evidence. It does not execute extraction or modify the two studies.

## Preconditions

Run only after the operational2000 process has exited and its final seal has
passed `product_eval.final_operational_verification`, and the paired quality240
campaign has permanently sealed and passed `product_eval.quality_scoring`.
Independently record the four exact input receipt/report SHA-256 values first.
The input receipts are attestations of those completed verification procedures;
the union helper does not repeat their source/prediction/reference checks.

`product_eval.verified_source_union` reads only:

- The operational `receipt.json` and `verification.json`.
- The quality `scoring-receipt.json`, `verified-before-labels.json` and
  `quality-results.json`.
- Each registered `protocol.json` and the quality `prediction-seal.json` metadata.

It never opens originals, predictions, provider requests/replies, reference
labels or SQLite. All current tests use self-authored synthetic reports; no
active campaign evidence was read to prepare the helper.

## Prospective command

Replace the report directory names and four hash placeholders with the actual
completed outputs and externally recorded pins. Do not use this command before
the preconditions above are satisfied.

```powershell
& 'I:/DocAI-Runtime/product-venv/Scripts/python.exe' -s -m product_eval.verified_source_union `
  --operational-dir 'I:/DocAI-Benchmarks/final-model2000-verified-report-20261013' `
  --operational-run 'I:/DocAI-Benchmarks/final-model2000-selective-v2-20261013' `
  --operational-receipt-sha256 '<PINNED_OPERATIONAL_RECEIPT_SHA256>' `
  --operational-report-sha256 '<PINNED_VERIFICATION_JSON_SHA256>' `
  --quality-dir 'I:/DocAI-Benchmarks/quality240-verified-scoring-20261013' `
  --quality-run 'I:/DocAI-Benchmarks/quality240-selective-v2-20261013' `
  --quality-receipt-sha256 '<PINNED_SCORING_RECEIPT_SHA256>' `
  --quality-result-sha256 '<PINNED_QUALITY_RESULTS_SHA256>' `
  --output 'I:/DocAI-Benchmarks/verified-distinct-original-union-20261013'
```

The output directory must be new and external to both campaigns and both input
report directories. Outputs are `union.json`, `report.md` and a hash receipt.

## Reported criteria

Each stage is a set of original-file SHA-256 values:

| Stage | Meaning |
|---|---|
| `selected` | Every frozen original, including pre-model rejection, uncertain and unstarted slots. |
| `request_begun` | At least one durable begun-request marker. This does not prove delivery or billing. |
| `valid_full_coverage` | A sealed result satisfying the existing verifier's strict parsed reply and complete source-coverage criteria; every begun request has a valid strict reply. |
| `non_null_full_coverage` | Full valid coverage with at least one non-null field. This does not establish semantic correctness or completeness. |

The report retains separate operational (897 registration, 305 ad-buy, 798
receipt) and quality-candidate (100 registration, 100 ad-buy, 40 receipt)
denominators. Only the `candidate` arm of quality240 contributes. The text
baseline never supplies a source, attempt or successful result to this union.

Per-stage intersections are explicit. Duplicate bytes within one study are
rejected. Duplicate bytes across studies count once and set
`source_disjoint=false`; their study denominators remain unchanged. Two partial
results are never combined to create a successful full-coverage result. The
four `at_least_2000` flags distinguish selection, begun requests, valid complete
inference and non-null complete inference; none is an accuracy claim or release
certification.

Known SDK counts, unknown SDK/usage counts, uncertain attempt counts, source
states, pre-model rejections and valid all-null outputs remain explicit by
study. Quality's missing input-token and output-token counts remain separate;
their sum must not be treated as the number of attempts missing any usage.

The model, OCR, strict output, long-document and selective-visual profile, output
limit, timeout and per-source call limit must match. Registered protocol bytes
remain hash-bound. Full profile hashes are separately recorded using sorted
compact JSON; operational four-worker/2,500-call limits and paired one-worker/
960-call arm limits legitimately differ. Counterbalancing and checkpoints stay
bound to their respective protocol hashes, without claiming identical study
execution.

This accounting does not measure accuracy, human-reviewed release or USD cost.
It neither changes a failed operational gate to a pass nor pools quality scores
with operational outcomes. Use the separate quality study for creator-label
agreement, uncertainty intervals and its documented annotation limitations.
