# ICORE two-public-PDF extraction diagnostic

**Status: source lock and offline runner prepared; no ICORE request made by this arm.** Execute only after the active 2,000-source local gate and TableMagic pilot release host resources. This is a fresh development diagnostic, not a continuation of the [stopped six-source attempt](ICORE_REAL_DEVELOPMENT_SIX_RESULT_20261012.md). That attempt's zero scores resulted from one ambiguous connection failure and eight unattempted document-model cells; it measured no real-document model quality.

## Frozen source and product path

The [two-source lock](../../product_eval/fixtures/icore_two_public_sources_v1.json), SHA-256 of canonical LF bytes `cfda5a748f8f5b914a9fd63558ae89f5645bd03d5490a97a023c32a8d7129556`, selects the raw-source-SHA **rank 6** public development PDF from each VRDU family in the prior twelve-source selection. Canonical hashing accepts the same fixture after Windows checkout converts LF to CRLF. Both sources were in the pre-existing [six-source lock](../../product_eval/fixtures/icore_real_dev_six_sources.json), but neither received a model call in its stopped run. Selection used family and source-hash rank before looking at gold or model replies. The runner checks each raw PDF hash, byte length, filename, completed prior OCR sidecar, OCR page hash, VRDU cohort hash, derived product gold hash, and Tesseract binary/language hashes **before reading a credential**. It does not touch the separate ExtractBench holdout, user files, private documents, or ASF mail.

| Family | Document ID | Raw PDF SHA-256 | Prior OCR pages |
| --- | --- | --- | ---: |
| Registration form | `4d8a3580763cfc54e07b943e4e5fe9d8` | `012038abfa3e045b23584aacd91dff687425c1b0933b3558fd51d34f44f1233b` | 2 |
| Ad-buy form | `480ff75645024ee29844be53be120fcf` | `022c46dc12f992dd7b632b2c3821f5158979934e7354e01dc4ecaf5c7a39d62c` | 3 |

The [runner](../../product_eval/icore_two_public_runner.py) calls the current `process_auto` route on each original PDF: fresh PDF/OCR intake, automatic schema proposal, value proposal, local exact-source evidence check, and review gate. Its only model is `innobot-luna-6`, through the existing ICORE OpenAI-compatible chat adapter. It does not feed prior OCR text or gold into prompts. The remote model revision cannot be pinned by a weights hash; report the model ID, product Git commit, source hashes, and credential-free request/response hashes. A changed product commit is a different implementation arm.

## Hard request and spending boundary

| Limit | Value |
| --- | ---: |
| Distinct public PDFs | 2 |
| Authenticated chat attempts | 4 total maximum; at most schema + values per PDF |
| Model output tokens | 1,536 maximum per attempt |
| User prompt | 12,000 characters and 14,000 UTF-8 bytes maximum |
| Aggregate provider-reported input + output tokens | 100,000 maximum |
| SDK retry count / concurrent calls | 0 / 1 |
| Per-call timeout | 60 seconds |
| OCR timeout | 30 seconds per call; 120 seconds per page budget |

The runner writes an append-only, credential-free attempt-start record before each SDK call. It stops further SDK calls on ambiguous transport, missing token usage, unknown SDK attempt count, any finish reason other than `stop`, any uncaught product exception, or budget exhaustion. Failed and unattempted PDFs stay in the two-document score denominator. A timeout might still be processed or billed remotely, so the runner never automatically retries a request or resumes an existing output directory. A model call limit controls quantity of requests; it does **not** guarantee a USD ceiling. ICORE's current rate card, settled charge ledger, provider hard spend cap, and document-processing terms have not been verified. Report `api_cost_usd: null` and `compute_cost_usd: null`; do not call this pilot free or cheaper.

The credential is read **in memory** from the user-provided attachment path by `load_credential`, which rejects anything other than exactly one distinct key associated with the pasted Copy control. The key is not a command argument, output value, or report field. Do not reuse the earlier PowerShell key-selection snippet from the synthetic one-call probe; its indexing guard was defective. The runner restores `ICORE_API_KEY` after constructing the SDK client. Raw source, OCR text, candidate artifacts, attempt ledger, and full scorer output remain outside Git. Model reply **bodies are not persisted**; the ledger retains hashes and usage only, which limits post-run diagnosis of a malformed reply.

## Exact execution, when released

Use a fresh output directory for exactly one invocation. The local source/sidecar hash preflight has passed without reading a credential or making a network request. The following command has **not** been executed:

```powershell
Set-Location 'C:\Users\USER\Documents\ChatGPT\Research\modular-multi-agent-document-ai'
C:\Python313\python.exe -m product_eval.icore_two_public_runner `
  --credential-file 'C:\Users\USER\.codex\attachments\1f923690-409e-4585-b28b-c0989444579b\Pasted text.txt' `
  --output-dir 'E:\DocAI-Benchmarks\icore-two-public-v1-20261013' `
  --vrdu-cohort 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\cohort.jsonl' `
  --vrdu-gold 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gold.jsonl' `
  --runs-root 'E:\DocAI-Benchmarks\runtime\product_runs' `
  --tesseract 'E:\DocAI-Benchmarks\tools\Tesseract-OCR\tesseract.exe' `
  --tessdata-dir 'E:\DocAI-Benchmarks\tools\Tesseract-OCR\tessdata'
```

Run sequentially with no corpus gate or TableMagic inference on the host. The two PDFs total about 303 KB and five prior OCR pages. Reserve roughly **2–4 GB free RAM**, **1 GB free output disk**, and **up to 15 minutes** for fresh OCR plus four 60-second network timeouts. These are operational reservations, not measured resource use. The output directory must not already exist; a partial attempt is an immutable receipt and requires a new protocol before any repeat.

## Score and interpretation

The runner uses the same existing `score_records` evaluator as the VRDU product gates, once per family. Primary schema scoring uses exact derived field IDs and types; values require exact typed accepted values; linked cells and complete rows require exact group/row identity and OCR surface strings; evidence and document review need are separate. No post-hoc alias mapping alters the primary score. The scorer includes both planned documents even when a source has no product candidate. `summary.json` contains only aggregate quality metrics, safe status/usage metadata and hashes. `*-full_score.json`, source pages, candidate data and the call ledger remain in the external output directory; never commit them without a separate scrub.

Interpret a completed response as a **two-source debugging observation**, not an estimate of reliability, arbitrary-document accuracy, or production cost. If the first call fails again or transport/usage is ambiguous, record only the operational failure; zero extraction scores in that case do not measure Luna 6 quality. Any production promotion still needs broad labeled, source-disjoint evaluation, human review evidence, and the separate 2,000-distinct-raw-source regression gate after a product change.
