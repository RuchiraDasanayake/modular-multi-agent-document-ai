# Frozen model-assisted operational gate

Surface: `research_evidence`. Action: `keep`. This implements the operational lane of [conference protocol v2](CONFERENCE_EVALUATION_PROTOCOL_V2_20261013.md). It does not run an accuracy evaluation or open labels.

## What this gate measures

Exactly 2,000 distinct original files go through the current `process_auto` intake and OCR path using one frozen confirmed schema per family. The allocation is 897 VRDU registration forms, 305 VRDU ad-buy forms, and 798 CORD training receipts. It does not replay cached OCR text. This corpus measures three-family operational coverage; it does not establish general accuracy across all supported file formats, schema discovery quality, independent visual correctness, or human approval.

The initial profile remains ICORE `innobot-luna-6`, RapidOCR, `strict_confirmed_values_v1`, `bounded_text_segments_v1`, and `visual_document_profile="disabled"`. An explicitly frozen `bounded_visual_v1` profile is also supported. Its image request accounting and complete-page receipts are locally tested; it is never silently ignored. A development comparison must select the final candidate before a real run is frozen.

The report distinguishes:

- Original files selected, attempted, sealed, uncertain, or unstarted.
- Request-begun markers versus known SDK attempts and received responses.
- Strict parsed replies and provider finish/refusal/error outcomes, with complete extracted-text coverage and complete bounded-page-image coverage reported separately.
- Non-null outputs, all-null outputs, scalar conflicts, and human review requirements.
- Known token subtotals, unknown usage, and measured provider latency. Dollar cost remains unknown without provider billing receipts.

`operational_gate_passed` requires all 2,000 originals to have valid, fully covered strict extraction receipts, at least one known attempt each, and no uncertain source states. All-null valid outputs are reported separately and do **not** establish useful extraction quality. Text coverage concerns the text produced by intake/OCR; it is not proof that OCR captured every visible character. Scalar conflicts can have complete inference coverage while still requiring human resolution.

`valid_full_coverage_originals` is the common operational count. `valid_full_text_coverage_originals` counts only
the text route; `valid_full_visual_coverage_originals` counts only the visual route. Visual source metrics require
the ordered original-page list, every planned/attempted/valid page, the complete plan digest, and exact request
hashes to agree with the recorder's prepared-request receipts. Every response is independently strict-parsed
against its own batch's source pages. Failed candidates, missing output fields, missing calls, invalid/truncated/
refused replies, partial coverage, and machine-accepted visual proposals cannot pass. An empty OCR aid can have
complete visual coverage because its whole source image was submitted; its `full_text_coverage` is not applicable.
For long text, the runner also rebuilds the frozen deterministic segment plan and independently strict-parses
every reply against its exact text slice. Successful counters and a product reason alone cannot pass the gate.

Visual preparation is bounded to four requests, at most 12 full-page images per request, 2048 pixels per image edge,
and 4 MiB per actual request body. The full-page downscale can lose legibility, so complete page-image coverage is
not proof of visual recognition or correct extraction. The product determines whether a source needs images;
native documents retain the strict text/long-document route. No visual-to-text inference fallback is introduced.

## Freeze

Use a clean committed checkout after integration. Set the private ICORE key in an environment variable only. Configure `IDPO_RAPIDOCR_PYTHON`, `IDPO_RAPIDOCR_WORK_DIR`, and any bounded OCR timeout/RSS overrides. Use the same interpreter and environment for freeze, run, and resume. User site imports and `PYTHONPATH` are rejected; run Python with `-s` or use an isolated virtual environment.

```powershell
python -s -m product_eval.final_model_gate profile > profile.json
python -s -m product_eval.final_model_gate freeze `
  --cohort <mixed2000-cohort.jsonl> `
  --schema-protocol <frozen-development-family-protocol.json> `
  --profile <profile.json> `
  --output <new-private-output-directory>
```

Keep the profile file outside the repository so the checkout remains clean. With Windows PowerShell 5, use an explicit UTF-8 writer instead of `>` to avoid UTF-16 JSON. The freeze returns the protocol SHA-256 required by subsequent commands.

Before publishing a protocol, freeze verifies every original's bytes, size, distinct SHA-256, and product intake ID. It copies and validates the three confirmed schema snapshots. No gold paths, expected values, or per-document field-presence information are carried into the frozen source inventory. The evaluator-owned schema identity is a research fixture, not evidence of user HITL confirmation.

The protocol binds the clean Git commit, product/evaluation Python source hashes, Python executable hashes, package versions and installation RECORD hashes, OCR revision, actual OCR model-file hashes, worker environment/configuration, endpoint/model, and all route/budget settings. RECORD hashes describe installed package manifests; they do not independently hash every installed wheel payload. The worker verifies its exact runtime/model pins without executing OCR during freeze.

When visual mode is explicitly enabled, freeze also requires its product entrypoint, provider method, and fixed
page-image/request bounds. The default disabled profile does not require the optional visual interface. Exact
visual body bytes are persisted without JSON re-encoding; their SHA-256 is the same one admitted by the provider's
wire guard. Both routes use the same durable call budget and request-before-SDK transaction.

Every run or resume repeats source/runtime/schema validation before dispatch. Code or runtime changes require a new frozen arm. Completed output, private request, and sanitized reply hashes are also checked before resume.

## Run and checkpoints

```powershell
python -s -m product_eval.final_model_gate run `
  --output <private-output-directory> `
  --protocol-sha256 <freeze-returned-sha256> `
  --api-key-env ICORE_API_KEY
```

Sources are sorted by existing shard and document ID, then processed in stable batches of 25. `--batches 1` performs a bounded first batch and stops cleanly; subsequent `resume` continues only untouched originals. All shards remain part of the fixed 2,000-source denominator. Native spawned Python processes are used, with one worker by default. No Docker is required.

Workers 2–4 require a profile-embedded resource validation receipt matching the exact code commit, runtime hash, and profile hash with `parallel_validation=null`. It must record `status="passed"`, matching `workers`, `completed_sources>=workers`, `peak_tree_rss_bytes`, at least 1 GiB `minimum_available_memory_bytes`, and a valid `evidence_sha256` for independently reviewed measurements. Current available RAM must exceed the validated peak plus 1 GiB. These measurements must exercise representative raster OCR; a syntactic receipt alone is not a resource experiment. No parallel profile has been validated by this implementation task.

The hard global cap is 2,500 requests, with at most four per original, up to 8,192 output tokens per request, and no SDK retries. Worst case at four requests per source is 8,000 requests; this initial budget does not promise every possible source can finish. Freeze performs no OCR, so it explicitly marks the exact segment forecast unavailable. The 2,500-request profile must be reconsidered only in a new frozen arm if the final candidate's measured plan requires more. At the existing cap, maximum requested completion allowance is 20.48 million tokens, plus input tokens; this is a ceiling, not a cost estimate.

## Failure and resume semantics

SQLite uses WAL and `synchronous=FULL`. A source claim is committed before a worker starts. Each request payload is persisted and fsynced, then a `request_begun` row is committed **before** the provider method can run. Only sanitized `ModelReply` fields and reply text are saved. Raw provider error strings, HTTP error bodies, credentials, and headers are excluded.

Private request paths are scoped by source (`requests/<doc_id>/<digest>.json`), so concurrent workers with identical
request bodies cannot inspect each other's partially written file. The active credential is passed explicitly to
the reply wrapper; literal matches and `iba_` token patterns are redacted before both private reply storage and
product parsing. Unknown/non-single SDK attempt counts and uncategorized provider errors remain uncertain.
A late concurrent provider reply cannot weaken a nonresumable integrity or budget stop into a resumable one.

After a response, the reply hash, usage, latency, finish/refusal/error state, and SDK attempt count are sealed. Product run/manifest/result receipts are verified and all produced files are hashed before the source outcome is sealed. A crash in between leaves the source or attempt uncertain. An OS file lock prevents competing coordinators and releases automatically if the coordinator dies.

```powershell
python -s -m product_eval.final_model_gate resume `
  --output <private-output-directory> `
  --protocol-sha256 <same-frozen-sha256> `
  --api-key-env ICORE_API_KEY
```

Resume never retries a started, sealed, failed, or uncertain source. It only dispatches sources still marked `unstarted`. A request-begun marker is not proof that the provider received or billed the request. An uncertain attempt therefore remains in accounting with unknown outcome, instead of being silently repeated.

The first authentication, rate-limit, or rejected-request response stops new dispatch. Two consecutive transport/server/unknown provider failures also stop dispatch. Already running requests can finish, bounded by the frozen worker count. Unexpected local failures stop dispatch and preserve a safe failure stage and exception class, not raw exception text.

After resolving an authentication/rate/transport condition, an operator can explicitly add `--acknowledge-stop authentication`, `rate_limit`, or `repeated_transport_failure` to `resume`. The supplied reason must exactly match the ledger. This records a control event and allows **only untouched sources** to continue; it does not erase earlier failures or repeat a paid attempt. Budget, unsupported-request, and local-integrity stops cannot be cleared this way. A gate with an uncertain original cannot claim all 2,000 succeeded.

Private artifacts contain source text and model proposals, so keep the output directory outside Git. Checkpoint reports always retain the complete denominator. A final accounting seal can include failures or uncertain sources; `all_prediction_receipts_sealed` and `operational_gate_passed` state the narrower facts explicitly. Do not unlock accuracy labels merely because a `seals` directory exists. No scoring or annotation loading occurs in this runner.

## Validation completed

Synthetic tests exercise request-before-call durability, SQLite concurrency, call caps, interruption/recovery, exclusive locking, provider circuit stops, explicit safe continuation, source/schema/runtime drift, duplicate originals, receipt tampering, strict/refusal/truncation failures, all-null separation, and partial segment coverage. Short and long synthetic text fixtures traverse the real product workflow using a mock model and no OCR.

The hardening suite contains 64 local tests, including identical requests published concurrently by two source
workers, active-key redaction, uncertain SDK accounting, nonresumable stop precedence, exact visual request
persistence before invocation, complete visual receipts through the real product workflow with mocked OCR/model
boundaries, and negative tests for false full-coverage claims. No provider requests, OCR execution, or label reads
were performed for these tests. This does not run or satisfy the final 2,000-original gate.

Read-only preflight of the actual staged cohort verified 2,000 distinct original hashes and intake IDs, totaling 2,024,195,542 bytes. The largest file is 14,252,400 bytes; none exceeds the 20 MiB product limit. The receipt SHA-256 is `a470f4df822cf60931d92a7296a8e2007a51dec2b3a8f001b8a61fdbd9a0bda0` (`model2000-runner-source-preflight-20261013.json` in the private conference-evaluation-plan directory). This is input verification, not an extraction run. No model calls, OCR calls, or label reads were performed for it.
