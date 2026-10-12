# PaddleOCR-VL 1.6 full-pipeline ad-buy table pilot: frozen protocol

**Status: protocol frozen before inference, 12 October 2026.** This is a
parser-only development diagnostic. The product extractor is not modified.
Model weights, package environment, PDF inputs, server logs and page JSON are
outside Git. Failures stay in the 12-document denominator.

## Decision to test

The [official PaddleOCR-VL pipeline](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.7.0/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md)
combines PP-DocLayoutV3 region detection/order with a 0.9B vision-language
recognizer. The [official GGUF repository](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF)
supports serving that recognizer through llama.cpp. A VLM-only Markdown run
would not test the complete parser. The full pipeline is the candidate.

The exact 12 VRDU ad-buy source PDFs are selected by the already committed
`vrdu_ad_buy_table12.jsonl` SHA256
`b843d48146a60f02bb206900ee06d446eb82ba484a3781c291235864b5230d2d`.
Its cohort hash is
`98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`.
Gold hash is
`8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
The source verifier checks every original PDF hash before serving the model.
Gold content is first opened after conversions for scoring. The denominator
is **219 linked rows and 808 cells over all 12 PDFs**, including two
image-only sources; it cannot shrink after errors.

## Pinned stack and execution

The five model artifacts and their exact bytes/SHA256 are in
`product_eval/fixtures/paddleocr_vl_16_models.json`. The GGUF pair is from
official revision `511b09642bb324401f15f97cc23bc67e8f0a291d` and the
layout model from official revision
`241f8bdfc77a7c7bee915a5057aaee58c235a8d3`. The isolated Windows
Python 3.11 runtime pins PaddlePaddle CPU 3.3.0, PaddleOCR 3.7.0 and
PaddleX 3.7.2. The 102-package installed closure and core wheel hashes are
in `product_eval/fixtures/paddleocr_vl_16_runtime.json` (SHA256
`43661458b1d981f046b616903c2190457b7abfb6545bf357eae67f1a69653b79`).
Its `pip freeze --all` SHA256 is
`9669f7a7d40344c5dd495aed22a72b4a23214b60c43f151be38935e6b5cda91e`,
and pip's install receipt SHA256 is
`7e4217ea60d31a9694f24e2208adf633f2827f6b61aba5e5ae80df9c7935ecc4`.
`pip check` passed and importing `PaddleOCRVL` in this environment passed.
The CUDA llama.cpp server is installed build
11425, executable SHA256
`4fdc1a67a8c1333429ea82186087a77db202fb588c2442dcdfa442b2182d0306`.
The server binds `127.0.0.1:18128` with one slot, 8192 context tokens,
GPU offload, four CPU threads and temperature 0. The preflight verifies
model path, build, vision support, context and slot count before inference.

The official `PaddleOCRVL` wrapper runs with pipeline version `v1.6`,
`PP-DocLayoutV3` loaded from the pinned local directory, CPU layout engine,
llama.cpp recognition backend, no orientation/unwarping/chart/seal/extra
image-block OCR, `format_block_content=False`, and a single concurrent VLM
request. PDF prediction uses rectangular region boxes, temperature 0 and
`max_new_tokens=3072` **per crop**. Both original page JSON and
`restructure_pages(..., merge_tables=True)` page JSON are saved with hashes.
PaddleX [merge code](https://github.com/PaddlePaddle/PaddleX/blob/v3.7.2/paddlex/inference/pipelines/layout_parsing/merge_table.py#L200-L240)
can empty the linked continuation block on a later page; this is counted
separately from malformed table HTML.

## Guards and stop rules

Only PDFs no larger than 2,000,000 bytes and no longer than 20 pages are
allowed. Startup has a 180-second limit; each document has 600 seconds; the
whole run has 3,600 seconds. Process-tree RSS must stay at or under 8 GiB,
host available RAM at or above 2 GiB, GPU free VRAM at or above 1 GiB, C:
free space at or above 4 GiB, and E: free space at or above 2 GiB. The
first selection PDF is a required smoke test. It must emit full-layout
`parsing_res_list` with at least one real HTML table block. Smoke RSS must
stay at or under 6 GiB, host RAM at or above 3 GiB and GPU free VRAM at or
above 1.5 GiB. Failure stops further PDFs. Resource or server failure at
any later point stops further PDFs; ordinary per-PDF conversion failures are
recorded and the run continues if guards remain satisfied.

## Scoring and promotion rule

The **primary** score reads only `block_label="table"` and actual
`block_content` HTML `<table><tr><td>/<th>` in merged page JSON. General
Markdown, OCR lines and other block labels cannot contribute. The same
frozen `score_tables` one-to-one matcher used for Docling, pdfplumber and
MinerU measures surface presence, exact cell text, and complete gold cell
sets in one distinct parser row. That complete-row metric allows extra
parser cells; it does not attribute cells to schema field IDs. The stricter
exact-multiset row metric is reported separately. The premerge page JSON
receives a separate secondary score with the
same denominators. Table-region `block_bbox` validity is counted, but a
table-region box is **not** cell-level source evidence. Every malformed
table and missing/invalid page remains visible; all 12 gold documents count.

Existing paired comparators recovered the complete gold cell set in one
parser row for 3/219 rows with Docling, 4/219 with pdfplumber text and
6/219 with MinerU Basic. A parser candidate
needs a meaningful, paired accuracy improvement that justifies runtime
and operational cost. Even a higher parser score does not prove automatic
schema induction, value-field attribution, field-level evidence or review
quality. Product promotion requires those separate gates and then a new
run of at least 2,000 distinct sources.
