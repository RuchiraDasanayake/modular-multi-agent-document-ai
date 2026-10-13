# VRDU 2,000-document v8 renderer and resource gate (12 October 2026)

This completed **no-model** gate ran product-auto at clean detached commit
`07a52e6d69abfd9e253072ef953becc8553986eb` on the same frozen two-family VRDU development cohort as
[v7](VRDU_2000_NO_MODEL_V7_PDFIUM.md). It checks actual per-page renderer provenance and worker resource receipts
added after v7. Eight disjoint 250-PDF shards ran with four workers and all exited 0. The source verifier checked
**2,000 documents from 2,000 distinct raw PDF hashes**, zero repeated sources, complete candidate/gold IDs, and no
missing candidates. Every document is `needs_review`; none failed, was unsupported, or was released.

## Observed renderer and OCR

| Observation | v7 | v8 |
| --- | ---: | ---: |
| PDF pages with native text / Tesseract | 3,481 / 831 | **3,481 / 831** |
| Documents with a Tesseract page | 677 | **677** |
| Tesseract pages with actual renderer identified | 0 (not recorded) | **831 / 831** |
| Actual PDFium / Poppler / direct fallback pages | unknown | **831 / 0 / 0** |
| PDF pages missing zero-based source page index | 4,312 (not recorded) | **0 / 4,312** |
| OCR page failure / timeout | 0 / 0 | **0 / 0** |
| Tesseract pages with positive reported confidence | 831 / 831 | **831 / 831** |
| OCR p50 / p95, all documents | 10.57 / 8,232.9 ms | **10.30 / 7,985.5 ms** |
| OCR p50 / p95, Tesseract documents | 3,066.6 / 26,009.5 ms | **2,994.3 / 25,052.3 ms** |
| Sum of per-document durations | 4,825,504 ms | **4,672,868 ms** |

The v8 receipt analyzer found no renderer fallback reason, missing rendered DPI/size, or missing resource/provenance
field. All 831 OCR PDF pages used PDFium on this cohort; this does **not** establish that PDFium never falls back on
other PDFs. Positive OCR confidence proves an engine returned a score, not transcription or field accuracy. The
per-document duration sum is 3.16% lower than v7 with four concurrent workers; this is not a controlled speed
comparison. Tesseract `v5.5.3.20260724` passed a real English OCR preflight with `eng.traineddata` SHA-256
`7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. The clean host environment had
`pypdfium2 5.14.0`, `pypdf 6.5.0`, `pdf2image 1.17.0`, and `psutil 7.2.2`.

## Extraction quality and cost coverage

| Metric | v7 | v8 |
| --- | ---: | ---: |
| Strict schema TP / FP / FN | 819 / 21,792 / 15,181 | **819 / 21,792 / 15,181** |
| Strict schema F1 | 4.2423% | **4.2423%** |
| Accepted-value F1 | 0% | **0%** |
| Proposed linked cells / complete rows | 0 / 0 | **0 / 0** |
| Gold linked cells / complete rows | 30,133 / 7,234 | **30,133 / 7,234** |
| Correct automatic releases / model calls | 0 / 0 | **0 / 0** |

A paired comparison by the same 2,000 document IDs found **zero changes in schema, extracted values, or document
status** between v7 and v8. Candidate files still have different byte hashes because they include run-specific
latency measurements. The strict scorer uses exact derived field IDs and row ordinals, not semantic alias alignment
or the creator's official VRDU matcher. This run tests 500 ad-buy and 1,500 registration forms, not arbitrary
document types, AI schema generation, model value extraction, specialist table parsing, reviewer corrections, or
the revised frontend.

Worker-process CPU and RSS snapshots were present for **2,000/2,000 documents and 8/8 runs**. Summed document
worker CPU was 899,234 ms; summed run worker CPU was 901,047 ms. The maximum observed **boundary** RSS was
183,005,184 bytes (about 174.5 MiB). These numbers exclude Tesseract child-process CPU/RSS, remote computation,
and memory peaks. All 2,000 documents have null API, compute, and total monetary cost, and none reports reviewer
time. Therefore cost per correctly released document is undefined; no lower-cost claim follows from this run.

**Decision:** the 2,000-source execution, actual-renderer coverage, and worker-telemetry gates passed. Extraction
quality, automation, and cost gates failed. Keep this no-model path review-only. Evaluate specialist tables and
model-backed schema/value extraction on source-locked development samples, then run distinct-source validation
with a broader held-out document mix before considering promotion.

## Reproduction and evidence

- Source: [Google VRDU](https://github.com/google-research-datasets/vrdu), creator commit
  `04a4df7ac5cc694e51c48115c03fe428f0e240cc`.
- Frozen cohort / gold SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90` /
  `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
- Candidate / execution / quality / family / receipt-analysis SHA-256:
  `a545e0559d73bc41810eed5b88799d9f6c97f7dd476aae633b154e5bea576ca4` /
  `bed4b2b4f05f800c54458bdc524baf659bde6098c3da2cd844a9d6133d8512b7` /
  `92644a0d82a33ca1dbd68421760bf2c9291eaf0f991c5f8e438e462e0fc10acb` /
  `00f19b4ba8dd124d1357b492e0546dc2d2810e8bc1a0e0ae5a6c9d198b3723b2` /
  `e31f6b3dbe4a4b8721510d1fd0b2c7c7ef38961e7ff91da37c43d2594b336c40`.
- Command: `python -m product_eval.run_gate --gold <frozen gold> --cohort <frozen cohort> --data-dir
  E:\DocAI-Benchmarks\runtime --report-dir E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v8-provenance
  --gate-id vrdu_v8_provenance --min-unique 2000 --workers 4 <eight pinned shard directories>`. The gate set
  `TESSERACT_CMD` and `TESSDATA_PREFIX` to the pinned local installation, and the per-run child clears model API
  secrets. The sidecar analysis used `python -m product_eval.receipt_analysis` after the source-verified gate.
- Reports, logs, candidates, provenance, sidecars and resource receipts are outside Git at
  `E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v8-provenance` and
  `E:\DocAI-Benchmarks\runtime\product_runs\vrdu_v8_provenance_*`.
