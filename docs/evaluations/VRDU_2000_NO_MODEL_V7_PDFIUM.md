# VRDU 2,000-document v7 PDFium-first gate (12 October 2026)

This completed **no-model** product-auto gate tests the PDF renderer change at clean, detached commit
`111f235e7f811059d6fbcdafe8c41df0cf06aeed` against the same frozen two-family VRDU development cohort as
[v6](VRDU_2000_NO_MODEL_V6.md). The product code selects `pypdfium2 5.14.0` first and keeps Poppler as a fallback.
It does not yet record the actual renderer for each page, so this is a **PDFium-first configured** run, not proof
that every scan page used PDFium. It does not test AI schema generation, table parsers, linked-row model proposals,
recipe matching, reviewer corrections, or arbitrary-document generalization.

## Execution

All eight disjoint 250-PDF shards exited 0. The gate verified **2,000 documents from 2,000 distinct raw source
hashes**, zero repeated sources, zero missing candidates, and a complete gold/candidate ID join. Every document
remained `needs_review`; none was released, unsupported, or failed. The gate preflight ran actual English OCR with
Tesseract `v5.5.3.20260724` and pinned `eng.traineddata` SHA-256
`7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. The same 30-second OCR-call
timeout and 120-second per-image-page budget as v6 were configured. No page recorded an OCR timeout or failure.

| Observation | v6 bounded Tesseract | v7 PDFium-first configured |
| --- | ---: | ---: |
| Native-text / Tesseract pages | 3,481 / 831 | 3,481 / 831 |
| Documents with a Tesseract page | 677 | 677 |
| Tesseract pages with positive reported confidence | 831 / 831 | 831 / 831 |
| OCR page paths: initial / quick / full / quick plus full | 650 / 87 / 72 / 22 | 656 / 89 / 62 / 24 |
| OCR p50 / p95, all documents | 10.85 / 8,613.7 ms | 10.57 / 8,232.9 ms |
| OCR p50 / p95, Tesseract documents | 3,062.1 / 22,872.3 ms | 3,066.6 / 26,009.5 ms |
| Maximum document OCR stage | 131,689 ms | 138,553 ms |
| Sum of per-document durations | 4,783,740 ms | 4,825,504 ms |

The sum of document durations is 0.87% higher in v7, while mixed-document OCR p95 is lower and scanned-document
OCR p95 is higher. Four workers ran concurrently; these are observations, **not a controlled speed comparison**.
Both engines report OCR confidence on 831 scan pages, which does not establish transcription accuracy. Individual
schema or value proposals changed on 301 documents; the renderer can affect downstream text even when the number
of scanned pages stays fixed.

## Exact extraction quality

| Metric | v6 | v7 |
| --- | ---: | ---: |
| Strict schema TP / FP / FN | 819 / 21,769 / 15,181 | **819 / 21,792 / 15,181** |
| Strict schema F1 | 4.2448% | **4.2423%** |
| Ad-buy / registration schema F1 | 1.2208% / 5.5236% | **1.2200% / 5.5203%** |
| Pre-review accepted-value F1 | 0% | **0%** |
| Proposed linked cells / complete rows | 0 / 0 | **0 / 0** |
| Gold linked cells / complete rows | 30,133 / 7,234 | 30,133 / 7,234 |
| Correct automatic releases / model calls | 0 / 0 | **0 / 0** |

The v7 run has 23 more spurious schema fields and the same matched fields as v6. It provides no extraction-quality
gain. The scorer requires exact derived field IDs and row ordinals, not semantic alias alignment or the creator's
official VRDU matcher. These 500 ad-buy and 1,500 registration forms are a development cohort, not a diverse
holdout. All documents still require human review. API cost, local compute cost, and reviewer time remain unpriced,
so cost per correctly released document is undefined.

**Decision:** the 2,000-source execution and OCR compatibility gate passed. Accuracy and cost gates failed. Keep
the PDFium-first renderer for its dependency/licensing and deployment advantages only; do not claim it improved
extraction. Add actual per-page renderer/fallback provenance before attributing scan-page outcomes to PDFium, and
test a specialist OCR/table path on frozen matched sources before promotion.

## Reproduction and immutable evidence

- Source: [Google VRDU](https://github.com/google-research-datasets/vrdu), creator commit
  `04a4df7ac5cc694e51c48115c03fe428f0e240cc`.
- Frozen cohort / gold SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90` /
  `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
- Candidate SHA-256: `1a7b1647ef1ec74cda270263a1f4f4a565429d5cf3de398c5f6b4e30a67753aa`.
- Execution / quality / family report SHA-256:
  `89428d1bf96a12314b63a9c3cce9fd1aa9bc884bcfe5b315db675d17f6da5e6a` /
  `b33f3353d6cfe12472d9d104c2baaa84e70ca04ca7894496c1dea889ec4e4a13` /
  `bfe753164862256b08cb203712a9918dfcf34ef657011813a34123bb127e45c4`.
- Command: `python -m product_eval.run_gate --gold <frozen gold> --cohort <frozen cohort> --data-dir
  E:\DocAI-Benchmarks\runtime --report-dir E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v7-pdfium
  --gate-id vrdu_v7_pdfium --min-unique 2000 --workers 4 <eight pinned shard directories>`, with the Tesseract
  paths in `provenance.json`. The clean worktree used `pypdfium2==5.14.0`, `pypdf==6.5.0`, and
  `pdf2image==1.17.0`.
- Reports, candidates, per-shard logs, provenance and product sidecars:
  `E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v7-pdfium` and
  `E:\DocAI-Benchmarks\runtime\product_runs\vrdu_v7_pdfium_*` (outside Git).
