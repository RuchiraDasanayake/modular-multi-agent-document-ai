# Product extraction evaluation v1

This is an **offline scorer**, independent of `idpo/evaluation`, the frozen October study, and the submitted paper. The opt-in `idpo.cli process-auto` runtime emits candidate records without reading gold labels. The two fixture documents are entirely synthetic.

Run from the repository root:

```powershell
python -m product_eval.cli --gold product_eval/fixtures/gold.jsonl --candidate product_eval/fixtures/candidate.jsonl --report product_eval-report.json
python -m pytest product_eval/tests -q
```

For a release-candidate evaluation, add `--min-documents 2000`. This guard checks unique IDs in both JSONL files;
it does not prove that 2,000 distinct source files ran through the pipeline. Verify source hashes and run manifests
separately, and include unsupported, failed and missing outputs in the scored denominator.

For the new `process-auto` runtime, verify the completed run before comparing it with gold:

```powershell
python -m product_eval.verify_execution path/to/product_runs/RUN_ID --min-unique 2000 --report execution-report.json
# Pass several completed run directories to verify sharded runs as one cohort.
python -m product_eval.verify_execution path/to/product_runs/RUN_A path/to/product_runs/RUN_B --min-unique 2000
```

This checks the final `run.json` completion marker, one manifest receipt per candidate, matching statuses and counts,
and hashes the actual source bytes (or the individual canonical JSON-array entry). Repeated inputs and retries do not
raise the unique-source count. A 2,000-source execution report proves volume and failure coverage; a field-quality
claim additionally requires an adjudicated gold set and `product_eval.cli` scoring on the matching candidate IDs.

For repeatable **no-model** gates, `run_gate` launches each disjoint input directory as a separate real `process-auto`
subprocess, verifies every source hash, joins all candidate records, requires the candidate IDs to equal the gold IDs,
and writes execution, quality, provenance, exit-code and per-shard log files. Pass a frozen VRDU `--cohort` to also
produce a source-verified family and OCR-grounding report. Use a new gate ID and report directory for
each candidate; partial shards are never silently reused. It removes provider secrets from the child environment and
records the Git commit and whether the working tree was dirty. Example:

```powershell
python -m product_eval.run_gate --gold path/to/gold.jsonl --cohort path/to/cohort.jsonl --data-dir path/to/runtime `
  --report-dir path/to/gate-v4 --gate-id vrdu_v4 --min-unique 2000 --workers 4 `
  path/to/shards/ad_00 path/to/shards/ad_01 path/to/shards/reg_00 path/to/shards/reg_01 `
  path/to/shards/reg_02 path/to/shards/reg_03 path/to/shards/reg_04 path/to/shards/reg_05
```

The gate records the sum of document durations, not parallel wall time. It cannot establish API, compute or reviewer
cost when those measurements are absent, and it does not turn a two-family development cohort into a generalization
holdout. Model-backed gates need a separate hard spend/data policy before this runner is extended to launch them.

## JSONL contract

Each line is one JSON object with `contract_version: 1` and a stable, unique `doc_id`. Gold and candidate files are separate. The scorer joins by exact `doc_id`; a missing candidate document is scored as no output, while an unknown candidate document is an error.

Gold records contain:

- `pages`: immutable normalized page text as `{ "page": 1, "text": "..." }`. Page numbers start at 1.
- `gold_schema`: fields with canonical `field_id`, `type`, optional `group`, and required boolean `critical`.
- `gold_values`: exactly one record per gold field, with a required `value`. JSON `null` means the field is genuinely absent; numeric zero and empty string are values. A non-null value may have adjudicated `evidence`.
- A linked field with `type: "array[object]"` uses `value: [{"row": 0, "value": "..."}, ...]`. Row ordinals are unique within that field and start at zero. This is the VRDU adapter's derived structure, not a general table interchange format.

Candidate records contain:

- `document_status`: `processed`, `needs_review`, `unsupported`, or `failed`.
- `proposed_schema`: discovered fields with `field_id`, `type`, and optional `group`.
- `extracted_values`: zero or one record per field ID, each with `value`, `status` (`accepted`, `needs_review`, `missing`, `rejected`), `review_state` (`none`, `pending`, `completed`), and optional `evidence`. A `needs_review` or `rejected` value is a proposal, never an accepted extraction.
- Optional `measurements`: non-negative measured `latency_ms`, `api_cost_usd`, `compute_cost_usd`, `review_minutes`, and `total_cost_usd`. Supply `total_cost_usd` only when the caller has measured the full chosen cost boundary; the scorer never guesses prices or substitutes zero for missing data.

An evidence reference is `{ "page": 1, "start": 8, "end": 13, "quote": "INV-7" }`. `start` and `end` are zero-based, half-open Python Unicode character offsets into that page's normalized text. A gold quote must exactly equal the slice. Candidate evidence is **valid** only when it has a complete span and matching quote, includes the adjudicated gold span on the same page, and the accepted typed value is correct. A page number alone is not grounding. Validity is not assessed when gold has no span; this is reported as an explicit denominator, not as a pass.

Field IDs are case-sensitive canonical IDs assigned during human gold adjudication. The scorer does **not** infer semantic aliases: an unadjudicated synonym counts as a missed gold field and a spurious candidate field. Type and group accuracy are reported only on fields whose IDs match. For an isolated value-extractor comparison, feed the same fixed canonical schema to each candidate; for end-to-end auto mode, use its proposed schema. Never let the candidate producer read the gold file.

## Metric definitions

- Schema precision/recall/F1 count matched, spurious, and missed field IDs. Type and group accuracies have their own matched-field denominators.
- Value precision/recall/F1 score **pre-review** accepted values using strict JSON type and value equality. A wrong accepted value contributes one false positive and, if gold has a value, one false negative. An abstention on a present gold value contributes one false negative. `0`, `0.0`, `false`, and `null` remain distinct. No date, currency, or text normalization is implied by this v1 scorer.
- `linked_rows` separately scores exact proposed and accepted cells by field ID, row ordinal, and OCR surface string. It also counts a complete row only when every predicted field/value on that ordinal equals gold. This diagnostic uses derived ordinals and does not perform semantic row alignment or the official VRDU matcher.
- `false_accepted` counts wrong, absent, or unknown accepted fields; `critical_false_accepted` is the subset on known critical gold fields. The two missing/zero counters expose missing declared for gold numeric zero and accepted numeric zero for gold absence.
- Evidence presence and validity use accepted fields with a gold span as the denominator. Incomplete or page-only references fail presence; incorrect quote, span, or value fail validity.
- Field automation is accepted gold fields with `review_state: none` divided by all gold fields. Review rates count a field or document requiring or receiving human review. Document automation counts processed documents with no review signal. These coverage metrics do not assert correctness.
- A correctly auto-released document has at least one critical gold field, `document_status: processed`, no review signal, every critical field accepted exactly (or explicitly `missing` when gold is absent), valid evidence for each accepted critical field that has a gold span, and no false accepted field. `cost_per_correctly_auto_released_doc_usd` divides the **sum of all documents' reported `total_cost_usd`** by this count, and is `null` if any document lacks total cost or none qualifies.

Every metric includes its numerator and denominator or the underlying counts; undefined ratios are JSON `null`. `per_field` and `per_document` list outcomes without copying document text or field values into the report. `measurements` reports coverage and observed sums; partial sums are not totals for the batch.

This scorer does not evaluate semantic row alignment across reordered or split tables, semantic aliases, reviewer corrections, calibrated confidence, OCR accuracy, or normalized business values. Those require adjudicated contracts and dedicated metrics before product claims are made.
