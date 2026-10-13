# CORD development full-page OCR result (12 October 2026)

**Decision:** PP-OCRv6 small is a strong full-page OCR candidate for these 60 public CORD receipts, but replacing Tesseract in the current product would **not yet improve structured extraction**. It exposed much more creator-annotated text and more of the fixed receipt field values, at higher local CPU time and process memory. Passing each engine's text through the unchanged deterministic product extraction logic produced **zero exact mapped scalar values or linked menu rows for either engine**. Next work is source-grounded schema induction and row linking on the same fixed text and geometry, followed by an independent adjudicated test; a product OCR adapter must then earn its cost through downstream gains.

The [protocol](CORD_FULL_PAGE_OCR_DEV_PROTOCOL_20261012.md) and read-only `check` were fixed before inference. The run used the exact 60 creator-sourced CORD v2 development PNGs and 1,389 `valid_line.words[].text` boxes; the 40 internally reserved receipts were not opened for inference or scoring. This derived development slice comes from the published CORD test set, so these are **not** official CORD test metrics or evidence of generalization to arbitrary documents. Both engines received identical original PNG bytes and returned page text plus original-pixel boxes. The prior [crop comparison](CORD_DEVELOPMENT_TEXT_BOX_OCR_RESULT_20261012.md) had supplied creator quads to the recognizers; this run includes detection.

## OCR text and geometry

"Page text present" means a normalized creator-annotated string occurs anywhere in the OCR page text. "Local text present" additionally requires the string in OCR lines whose rectangular bounds cover at least half the annotation box. Unicode NFKC, casefold, and punctuation/whitespace token normalization make these **optimistic, duplicate-sensitive positive-only proxies**. They are not CER, OCR precision, field correctness, or verified evidence overlap.

| Fixed creator-positive unit | Tesseract direct `psm 6` | RapidOCR PP-OCRv6 small | Paired Rapid-only / Tesseract-only |
| --- | ---: | ---: | ---: |
| Annotated box text appears on page | 791/1,389 (56.95%) | **1,311/1,389 (94.38%)** | 536 / 16 |
| Annotated box has overlapping OCR line | 963/1,389 (69.33%) | **1,314/1,389 (94.60%)** | 397 / 46 |
| Annotated box text appears in overlapping lines | 667/1,389 (48.02%) | **1,241/1,389 (89.35%)** | 614 / 40 |

For page text presence, 775 boxes matched both engines, 62 neither. The Rapid minus Tesseract difference is +37.44 percentage points. A 10,000-replicate paired receipt bootstrap (seed `20261012`) gave +28.6 to +46.5 points; the interval only reweights these 60 development receipts. The geometry-local text difference is +41.32 points, with an analogous +32.0 to +50.9 point interval. RapidOCR returned 974 lines and Tesseract returned 620; **all** line polygons/rectangles lay within their source PNG dimensions. This checks coordinate bounds, not whether the right receipt field or menu row was identified. One Tesseract page returned empty text without a process failure; RapidOCR had none. All 60 pages were retained in every denominator.

The mapped [CORD partial-positive labels](CORD_SECONDARY_SLICE.md) give a separate, looser OCR text ceiling. These labels are exact creator `gt_parse` values; their occurrence anywhere on the page does not establish that a value was assigned to its right field.

| Gold value strings found somewhere in OCR page text | Tesseract | RapidOCR |
| --- | ---: | ---: |
| Summary scalar values | 101/195 (51.79%) | **171/195 (87.69%)** |
| Menu cells | 253/458 (55.24%) | **428/458 (93.45%)** |
| Menu rows with every annotated value somewhere on page | 50/157 (31.85%) | **133/157 (84.71%)** |

The last row is a **text-complete row proxy only**. Values can come from unrelated visual rows; no row IDs are inferred from that count.

## Downstream extraction remains the blocker

The runner fed each complete page string to the existing no-model `_process_document` logic, with no gold, through a supplied-page OCR stub. This executes the product's current label/value parsing, source-quote and review rules but bypasses normal intake, OCR routing, and retries; it is not a full `process-auto` service run. The existing CORD positive-only scorer then verified all 60 source hashes and scored the two candidate files. Both routes had **0/195 exact proposed summary values, 0/458 exact proposed linked cells, and 0/157 exact proposed complete menu rows**; accepted recall was also zero. Tesseract text produced 39 proposed fields across 22 receipts, RapidOCR text 13 fields across 11 receipts, and neither route proposed a linked column or any of the eight mapped CORD field IDs. All proposed fields were pending review. The single empty Tesseract page yielded an `unsupported` candidate; its other 59 candidates were `needs_review`. All 60 RapidOCR candidates were `needs_review`.

The previously completed [full product Tesseract adaptive run](CORD_DEVELOPMENT_NO_MODEL_V1.md) also yielded zero mapped recall, but its OCR path included quality retries, image preprocessing and full intake. It is a separate baseline; the direct `psm 6` timings below must not be compared with its 604-second end-to-end wall time. More readable OCR lines can even trigger fewer brittle colon-delimited key/value patterns. Adding an OCR engine without improving schema and row logic would make this particular product path slower with no measured extraction gain.

## Resource and execution receipts

| Measure across 60 pages | Direct Tesseract child | Warm RapidOCR worker |
| --- | ---: | ---: |
| Page failures / empty text | 0 / 1 | 0 / 0 |
| Per-page latency p50 / p95 | 0.260 / 0.978 s | 1.080 / 2.302 s |
| Sum of 60 OCR calls | 22.615 s | 76.689 s |
| Peak sampled RSS | 123.6 MiB | 679.2 MiB |

RapidOCR's separate synthetic first call loaded all three models in 2.999 s. The raw files were created at 18:03:58 and the summary was written at 18:05:40 local time, roughly 102 seconds elapsed for the sequential calls, serialization, source checking, candidate scoring, and summary. The RSS scopes differ: Tesseract is a child executable, while RapidOCR is the Python/NumPy/ONNX worker. Samples every 20 ms can miss short peaks. CPU energy, reviewer minutes, local hardware dollar cost, and actual production throughput were not measured. All three ONNX sessions reported `CPUExecutionProvider`, and no cloud/API call or GPU inference occurred.

The preflight fixed the development cohort SHA `48f9af8c04a5ee874c68ccb4c70a5fb81bcfddc508064747779678949103414a`, annotation manifest SHA `03eeddf3526b28031582460419b3c1ed27bcacc285e194d193b19110fbb610f5`, positive gold SHA `84a097116eaad75fb66265447d1b831f5a2ffa98792e10e9ad7edb517cb8e318`, Tesseract executable and `eng` hashes, and all three PP-OCRv6 small ONNX hashes recorded in the [protocol](CORD_FULL_PAGE_OCR_DEV_PROTOCOL_20261012.md). Versions were RapidOCR 3.10.0, ONNX Runtime 1.23.2, Pillow 12.3.0, and psutil 7.1.1. An independent post-run read verified 60 raw rows, 60 distinct source hashes matching the development cohort, no intersection with the 40 reserved source hashes, 60 candidate rows per engine, and the saved raw SHA.

Raw page text, box geometry, per-page timing/failures, and candidates stay outside Git at `E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\full-page-ocr-dev-v1`. Output SHA-256: `raw.jsonl` `3c1322181b893cc948b0dbde6414dcf7ed9669a1609ec007b09a12e52e40a92f`; `tesseract_candidates.jsonl` `2135e2ab733038e7382bb7b006cb5a4153fbce5aa472e40507126b5fcdcb6879`; `rapidocr_candidates.jsonl` `8913102a84e9a2635840d0c86486427b3f1ca343162004bc0403bfb44216e522`; `summary.json` `fa0f1bb4ce548324ca5f1114e3c110a62424228963c6bc9e91a9bd54e1bc440e`. The runner and focused tests are `product_eval/cord_page_ocr_diagnostic.py` and `product_eval/tests/test_cord_page_ocr_diagnostic.py`.

The next decision should use a fixed extractor that consumes OCR geometry and can propose typed scalars and linked menu rows with inspectable source evidence. Evaluate it with adjudicated false positives, correct row IDs, evidence overlap, reviewer effort, and cost per correct document. Keep the reserved 40 CORD receipts out of iterative selection. If a measured OCR adapter is integrated into product code, run a fresh 2,000-distinct-document regression gate before claiming an implementation improvement.
