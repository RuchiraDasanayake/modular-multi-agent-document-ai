# VRDU 2,000-document v6 bounded-OCR gate (2026-10-12)

This completed **no-model** product-auto gate tests the bounded Tesseract calls introduced at clean, detached commit
`3e4261202108abfa68d3112436d837ff914903cf`. It uses the same frozen two-family VRDU development cohort and
English OCR installation as [v5](VRDU_2000_NO_MODEL_V5.md). It does **not** test AI schema generation, linked-row
model proposals, recipe matching, reviewer corrections, or a new OCR engine. The scorer uses exact derived field IDs and
row ordinals, not the official VRDU matcher. These two form families are not an arbitrary-document holdout.

## Execution and OCR

All eight disjoint 250-PDF shards exited 0. The gate verified **2,000 documents from 2,000 distinct raw source hashes**,
with zero repeats, zero missing candidates, and a complete gold/candidate ID join. All 2,000 results are
`needs_review`; none is released, failed, or unsupported. The preflight recognized a generated image using Tesseract
`v5.5.3.20260724` and pinned `eng.traineddata` SHA-256
`7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2` in each child process.

| Observation | v5 | v6 |
| --- | ---: | ---: |
| Native-text / Tesseract pages | 3,481 / 831 | 3,481 / 831 |
| Documents with a Tesseract page | 677 | 677 |
| Tesseract pages with positive reported confidence | 831 / 831 | 831 / 831 |
| Tesseract page paths: initial / quick / full / quick plus full | 650 / 87 / 72 / 22 | 650 / 87 / 72 / 22 |
| OCR timeout or page failure recorded | not bounded | **0** |
| OCR p50 / p95, all documents | 11.23 / 9,333.5 ms | 10.85 / 8,618.8 ms |
| OCR p50 / p95, Tesseract documents | 3,058.3 / 21,632.4 ms | 3,062.1 / 22,895.3 ms |
| Maximum document OCR stage | 139,875 ms | 131,689 ms |
| Sum of per-document durations | 4,993,602 ms | 4,783,740 ms |

The 30-second call timeout and 120-second per-image-page budget were configured for v6. **No sampled page hit either
limit**, so this large run verifies compatibility and coverage, not the timeout recovery branch under a real slow-page
event. Focused tests and a separate forced-timeout smoke cover that branch. The smoke used one of the same public
single-page scans (`2dbc09fdc1ec2800caaa93f1d10acd214ec3c311c519a12bc193f211b5e0ec46`) with a deliberately
tiny 0.01-second call timeout and 0.02-second page budget. It completed with one `failed` result and an explicit
`ocr_timeout` reason, rather than labeling the document unsupported. This proves the error taxonomy for a forced limit,
not the frequency of natural slow-page failures. The 4.2% lower sum of document durations is
an observation across four concurrent workers, not a controlled speedup or wall-time result. Nonzero OCR confidence
shows the OCR engine ran; it does not prove transcription or field correctness. The 35 scans marked unsupported in v4
remain reviewable in v6 because every source is reviewable; v4's missing OCR executable was the original cause.

## Extraction quality and decision

| Metric | v5 | v6 |
| --- | ---: | ---: |
| Strict schema F1 | 4.245% | **4.245%** |
| Strict schema TP / FP / FN | 819 / 21,769 / 15,181 | **819 / 21,769 / 15,181** |
| Pre-review accepted-value F1 | 0% | **0%** |
| Proposed linked cells / rows | 0 / 0 | **0 / 0** |
| Gold linked cells / rows | 30,133 / 7,234 | 30,133 / 7,234 |
| `needs_review` / `unsupported` / `failed` | 2,000 / 0 / 0 | **2,000 / 0 / 0** |
| Model calls / correct automatic releases | 0 / 0 | **0 / 0** |

The v6 strict schema F1 is 1.221% on the 500 ad-buy forms and 5.524% on the 1,500 registration forms. The exact
field-name scorer does not infer semantic aliases. Regardless of alias policy, the no-model path produces no linked
rows and leaves every document in review. API, compute, and reviewer cost fields are null, so cost per correctly
released document is undefined.

**Decision: the 2,000-source execution and OCR compatibility gate passed; extraction quality and cost gates failed.**
Keep this no-model path review-only. Do not use this run to claim useful automatic extraction, lower total cost, a
new camera-ready research result, or performance of the local/ICORE model-backed paths. The newer provider, frontend
security, and run-recovery commits postdate this detached gate and require their own targeted validation; they did not
change the no-model parser or schema algorithm measured here.

## Reproduction record

- Source: [Google VRDU](https://github.com/google-research-datasets/vrdu), creator commit
  `04a4df7ac5cc694e51c48115c03fe428f0e240cc`.
- Frozen cohort / gold SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90` /
  `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
- Candidate SHA-256: `3b471fa03a15928d0c8b5f3e1df54ce389d343ba9df9c03d696d3d4adfb162c0`.
- Execution / quality / family report SHA-256:
  `12723fcfc64475f842a3844bb0fcfe041fcf42384ee882c9352f08ab031b42f6` /
  `6b68cc9ef6a46b6f68f961d7c177ea0b427b1eb8d875f7a3ea314eafba1822db` /
  `2d9fe22d9ca2eb799cb3dc0328e0cd967d53652ce63e8ee880acf8836e472180`.
- Command: `python -m product_eval.run_gate --gold <frozen gold> --cohort <frozen cohort> --data-dir
  E:\DocAI-Benchmarks\runtime --report-dir E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v6 --gate-id vrdu_v6
  --min-unique 2000 --workers 4 <eight pinned shard directories>`, with `TESSERACT_CMD` and `TESSDATA_PREFIX` set to
  the pinned paths in `provenance.json`.
- Full reports, candidates, logs, and provenance: `E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v6` (outside Git).
- Forced-timeout sidecar and run receipt: `E:\DocAI-Benchmarks\runtime\product_runs\ocr_forced_timeout_smoke_20261011`
  (outside Git; same pinned Tesseract/English paths, no model).
