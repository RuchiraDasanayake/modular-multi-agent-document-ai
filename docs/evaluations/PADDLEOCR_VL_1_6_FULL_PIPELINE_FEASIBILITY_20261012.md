# PaddleOCR-VL-1.6 full-pipeline feasibility for ad-buy tables

**Research-only decision, 12 October 2026: viable candidate to pilot, not a
measured replacement.** No model or package was downloaded and no inference
ran for this assessment. The proposed comparison is parser-only on the
already frozen 12 VRDU ad-buy PDFs and their 219 exact complete linked rows.
It does not test automatic schema induction, value-field mapping, source
verification, human review, or the product's 2,000-document quality.

## What must be run

The [official PaddleOCR/PaddleX guide](https://github.com/PaddlePaddle/PaddleX/blob/release/3.7/docs/pipeline_usage/tutorials/ocr_pipelines/PaddleOCR-VL.en.md)
states that `PaddleOCR-VL-1.6` is a *pipeline*: `PP-DocLayoutV3` detects regions,
crops them and determines reading order; `PaddleOCR-VL-1.6-0.9B` recognizes
those regions; PaddleX assembles page results. The VLM model alone is only one
stage. The [current PaddleOCR guide](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PaddleOCR-VL.html)
explicitly describes a `llama-cpp-server` backend for that VLM stage and a
PaddlePaddle or Transformers layout client. It documents x64 CPU support for
layout inference and the `device="cpu"` option. The
[official GGUF card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF)
shows `PaddleOCRVL(pipeline_version="v1.6", vl_rec_backend="llama-cpp-server",
vl_rec_server_url="http://127.0.0.1:8080/v1")` after starting a
`llama-server` with both GGUF and projector.

The official GGUF repository at revision
`511b09642bb324401f15f97cc23bc67e8f0a291d` is Apache-2.0. Its
repository metadata gives:

| File | Bytes | SHA256 |
| --- | ---: | --- |
| `PaddleOCR-VL-1.6-GGUF.gguf` | 935,769,056 | `f3ae46ec885050acf4b3d31944431e1fd90d50664fb09126af4a3c050ba14ee8` |
| `PaddleOCR-VL-1.6-GGUF-mmproj.gguf` | 881,770,560 | `204d757d7610d9b3faab10d506d69e5b244e32bf765e2bab2d0167e65e0a058a` |

These 1.82 GB of GGUF files do **not** include the layout model or framework.
The default [official pipeline
configuration](https://github.com/PaddlePaddle/PaddleX/blob/release/3.7/paddlex/configs/pipelines/PaddleOCR-VL-1.6.yaml)
uses `PP-DocLayoutV3` with layout detection enabled. Its
[official model repository](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3)
contains about 131 MB of Paddle weights. A pinned PaddleOCR/PaddleX runtime,
PaddlePaddle/Transformers layout engine, and isolated environment are still
required. On this Windows host, Python 3.13 and an RTX 3060 Ti 8 GB are
present, but none of `paddle`, `paddleocr`, or `paddlex` is installed in the
current Python environment. GPU fit, RAM peak, Windows package compatibility,
startup time, and accuracy are **unverified**. At inspection, E: had about
9.28 GB free; installing another isolated stack requires a disk guard.

## Measurable output and fair comparison

The full pipeline returns `parsing_res_list` with page, region
`block_bbox`, `block_label` such as `table`, `block_content`, and reading
order. It can export tables as HTML; for multipage PDFs it can call
`restructure_pages(..., merge_tables=True)`. Those are directly useful for a
parser-only trial. The guide does **not** establish that each HTML cell has an
individual source polygon; a table-region box cannot be reported as
cell-level evidence.

Run one PDF first under process-time, RAM, VRAM, and disk limits. If the
complete pipeline loads and emits a table, process the same frozen 12 ad-buy
sources as the [Docling/pdfplumber
comparison](VRDU_ADBUY12_TABLE_PARSER_COMPARISON_20261012.md), retaining all
failures and timeouts. Parse **only actual HTML table cells** and rows from
the pipeline output; do not score general Markdown or OCR lines as table
rows. Use the existing exact one-to-one cell and complete-row scorer, record
table-region boxes separately, and report per-document page count, latency,
peak host resources, malformed HTML, and all 219 gold-row outcomes. Keep raw
output outside Git and pin every runtime/model hash. The current
[MinerU Basic comparator](MINERU_4_BASIC_ADBUY12_RESULT_20261012.md) recovered
6/219 exact complete rows, versus Docling's 3 and pdfplumber `text`'s 4; a
new candidate must improve on that denominator and justify its runtime cost.

Successful parser rows would still need semantic column mapping, normalized
field values, source-backed evidence, and HITL before product promotion. Any
extraction implementation change then requires a fresh >=2,000-distinct-
source gate. The vendor's document-parsing benchmark is not a substitute for
this paired result.
