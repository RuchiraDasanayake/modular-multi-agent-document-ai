# Offline verification of the completed operational campaign

Classification: **research_evidence / keep**. This is an independent post-run
verification tool, not an extraction path or a change to the frozen campaign.

## Execution boundary

Run `product_eval.final_operational_verification` only after the campaign process
has exited, every selected original is terminal, and a final `seals/<timestamp>.json`
exists. Record that exact seal's SHA-256 independently; do not select the newest
file implicitly. The verifier checks the externally supplied protocol and seal
hashes, original identities and terminal states before opening any source bytes,
requests, replies or predictions. An absent seal or a started/unstarted source
refuses verification. The frozen runner permits a terminal `uncertain` source;
this remains in the full denominator and never becomes a valid extraction.

No current campaign predictions, source bytes or reference labels were opened to
prepare this tool. Preparation used code, protocol metadata and self-authored
fixtures only. The command below is prospective until a completed seal is available.

```powershell
& 'I:/DocAI-Runtime/product-venv/Scripts/python.exe' -s -m product_eval.final_operational_verification `
  --run 'I:/DocAI-Benchmarks/final-model2000-selective-v2-20261013' `
  --protocol-sha256 b9571b78a9be196573cd14c7ac8b4050cb741f091646eeb1c76257bfdae69eeb `
  --seal 'seals/REPLACE_WITH_COMPLETED_TIMESTAMP.json' `
  --seal-sha256 REPLACE_WITH_INDEPENDENTLY_RECORDED_SEAL_SHA256 `
  --output 'I:/DocAI-Benchmarks/final-model2000-verified-report-20261013'
```

Use the clean checkout containing this verifier. Its frozen receipt-verification
and strict-parser modules must match the campaign hashes. The sole permitted code
normalization is CRLF to LF, anchored to the registered Git blob and recording
both raw hashes. Source, schema, request, reply, prediction and protocol bytes are
never normalized. The final output directory must be new and outside the run.

## Reuse and verification

The runner's `summary()` is insufficient for this task: it opens the live SQLite
ledger with a write transaction and trusts stored metrics. This tool never opens
SQLite. It uses the source/attempt/control snapshots already present in the final
seal, checks their hashes, and recomputes every shared total and family summary.

Existing implementations remain authoritative:

- `final_model_gate._verify_existing`: source outcome, request, reply and product
  artifact hash chains, supplied with the sealed snapshot rather than a live ledger.
- `execution.verify_run` and `verify_result_receipts`: one original, product run,
  manifest, candidate and exact result receipt agreement.
- `quality_scoring_verification._attempts`: frozen family schema and response format,
  source text segments or image/OCR hashes, exact wire requests, reply/attempt
  accounting and strict response parsing. This helper loads no reference labels.
- `final_model_gate.source_metrics`: complete extracted-text or bounded image-page
  coverage, strict parsing, conflicts and machine acceptance, under the frozen method.

All 2,000 original file hashes are verified. Failed and uncertain cases remain in
their original families: 897 registration forms, 305 ad-buy forms and 798 receipts.
All referenced outcome/product/request/reply files are checked. A product result
cannot be used unless the required run, candidate, manifest and sidecar files are
included in its sealed output manifest. Referenced artifacts and original hashes
are checked again before the external report is returned.

Unreferenced partial outputs, orphan request/reply files, checkpoints or debug files
are hashed separately and excluded from every success count. Their relative names
are hashed in the sanitized report. SQLite files and process lock files are ignored;
neither becomes an alternative authority for the sealed results.

## Outputs and interpretation

The new directory contains `verification.json`, `report.md` and `receipt.json`.
The last file binds the first two files and the verifier/request-checking source.
The machine report includes per-source identities and metrics, aggregate and family
counts, verified artifact hashes and unreferenced-artifact hash receipts. It excludes
source text, extracted values, provider reply bodies, credentials and original paths.

Keep these quantities separate:

- **Selected originals**: the fixed 2,000-document denominator.
- **Request begun**: a durable pre-request marker; not proof of delivery or billing.
- **Known SDK attempts**: the reported count, with unknown counts explicitly retained.
- **Valid strict reply**: a completed, parsed response; not necessarily complete source coverage.
- **Valid full coverage**: a sealed source with valid strict replies and complete
  inference coverage under its text or visual route. It includes valid all-null output.
- **Valid non-null output**: at least one non-null machine proposal; still not accuracy.
- **Pre-model rejection**: a sealed outcome with zero begun requests.
- **Uncertain**: an interrupted or ambiguous attempt/source; no retry or success inference.

Known input/output tokens, missing usage, provider latency and missing latency are
reported separately. Summed request latency is not campaign wall-clock duration,
especially with four workers. There is no USD claim without provider billing data.
The historical all-original operational gate is retained unchanged; no new threshold
is introduced to convert an incomplete gate into a pass.

Machine `accepted` fields mean automatic grounding acceptance, not human-reviewed
release. `human_release_measured=false`, `accuracy_measured=false`, and `usd_cost=null`
are explicit. This run cannot support field correctness, independent visual
adjudication or a quality comparison. The planned quality240 experiment remains a
separate denominator; byte-disjoint union counting can be performed only after both
campaigns are sealed and verified.

The runtime hash in the report binds the attestation already frozen in the protocol;
the verifier does not rebuild the original environment or infer that it ran. The
final runner seal is a snapshot, not a permanent execution lock. Run this verifier
offline after process exit and preserve the independently recorded seal hash.

## Synthetic validation

Tests use real product TXT intake with fake providers and a self-authored unsupported
file. They reproduce valid output, a pre-model rejection, transport uncertainty and
an interrupted attempt with no reply/outcome. They cover missing and corrupt source,
schema, outcome, request, reply and result files; incomplete campaigns rejected before
evidence access; altered token/family/success accounting; unsealed result files; and
external-only reporting. Verification is tested with SQLite snapshots and provider
construction explicitly disabled and with before/after campaign byte equality.

```text
python -s -m pytest product_eval/tests/test_final_operational_verification.py -q
python -m ruff check product_eval/final_operational_verification.py product_eval/tests/test_final_operational_verification.py
```

Result: **23 tests passed; targeted Ruff checks passed**. Independent read-only
review found no material defect and separately ran the initial 20-test suite.
The final additions check family accounting, unsealed product files and valid
all-null coverage separately from non-null extraction.

No model or OCR calls, reference-label access, or campaign execution are needed.
