# Schema-only scorer v1 contract

**Status: implemented and tested with synthetic files only (13 October 2026).** [`product_eval/schema_only_scorer.py`](../../product_eval/schema_only_scorer.py) scores field discovery and repeated-group structure for exactly 12 planned source IDs. It makes **no model call** and does not read original documents. It does **not** score values, rows, source evidence, human review, cost, or product release. The [human-gold protocol](SCHEMA12_HUMAN_GOLD_AND_SCORING_PROTOCOL_20261013.md) still requires independent annotation, adjudication, source anchors and a separate value/evidence scorer. This implementation is a supporting research component; the primary action is **keep** while its version-1 contract is used, then revise under a new version when justified.

The current v2 public set is **not admitted for inference**: source/template overlap and per-file rights are still being audited, including NICE terms that may restrict AI processing. A source-only v3 substitution may be required. This scorer is corpus-agnostic; it has no hard-coded v2 IDs or paths. Do not run it on a model output and call the result a validated public score until the admission, human-gold and pre-inference locks are complete.

## Four input files

All files are UTF-8 JSON, `contract_version: 1`. The source lock has **exactly 12 unique IDs and unique lowercase raw-source SHA-256 hashes**. Its exact file-byte SHA-256 is copied into the gold and candidate envelopes as `source_lock_sha256`; every included document record also repeats its exact raw-source SHA-256, which must agree with the lock. The scorer does not verify original document bytes; the upstream source admission must do that. Full source bytes, gold annotations and raw model replies remain outside Git.

```json
{"contract_version":1,"sources":[
  {"doc_id":"synthetic-01","source_sha256":"<64 lowercase hex characters>"}
  /* eleven more distinct sources */
]}
```

The block illustrates shape only; `/* ... */` is explanatory and is **not valid JSON**. Gold contains **one document record for every planned ID**, even if no candidate processes it. `gold_complete` means both annotators and the adjudicator completed the predeclared full-document schema inventory. If false, recall over known fields remains diagnostic but precision/F1 and full-document claims are withheld. A field has a canonical snake-case ID and one primitive type: `string`, `number`, `integer`, `boolean`, `date`, `datetime`, `currency`, or `identifier`. Version 1 compares these types **exactly**, with no `integer`→`number`, `currency`→`number`, or `identifier`→`string` coercion. `group: null` is scalar; a linked leaf references a declared `array[object]` group. `object` and `array[scalar]` group declarations are permitted but do not create linked leaf pairs.

```json
{"contract_version":1,"source_lock_sha256":"<source lock file SHA-256>","documents":[
  {"doc_id":"synthetic-01","source_sha256":"<synthetic-01 raw SHA-256>","gold_complete":true,
   "groups":[{"group_id":"items","kind":"array[object]"}],
   "fields":[
     {"field_id":"invoice_number","type":"identifier","group":null},
     {"field_id":"item_name","type":"string","group":"items"},
     {"field_id":"item_quantity","type":"integer","group":"items"}
   ]}
]}
```

The aliases file is prepared from source-only adjudicated concepts **before model inference**. Each term may belong to only one canonical gold ID across the cohort. Canonical IDs themselves are included as normalized literal terms, so an empty `entries` list is valid but explicit. There is no family-conditioned or gold-value-conditioned alias choice.

```json
{"contract_version":1,"entries":[
  {"field_id":"item_quantity","aliases":["qty","line_item_quantity"]}
]}
```

Candidate records are projected from raw model output without looking at gold. `status` is one of `ok`, `failed`, `unsupported`, `over_limit`, `malformed`, or `skipped`. Only `ok` may carry fields/groups. An invalid or missing raw model response should be recorded with its planned `doc_id` and `status: "malformed"`; do not silently omit it. A projection adapter may map a model's type tokens into the version-1 primitive types, but the adapter must be frozen before inference and must preserve field/group meaning and the raw reply elsewhere for audit. Candidate field names may use the model's original case and separators; duplicate exact names invalidate that source's schema.

```json
{"contract_version":1,"source_lock_sha256":"<source lock file SHA-256>","documents":[
  {"doc_id":"synthetic-01","source_sha256":"<synthetic-01 raw SHA-256>","status":"ok",
   "groups":[{"group_id":"line_items","kind":"array[object]"}],
   "fields":[
     {"field_id":"invoice_number","type":"identifier","group":null},
     {"field_id":"itemName","type":"string","group":"line_items"},
     {"field_id":"qty","type":"integer","group":"line_items"}
   ]},
  {"doc_id":"synthetic-02","source_sha256":"<synthetic-02 raw SHA-256>","status":"over_limit"}
]}
```

## Scoring and failures

- **Exact mode:** one-to-one raw field-ID equality. **Predeclared-alias mode:** first preserve exact matches, then apply NFKC, ASCII camel-boundary insertion, casefold and Unicode alphanumeric token normalization to unmatched candidate names. Literal normalized equality and only the frozen alias terms are eligible. If multiple candidates claim a gold ID, the alias claims collide and receive no alias credit. Report unmatched/colliding names, exact type agreement and group-role agreement separately from field-name TP.
- For each declared `array[object]` group, form unordered pairs of its leaf fields. A pair is correct only when both candidate leaves uniquely match gold leaves in the **same gold group** and share one candidate `array[object]` parent. Report pair TP/FP/FN and two group counts: `coverage_hit` when all gold leaves share one candidate repeated parent, and stricter `hit` only when that candidate parent has **no extra leaves**. Extra leaf pairs also count as pair FP. A matching field name in a scalar or another group does not prove the link. Empty pair denominators have `null` recall.
- All 12 planned IDs remain in the report. A missing candidate or a declared failure produces zero schema TP and all its known gold fields/pairs as FN. Duplicate candidate document records invalidate that ID; duplicate field IDs, invalid group references, unsupported types or malformed `ok` envelopes invalidate that document. An unknown candidate ID, missing/duplicate gold ID, wrong per-document source hash, changed source-lock digest, duplicate JSON object key, invalid top-level JSON or invalid source lock aborts scoring because identity/provenance cannot be trusted. Raw syntactically invalid model replies must be converted to a per-source `malformed` envelope **before** the scorer sees the candidate file.
- Unmatched predicted fields/pairs are reference-ontology FP only when all relevant gold records have `gold_complete: true`. If any gold record is incomplete, aggregate precision and F1 are `null`; per-source completed records still carry their own precision. An unmatched field is **not** automatically a hallucinated value. Score exact and aliases in separate report branches, including per-source results. The 12-source sample cannot establish arbitrary-document accuracy.

Run after all real source, rights, gold, alias, adapter and model locks are frozen:

```powershell
python -m product_eval.schema_only_scorer `
  --source-lock '<source-lock.json>' --gold '<adjudicated-gold.json>' `
  --candidate '<sealed-candidate.json>' --aliases '<frozen-aliases.json>' `
  --report '<new-external-report.json>'
```

The report path must not exist, and the report records SHA-256 of all four exact input files. Keep these files and the full per-source report outside Git; commit only scrubbed aggregates and hashes. The synthetic unit tests check the 12-source denominator, exact/alias separation, split linked groups, alias collisions, malformed/duplicate failures, incomplete gold and CLI provenance. A later row-content/evidence/reviewer scorer must be implemented and frozen separately.
