# Frozen, resumable quality240 comparison

Surface: `research_evidence`; action: `keep`. This runner performs the paired
execution specified in [the source audit](QUALITY240_SOURCE_AUDIT_20261013.md).
It never imports a scorer or opens labels. No live experiment was run while
implementing it.

## Contract

- Exactly the pinned source-only inventory: 100 registration, 100 ad-buy and 40
  reserved CORD test originals. All original bytes are hashed at freeze and every
  run/resume preflight. Product document IDs remain unchanged.
- Exactly the three pinned schema snapshots from the confirmed dev6 baseline.
  Every document in a family receives the same schema bytes.
- Text versus `bounded_visual_selective_v2`, selected from development evidence.
  Shared product-profile validation checks both profiles and their interfaces.
  Both use fresh original intake and RapidOCR, strict confirmed values, bounded
  text segmentation, Luna 6, 8,192 output tokens and 180 seconds. No cached OCR,
  blind schema discovery, SDK retry, Sonnet or per-document tuning.
- Clean executing Git/source receipt; product/OCR Python, package closure and
  model-file receipts; exact scratch/OCR environment and protocol hash.
- Family-interleaved documents, pairs adjacent, first-arm order counterbalanced
  within each family. One spawned process and one active model request. Batches
  contain 25 originals/50 source-arm slots, with a final smaller batch.
- Separate arm ledgers enforce 960 attempted requests each, at most four per
  original. Their sum is a durable global maximum of 1,920. This is a request
  bound, not a monetary guarantee or a forecast that every document needs four.

The coordinator reuses `final_model_gate._run_source`, `summary`, `_verify_existing`,
the existing request recorder, and `final_gate_ledger.Ledger`. It does not alter
the product or mixed2000 validation/semantics. The shared worker's internal run
directory prefix remains `model2000_`; the outer frozen mode is `paired_quality240`.
That internal prefix does not count these 240 as the operational2000 experiment.

## Commands

Run from the eventual clean committed checkout with the product Python runtime
and user site disabled. Outputs and scratch must remain outside Git.

```powershell
python -s -m product_eval.quality_comparison prepare `
  --inventory I:/DocAI-Benchmarks/conference-evaluation-plan/candidate_quality240_sources.json `
  --baseline I:/DocAI-Benchmarks/icore-confirmed-schema-dev6-paint-v1/protocol.json `
  --output I:/DocAI-Benchmarks/quality240-paired-v1 `
  --rapidocr-python <validated-OCR-python.exe> --scratch <existing-private-scratch>

python -s -m product_eval.quality_comparison run `
  --output I:/DocAI-Benchmarks/quality240-paired-v1 `
  --protocol-sha256 <exact-prepare-result> --api-key-env ICORE_API_KEY --batches 1

python -s -m product_eval.quality_comparison resume `
  --output I:/DocAI-Benchmarks/quality240-paired-v1 `
  --protocol-sha256 <same-hash> --api-key-env ICORE_API_KEY
```

`prepare` only validates/hashes; it performs no OCR or model calls. The credential
is read from the named environment variable and active-key/provider-token strings
are redacted from persisted replies by the shared recorder. No headers are saved.

## Stops, interruptions and irreversible prediction sealing

A request marker is committed before the provider method. Requests, sanitized
replies, tokens, finish/refusal/error states and source outcomes remain private.
The first provider error, uncertain attempt or integrity/process failure stops
both arms, even when the shared single-arm ledger would tolerate another transport
failure. Invalid strict output or an output-length limit is an extraction failure
included in the results; it is not automatically retried.

Resume rechecks both ledgers and every sealed request/reply/product hash. It only
dispatches unstarted slots. Started slots interrupted before their final source
receipt become uncertain, including a saved reply whose source commit did not
finish. Their paid attempts are never replayed automatically. Partial artifacts
remain available privately; they do not become scored successful candidates.

After resolving a resumable provider stop, pass `--acknowledge-stop` to `resume`
with the exact stop receipt SHA printed in its checkpoint. The hash-linked
control journal records acknowledgment. This permits untouched slots only and
does not erase the failed or uncertain member of a pair. SDK-count, request,
budget and integrity violations cannot be acknowledged away.

When every slot is terminal, the runner automatically exports all 240 candidate
rows per arm and writes `prediction-seal.json`. If the campaign must end early,
`seal --include-unattempted` explicitly exports missing/failed placeholders for
all remaining originals. This is not completion of their extraction. A durable
`seal-started.json` permanently closes paid execution before export begins;
interrupted local sealing can be completed with `seal`, never resumed inference.

Every final artifact is hashed, with SQLite state captured in immutable snapshots.
The mutable SQLite storage/locks are excluded from the prediction seal. Only a
separate post-seal offline analysis may open the quality references.

## Interpretation and tests

The shared arm reports preserve valid strict output, complete input coverage,
non-null values, scalar conflicts, human-review status, real/uncertain attempts,
usage, failures and all selected-source denominators. `all_sources_have_valid_model_coverage`
means exactly that; it is not an accuracy or visual-grounding score. Both arms
retain 240 outcomes even when one stops. Uncertain/unverified results are exported
as failed candidates while their raw private artifacts remain preserved.

Synthetic tests use actual `process_auto`, synthetic image originals, fake fresh
OCR and fake providers. They cover selective text/visual routes, request markers,
source/schema/runtime/receipt drift, global stopping, explicit resume, saved-reply
and pending-request crashes, durable arm/global caps, output-validation failure,
permanent sealing and unattempted denominators. No OCR engine or external API is
called by these tests. The executor is replaced with an inline test adapter;
production explicitly uses the Python `spawn` process context with one worker.
