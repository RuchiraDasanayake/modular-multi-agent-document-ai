# CORD S1 OCR line graph: source-only preflight

**Status:** research graph only. This is neither an S1 schema run nor a product extraction change. The [source-free receipt](CORD_S1_OCR_LINE_GRAPH_SOURCE_ONLY_RECEIPT_20261013.json) and [runner](../../product_eval/cord_ocr_line_graph.py) record one original-image OCR line graph per engine and development source. No model, gold, reserved source, or product extraction path was used.

## Input and validation

The runner reuses the already completed [full-page OCR development sidecar](CORD_FULL_PAGE_OCR_DEV_RESULT_20261012.md) rather than running OCR again. It verifies the committed development-cohort SHA-256 `48f9af8c04a5ee874c68ccb4c70a5fb81bcfddc508064747779678949103414a`, raw OCR `raw.jsonl` SHA-256 `3c1322181b893cc948b0dbde6414dcf7ed9669a1609ec007b09a12e52e40a92f`, and producer source's canonical-LF SHA-256 `8097af878f63c834757b65edbc8172473284c46da6f2a8a86597f00b2f2d5cf9`. It checks all 60 distinct development PNG byte hashes and dimensions against the source-only cohort. It never opens the development gold or reserved-40 manifests or images.

Each admitted node is explicitly an `ocr_line`. It carries source and sidecar hashes, engine/config and graph-rule hashes, original-image size, a convex in-bounds pixel quadrilateral, exact code-point offsets in the saved page string, raw engine order, a separate position order, confidence, and a hash of the raw sidecar line. A second pass checks source, offset, line-ID, and locator consistency before serialization. A line longer than 500 characters, malformed polygon, mismatched page string, or invalid order causes a page-level abstention with a fixed reason. A changed original source or sidecar lock aborts the run globally. No output is truncated to fit a model prompt.

The parser-config digest records the explicit Tesseract `eng`, OEM 3, PSM 6 route or RapidOCR 3.10.0/ONNX Runtime 1.23.2 CPU route with the three pinned PP-OCRv6 model hashes. This run relies on the previously sealed raw sidecar; it does **not** reverify current installed executable, package, or model bytes. The graph-rule SHA-256 in the receipt identifies the exact local implementation used. The graph is a research payload and has no inference entry point.

## Source-only result

| Engine | Raw sidecar lines | Candidate pages | Abstained pages | Admitted line nodes |
| --- | ---: | ---: | ---: | ---: |
| RapidOCR PP-OCRv6 small | 974 | 60/60 | 0 | 974 |
| Tesseract PSM 6 | 620 | 56/60 | 4/60 | 600 |

One Tesseract page had empty OCR output. On three other pages, the prior TSV grouping produced at least one line longer than the 500-character line bound; all three entire pages abstained, accounting for the 20 raw lines absent from candidate graphs. These are explicit coverage losses, not transcription or extraction scores. All 60 source images and both engine records remain in the 120-record denominator.

The raw graph JSONL, including OCR text, is outside Git at `I:\DocAI-Benchmarks\cord-s1-ocr-line-graph-preflight2\line_graphs.jsonl`, SHA-256 `4eb59422fddeb51778150f3cb79ed8f4ff9a34572e4f74b5974d680aaecd4b0d`. An independent read checked 120 records, 60 distinct source hashes with both engines, exact node text spans, pixel bounds, and absence of table/word-box fields. Focused tests cover repeated text, stable IDs, source mismatch, malformed polygons, offsets, ordering, confidence, long lines, empty OCR, Tesseract hierarchy, and serialization tampering. `pytest` passed 13 tests; Ruff passed.

## Interpretation

Pixel bounds and exact offsets make OCR lines inspectable; they do not prove that OCR text matches the pixels, identify a word, infer a table cell or row, or establish a field's meaning. This graph cannot satisfy the [S1 linked-cell/row development gate](EVIDENCE_FIRST_AUTO_SCHEMA_DECISION_AND_PROTOCOL_20261013.md). A word/cell witness, candidate projection, grammar/model-output validator, and sealed inference profile are still required before an S1 model call. A product-path change would require a new evaluation and the user's fresh 2,000-distinct-source end-to-end gate.
