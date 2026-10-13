# Paired product candidate development trial

Surface: `research_evidence`. Action: `keep`. This is a bounded comparison to choose a candidate before the final operational run. It is not a release accuracy claim.

## Frozen design

Use the six existing development originals in `icore-confirmed-schema-dev6-paint-v1/protocol.json`, whose SHA-256 must be `2900c5d167825d1924e2b90ee225f8e16007cfdc370d57d01b8be7d2404d83fa`. The two registration forms, two ad-buy forms, and two CORD receipts retain their exact source bytes and order. Three family schema files are copied byte-for-byte from that protocol. No new fields, descriptions, examples, per-document field-presence decisions, or target values are introduced.

| Setting | Text candidate | Visual candidate |
|---|---|---|
| Intake | Original PDF/PNG, fresh product intake | Same original, independently fresh product intake |
| OCR | Corrected RapidOCR product adapter | Same adapter, independently executed |
| Confirmed schema | Existing family snapshot | Identical snapshot |
| Configured response profile | `strict_confirmed_values_v1` | `strict_confirmed_values_v1` |
| Long text | `bounded_text_segments_v1` | Same, when the product selects its text route |
| Visual document profile | `disabled` | `bounded_visual_v1` |
| Model | ICORE `innobot-luna-6` | Same |

The visual profile is adaptive: scanned/image sources use complete bounded page images plus fresh OCR; native text documents can retain the text route. Its effective response schema is `strict_visual_confirmed_values_v1` on the visual route. Actual route and effective response profile must be reported rather than assuming every visual-arm request sent images. Visual proposals require review even when OCR quotes match.

Use baseline source index starting at zero. Even indices execute text then visual; odd indices execute visual then text. Each family therefore has one source in each order. Concurrency is one. Both arms independently call the real `process_auto` on the original file; cached OCR and baseline prediction replay are prohibited.

Budgets are at most four requests per source per arm, 48 total requests, 8,192 requested output tokens each, 180-second request timeout, and zero SDK retries. The maximum requested completion allowance is 393,216 tokens plus input tokens. This is not a dollar estimate. Visual requests preserve the product's complete-page planning, 2,048-pixel edge bound, at most 12 images and 4 MiB encoded JSON per request, and four-request complete-source cap. A source that cannot meet those bounds is reported unsupported/incomplete; it is never silently truncated.

## Prepare without OCR or inference

```powershell
python -s -m product_eval.product_candidate_dev prepare `
  --baseline-protocol <paint-v1-protocol.json> `
  --output-dir <new-private-directory> `
  --rapidocr-python <verified-rapidocr-python.exe> `
  --scratch-dir <existing-private-scratch-directory>
```

The output and scratch locations must be outside Git. Use a clean committed isolated checkout. The visual workflow interface must already exist. Python user site imports and `PYTHONPATH` are excluded by the shared runtime preflight; use `-s` or an isolated virtual environment.

Prepare verifies all original hashes, sizes and product intake IDs; copies and validates schemas; and freezes the code commit, product/evaluation Python source hashes, driver hash, interpreter hashes, package versions/installation manifest hashes, OCR revision/model hashes, runtime environment, schedule, endpoint/model and fixed budgets. It only reads source/runtime metadata and model files. It neither OCRs nor renders sources, creates a provider, reads labels, or imports a scorer. Inherited OCR timeout and RSS settings are validated and included in the frozen runtime receipt. Scratch is used for both temporary product files and the isolated OCR worker.

## Run once

```powershell
python -s -m product_eval.product_candidate_dev run `
  --output-dir <same-private-directory> `
  --protocol-sha256 <prepare-returned-sha256> `
  --api-key-env ICORE_API_KEY
```

The key must already be in the named private environment variable. It is never embedded in the protocol, command arguments, or recorded request body. The active key and ICORE token pattern are redacted from saved/returned reply text; raw provider error bodies and headers are not captured.

Run revalidates the frozen code, runtime, all six originals, exact schemas, schedule and pristine ledger before sending anything. An exclusive, fsynced `run-started.json` prevents replay after either a completed or interrupted invocation. There is deliberately no resume command for this small comparison. Do not delete the marker to retry a possibly billed request; a separately authorized new arm needs a new output directory and protocol.

Every source/arm request has a unique path. Request body bytes and provenance are fsynced first; SQLite commits `request_begun` with `synchronous=FULL` before invoking the provider. Visual requests retain their exact prepared body bytes, page/image hashes and image transformation receipt; the product provider also checks actual wire encoding. Text receipts preserve the logical request body. Replies contain only sanitized `ModelReply` fields and reply text, with hashes, usage, latency, finish/refusal/error status and SDK attempt accounting.

The first authentication, rate-limit, transport/server/unknown provider error stops the entire trial; known request rejections also stop it. Local integrity errors stop the trial. Invalid JSON, refusal, or truncated completed responses are recorded as failed extraction outcomes; they are not repaired or silently retried. Remaining source/arm slots are explicitly marked unattempted and remain in the six-document denominator for each arm.

## Outputs and interpretation

Each arm has its own `product_runs`, `requests`, `outcomes`, `candidates.jsonl`, `documents.jsonl`, and `summary.json`. The top-level summary, ledger snapshot, and `prediction-seal.json` bind all immutable protocol/schema/request/reply/product/summary artifacts. A seal can include explicit unattempted placeholders after a stop; it does not mean all 12 source/arm slots succeeded.

Report independently:

- Request-begun markers, known SDK attempts, uncertain attempts, and unknown usage. A marker alone does not prove the provider received or charged a request.
- Actual product execution, effective routes, strict parsed call counts, and complete source-page or extracted-text coverage.
- Scalar conflicts, non-null scalars, accepted scalars, linked cells, review-only cells, and all-null documents.
- Human review requirements and absence of verified visual grounding.
- Original-file identity, source page/image/transform provenance, tokens, latency and reason codes.

Visual full coverage requires the product's `full_source_covered` receipt, valid/planned/source page equality, valid/planned request equality, independently parseable strict visual replies, and a non-failed candidate. Text coverage follows the strict short-document parse or complete bounded segment receipt. Neither kind of coverage proves value correctness. An HTTP 200, valid JSON, or `needs_review` status alone is insufficient.

No gold or score is read during prepare or run. After the prediction seal is verified, the existing development-only scorer may compare the sealed candidates with creator-derived labels, preserving previous strict metrics and known annotation-quality caveats. Keep any independent visual adjudication separate. Do not inspect reserved evaluation labels or change a family schema to match a selected document's answers.

This implementation task runs only synthetic tests with mock provider/OCR boundaries, including the actual product workflow and bounded image preparation. Live OCR and ICORE calls are reserved for the separately authorized trial launch.
